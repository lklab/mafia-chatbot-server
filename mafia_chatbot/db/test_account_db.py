import sqlite3
import time

class TestAccountDB :
    def __init__(self) :
        self._create_table()

    def _get_connection(self) :
        """Helper function to create a connection to the SQLite database."""
        return sqlite3.connect('test_account.db')

    def _create_table(self) :
        """Create the table if it doesn't already exist."""
        conn = self._get_connection()
        with conn :
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    password TEXT NOT NULL,
                    client_id TEXT NOT NULL
                )
                """
            )
        conn.close()

    def enable_wal(self) :
        conn = self._get_connection()
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.close()

    def upsert_user(self, user_id: str, password: str, client_id: str):
        """Insert a new row or update an existing row by ID."""
        for _ in range(50) :
            try :
                conn = self._get_connection()
                with conn :
                    conn.execute("BEGIN IMMEDIATE")
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1 FROM users WHERE id = ?", (user_id,))
                    if cursor.fetchone() :
                        conn.execute(
                            "UPDATE users SET password = ?, client_id = ? WHERE id = ?",
                            (password, client_id, user_id)
                        )
                    else :
                        conn.execute(
                            "INSERT INTO users (id, password, client_id) VALUES (?, ?, ?)",
                            (user_id, password, client_id)
                        )
                    conn.commit()
                    return

            except sqlite3.OperationalError :
                time.sleep(0.1)
                continue

            finally :
                conn.close()

        raise sqlite3.OperationalError("Max retries reached.")

    def get_user_by_id(self, user_id: str) :
        """Retrieve password and client_id by ID. Return None if not found."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT password, client_id FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row

    def delete_user_by_id(self, user_id: str) :
        """Delete a row by ID. No exception is raised if the row does not exist."""
        conn = self._get_connection()
        with conn :
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.close()

    def get_all_users(self) :
        """Retrieve all rows from the users table."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, password, client_id FROM users")
        rows = cursor.fetchall()
        conn.close()
        return rows

testAccountDB: TestAccountDB = TestAccountDB()
