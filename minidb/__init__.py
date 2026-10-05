"""MiniDB: a persistent Python document database."""
from .engine import Database, DatabaseError

__all__ = ["Database", "DatabaseError"]
