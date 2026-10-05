import argparse
import json
import os
import sys
from .engine import Database, DatabaseError


def main():
    parser = argparse.ArgumentParser(description="MiniDB document database")
    parser.add_argument("--db", default="data/database.json")
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("gui")
    web = modes.add_parser("web")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8080)
    cli = modes.add_parser("exec")
    cli.add_argument("command", help="JSON command or - for stdin")
    args = parser.parse_args()
    try:
        db = Database(args.db)
        if args.mode == "gui":
            try:
                from .gui import launch
            except ImportError:
                parser.exit(1, "Tkinter is unavailable. Use the web interface or install Python with Tk support.\n")
            launch(db)
        elif args.mode == "web":
            from .web import make_server
            token = os.environ.get("MINIDB_TOKEN")
            if args.host not in {"127.0.0.1", "localhost"} and not token:
                parser.error("Set MINIDB_TOKEN before binding to a non-loopback host.")
            with make_server(db, args.host, args.port, token) as server:
                print(f"MiniDB: http://{args.host}:{server.server_port} · {db.path}", flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    print("\nServer stopped.")
        else:
            raw = sys.stdin.read() if args.command == "-" else args.command
            print(json.dumps(db.execute(json.loads(raw)), indent=2, ensure_ascii=False))
    except (DatabaseError, OSError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
