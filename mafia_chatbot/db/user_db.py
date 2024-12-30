import sqlite3
import time

class UserDB :
    def __init__(self) :
        self._create_table()

    def _get_connection(self) :
        """Helper function to create a connection to the SQLite database."""
        return sqlite3.connect('user.db')

    def _create_table(self) :
        """Create the table if it doesn't already exist."""
        conn = self._get_connection()
        with conn :
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    uid TEXT PRIMARY KEY,
                    name TEXT NOT NULL
                )
                """
            )
        conn.close()

    def enable_wal(self) :
        conn = self._get_connection()
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.close()

    def get_user_by_uid(self, uid: str) :
        """Retrieve a row by uid. Return None if not found."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT uid, name FROM users WHERE uid = ?", (uid,))
        row = cursor.fetchone()
        conn.close()
        return row

    def upsert_user(self, uid: str, name: str) :
        """Insert a new row or update the name of the user with the given uid."""
        for _ in range(50) :
            try:
                conn = self._get_connection()
                with conn :
                    conn.execute("BEGIN IMMEDIATE")
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1 FROM users WHERE uid = ?", (uid,))
                    if cursor.fetchone() :
                        conn.execute("UPDATE users SET name = ? WHERE uid = ?", (name, uid))
                    else :
                        conn.execute("INSERT INTO users (uid, name) VALUES (?, ?)", (uid, name))
                    conn.commit()
                    return

            except sqlite3.OperationalError :
                time.sleep(0.1)
                continue

            finally :
                conn.close()

        raise sqlite3.OperationalError("Max retries reached.")

    def delete_user_by_uid(self, uid: str) :
        """Delete a row by uid."""
        conn = self._get_connection()
        with conn :
            conn.execute("DELETE FROM users WHERE uid = ?", (uid,))
        conn.close()

    def get_all_users(self) :
        """Retrieve all rows from the users table."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT uid, name FROM users")
        rows = cursor.fetchall()
        conn.close()
        return rows

userDB: UserDB = UserDB()
