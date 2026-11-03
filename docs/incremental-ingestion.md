# Incremental PDF ingestion (MVP)

Run from repository root after installing `requirements-parsing.txt`:

```bash
python -m src.ingestion.incremental --source data/raw --out data/parsed --db data/ingestion/state.sqlite3
python -m unittest discover -s tests -p "test_*.py" -v
```

The command scans the **top level** of the source folder once. Run it periodically using a scheduler to automate detection; no upload API, watcher, or daemon is included. Only text PDFs are supported by the existing parser. Keep original PDFs and generated Markdown private unless redistribution rights are verified.

SQLite stores a document's relative filename, SHA-256, parser version, status (`processing`, `ready`, `failed`, `deleted`), output path, attempt count, error, and UTC timestamp. Identical ready documents with an existing output are skipped. Changed bytes or parser versions are reparsed. Failed documents retry on subsequent scans. Missing outputs regenerate. Files absent from a complete scan become tombstones, with a `deleted` outbox event; source PDFs are never deleted by this program.

## Downstream integration contract

`Ingestor.pending_events()` returns ordered dictionaries with `id`, `path`, `event` (`created`, `updated`, `recovered`, `deleted`), `sha256`, and `output_path`. A future chunking/indexing consumer must process events idempotently and call `acknowledge(id)` only after successful completion. For deletion, remove indexed chunks for that document identity. For update, diff normalized blocks and only re-embed changed blocks in a **future** implementation.

## Operational limitations

- This MVP reparses a whole changed PDF, not individual articles; it does not implement chunking, embeddings, vector indexing, retrieval, or answering.
- The scanner is single-worker; do not run concurrent scans against the same source/state database.
- A file missing during a scan is treated as deleted; use atomic upload staging and a stable completed upload location to prevent false deletions.
- The outbox provides at-least-once delivery when a consumer is attached. Consumers must deduplicate events.
- Interrupted processing retries on the next scan; orphaned versioned output folders are not garbage-collected.
- Files are hashed before and after parsing, but producers should still atomically rename fully written PDFs into the input folder.
- Synthetic fixtures exercise the state machine, not the real parser's layout accuracy.
