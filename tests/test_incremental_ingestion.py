"""Synthetic-only regression tests for incremental ingestion."""
import tempfile
import unittest
from pathlib import Path
from src.ingestion.incremental import Ingestor

class IncrementalIngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.raw = root / "raw"
        self.raw.mkdir()
        self.calls = 0
        def parser(path):
            self.calls += 1
            if path.read_bytes() == b"bad":
                raise ValueError("synthetic failure")
            return {"document": {"filename": path.name},
                    "blocks": [{"type": "text", "text": "합성 테스트 조항"}],
                    "warnings": []}
        self.worker = Ingestor(self.raw, root / "parsed", root / "state.sqlite3", parser)

    def tearDown(self):
        self.worker.close()
        self.temp.cleanup()

    def test_create_unchanged_update_failure_retry_delete_recreate(self):
        pdf = self.raw / "synthetic.pdf"
        pdf.write_bytes(b"v1")
        self.assertEqual(self.worker.scan()[pdf.name], "created")
        self.assertEqual(self.worker.scan()[pdf.name], "unchanged")
        self.assertEqual(self.calls, 1)
        pdf.write_bytes(b"v2")
        self.assertEqual(self.worker.scan()[pdf.name], "updated")
        pdf.write_bytes(b"bad")
        self.assertEqual(self.worker.scan()[pdf.name], "failed")
        self.assertEqual(self.worker.scan()[pdf.name], "failed")
        pdf.write_bytes(b"v3")
        self.assertEqual(self.worker.scan()[pdf.name], "updated")
        pdf.unlink()
        self.assertEqual(self.worker.scan()[pdf.name], "deleted")
        self.assertEqual(self.worker.scan(), {})
        pdf.write_bytes(b"v3")
        self.assertEqual(self.worker.scan()[pdf.name], "created")
        events = self.worker.pending_events()
        self.assertEqual([e["event"] for e in events],
                         ["created", "updated", "updated", "deleted", "created"])
        self.worker.acknowledge(events[0]["id"])
        self.assertEqual(len(self.worker.pending_events()), 4)

    def test_missing_output_is_regenerated(self):
        pdf = self.raw / "a.pdf"
        pdf.write_bytes(b"synthetic")
        self.worker.scan()
        output = self.worker.db.execute(
            "SELECT output_path FROM documents WHERE path='a.pdf'").fetchone()[0]
        Path(output).unlink()
        self.assertEqual(self.worker.scan()["a.pdf"], "recovered")

if __name__ == "__main__":
    unittest.main()
