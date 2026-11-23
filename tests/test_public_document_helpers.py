"""Temporary-fixture smoke tests for the independent public document helpers.

Run: python -m unittest discover -s tests -p test_public_document_helpers.py -v
No customer documents, account data or prebuilt binaries are required.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from xml.dom import minidom
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugins" / "mechanical-patent-workflow"
SKILL_BASE = PLUGIN_ROOT if PLUGIN_ROOT.is_dir() else ROOT


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, SKILL_BASE / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


doc_scrub = load_module("public_doc_scrub", "skills/documents/scripts/privacy_scrub.py")
doc_render = load_module("public_doc_render", "skills/documents/render_docx.py")
pdf_scrub = load_module("public_pdf_scrub", "skills/pdf/scripts/privacy_scrub.py")
pdf_render = load_module("public_pdf_render", "skills/pdf/scripts/render_pdf.py")

W = doc_scrub.W
R = doc_scrub.R
P = doc_scrub.PKG
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
MARKER = "PRIVATE_FIXTURE_IDENTITY_482"


def write_docx(path, *, structural=False, embedded=False):
    deletion = '<w:pPr><w:rPr><w:del w:author="fixture"/></w:rPr></w:pPr>' if structural else ""
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="{W}" xmlns:r="{R}"
 xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
 xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" mc:Ignorable="w14">
<w:body><w:p w:rsidR="00ABC123">{deletion}
<w:r><w:t>Approved base text. </w:t></w:r>
<w:ins w:id="1" w:author="{MARKER}" w:date="2020-01-01T00:00:00Z"><w:r><w:t>Inserted text.</w:t></w:r></w:ins>
<w:del w:id="2" w:author="{MARKER}"><w:r><w:delText>Deleted text.</w:delText></w:r></w:del>
<w:commentRangeStart w:id="0"/><w:commentRangeEnd w:id="0"/><w:r><w:commentReference w:id="0"/></w:r>
<w:hyperlink r:id="localLink"><w:r><w:t>Visible link caption.</w:t></w:r></w:hyperlink>
</w:p><w:p><w:r><w:br w:type="page"/><w:t>Second page.</w:t></w:r></w:p>
<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>
</w:body></w:document>'''
    parts = {
        "[Content_Types].xml": f'''<Types xmlns="{CT}"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/></Types>''',
        "_rels/.rels": f'''<Relationships xmlns="{P}"><Relationship Id="rId1" Type="{R}/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>''',
        "word/document.xml": xml,
        "word/_rels/document.xml.rels": f'''<Relationships xmlns="{P}"><Relationship Id="commentRel" Type="{R}/comments" Target="comments.xml"/><Relationship Id="settingsRel" Type="{R}/settings" Target="settings.xml"/><Relationship Id="localLink" Type="{R}/hyperlink" Target="file:///fixture-private-location/source.docx" TargetMode="External"/></Relationships>''',
        "word/settings.xml": f'''<w:settings xmlns:w="{W}" xmlns:r="{R}"><w:trackRevisions/><w:attachedTemplate r:id="templateRel"/><w:docVars><w:docVar w:name="internalIdentity" w:val="{MARKER}"/></w:docVars></w:settings>''',
        "word/_rels/settings.xml.rels": f'''<Relationships xmlns="{P}"><Relationship Id="templateRel" Type="{R}/attachedTemplate" Target="file:///fixture-private-location/template.dotx" TargetMode="External"/></Relationships>''',
        "docProps/core.xml": f'''<coreProperties xmlns="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>{MARKER}</dc:creator></coreProperties>''',
        "word/comments.xml": f'''<w:comments xmlns:w="{W}"><w:comment w:id="0" w:author="{MARKER}"><w:p/></w:comment></w:comments>''',
        "customXml/item1.xml": f"<private>{MARKER}</private>",
    }
    if embedded:
        parts["word/embeddings/fixture.bin"] = b"embedded source fixture"
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in parts.items():
            archive.writestr(name, data)


def available_renderer():
    try:
        doc_render.find_program(None, "libreoffice")
        doc_render.find_program(None, "pdftoppm")
        return True
    except ValueError:
        return False


class DocxPrivacyTests(unittest.TestCase):
    def test_preserves_real_revisions_and_visible_content_anonymously(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output = root / "source.docx", root / "redline.docx"
            write_docx(source)
            before = hashlib.sha256(source.read_bytes()).digest()
            report = doc_scrub.scrub_docx(source, output, revisions="preserve")
            self.assertEqual(before, hashlib.sha256(source.read_bytes()).digest())
            with zipfile.ZipFile(output) as archive:
                self.assertFalse(any(n.startswith(("docProps/", "customXml/", "word/comments")) for n in archive.namelist()))
                all_xml = b"\n".join(archive.read(n) for n in archive.namelist())
                self.assertNotIn(MARKER.encode(), all_xml)
                self.assertNotIn(b"fixture-private-location", all_xml)
                doc = minidom.parseString(archive.read("word/document.xml"))
                changes = doc.getElementsByTagNameNS(W, "ins")
                self.assertEqual(len(changes), 1)
                self.assertEqual(changes[0].getAttributeNS(W, "author"), "Anonymous")
                self.assertFalse(changes[0].hasAttributeNS(W, "date"))
                self.assertIn(b"xmlns:w14=", archive.read("word/document.xml"))
                self.assertTrue(all(i.date_time == (1980, 1, 1, 0, 0, 0) for i in archive.infolist()))
            self.assertEqual(report["visual_review"], "pending")

    def test_accepts_text_changes_but_rejects_structural_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output = root / "source.docx", root / "clean.docx"
            write_docx(source)
            doc_scrub.scrub_docx(source, output, revisions="accept")
            with zipfile.ZipFile(output) as archive:
                doc = minidom.parseString(archive.read("word/document.xml"))
                xml = doc.toxml()
                self.assertIn("Inserted text.", xml)
                self.assertNotIn("Deleted text.", xml)
                self.assertFalse(doc.getElementsByTagNameNS(W, "ins"))
                self.assertFalse(doc.getElementsByTagNameNS(W, "del"))
                self.assertIn("Visible link caption.", xml)
            structural = root / "structural.docx"
            write_docx(structural, structural=True)
            rejected = root / "rejected.docx"
            with self.assertRaisesRegex(ValueError, "Paragraph/row"):
                doc_scrub.scrub_docx(structural, rejected, revisions="accept")
            self.assertFalse(rejected.exists())

    def test_rejects_overwrite_and_embedded_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.docx"
            write_docx(source)
            with self.assertRaises(ValueError):
                doc_scrub.scrub_docx(source, source, revisions="preserve")
            embedded = root / "embedded.docx"
            write_docx(embedded, embedded=True)
            with self.assertRaisesRegex(ValueError, "Embedded packages"):
                doc_scrub.scrub_docx(embedded, root / "blocked.docx", revisions="preserve")

    def test_rejects_entity_declarations_and_accepts_property_history(self):
        with self.assertRaisesRegex(ValueError, "DTD/entity"):
            doc_scrub.parse_xml('<!DOCTYPE x [<!ENTITY p "private">]><x>&p;</x>'.encode("utf-16"))
        xml = f'''<w:tblPrEx xmlns:w="{W}"><w:tblPrExChange w:id="1" w:author="{MARKER}"><w:tblPrEx/></w:tblPrExChange></w:tblPrEx>'''.encode()
        cleaned, _ = doc_scrub.transform_word_xml(xml, "accept", set())
        self.assertNotIn(b"tblPrExChange", cleaned)
        self.assertNotIn(MARKER.encode(), cleaned)

    @unittest.skipUnless(available_renderer(), "Local LibreOffice/Poppler unavailable")
    def test_actual_word_pdf_png_render_does_not_modify_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original, source = root / "fixture.docx", root / "clean.docx"
            write_docx(original)
            doc_scrub.scrub_docx(original, source, revisions="accept")
            before = source.read_bytes()
            report = doc_render.render_docx(source, root / "render", dpi=72, timeout=90)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(len(report["pages"]), 2)
            self.assertTrue((root / "render/document.pdf").read_bytes().startswith(b"%PDF-"))
            for page in report["pages"]:
                self.assertTrue((root / "render" / page).read_bytes().startswith(b"\x89PNG"))
            with self.assertRaises(ValueError):
                doc_render.render_docx(source, root / "render", dpi=72)


@unittest.skipUnless(importlib.util.find_spec("pypdf"), "Install public pdf/requirements.txt for PDF fixtures")
class PdfPrivacyTests(unittest.TestCase):
    def make_pdf(self, path):
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, TextStringObject
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=300)
        writer.add_blank_page(width=200, height=300)
        writer.add_metadata({"/Author": MARKER, "/CreationDate": "D:20200101000000"})
        writer.add_attachment("private-source.txt", (MARKER + " attachment payload").encode())
        xmp = DecodedStreamObject()
        xmp.set_data(("<private>" + MARKER + " xmp</private>").encode())
        xmp[NameObject("/Type")] = NameObject("/Metadata")
        xmp[NameObject("/Subtype")] = NameObject("/XML")
        writer.root_object[NameObject("/Metadata")] = writer._add_object(xmp)
        writer.pages[0][NameObject("/Metadata")] = writer._add_object(xmp)
        writer.root_object[NameObject("/OpenAction")] = DictionaryObject({NameObject("/S"): NameObject("/JavaScript"), NameObject("/JS"): TextStringObject(MARKER + " script")})
        writer.write(path)

    def test_pdf_metadata_attachment_and_orphan_bytes_removed(self):
        from pypdf import PdfReader
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output = root / "source.pdf", root / "clean.pdf"
            self.make_pdf(source)
            before = source.read_bytes()
            report = pdf_scrub.scrub_pdf(source, output)
            self.assertEqual(source.read_bytes(), before)
            reader = PdfReader(output)
            self.assertEqual(len(reader.pages), 2)
            self.assertFalse(reader.metadata)
            self.assertFalse(list(reader.attachments))
            self.assertNotIn("/Metadata", reader.root_object)
            self.assertNotIn("/Metadata", reader.pages[0])
            self.assertNotIn("/OpenAction", reader.root_object)
            self.assertNotIn(MARKER.encode(), output.read_bytes())
            self.assertEqual(report["visual_review"], "pending")
            with self.assertRaises(ValueError):
                pdf_scrub.scrub_pdf(source, output)

    def test_rejects_encrypted_and_signed_sources(self):
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, TextStringObject
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            encrypted = root / "encrypted.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=300)
            writer.encrypt("fixture-password")
            writer.write(encrypted)
            with self.assertRaisesRegex(ValueError, "Encrypted"):
                pdf_scrub.scrub_pdf(encrypted, root / "blocked.pdf")
            signed = root / "signature-fixture.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=300)
            writer.root_object[NameObject("/FixtureSignature")] = DictionaryObject({
                NameObject("/Type"): NameObject("/Sig"), NameObject("/Name"): TextStringObject(MARKER)
            })
            writer.write(signed)
            with self.assertRaisesRegex(ValueError, "Signed"):
                pdf_scrub.scrub_pdf(signed, root / "blocked.pdf")

    @unittest.skipUnless(available_renderer(), "Local Poppler unavailable")
    def test_actual_pdf_png_render(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "fixture.pdf"
            self.make_pdf(source)
            report = pdf_render.render_pdf(source, root / "pages", dpi=72)
            self.assertEqual(len(report["pages"]), 2)
            self.assertEqual(report["visual_review"], "pending")
            for name in report["pages"]:
                self.assertTrue((root / "pages" / name).read_bytes().startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()
