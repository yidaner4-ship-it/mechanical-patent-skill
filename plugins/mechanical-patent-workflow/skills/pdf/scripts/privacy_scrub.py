#!/usr/bin/env python3
"""Create a PDF copy without document metadata, attachments or active actions.

Requires the public pypdf package. This does not redact page content or certify
visual equivalence. New code: 2026 Mechanical Patent Toolkit contributors, MIT.
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path


def _pypdf():
    try:
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, NameObject, StreamObject
    except ImportError as exc:
        raise ValueError("Install the public requirements.txt dependencies in your own environment first.") from exc
    return PdfReader, PdfWriter, ArrayObject, DictionaryObject, IndirectObject, NameObject, StreamObject


def scrub_pdf(source: Path, destination: Path) -> dict:
    PdfReader, PdfWriter, ArrayObject, DictionaryObject, IndirectObject, NameObject, StreamObject = _pypdf()
    source = source.expanduser().resolve()
    destination = destination.expanduser().resolve()
    if source == destination or destination.exists():
        raise ValueError("Use a new destination; source and existing files are never overwritten.")
    if source.suffix.lower() != ".pdf" or destination.suffix.lower() != ".pdf":
        raise ValueError("Both files must use the .pdf extension.")
    reader = PdfReader(str(source))
    if reader.is_encrypted:
        raise ValueError("Encrypted PDFs need an authorized unencrypted independent export first.")
    seen: set[tuple | int] = set()
    counters = {"metadata_entries": 0, "attachment_entries": 0, "active_entries": 0}

    def resolve(obj):
        return obj.get_object() if isinstance(obj, IndirectObject) else obj

    def children(obj):
        if isinstance(obj, DictionaryObject):
            return list(obj.values())
        if isinstance(obj, (ArrayObject, list, tuple)):
            return list(obj)
        return []

    def contains_signature(obj, visited):
        if isinstance(obj, IndirectObject):
            identity = (id(obj.pdf), obj.idnum, obj.generation)
        else:
            identity = id(obj)
        if identity in visited:
            return False
        visited.add(identity)
        obj = resolve(obj)
        if isinstance(obj, DictionaryObject) and (obj.get("/Type") == "/Sig" or "/ByteRange" in obj):
            return True
        return any(contains_signature(child, visited) for child in children(obj))

    if contains_signature(reader.trailer, set()):
        raise ValueError("Signed PDFs need an unsigned independent export first.")
    writer = PdfWriter()
    # Clone the catalog only: original Info entries and trailer IDs are not
    # part of the delivery copy.
    writer.clone_reader_document_root(reader)
    writer.metadata = None

    def drop(obj, key, category):
        if key in obj:
            del obj[key]
            counters[category] += 1

    def walk(obj):
        if isinstance(obj, IndirectObject):
            identity = (id(obj.pdf), obj.idnum, obj.generation)
        else:
            identity = id(obj)
        if identity in seen:
            return
        seen.add(identity)
        obj = resolve(obj)
        if isinstance(obj, DictionaryObject):
            obj_type = obj.get("/Type")
            # /Metadata can also be an arbitrary resource name. Restrict removal
            # to metadata streams or standard owners, preserving font resources.
            metadata = resolve(obj.get("/Metadata"))
            if (obj_type in {"/Catalog", "/Page", "/Pages", "/XObject", "/Font", "/FontDescriptor", "/Annot", "/StructTreeRoot"}
                    or isinstance(obj, StreamObject)
                    or (isinstance(metadata, StreamObject) and metadata.get("/Type") == "/Metadata")):
                drop(obj, "/Metadata", "metadata_entries")
                drop(obj, "/PieceInfo", "metadata_entries")
            if obj_type == "/Catalog":
                names = resolve(obj.get("/Names"))
                if isinstance(names, DictionaryObject):
                    drop(names, "/EmbeddedFiles", "attachment_entries")
                    drop(names, "/JavaScript", "active_entries")
                drop(obj, "/OpenAction", "active_entries")
                drop(obj, "/Collection", "attachment_entries")
            if obj_type in {"/Catalog", "/Page", "/Pages", "/XObject", "/Annot", "/StructElem", "/Filespec"} or obj.get("/Subtype"):
                drop(obj, "/AF", "attachment_entries")
                drop(obj, "/AA", "active_entries")
            extra_actions = resolve(obj.get("/AA"))
            if isinstance(extra_actions, DictionaryObject) and any(
                isinstance(resolve(action), DictionaryObject) and "/S" in resolve(action)
                for action in extra_actions.values()
            ):
                drop(obj, "/AA", "active_entries")
            action = resolve(obj.get("/A"))
            if isinstance(action, DictionaryObject) and action.get("/S") in {
                "/JavaScript", "/Launch", "/SubmitForm", "/ImportData", "/GoToR",
                "/GoToE", "/GoTo", "/URI", "/Rendition", "/RichMediaExecute",
                "/ResetForm", "/Named", "/Hide", "/SetOCGState", "/Thread", "/Sound", "/Movie"
            }:
                drop(obj, "/A", "active_entries")
            file_entries = resolve(obj.get("/EF"))
            if obj_type == "/Filespec" or (isinstance(file_entries, DictionaryObject)
                                           and any(k in file_entries for k in ("/F", "/UF", "/DOS", "/Mac", "/Unix"))):
                drop(obj, "/EF", "attachment_entries")
                for key in ("/F", "/UF", "/DOS", "/Mac", "/Unix", "/Desc"):
                    drop(obj, key, "attachment_entries")
            if obj_type == "/Annot" or obj.get("/Subtype") in {"/Link", "/Widget", "/FileAttachment"}:
                # Interactive actions are intentionally removed. Visible text
                # and static annotation appearances still require visual QA.
                drop(obj, "/A", "active_entries")
                if obj.get("/Subtype") == "/FileAttachment":
                    drop(obj, "/FS", "attachment_entries")
            annotations = resolve(obj.get("/Annots"))
            if isinstance(annotations, ArrayObject):
                retained = []
                for annotation in annotations:
                    item = resolve(annotation)
                    if isinstance(item, DictionaryObject) and item.get("/Subtype") == "/FileAttachment":
                        counters["attachment_entries"] += 1
                    else:
                        retained.append(annotation)
                obj[NameObject("/Annots")] = ArrayObject(retained)
            for child in children(obj):
                walk(child)
        elif isinstance(obj, (ArrayObject, list, tuple)):
            for child in obj:
                walk(child)

    walk(writer.root_object)
    # Removing references alone can leave the attachment stream as an orphan
    # object in a writer. Re-clone only the reachable catalog graph into a
    # fresh writer, so those original bytes are not serialized for delivery.
    intermediate = io.BytesIO()
    writer.write(intermediate)
    catalog_only = PdfReader(io.BytesIO(intermediate.getvalue()))
    final_writer = PdfWriter()
    final_writer.clone_reader_document_root(catalog_only)
    final_writer.metadata = None
    buffer = io.BytesIO()
    final_writer.write(buffer)
    check = PdfReader(io.BytesIO(buffer.getvalue()))
    if len(check.pages) != len(reader.pages) or check.metadata:
        raise ValueError("PDF page/metadata validation failed.")
    # Check the public attachment interface, not only one catalog key.
    if list(check.attachments):
        raise ValueError("PDF attachment validation failed.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as output:
        output.write(buffer.getvalue())
    return {"pages": len(check.pages), **counters, "package_validation": "passed",
            "visual_review": "pending", "content_privacy_review": "pending"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(scrub_pdf(args.source, args.destination), ensure_ascii=False))
    except Exception as exc:
        parser.exit(1, f"PDF scrub failed: {type(exc).__name__}: {str(exc) if isinstance(exc, ValueError) else 'inspect input and public dependency compatibility'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
