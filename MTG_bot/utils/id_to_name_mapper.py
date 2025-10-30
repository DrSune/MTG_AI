import sqlite3
from typing import Optional

class IDToNameMapper:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def get_name(self, _id: int, table_name: str) -> Optional[str]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        name = None
        if table_name == "cards":
            cursor.execute("SELECT name FROM cards WHERE card_id = ?", (_id,))
            result = cursor.fetchone()
            if result:
                name = result[0]
        elif table_name == "game_vocabulary":
            cursor.execute("SELECT name FROM game_vocabulary WHERE id = ?", (_id,))
            result = cursor.fetchone()
            if result:
                name = result[0]
        
        conn.close()
        return name

    def get_id_by_name(self, name: str, table_name: str) -> Optional[int]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        _id = None
        if table_name == "cards":
            # This should ideally not be used for cards due to potential name collisions.
            # CardDataLoader handles unique card IDs.
            cursor.execute("SELECT card_id FROM cards WHERE name = ?", (name,))
            result = cursor.fetchone()
            if result:
                _id = result[0]
        elif table_name == "game_vocabulary":
            cursor.execute("SELECT id FROM game_vocabulary WHERE name = ?", (name,))
            result = cursor.fetchone()
            if result:
                _id = result[0]
        
        conn.close()
        return _id
