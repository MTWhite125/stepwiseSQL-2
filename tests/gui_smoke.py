"""Manual GUI smoke check: python3 tests/gui_smoke.py (requires desktop access)."""
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from minidb import Database
from minidb.gui import DatabaseGUI

with tempfile.TemporaryDirectory() as directory:
    root = tk.Tk()
    try:
        app = DatabaseGUI(root, Database(Path(directory) / "db.json"))
        root.update()
        with patch("minidb.gui.simpledialog.askstring", return_value="people"):
            app.create()
        with patch("minidb.gui.simpledialog.askstring", return_value='{"name":"Ada","age":36}'):
            app.insert()
        items = app.grid.get_children()
        assert len(items) == 1
        app.grid.selection_set(items[0])
        with patch("minidb.gui.simpledialog.askstring", return_value='{"age":37}'):
            app.update()
        item = app.grid.get_children()[0]
        assert app.rows[item]["age"] == 37
        app.grid.selection_set(item)
        with patch("minidb.gui.messagebox.askyesno", return_value=True):
            app.delete()
        assert not app.grid.get_children()
        app.editor.delete("1.0", "end")
        app.editor.insert("1.0", '{"op":"tables"}')
        app.execute()
        root.update()
        assert 'people' in app.output.get("1.0", "end")
        print("Desktop GUI smoke check passed: create, insert, browse, update, delete, command editor.")
    finally:
        root.destroy()
