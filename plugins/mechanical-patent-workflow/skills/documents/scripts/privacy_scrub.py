#!/usr/bin/env python3
"""Create an anonymized DOCX copy without modifying its source. MIT licensed.

This is a package-level aid, not a substitute for Word's Document Inspector or
visual/technical review. Unsupported structural tracked changes fail closed.
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import posixpath
import re
from urllib.parse import unquote, urlsplit
from xml.dom import Node, minidom
import zipfile

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
MAX_EXPANDED = 250 * 1024 * 1024
REMOVED_WORD_PARTS = ("word/comments", "word/people", "word/person")
HIDDEN_ELEMENTS = {"rsids", "docVars", "mailMerge", "attachedTemplate", "docId",
                   "permStart", "permEnd", "commentRangeStart", "commentRangeEnd",
                   "commentReference", "annotationRef", "dataBinding", "printerSettings"}
CHANGE_RANGES = {"moveFromRangeStart", "moveFromRangeEnd", "moveToRangeStart", "moveToRangeEnd",
                 "customXmlInsRangeStart", "customXmlInsRangeEnd", "customXmlDelRangeStart",
                 "customXmlDelRangeEnd", "customXmlMoveFromRangeStart", "customXmlMoveFromRangeEnd",
                 "customXmlMoveToRangeStart", "customXmlMoveToRangeEnd"}


def parse_xml(data: bytes) -> minidom.Document:
    # Also recognize UTF-16/32 encodings without expanding declarations.
    inspection = data.replace(b"\x00", b"").upper()
    if b"<!DOCTYPE" in inspection or b"<!ENTITY" in inspection:
        raise ValueError("DTD/entity declarations are unsupported.")
    return minidom.parseString(data)


def elements(document):
    return list(document.getElementsByTagName("*"))


def remove(node):
    if node.parentNode is not None:
        node.parentNode.removeChild(node)


def unwrap(node):
    parent = node.parentNode
    if parent is not None:
        while node.firstChild:
            parent.insertBefore(node.firstChild, node)
        parent.removeChild(node)


def has_local_path(value: str) -> bool:
    value = value.strip()
    return (value.lower().startswith("file:") or value.startswith(("/", "\\\\"))
            or bool(re.match(r"^[A-Za-z]:[\\/]", value)))


def source_for_rels(name: str) -> str:
    if name == "_rels/.rels":
        return ""
    directory, filename = posixpath.split(name)
    return posixpath.join(posixpath.dirname(directory), filename[:-5])


def target_part(rels: str, target: str) -> str:
    target = unquote(urlsplit(target).path)
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(source_for_rels(rels)), target))


def transform_word_xml(data: bytes, mode: str, removed_ids: set[str]) -> tuple[bytes, int]:
    doc = parse_xml(data)
    all_elements = elements(doc)
    revision_count = 0
    # Accepting deleted paragraph/row/cell marks requires real document editing,
    # not merely unwrapping runs. Refuse such cases instead of silently merging
    # or retaining the wrong structure.
    if mode == "accept":
        for node in all_elements:
            local = node.localName
            if local in {"cellIns", "cellDel", "cellMerge", "conflictIns", "conflictDel"}:
                raise ValueError("Structural/conflict tracked changes require acceptance in Word first.")
            if (node.namespaceURI == W and local in {"ins", "del", "moveFrom", "moveTo"}
                    and getattr(node.parentNode, "localName", None) in {"rPr", "trPr"}):
                raise ValueError("Paragraph/row tracked changes require acceptance in Word first.")
    for node in all_elements:
        local = node.localName or ""
        # Preserve text/results but refuse hidden local-path field instructions.
        if node.namespaceURI == W and local == "instrText":
            instruction = "".join(c.data for c in node.childNodes if c.nodeType == Node.TEXT_NODE)
            if re.search(r"(?:file:|[A-Za-z]:[\\/]|\\\\|/(?:Users|home|tmp)/)", instruction, re.I):
                raise ValueError("A field contains a local source path; unlink it in Word first.")
        if node.namespaceURI == W and local in HIDDEN_ELEMENTS:
            remove(node)
            continue
        if local == "docId" and node.namespaceURI and "word" in node.namespaceURI:
            remove(node)
            continue
        if node.hasAttributeNS(R, "id") and node.getAttributeNS(R, "id") in removed_ids:
            if node.namespaceURI == W and local == "hyperlink":
                unwrap(node)
                continue
            raise ValueError("A linked content object needs manual removal or embedding first.")
        for index in range(node.attributes.length - 1, -1, -1):
            attr = node.attributes.item(index)
            attr_local = attr.localName or attr.name
            if attr_local in {"author", "initials", "userId", "providerId"}:
                node.setAttributeNS(attr.namespaceURI, attr.name, "Anonymous" if attr_local == "author" else "")
            elif attr_local in {"date", "dateUtc"} or attr_local.lower().startswith("rsid"):
                node.removeAttributeNode(attr)
        if node.namespaceURI != W:
            continue
        is_property_change = local.endswith(("PrChange", "PrExChange"))
        is_change = local in {"ins", "del", "moveFrom", "moveTo", "cellIns", "cellDel", "cellMerge"} or is_property_change or local in {"tblGridChange", "numberingChange"}
        if is_change:
            revision_count += 1
        if mode == "accept":
            if local in {"ins", "moveTo"}:
                unwrap(node)
            elif (local in {"del", "moveFrom", "trackRevisions", "tblGridChange", "numberingChange"}
                  or is_property_change or local in CHANGE_RANGES):
                remove(node)
    if mode == "accept" and any(node.namespaceURI == W and node.localName in {"delText", "delInstrText"}
                                 for node in elements(doc)):
        raise ValueError("Uncontained deleted text requires acceptance in Word first.")
    return doc.toxml(encoding="UTF-8"), revision_count


def scrub_docx(source: Path, destination: Path, *, revisions: str) -> dict:
    if revisions not in {"preserve", "accept"}:
        raise ValueError("Choose revisions='preserve' or 'accept'.")
    source = source.expanduser().resolve()
    destination = destination.expanduser().resolve()
    if source == destination or destination.exists():
        raise ValueError("Use a new destination; source and existing files are never overwritten.")
    if source.suffix.lower() != ".docx" or destination.suffix.lower() != ".docx":
        raise ValueError("Both files must use the .docx extension.")
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        if sum(i.file_size for i in infos) > MAX_EXPANDED:
            raise ValueError("Expanded package exceeds the supported size limit.")
        names = [i.filename for i in infos if not i.is_dir()]
        if len(names) != len(set(names)) or any(n.startswith("/") or ".." in n.split("/") or "\\" in n for n in names):
            raise ValueError("Duplicate or unsafe package entries.")
        parts = {name: archive.read(name) for name in names}
    if "word/document.xml" not in parts or "[Content_Types].xml" not in parts:
        raise ValueError("Not a supported Word OOXML package.")
    if any(n.startswith("_xmlsignatures/") for n in parts):
        raise ValueError("Digitally signed input requires an unsigned independent export first.")
    if any(n.startswith("word/embeddings/") or "vbaProject" in n or "afchunk" in n.lower()
           or (n.endswith(".bin") and not n.startswith("word/printerSettings/")) for n in parts):
        raise ValueError("Embedded packages/macros/binary objects need manual inspection and removal first.")
    dropped = {n for n in parts if n.startswith(("docProps/", "customXml/", "word/printerSettings/"))
               or n.startswith(REMOVED_WORD_PARTS)}
    dropped |= {n for n in parts if n.endswith(".rels") and source_for_rels(n) in dropped}
    ids_by_source: dict[str, set[str]] = {}
    for name, data in list(parts.items()):
        if name in dropped or not name.endswith(".rels"):
            continue
        doc = parse_xml(data)
        removed_ids: set[str] = set()
        for rel in elements(doc):
            if rel.namespaceURI != PKG or rel.localName != "Relationship":
                continue
            target = rel.getAttribute("Target")
            external = rel.getAttribute("TargetMode").lower() == "external"
            drop = (rel.getAttribute("Type").endswith("/attachedTemplate")
                    or (external and has_local_path(target))
                    or (not external and target_part(name, target) in dropped))
            if drop:
                removed_ids.add(rel.getAttribute("Id"))
                remove(rel)
        ids_by_source[source_for_rels(name)] = removed_ids
        parts[name] = doc.toxml(encoding="UTF-8")
    revision_count = 0
    for name in list(parts):
        if name in dropped:
            continue
        if name.startswith("word/") and name.endswith(".xml"):
            parts[name], count = transform_word_xml(parts[name], revisions, ids_by_source.get(name, set()))
            revision_count += count
    content_types = parse_xml(parts["[Content_Types].xml"])
    for node in elements(content_types):
        if node.localName == "Override" and unquote(node.getAttribute("PartName")).lstrip("/") in dropped:
            remove(node)
    parts["[Content_Types].xml"] = content_types.toxml(encoding="UTF-8")
    # Build in memory, using neutral timestamps and no inherited ZIP comments,
    # filenames, filesystem attributes, or extra fields.
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(set(parts) - dropped):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, parts[name])
    with zipfile.ZipFile(io.BytesIO(result.getvalue())) as check:
        if check.testzip() is not None:
            raise ValueError("Output ZIP validation failed.")
        for name in check.namelist():
            if name.endswith((".xml", ".rels")):
                parse_xml(check.read(name))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as output:
        output.write(result.getvalue())
    return {"revisions": revisions, "revision_elements_examined": revision_count,
            "removed_parts": len(dropped), "package_validation": "passed",
            "word_inspector": "pending", "visual_review": "pending"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--revisions", choices=("preserve", "accept"), required=True,
                        help="Preserve real tracked changes anonymously, or accept supported run changes")
    args = parser.parse_args()
    try:
        print(json.dumps(scrub_docx(args.source, args.destination, revisions=args.revisions), ensure_ascii=False))
    except Exception as exc:
        # Do not echo paths or XML fragments from private source files.
        parser.exit(1, f"DOCX scrub failed: {type(exc).__name__}: {str(exc) if isinstance(exc, ValueError) else 'inspect input and package validity'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
