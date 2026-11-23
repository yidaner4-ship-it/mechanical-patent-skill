#!/usr/bin/env python3
"""Read-only structural checks for a DOCX with embedded patent drawing pages."""

import argparse
from pathlib import Path
import posixpath
import re
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
PAGE_FRACTION = re.compile(r'^\d+\s*/\s*\d+$')
FIGURE_CAPTION = re.compile(r'^图[1-9]\d*$')
PAGE_INSTRUCTION = re.compile(r'PAGE(?:\s+\\\*\s+(?:ARABIC|MERGEFORMAT))*', re.IGNORECASE)
PAGE_TOKEN = '\0'  # This marker cannot appear in XML text.


def parse_part(package, path):
    return ET.fromstring(package.read(path))


def accepted_nodes(root, tag=None):
    if root.tag in {W + 'del', W + 'moveFrom'}:
        return
    if tag is None or root.tag == tag:
        yield root
    for child in root:
        yield from accepted_nodes(child, tag)


def visible_text(root):
    return ''.join(node.text or '' for node in accepted_nodes(root, W + 't'))


def compact(text):
    return ''.join(text.split())


def enabled(element):
    return element is not None and element.get(W + 'val', '1').lower() not in {'0', 'false', 'off'}


def sections(body):
    items = []
    for node in body:
        if node.tag == W + 'sectPr':
            yield node, items
            return
        items.append(node)
        props = node.find(f'{W}pPr/{W}sectPr') if node.tag == W + 'p' else None
        if props is not None:
            yield props, items
            items = []
    if items:
        yield ET.Element(W + 'sectPr'), items


def part_path(target):
    return posixpath.normpath(target.lstrip('/') if target.startswith('/') else f'word/{target}')


def figure_footer(footer):
    """Return a literal caption, or a caption containing PAGE_TOKEN."""
    if footer is None or footer.tag != W + 'ftr':
        return None
    lines = []
    for paragraph in accepted_nodes(footer, W + 'p'):
        simple_fields = list(accepted_nodes(paragraph, W + 'fldSimple'))
        field_results = {node for fld in simple_fields for node in accepted_nodes(fld, W + 't')}
        text = []
        instruction = None
        for node in accepted_nodes(paragraph):
            if node.tag == W + 'fldSimple':
                if instruction is not None or not PAGE_INSTRUCTION.fullmatch(node.get(W + 'instr', '').strip()):
                    return None
                text.append(PAGE_TOKEN)
            elif node.tag == W + 'fldChar':
                part = node.get(W + 'fldCharType')
                if part == 'begin' and instruction is None:
                    instruction = []
                elif part == 'end' and instruction is not None:
                    if not PAGE_INSTRUCTION.fullmatch(''.join(instruction).strip()):
                        return None
                    text.append(PAGE_TOKEN)
                    instruction = None
                elif part != 'separate' or instruction is None:
                    return None
            elif node.tag == W + 'instrText':
                if instruction is None:
                    return None
                instruction.append(node.text or '')
            elif node.tag == W + 't' and node not in field_results and instruction is None:
                text.append(node.text or '')
        if instruction is not None:
            return None
        line = compact(''.join(text))
        if line:
            lines.append(line)
    return lines[0] if len(lines) == 1 else None


