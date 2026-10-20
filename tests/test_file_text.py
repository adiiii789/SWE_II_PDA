"""mcp_servers/file_text.py: Text aus PDF, Office, HTML, Mails und Textdateien - Testdateien werden hier erzeugt."""
import io
import sys
import unittest
import zipfile
from email.message import EmailMessage
from unittest import mock

from backend import config

sys.path.insert(0, str(config.ROOT_DIR / "mcp_servers"))
import file_text  # noqa: E402

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def make_pdf(*page_texts: str) -> bytes:
    """Minimales PDF, eine Seite pro Text (leerer Text = Seite ohne Text, wie ein Scan)."""
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [%s] /Count %d >>"
               % (b" ".join(b"%d 0 R" % (4 + 2 * i) for i in range(len(page_texts))), len(page_texts)),
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for i, text in enumerate(page_texts):
        content = b"BT /F1 12 Tf 10 100 Td (%s) Tj ET" % text.encode("latin-1") if text else b""
        objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] "
                       b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % (5 + 2 * i))
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content))
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def make_zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def make_docx(*paragraphs: str) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
    body += "<w:p><w:r><w:t>Name</w:t></w:r><w:r><w:tab/><w:t>Ort</w:t></w:r></w:p>"
    return make_zip({"word/document.xml": f'<w:document xmlns:w="{WORD_NS}"><w:body>{body}</w:body></w:document>'})


def make_pptx(slides: dict[int, str]) -> bytes:
    return make_zip({f"ppt/slides/slide{number}.xml":
                     f'<p:sld xmlns:p="x" xmlns:a="{DRAWING_NS}"><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:sld>'
                     for number, text in slides.items()})


class PdfTest(unittest.TestCase):
    def test_pages_are_labelled(self):
        text = file_text.extract_text(make_pdf("Rechnung Nr. 42", "Summe 99 EUR"), "rechnung.pdf")
        self.assertEqual(text, "[Seite 1]\nRechnung Nr. 42\n\n[Seite 2]\nSumme 99 EUR")

    def test_detected_by_mime_type(self):
        self.assertIn("Hallo", file_text.extract_text(make_pdf("Hallo"), "download", "application/pdf"))

    def test_scanned_pdf_without_text(self):
        with self.assertRaisesRegex(file_text.FileTextError, "eingescannt"):
            file_text.extract_text(make_pdf(""), "scan.pdf")

    def test_page_limit(self):
        with mock.patch.object(file_text, "MAX_PDF_PAGES", 2):
            text = file_text.extract_text(make_pdf("A", "B", "C"), "x.pdf")
        self.assertIn("[Seite 2]\nB", text)
        self.assertNotIn("[Seite 3]", text)
        self.assertIn("nur die ersten 2 von 3 Seiten", text)

    def test_broken_pdf(self):
        with self.assertRaisesRegex(file_text.FileTextError, "PDF konnte nicht gelesen werden"):
            file_text.extract_text(b"%PDF-1.4 kaputt", "x.pdf")


class OfficeTest(unittest.TestCase):
    def test_docx(self):
        text = file_text.extract_text(make_docx("Protokoll", "Grüße &amp; mehr"), "protokoll.docx")
        self.assertEqual(text, "Protokoll\nGrüße & mehr\nName\tOrt")

    def test_pptx_slides_in_numeric_order(self):
        text = file_text.extract_text(make_pptx({10: "Ende", 2: "Mitte", 1: "Titel"}), "folien.pptx")
        self.assertEqual(text, "[Folie 1]\nTitel\n\n[Folie 2]\nMitte\n\n[Folie 3]\nEnde")

    def test_xlsx(self):
        from openpyxl import Workbook
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Noten"
        sheet.append(["Fach", "Note"])
        sheet.append(["Mathe", 1.3])
        sheet.append([None, None])
        buffer = io.BytesIO()
        workbook.save(buffer)
        text = file_text.extract_text(buffer.getvalue(), "noten.xlsx")
        self.assertEqual(text, "[Tabellenblatt Noten]\nFach | Note\nMathe | 1.3")

    def test_broken_office_file(self):
        with self.assertRaisesRegex(file_text.FileTextError, "Word-Datei ist beschädigt"):
            file_text.extract_text(b"kein zip", "x.docx")
        with self.assertRaisesRegex(file_text.FileTextError, r"beschädigt \(word/document.xml\)"):
            file_text.extract_text(make_zip({"anderes.xml": "<a/>"}), "x.docx")

    def test_zip_bomb_is_refused(self):
        with mock.patch.object(file_text, "MAX_UNPACKED_BYTES", 100):
            with self.assertRaisesRegex(file_text.FileTextError, "entpackt zu groß"):
                file_text.extract_text(make_docx("x" * 200), "x.docx")


class OtherTypesTest(unittest.TestCase):
    def test_text_utf8_and_windows_1252(self):
        self.assertEqual(file_text.extract_text("Grüße".encode(), "a.txt"), "Grüße")
        self.assertEqual(file_text.extract_text("Grüße".encode("cp1252"), "a.csv"), "Grüße")
        self.assertEqual(file_text.extract_text(b"x", "ohne-endung", "text/calendar"), "x")

    def test_html(self):
        html = b"<html><head><title>T</title></head><body><h1>Hallo</h1><p>Welt &amp; mehr</p></body></html>"
        self.assertEqual(file_text.extract_text(html, "seite.html"), "Hallo\n\nWelt & mehr")

    def test_eml(self):
        message = EmailMessage()
        message.set_content("Inhalt der Mail")
        self.assertEqual(file_text.extract_text(message.as_bytes(), "mail.eml"), "Inhalt der Mail")

    def test_unknown_types_have_no_text(self):
        for name, mime in (("foto.jpg", "image/jpeg"), ("archiv.zip", "application/zip"), ("x.exe", "")):
            self.assertIsNone(file_text.extract_text(b"\x00\x01", name, mime))
            self.assertFalse(file_text.can_extract(name, mime))
        self.assertTrue(file_text.can_extract("bericht.PDF"))


if __name__ == "__main__":
    unittest.main()
