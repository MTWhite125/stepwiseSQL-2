"""Tkinter desktop database browser and command editor."""
import json
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from .engine import DatabaseError


class DatabaseGUI:
    def __init__(self, root, database):
        self.root, self.db = root, database
        root.title("MiniDB — Python Database")
        root.geometry("1000x720")
        root.minsize(700, 500)
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="MiniDB", font=("Arial", 24, "bold")).pack(anchor="w")
        ttk.Label(frame, text=str(database.path)).pack(anchor="w", pady=(0, 12))
        bar = ttk.Frame(frame)
        bar.pack(fill="x")
        self.table = ttk.Combobox(bar, state="readonly", width=28)
        self.table.pack(side="left", padx=(0, 8))
        self.table.bind("<<ComboboxSelected>>", lambda event: self.browse())
        for label, action in [("Refresh", self.refresh), ("Create table", self.create),
                              ("Insert record", self.insert), ("Update selected", self.update),
                              ("Delete selected", self.delete)]:
            ttk.Button(bar, text=label, command=action).pack(side="left", padx=2)
        grid_frame = ttk.Frame(frame)
        grid_frame.pack(fill="both", expand=True, pady=12)
        self.grid = ttk.Treeview(grid_frame, show="headings", selectmode="browse")
        y = ttk.Scrollbar(grid_frame, orient="vertical", command=self.grid.yview)
        x = ttk.Scrollbar(grid_frame, orient="horizontal", command=self.grid.xview)
        self.grid.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        self.grid.grid(row=0, column=0, sticky="nsew")
        y.grid(row=0, column=1, sticky="ns")
        x.grid(row=1, column=0, sticky="ew")
        grid_frame.rowconfigure(0, weight=1)
        grid_frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text="JSON command (see README for all operations)").pack(anchor="w")
        self.editor = tk.Text(frame, height=5, font=("Courier", 12))
        self.editor.pack(fill="x", pady=6)
        self.editor.insert("1.0", '{"op": "tables"}')
        ttk.Button(frame, text="Execute command", command=self.execute).pack(anchor="w")
        self.output = tk.Text(frame, height=6, state="disabled", font=("Courier", 11))
        self.output.pack(fill="x", pady=(8, 0))
        self.refresh()

    def show(self, value):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", json.dumps(value, indent=2, ensure_ascii=False))
        self.output.configure(state="disabled")

    def run(self, command):
        try:
            result = self.db.execute(command)
            self.show(result)
            self.refresh()
            return result
        except (DatabaseError, OSError) as exc:
            messagebox.showerror("Database error", str(exc))

    def refresh(self):
        try:
            names = [t["name"] for t in self.db.execute({"op": "tables"})["tables"]]
            current = self.table.get()
            self.table["values"] = names
            self.table.set(current if current in names else (names[0] if names else ""))
            self.browse()
        except (DatabaseError, OSError) as exc:
            messagebox.showerror("Database error", str(exc))

    def browse(self):
        self.grid.delete(*self.grid.get_children())
        self.rows = {}
        if not self.table.get():
            self.grid["columns"] = ()
            return
        result = self.db.execute({"op": "select", "table": self.table.get(), "limit": 1000})
        columns = ["_id"] + sorted({k for row in result["rows"] for k in row if k != "_id"})
        self.grid["columns"] = columns
        for column in columns:
            self.grid.heading(column, text=column)
            self.grid.column(column, width=140, minwidth=80)
        for row in result["rows"]:
            item = self.grid.insert("", "end", values=[json.dumps(row[k], ensure_ascii=False) if k in row else "" for k in columns])
            self.rows[item] = row
        self.root.title(f"MiniDB — {self.table.get()} — showing {len(result['rows'])} of {result['total']} records")

    def create(self):
        name = simpledialog.askstring("Create table", "Table name:")
        if name:
            result = self.run({"op": "create", "table": name})
            if result:
                self.table.set(name)
                self.browse()

    def ask_values(self, initial="{}"):
        value = simpledialog.askstring("Record values", "Enter a JSON object:", initialvalue=initial)
        if value is None:
            return None
        try:
            return json.loads(value)
        except ValueError as exc:
            messagebox.showerror("Invalid JSON", str(exc))

    def insert(self):
        if self.table.get():
            values = self.ask_values('{"name": "Ada", "age": 36}')
            if values is not None:
                self.run({"op": "insert", "table": self.table.get(), "values": values})

    def selected(self):
        items = self.grid.selection()
        if not items:
            messagebox.showinfo("Select a record", "Select a record in the table first.")
            return None
        return self.rows[items[0]]

    def update(self):
        row = self.selected()
        if row is not None:
            values = self.ask_values(json.dumps({k: v for k, v in row.items() if k != "_id"}))
            if values is not None:
                self.run({"op": "update", "table": self.table.get(), "where": {"_id": row["_id"]}, "values": values})

    def delete(self):
        row = self.selected()
        if row is not None and messagebox.askyesno("Delete record", f"Delete record {row['_id']}?"):
            self.run({"op": "delete", "table": self.table.get(), "where": {"_id": row["_id"]}})

    def execute(self):
        try:
            command = json.loads(self.editor.get("1.0", "end"))
            if isinstance(command, dict) and command.get("op") in {"delete", "drop"}:
                if not messagebox.askyesno("Confirm removal", "Execute this destructive command?"):
                    return
            self.run(command)
        except ValueError as exc:
            messagebox.showerror("Invalid JSON", str(exc))


def launch(database):
    root = tk.Tk()
    DatabaseGUI(root, database)
    root.mainloop()