def audit(package, heading, expected, allow_footer=False):
    document = parse_part(package, 'word/document.xml')
    body = document.find(W + 'body')
    if body is None:
        raise ValueError('word/document.xml is missing its body')
    rels = parse_part(package, 'word/_rels/document.xml.rels')
    by_id = {rel.attrib['Id']: rel.attrib for rel in rels}
    settings = parse_part(package, 'word/settings.xml') if 'word/settings.xml' in package.namelist() else ET.Element(W + 'settings')
    even = enabled(settings.find(W + 'evenAndOddHeaders'))
    parts = set(package.namelist())
    errors = []
    graphic_count = 0
    matched_sections = []
    inherited = {'header': {}, 'footer': {}}
    last_numbered_section = 0

    def read_related(rel_id):
        if not rel_id:
            return None
        item = by_id.get(rel_id, {})
        if 'Target' not in item or item.get('TargetMode') == 'External':
            raise ValueError(f'Invalid internal document relation: {rel_id}')
        return parse_part(package, part_path(item['Target']))

    for section_index, (props, nodes) in enumerate(sections(body), 1):
        for kind, slots in inherited.items():
            for ref in props.findall(W + kind + 'Reference'):
                slots[ref.get(W + 'type', 'default')] = ref.get(R + 'id')
        active = ['default']
        if even:
            active.append('even')
        if enabled(props.find(W + 'titlePg')):
            active.append('first')
        headers = {slot: read_related(inherited['header'].get(slot)) for slot in active}
        labels = {slot: compact(visible_text(root)) if root is not None else '' for slot, root in headers.items()}
        if compact(heading) not in labels.values():
            continue
        matched_sections.append(section_index)
        for slot, label in labels.items():
            if label != compact(heading):
                errors.append(f'Section {section_index}: {slot} header should contain {heading!r}.')
        first_figure = graphic_count + 1
        for node in nodes:
            for paragraph in accepted_nodes(node, W + 'p'):
                line = visible_text(paragraph).strip()
                if PAGE_FRACTION.fullmatch(line):
                    errors.append(f'Section {section_index}: page fraction found in the drawing body.')
                if not allow_footer and FIGURE_CAPTION.fullmatch(compact(line)):
                    errors.append(f'Section {section_index}: {line!r} belongs in the drawing footer, not the body.')
                if compact(line) == compact(heading):
                    errors.append(f'Section {section_index}: duplicated heading found in the drawing body.')
            for graphic in accepted_nodes(node, A + 'blip'):
                graphic_count += 1
                rel = by_id.get(graphic.get(R + 'embed', ''), {})
                if graphic.get(R + 'link') or rel.get('TargetMode') == 'External' or not rel.get('Type', '').endswith('/image'):
                    errors.append(f'Section {section_index}: an image is linked or has no embedded image relation.')
                elif part_path(rel.get('Target', '')) not in parts:
                    errors.append(f'Section {section_index}: the embedded image resource is missing.')
        if not allow_footer:
            paging = props.find(W + 'pgNumType')
            start = paging.get(W + 'start') if paging is not None else None
            # An explicit restart takes precedence. A section without one can
            # continue a verified drawing sequence, or start the document at 1.
            synced = (start == str(first_figure) if start is not None
                      else section_index == last_numbered_section + 1)
            if paging is not None and paging.get(W + 'fmt', 'decimal') != 'decimal':
                synced = False
            if synced and graphic_count >= first_figure:
                last_numbered_section = section_index
            for slot in active:
                footer = read_related(inherited['footer'].get(slot))
                caption = figure_footer(footer)
                if caption == '图' + PAGE_TOKEN and not synced:
                    errors.append(f'Section {section_index}: {slot} footer PAGE must use decimal numbering from {first_figure}.')
                elif caption != '图' + PAGE_TOKEN and not (graphic_count == first_figure and caption == f'图{first_figure}'):
                    errors.append(f'Section {section_index}: {slot} footer needs 图 followed by a PAGE field or the number for a single drawing.')

    if not matched_sections:
        errors.append(f'No drawing section with a real {heading!r} header found.')
    elif graphic_count == 0:
        errors.append('No DrawingML embedded images in drawing section body.')
    if expected is not None and expected != graphic_count:
        errors.append(f'Expected {expected} drawing images, found {graphic_count}.')

    revisions = sum(1 for element in document.iter() if element.tag in {W + 'ins', W + 'del'})
    return matched_sections, graphic_count, revisions, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('docx', type=Path)
    parser.add_argument('--figures', type=int, help='Expected number of body images in drawing section(s)')
    parser.add_argument('--heading', default='说明书附图')
    parser.add_argument('--allow-footer', action='store_true', help='Skip figure-caption placement checks for a supplied or legacy layout')
    args = parser.parse_args()
    if args.figures is not None and args.figures < 1:
        parser.error('--figures must be a positive integer')
    try:
        with ZipFile(args.docx) as package:
            sections_found, images, revisions, errors = audit(package, args.heading, args.figures, args.allow_footer)
    except (OSError, BadZipFile, KeyError, ET.ParseError, ValueError) as exc:
        parser.exit(2, f'Cannot audit DOCX: {exc}\n')
    print(f'Drawing sections: {sections_found}; body images: {images}; text revision elements: {revisions}')
    for error in errors:
        print(f'FAIL: {error}')
    if not errors:
        checks = 'header and embedded image relations' if args.allow_footer else 'header, footer, and embedded image relations'
        print(f'PASS: {checks}.')
    print('Visual QA is still required for page breaks, markings inside images, and graphical alignment.')
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
