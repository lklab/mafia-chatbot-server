import sqlite3

def get_connection(db_name="example.db"):
    """Helper function to create a connection to the SQLite database."""
    return sqlite3.connect(db_name)

def create_table():
    """Create the table if it doesn't already exist."""
    conn = get_connection()
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                uid TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
            """
        )
    conn.close()

def get_user_by_uid(uid):
    """Retrieve a row by uid. Return None if not found."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT uid, name FROM users WHERE uid = ?", (uid,))
    row = cursor.fetchone()
    conn.close()
    return row

def insert_user(uid, name):
    """Insert a new row with the given uid and name."""
    conn = get_connection()
    try:
        with conn:
            conn.execute("INSERT INTO users (uid, name) VALUES (?, ?)", (uid, name))
    except sqlite3.IntegrityError as e:
        print(f"Error inserting user: {e}")
    finally:
        conn.close()

def upsert_user(uid, name):
    """Insert a new row or update the name of the user with the given uid."""
    conn = get_connection()
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM users WHERE uid = ?", (uid,))
        if cursor.fetchone():
            conn.execute("UPDATE users SET name = ? WHERE uid = ?", (name, uid))
        else:
            conn.execute("INSERT INTO users (uid, name) VALUES (?, ?)", (uid, name))
    conn.close()

# Example usage
if __name__ == "__main__":
    create_table()
    insert_user("user1", "Alice")
    print(get_user_by_uid("user1"))  # Output: ('user1', 'Alice')
    upsert_user("user1", "Bob")
    print(get_user_by_uid("user1"))  # Output: ('user1', 'Bob')
    upsert_user("user2", "Charlie")
    print(get_user_by_uid("user2"))  # Output: ('user2', 'Charlie')
