"""Document database with process locking and atomic, durable snapshots."""
import copy
import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path


class DatabaseError(ValueError):
    """An invalid database operation or damaged database file."""


class Database:
    def __init__(self, path="data/database.json"):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    @contextmanager
    def _lock(self):
        with self.lock_path.open("a+b") as lock:
            if os.name == "nt":
                import msvcrt
                lock.seek(0, 2)
                if lock.tell() == 0:
                    lock.write(b"0")
                    lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == "nt":
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _read(self):
        if not self.path.exists():
            return {"version": 1, "tables": {}}
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
            if state["version"] != 1 or not isinstance(state["tables"], dict):
                raise ValueError("Invalid format")
            for table in state["tables"].values():
                if not isinstance(table, dict) or not isinstance(table["rows"], list):
                    raise ValueError("Invalid table")
                if type(table["next_id"]) is not int or table["next_id"] < 1:
                    raise ValueError("Invalid ID sequence")
                ids = [row["_id"] for row in table["rows"] if isinstance(row, dict)]
                if len(ids) != len(table["rows"]) or any(type(i) is not int or i < 1 for i in ids):
                    raise ValueError("Invalid records")
                if len(set(ids)) != len(ids) or any(i >= table["next_id"] for i in ids):
                    raise ValueError("Invalid ID sequence")
            return state
        except (ValueError, KeyError, TypeError) as exc:
            raise DatabaseError("Database file is damaged or unsupported; restore a backup.") from exc

    def _write(self, state):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=".minidb-", delete=False) as file:
                temporary = file.name
                json.dump(state, file, indent=2, allow_nan=False)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
            if os.name != "nt":
                fd = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _equal(left, right):
        if type(left) is not type(right):
            return False
        if isinstance(left, dict):
            return left.keys() == right.keys() and all(Database._equal(left[k], right[k]) for k in left)
        if isinstance(left, list):
            return len(left) == len(right) and all(Database._equal(a, b) for a, b in zip(left, right))
        return left == right

    @staticmethod
    def _matches(row, where):
        return all(key in row and Database._equal(row[key], value)
                   for key, value in where.items())

    def execute(self, command):
        """Execute one atomic command. Filters use exact field equality."""
        if not isinstance(command, dict):
            raise DatabaseError("Command must be a JSON object.")
        try:
            command = json.loads(json.dumps(command, allow_nan=False))
        except (ValueError, TypeError) as exc:
            raise DatabaseError("Command must contain finite JSON values.") from exc
        op = command.get("op")
        allowed = {
            "tables": {"op"}, "create": {"op", "table"}, "drop": {"op", "table"},
            "insert": {"op", "table", "values"}, "select": {"op", "table", "where", "limit", "offset"},
            "update": {"op", "table", "where", "values"}, "delete": {"op", "table", "where"},
        }
        if not isinstance(op, str) or op not in allowed:
            raise DatabaseError("Unknown operation. Use tables, create, drop, insert, select, update, or delete.")
        extra = command.keys() - allowed[op]
        if extra:
            raise DatabaseError("Unknown command fields: " + ", ".join(sorted(extra)))
        name = command.get("table")
        if op != "tables" and (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name)):
            raise DatabaseError("Table names must start with a letter and contain only letters, numbers, or underscores (max 64).")
        where = command.get("where", {})
        if not isinstance(where, dict):
            raise DatabaseError("where must be a JSON object.")
        if op in {"update", "delete"} and ("where" not in command or not where):
            raise DatabaseError("Updates and deletes require a nonempty where filter.")
        values = command.get("values")
        if op in {"insert", "update"}:
            if not isinstance(values, dict) or not values:
                raise DatabaseError("values must be a nonempty JSON object.")
            if "_id" in values:
                raise DatabaseError("_id is generated automatically and cannot be changed.")
        limit, offset = command.get("limit", 100), command.get("offset", 0)
        if op == "select" and (type(limit) is not int or not 1 <= limit <= 10000 or
                               type(offset) is not int or offset < 0):
            raise DatabaseError("limit must be 1–10000 and offset must be a nonnegative integer.")
        with self._lock():
            state = self._read()
            tables = state["tables"]
            if op == "tables":
                return {"tables": [{"name": n, "count": len(t["rows"])} for n, t in sorted(tables.items())]}
            if op == "create":
                if name in tables:
                    raise DatabaseError("Table already exists.")
                tables[name] = {"next_id": 1, "rows": []}
                result = {"created": name}
            else:
                if name not in tables:
                    raise DatabaseError("Table does not exist.")
                table = tables[name]
                if op == "drop":
                    del tables[name]
                    result = {"dropped": name}
                elif op == "insert":
                    row = {**values, "_id": table["next_id"]}
                    table["next_id"] += 1
                    table["rows"].append(row)
                    result = {"row": row}
                else:
                    matches = [r for r in table["rows"] if self._matches(r, where)]
                    if op == "select":
                        return copy.deepcopy({"rows": matches[offset:offset + limit], "total": len(matches)})
                    if op == "update":
                        for row in matches:
                            row.update(values)
                        result = {"updated": len(matches)}
                    else:
                        ids = {r["_id"] for r in matches}
                        table["rows"] = [r for r in table["rows"] if r["_id"] not in ids]
                        result = {"deleted": len(matches)}
            self._write(state)
            return copy.deepcopy(result)
