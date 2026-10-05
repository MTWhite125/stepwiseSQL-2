# MiniDB

A database engine written in Python, a Tkinter desktop GUI, and an HTTP server with a browser GUI and JSON API. The engine implements document storage directly, without SQLite or an external database.

## Run

Requires Python 3.10 or newer. No pip installation is needed. Run from this directory:

```sh
python3 -m minidb gui
python3 -m minidb web
```

Open **http://127.0.0.1:8080** for the browser GUI. Stop the server with Ctrl+C. The desktop GUI requires Python with Tkinter support; the browser GUI works without Tkinter.

Both interfaces default to `data/database.json`, relative to your working directory. To share another file, put `--db` before the mode:

```sh
python3 -m minidb --db /absolute/path/database.json gui
python3 -m minidb --db /absolute/path/database.json web --port 9000
```

## Use the interfaces

Create a `people` table and insert `{"name": "Ada", "age": 36}`. The desktop GUI has buttons for insert, update, and delete; select a record before updating or deleting it. It displays the first 1,000 records; its command editor supports pagination. The browser displays 100 records per page and provides command templates for each operation. Both interfaces confirm deletion and table removal.

## Commands

Records are JSON objects with arbitrary fields, nested objects, and arrays. Each table generates increasing integer `_id` values; deleted IDs are never reused. Updates merge fields into matching records. Filters compare exact JSON values and require every supplied field to match; missing fields do not match null. Booleans and numbers are distinct.

Execute one JSON object at a time:

```json
{"op": "tables"}
{"op": "create", "table": "people"}
{"op": "insert", "table": "people", "values": {"name": "Ada", "age": 36}}
{"op": "select", "table": "people"}
{"op": "select", "table": "people", "where": {"name": "Ada"}, "limit": 100, "offset": 0}
{"op": "update", "table": "people", "where": {"_id": 1}, "values": {"age": 37}}
{"op": "delete", "table": "people", "where": {"_id": 1}}
{"op": "drop", "table": "people"}
```

Update and delete require a nonempty filter. Drop permanently removes a table and its records. Select defaults to 100 records and permits a limit up to 10,000. `total` reports the matching count before pagination.

CLI example:

```sh
python3 -m minidb exec '{"op":"create","table":"people"}'
python3 -m minidb exec '{"op":"insert","table":"people","values":{"name":"Ada","age":36}}'
python3 -m minidb exec '{"op":"select","table":"people"}'
```

Python API:

```python
from minidb import Database

db = Database("data/database.json")
print(db.execute({"op": "select", "table": "people"})["rows"])
```

## HTTP API

`GET /api/tables` lists tables and counts. `POST /api/execute` accepts one JSON command and returns JSON. Invalid commands return HTTP 400, invalid authentication returns 401, unknown routes return 404, oversized bodies return 413, and unsupported content types return 415. The request body limit is 1 MiB.

```sh
curl -X POST http://127.0.0.1:8080/api/execute \
  -H 'Content-Type: application/json' \
  -d '{"op":"select","table":"people"}'
```

Optional bearer authentication uses the `MINIDB_TOKEN` environment variable. Enter its value in the browser API token field, or send `Authorization: Bearer YOUR_TOKEN`. The server binds to loopback by default. A token is required for non-loopback bindings. For remote use, place it behind a TLS reverse proxy. This local development server uses a single shared token and has no per-user permissions or built-in TLS.

## Storage and scope

Each command locks a separate lock file, reloads the latest snapshot, and applies one operation. Writes fsync a temporary snapshot and atomically replace the database file. POSIX systems also fsync the parent directory. Desktop and server processes can share the same local file without losing concurrent updates. Keep the lock file in place and use local disk. Stop writers before copying the database for backup.

This educational document database loads the entire database into memory, scans records for filters, and rewrites the snapshot for each change. It has no SQL parser, indexes, joins, multi-command transactions, or distributed replication. Each successful mutation is an individual atomic operation.

## Verify

```sh
python3 -m unittest discover -s tests -v
```

Tests cover persistence, CRUD, filtering, pagination, validation, damaged files, concurrent process writes, and HTTP page/API responses and authentication.

To smoke-test the desktop GUI on a machine with display access:

```sh
python3 tests/gui_smoke.py
```
