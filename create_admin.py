import sqlite3
from getpass import getpass
from werkzeug.security import generate_password_hash

DATABASE = "database.db"

conn = sqlite3.connect(DATABASE)

conn.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    )
""")

username = input("Admin username: ").strip()
password = getpass("Admin password: ")

if not username or not password:
    print("Username aur password dono required hain.")
    conn.close()
    exit()

password_hash = generate_password_hash(password)

conn.execute("""
    INSERT INTO admins (username, password_hash)
    VALUES (?, ?)
    ON CONFLICT(username)
    DO UPDATE SET password_hash = excluded.password_hash
""", (username, password_hash))

conn.commit()
conn.close()

print("Admin account successfully created/updated.")