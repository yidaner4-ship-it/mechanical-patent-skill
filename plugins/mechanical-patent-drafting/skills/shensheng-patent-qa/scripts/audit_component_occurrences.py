#!/usr/bin/env python3
"""Inventory every configured component-name occurrence in a chosen DOCX view."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
SKIP_PROPERTIES = {W + n for n in ('pPr', 'rPr', 'pPrChange', 'rPrChange', 'sdtPr')}


def visible_text(element, view, top=True):
    if element.tag in SKIP_PROPERTIES or (element.tag == W + 'p' and not top):
        return ''
    deleted = element.tag in {W + 'del', W + 'moveFrom'}
    inserted = element.tag in {W + 'ins', W + 'moveTo'}
    if (deleted and view == 'accepted') or (inserted and view == 'rejected'):
        return ''
    if element.tag in {W + 't', W + 'delText'}:
        return element.text or ''
    if element.tag in {W + 'tab', W + 'br', W + 'cr'}:
        return ' '
    return ''.join(visible_text(child, view, False) for child in element)


def extract_paragraphs(docx, view):
    with ZipFile(docx) as package:
        document = ET.fromstring(package.read('word/document.xml'))
    result = []
    boundary_review = []
    for source_number, paragraph in enumerate(document.iter(W + 'p'), 1):
        text = visible_text(paragraph, view)
        marker_properties = paragraph.find(f'{W}pPr/{W}rPr')
        removed_marker = False
        if marker_properties is not None:
            kind = 'del' if view == 'accepted' else 'ins'
            removed_marker = marker_properties.find(W + kind) is not None
        if removed_marker and not text:
            continue
        result.append({'paragraph': len(result) + 1, 'source_paragraph': source_number, 'text': text})
        if removed_marker:
            boundary_review.append({
                'paragraph': len(result),
                'reason': 'Paragraph-boundary revision retains visible text. Review Word acceptance or rejection before relying on paragraph ranges.'})
    return result, boundary_review


def load_components(config):
    terms = {}
    canonical_by_number = {}
    strict_names = config.get('require_canonical_names', False)
    if not isinstance(strict_names, bool):
        raise ValueError('require_canonical_names must be a boolean')
    for component in config['components']:
        number = str(component['number'])
        if not re.fullmatch(r'\d+', number):
            raise ValueError(f'Component number must be numeric: {number}')
        canonical = component['name']
        if strict_names and number in canonical_by_number and canonical_by_number[number] != canonical:
            raise ValueError(f'Final naming requires one canonical name for number {number}')
        canonical_by_number[number] = canonical
        for term in [canonical, *component.get('aliases', [])]:
            if not term:
                raise ValueError('Empty component name or alias')
            value = {'number': number, 'canonical_name': component['name']}
            if term in terms and (terms[term]['number'] != number or
                                  (strict_names and terms[term]['canonical_name'] != canonical)):
                raise ValueError(f'Ambiguous alias requires manual disambiguation: {term}')
            terms[term] = value
    return terms


def parenthetical_name_candidates(paragraphs, terms, pattern, config):
    """Find naming-like parentheses; unknown wording remains a manual candidate."""
    if not config.get('require_canonical_names', False) or pattern is None:
        return []
    exceptions = config.get('parenthetical_name_exceptions', [])
    used = set()
    candidates = []
    for paragraph in paragraphs:
        text = paragraph['text']
        for match in pattern.finditer(text):
            entry = terms[match[0]]
            found, _, suffix_end = suffix_label(text, match.end())
            position = suffix_end if found else match.end()
            parens = re.match(r'\s*[（(]([^（）()\n]{1,80})[）)]', text[position:])
            if not parens:
                continue
            inner = parens[1].strip()
            if re.fullmatch(r'\d+', inner):
                continue  # Normal reference-numeral parentheses.
            known = terms.get(inner)
            preceding_number = re.search(r'(?<!\d)(\d+)\s*[、.．:：]\s*$', text[:match.start()])
            legend_item = preceding_number is not None and preceding_number[1] == entry['number']
            kind = ''
            if known and inner != match[0]:
                kind = ('parenthetical_alias' if known['number'] == entry['number']
                        else 'parenthetical_component_name')
            elif legend_item and not re.search(
                    r'^(?:用于|用作|供|例如|如图|参见|其中|注[:：]|安装于|位于|固定于|连接于)|[=+*/≤≥<>]', inner):
                kind = 'legend_parenthetical_text'
            if not kind:
                continue
            end = position + parens.end()
            candidate = {
                'paragraph': paragraph['paragraph'], 'source_paragraph': paragraph['source_paragraph'],
                'start': match.start(), 'end': end, 'name': match[0],
                'canonical_name': entry['canonical_name'], 'expected_label': entry['number'],
                'text': text[match.start():end], 'parenthetical_text': inner,
                'kind': kind, 'status': 'needs_review', 'exception_reason': '',
            }
            matching = [e for e in exceptions if e['paragraph'] == candidate['paragraph']
                        and e['start'] == candidate['start'] and e['text'] == candidate['text']]
            if len(matching) > 1:
                raise ValueError('Duplicate parenthetical naming exception')
            if matching:
                exception = matching[0]
                reason = exception['reason'].strip()
                if not reason:
                    raise ValueError('Each parenthetical naming exception needs a reason')
                candidate['status'] = 'accepted_exception'
                candidate['exception_reason'] = reason
                used.add((exception['paragraph'], exception['start'], exception['text']))
            candidates.append(candidate)
    configured = {(e['paragraph'], e['start'], e['text']) for e in exceptions}
    if configured - used:
        raise ValueError(f'Stale parenthetical naming exceptions need re-review: {sorted(configured-used)}')
    return candidates


def region_for(paragraph, config):
    matching = [region for region in config['regions']
                if region['start_paragraph'] <= paragraph <= region['end_paragraph']]
    if len(matching) != 1:
        raise ValueError(f'Paragraph {paragraph} needs exactly one section policy, found {len(matching)}')
    region = matching[0]
    if region['mode'] not in {'required', 'optional', 'exempt'}:
        raise ValueError(f'Unknown section mode: {region["mode"]}')
    if region.get('style', 'either') not in {'bare', 'parenthesized', 'either'}:
        raise ValueError(f'Unknown suffix style: {region["style"]}')
    return region


def suffix_label(text, position):
    tail = text[position:]
    parenthesized = re.match(r'\s*[（(]\s*(\d+)\s*[）)]', tail)
    if parenthesized:
        return parenthesized[1], 'parenthesized', position + parenthesized.end()
    bare = re.match(r'\s*(\d+)', tail)
    if bare:
        return bare[1], 'bare', position + bare.end()
    return '', '', position


def inspect(docx, config, view='accepted'):
    paragraphs, boundary_review = extract_paragraphs(docx, view)
    terms = load_components(config)
    numbers = {value['number'] for value in terms.values()}
    # Alternation selects the longest known term at the earliest position. A parent name
    # inside a known longer component name is consequently not counted twice.
    names = sorted(terms, key=lambda term: (-len(term), term))
    pattern = re.compile('|'.join(re.escape(name) for name in names)) if names else None
    exceptions = config.get('exceptions', [])
    strict_names = config.get('require_canonical_names', False)
    rows = []
    used_exceptions = set()
    for paragraph in paragraphs:
        text = paragraph['text']
        region = region_for(paragraph['paragraph'], config)
        if pattern is None:
            continue
        for match in pattern.finditer(text):
            name = match[0]
            entry = terms[name]
            found, style, suffix_end = suffix_label(text, match.end())
            status = 'ok'
            if region['mode'] == 'exempt':
                status = 'exempt_section'
            elif not found:
                status = 'missing_label' if region['mode'] == 'required' else 'optional_unlabeled'
            elif found != entry['number']:
                status = 'wrong_label' if found in numbers else 'unknown_label'
            elif region.get('style', 'either') not in {'either', style}:
                status = 'label_style'
            label_status = status
            noncanonical = strict_names and name != entry['canonical_name']
            if noncanonical:
                status = 'noncanonical_name'
            reason = ''
            matched_exceptions = [exception for exception in exceptions
                                  if exception['paragraph'] == paragraph['paragraph']
                                  and exception['name'] == name
                                  and exception['start'] == match.start()]
            if len(matched_exceptions) > 1:
                raise ValueError('Duplicate exception for one occurrence')
            if matched_exceptions:
                exception = matched_exceptions[0]
                used_exceptions.add((exception['paragraph'], exception['name'], exception['start']))
                reason = exception['reason'].strip()
                if not reason:
                    raise ValueError('Each occurrence exception needs a reason')
                non_component = exception.get('non_component_usage', False)
                if not isinstance(non_component, bool):
                    raise ValueError('non_component_usage must be a boolean')
                # An old suffix exception cannot silently authorize a formal alias.
                if not noncanonical or non_component:
                    status = 'accepted_exception'
            rows.append({
                'occurrence_id': f'P{paragraph["paragraph"]:04}-C{match.start():04}',
                'paragraph': paragraph['paragraph'], 'source_paragraph': paragraph['source_paragraph'],
                'section': region['name'], 'start': match.start(), 'end': match.end(),
                'name': name, 'canonical_name': entry['canonical_name'],
                'expected_label': entry['number'], 'actual_label': found,
                'actual_style': style, 'policy': region['mode'], 'status': status,
                'label_status': label_status,
                'naming_status': ('noncanonical_name' if noncanonical else
                                  ('canonical' if strict_names else 'not_checked')),
                'context': text[max(0, match.start()-22):min(len(text), max(match.end(), suffix_end)+22)],
                'exception_reason': reason,
            })
    configured_exceptions = {(e['paragraph'], e['name'], e['start']) for e in exceptions}
    unused = configured_exceptions - used_exceptions
    if unused:
        raise ValueError(f'Stale occurrence exceptions need re-review: {sorted(unused)}')
    naming_candidates = parenthetical_name_candidates(paragraphs, terms, pattern, config)
    unresolved_candidates = [c for c in naming_candidates if c['status'] == 'needs_review']
    error_types = {'missing_label', 'wrong_label', 'unknown_label', 'label_style', 'noncanonical_name'}
    issues = [row for row in rows if row['status'] in error_types]
    summary = {
        'paragraphs': len(paragraphs), 'configured_names_and_aliases': len(terms),
        'component_numbers': len(numbers), 'occurrences': len(rows), 'issues': len(issues),
        'required_occurrences': sum(row['policy'] == 'required' for row in rows),
        'explicit_exemptions': sum(row['status'] == 'accepted_exception' for row in rows),
        'paragraph_boundary_reviews': len(boundary_review),
        'require_canonical_names': strict_names,
        'noncanonical_name_issues': sum(row['status'] == 'noncanonical_name' for row in rows),
        'parenthetical_naming_reviews': len(unresolved_candidates),
        'unmatched_configured_terms': sorted(set(terms)-{row['name'] for row in rows}),
    }
    return {
        'document_name': Path(docx).name,
        'document_sha256': hashlib.sha256(Path(docx).read_bytes()).hexdigest(),
        'view': view, 'summary': summary, 'paragraphs': paragraphs,
        'occurrences': rows, 'issues': issues, 'boundary_review': boundary_review,
        'parenthetical_name_candidates': naming_candidates,
        'limitations': [
            'Matches only the configured names and aliases. Manual review must add shorthand, grouped names, unnamed features, and components absent from the dictionary.',
            'Suffix checks do not establish that the referenced feature is present in the drawing or that its leader points to the intended entity.',
            'Paragraph numbers refer to the selected view and are not rendered page numbers.',
            'Final naming checks recognize only configured terms and naming-like parentheses. Unknown synonyms, short forms, quotations and structural type descriptions still require contextual human review.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('docx', type=Path)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='Output prefix for JSON and CSV')
    parser.add_argument('--view', choices=('accepted', 'rejected'), default='accepted')
    parser.add_argument('--fail-on-issues', action='store_true')
    arguments = parser.parse_args()
    config = json.loads(arguments.config.read_text(encoding='utf-8'))
    result = inspect(arguments.docx, config, arguments.view)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.with_suffix('.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    columns = ['occurrence_id','paragraph','source_paragraph','section','start','end','name',
               'canonical_name','expected_label','actual_label','actual_style','policy','status',
               'context','exception_reason','label_status','naming_status']
    with arguments.output.with_suffix('.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=columns)
        writer.writeheader()
        writer.writerows(result['occurrences'])
    print(json.dumps(result['summary'],ensure_ascii=False))
    if arguments.fail_on_issues and (result['issues'] or result['boundary_review'] or
                                   result['summary']['parenthetical_naming_reviews']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
