"""backend/attachments.py: nur Dateien aus dem Anhang-Ordner, Öffnen ohne ausführbare Dateien, Speichern."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.assistant.tools import Attachment
from backend.attachments import AttachmentError, AttachmentStore


class AttachmentStoreTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.base, self.downloads = root / "anhaenge", root / "Downloads"
        self.base.mkdir()
        self.opener = mock.Mock()
        self.store = AttachmentStore(self.base, self.downloads, self.opener)

    def _file(self, name="plan.pdf", content=b"PDF", base=None):
        path = (base or self.base) / name
        path.write_bytes(content)
        return Attachment(name, path.as_uri(), "application/pdf", len(content))

    def test_register_returns_id_but_no_path(self):
        entry = self.store.register(self._file())
        self.assertEqual(set(entry), {"id", "name", "mime_type", "size", "can_open"})
        self.assertEqual((entry["name"], entry["size"], entry["can_open"]), ("plan.pdf", 3, True))

    def test_same_file_keeps_its_id(self):
        attachment = self._file()
        self.assertEqual(self.store.register(attachment)["id"], self.store.register(attachment)["id"])

    def test_files_outside_the_folder_are_refused(self):
        outside = self.base.parent / "geheim"
        outside.mkdir()
        self.assertIsNone(self.store.register(self._file(base=outside)))
        sneaky = Attachment("x", (self.base / ".." / "geheim" / "plan.pdf").as_uri())
        self.assertIsNone(self.store.register(sneaky))
        self.assertIsNone(self.store.register(Attachment("x", "https://example.com/plan.pdf")))
        self.assertIsNone(self.store.register(Attachment("x", (self.base / "fehlt.pdf").as_uri())))

    def test_open_uses_default_app(self):
        entry = self.store.register(self._file("Grüße an alle.pdf"))
        self.assertEqual(self.store.open(entry["id"]), "Grüße an alle.pdf")
        self.opener.assert_called_once_with((self.base / "Grüße an alle.pdf").resolve())

    def test_executables_are_not_opened(self):
        for name in ("setup.exe", "rechnung.pdf.js", "makro.docm", "link.LNK"):
            entry = self.store.register(self._file(name))
            self.assertFalse(entry["can_open"])
            with self.assertRaisesRegex(AttachmentError, "nicht direkt geöffnet"):
                self.store.open(entry["id"])
        self.opener.assert_not_called()

    def test_save_copies_without_overwriting(self):
        entry = self.store.register(self._file(content=b"neu"))
        self.downloads.mkdir()
        (self.downloads / "plan.pdf").write_bytes(b"alt")
        target = Path(self.store.save(entry["id"]))
        self.assertEqual(target, self.downloads / "plan (1).pdf")
        self.assertEqual(target.read_bytes(), b"neu")
        self.assertEqual((self.downloads / "plan.pdf").read_bytes(), b"alt")

    def test_save_ignores_display_name(self):
        path = self._file()
        entry = self.store.register(Attachment("..\\..\\autostart\\evil.pdf", path.uri))
        self.assertEqual(Path(self.store.save(entry["id"])), self.downloads / "plan.pdf")

    def test_executables_can_be_saved(self):
        entry = self.store.register(self._file("tool.exe"))
        self.assertTrue(Path(self.store.save(entry["id"])).is_file())

    def test_unknown_id_and_deleted_file(self):
        with self.assertRaisesRegex(AttachmentError, "Unbekannter Anhang"):
            self.store.open("gibtsnicht")
        entry = self.store.register(self._file())
        (self.base / "plan.pdf").unlink()
        with self.assertRaisesRegex(AttachmentError, "nicht mehr vorhanden"):
            self.store.save(entry["id"])


if __name__ == "__main__":
    unittest.main()
