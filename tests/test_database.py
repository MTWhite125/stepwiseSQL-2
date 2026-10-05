import json
import multiprocessing
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from minidb import Database, DatabaseError
from minidb.web import make_server


def insert_many(path):
    db = Database(path)
    for i in range(15):
        db.execute({"op": "insert", "table": "people", "values": {"index": i}})


class EngineTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "db.json"
        self.db = Database(self.path)
        self.db.execute({"op": "create", "table": "people"})

    def test_crud_and_persistence(self):
        row = self.db.execute({"op": "insert", "table": "people", "values": {"name": "Ada", "nested": [1, None]}})["row"]
        self.assertEqual(row["_id"], 1)
        row["nested"].append(2)
        reopened = Database(self.path)
        self.assertEqual(reopened.execute({"op": "select", "table": "people"})["rows"][0]["nested"], [1, None])
        self.assertEqual(reopened.execute({"op": "update", "table": "people", "where": {"_id": 1}, "values": {"age": 37}}), {"updated": 1})
        self.assertEqual(self.db.execute({"op": "select", "table": "people", "where": {"age": 37}})["total"], 1)
        self.assertEqual(self.db.execute({"op": "delete", "table": "people", "where": {"_id": 1}}), {"deleted": 1})
        self.assertEqual(self.db.execute({"op": "insert", "table": "people", "values": {"name": "Grace"}})["row"]["_id"], 2)
        self.db.execute({"op": "drop", "table": "people"})
        self.assertEqual(self.db.execute({"op": "tables"}), {"tables": []})

    def test_validation_preserves_storage(self):
        before = self.path.read_bytes()
        commands = [None, {"op": []}, {"op": "bad"}, {"op": "create", "table": "../bad"},
                    {"op": "delete", "table": "people"},
                    {"op": "update", "table": "people", "where": {}, "values": {"a": 1}},
                    {"op": "insert", "table": "people", "values": {"_id": 3}},
                    {"op": "insert", "table": "people", "values": {"a": float('nan')}},
                    {"op": "select", "table": "people", "limit": True},
                    {"op": "delete", "table": "people", "where": {"_id": 1}, "typo": 1}]
        for command in commands:
            with self.subTest(command=command), self.assertRaises(DatabaseError):
                self.db.execute(command)
        self.assertEqual(self.path.read_bytes(), before)

    def test_filters_and_pagination(self):
        self.assertFalse(Database._equal({"nested": [True]}, {"nested": [1]}))
        for value in [True, 1, None, "1"]:
            self.db.execute({"op": "insert", "table": "people", "values": {"value": value}})
        self.assertEqual(self.db.execute({"op": "select", "table": "people", "where": {"value": True}})["total"], 1)
        self.assertEqual(self.db.execute({"op": "select", "table": "people", "where": {"missing": None}})["total"], 0)
        result = self.db.execute({"op": "select", "table": "people", "limit": 2, "offset": 1})
        self.assertEqual([r["_id"] for r in result["rows"]], [2, 3])
        self.assertEqual(result["total"], 4)

    def test_concurrent_process_writes(self):
        context = multiprocessing.get_context("spawn")
        processes = [context.Process(target=insert_many, args=(str(self.path),)) for _ in range(3)]
        for process in processes:
            process.start()
        for process in processes:
            process.join(20)
            if process.is_alive():
                process.terminate()
                process.join()
            self.assertEqual(process.exitcode, 0)
        rows = self.db.execute({"op": "select", "table": "people"})["rows"]
        self.assertEqual(len(rows), 45)
        self.assertEqual(len({r["_id"] for r in rows}), 45)

    def test_corruption_is_not_overwritten(self):
        self.path.write_text('{"bad":true}')
        with self.assertRaises(DatabaseError):
            self.db.execute({"op": "create", "table": "new"})
        self.assertEqual(self.path.read_text(), '{"bad":true}')


class WebTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.server = make_server(Database(Path(temp.name) / "db.json"), port=0, token="secret")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path, command=None, token="secret"):
        data = json.dumps(command).encode() if command is not None else None
        return urlopen(Request(self.url + path, data=data, headers={"Content-Type": "application/json", "Authorization": "Bearer " + token}), timeout=5)

    def test_api_and_page(self):
        with self.request("/") as response:
            self.assertIn(b"Command editor", response.read())
        for command in [{"op": "create", "table": "people"}, {"op": "insert", "table": "people", "values": {"name": "Ada"}}]:
            with self.request("/api/execute", command) as response:
                self.assertEqual(response.status, 200)
        with self.request("/api/execute", {"op": "select", "table": "people"}) as response:
            self.assertEqual(json.load(response)["rows"][0]["name"], "Ada")
        with self.request("/api/tables") as response:
            self.assertEqual(json.load(response)["tables"][0]["count"], 1)

    def test_api_errors(self):
        for path, command, token, status in [("/api/tables", None, "bad", 401), ("/missing", None, "secret", 404), ("/api/execute", {"op": "bad"}, "secret", 400)]:
            with self.subTest(status=status), self.assertRaises(HTTPError) as error:
                self.request(path, command, token)
            self.assertEqual(error.exception.code, status)
            error.exception.close()
        request = Request(self.url + "/api/execute", data=b"broken", headers={"Content-Type": "application/json", "Authorization": "Bearer secret"})
        with self.assertRaises(HTTPError) as error:
            urlopen(request, timeout=5)
        self.assertEqual(error.exception.code, 400)
        error.exception.close()


if __name__ == "__main__":
    unittest.main()
