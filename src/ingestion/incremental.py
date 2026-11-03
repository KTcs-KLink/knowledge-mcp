"""Incremental PDF ingestion; SQLite state and durable downstream outbox."""
import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from src.ingestion.pdf_parser import PARSER_VERSION, parse_pdf, render_markdown

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def timestamp():
    return datetime.now(timezone.utc).isoformat()

class Ingestor:
    def __init__(self, source, output, database, parser=None):
        self.source, self.output, self.database = map(lambda p: Path(p).resolve(), (source, output, database))
        self.parser = parser or parse_pdf
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.database, timeout=30)
        self.db.execute("PRAGMA busy_timeout=30000")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            path TEXT PRIMARY KEY, sha256 TEXT, parser_version TEXT,
            status TEXT NOT NULL, output_path TEXT, attempts INTEGER NOT NULL DEFAULT 0,
            error TEXT, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL,
            event TEXT NOT NULL, sha256 TEXT, output_path TEXT,
            created_at TEXT NOT NULL, delivered_at TEXT);
        """)
        self.db.commit()

    def close(self):
        self.db.close()

    def record(self, key, digest, status, output=None, error=None, event=None, attempts=0):
        with self.db:
            self.db.execute("""INSERT INTO documents
            (path,sha256,parser_version,status,output_path,attempts,error,updated_at)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(path) DO UPDATE SET
            sha256=excluded.sha256,parser_version=excluded.parser_version,
            status=excluded.status,output_path=excluded.output_path,
            attempts=excluded.attempts,error=excluded.error,updated_at=excluded.updated_at""",
            (key,digest,PARSER_VERSION,status,output,attempts,error,timestamp()))
            if event:
                self.db.execute("""INSERT INTO outbox
                (path,event,sha256,output_path,created_at) VALUES(?,?,?,?,?)""",
                (key,event,digest,output,timestamp()))

    def scan(self):
        if not self.source.is_dir():
            raise NotADirectoryError(self.source)
        files = sorted(p for p in self.source.iterdir()
                       if p.is_file() and p.suffix.lower() == ".pdf" and not p.is_symlink())
        seen, outcomes = {p.name for p in files}, {}
        for path in files:
            key = path.name
            old = self.db.execute("""SELECT sha256,parser_version,status,output_path,attempts
                                    FROM documents WHERE path=?""", (key,)).fetchone()
            digest = None
            attempts = (old[4] if old else 0) + 1
            try:
                digest = sha256(path)
                if (old and old[0] == digest and old[1] == PARSER_VERSION
                        and old[2] == "ready" and old[3] and Path(old[3]).is_file()):
                    outcomes[key] = "unchanged"
                    continue
                event = ("created" if not old or old[2] == "deleted"
                         else "updated" if old[0] != digest or old[1] != PARSER_VERSION
                         else "recovered")
                self.record(key, digest, "processing", attempts=attempts)
                result = self.parser(path)
                if sha256(path) != digest:
                    raise RuntimeError("PDF changed during parsing; retry next scan")
                markdown = render_markdown(result)
                folder = hashlib.sha256(key.encode()).hexdigest()[:12] + "_" + digest[:12]
                destination = self.output / folder / "parsing.md"
                destination.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp = tempfile.mkstemp(prefix=".parsing-", dir=destination.parent)
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as stream:
                        stream.write(markdown)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(tmp, destination)
                finally:
                    if os.path.exists(tmp):
                        os.unlink(tmp)
                self.record(key, digest, "ready", str(destination), event=event, attempts=attempts)
                outcomes[key] = event
            except Exception as exc:
                self.record(key, digest, "failed", error=f"{type(exc).__name__}: {exc}",
                            attempts=attempts)
                outcomes[key] = "failed"
        for (key,) in self.db.execute(
                "SELECT path FROM documents WHERE status != 'deleted'").fetchall():
            if key not in seen:
                self.record(key, None, "deleted", event="deleted")
                outcomes[key] = "deleted"
        return outcomes

    def pending_events(self):
        """Consumers process events and acknowledge only after downstream success."""
        return [dict(zip(("id","path","event","sha256","output_path"), row))
                for row in self.db.execute("""SELECT id,path,event,sha256,output_path
                FROM outbox WHERE delivered_at IS NULL ORDER BY id""")]

    def acknowledge(self, event_id):
        with self.db:
            self.db.execute("""UPDATE outbox SET delivered_at=?
            WHERE id=? AND delivered_at IS NULL""", (timestamp(), event_id))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, default=Path("data/raw"))
    ap.add_argument("--out", type=Path, default=Path("data/parsed"))
    ap.add_argument("--db", type=Path, default=Path("data/ingestion/state.sqlite3"))
    args = ap.parse_args()
    worker = Ingestor(args.source, args.out, args.db)
    try:
        print(json.dumps(worker.scan(), ensure_ascii=False, indent=2))
    finally:
        worker.close()

if __name__ == "__main__":
    main()
