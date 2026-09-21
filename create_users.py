import sqlite3
from getpass import getpass
from werkzeug.security import generate_password_hash

DATABASE = "database.db"


def create_users_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('hod', 'teacher', 'student')),
            student_id INTEGER,
            FOREIGN KEY(student_id) REFERENCES students(id)
        )
    """)

    conn.commit()


def create_user(conn):
    print("\n===== CREATE USER =====")

    username = input("Username: ").strip()
    password = getpass("Password: ").strip()

    print("\nRole select karein:")
    print("1. HOD")
    print("2. Teacher")
    print("3. Student")

    choice = input("Enter choice (1/2/3): ").strip()

    role_map = {
        "1": "hod",
        "2": "teacher",
        "3": "student"
    }

    role = role_map.get(choice)

    if not role:
        print("Invalid role.")
        return

    student_id = None

    if role == "student":
        print("\nAvailable Students:")

        students = conn.execute("""
            SELECT id, name, roll_number, class_name
            FROM students
            ORDER BY id
        """).fetchall()

        if not students:
            print("Database me koi student nahi hai.")
            return

        for student in students:
            print(
                f"{student['id']} - "
                f"{student['name']} - "
                f"Roll: {student['roll_number'] or '-'} - "
                f"Class: {student['class_name']}"
            )

        try:
            student_id = int(
                input("\nStudent ID select karein: ").strip()
            )
        except ValueError:
            print("Invalid Student ID.")
            return

        student = conn.execute(
            "SELECT id FROM students WHERE id = ?",
            (student_id,)
        ).fetchone()

        if not student:
            print("Student ID nahi mila.")
            return

    password_hash = generate_password_hash(password)

    try:
        conn.execute("""
            INSERT INTO users
            (username, password_hash, role, student_id)
            VALUES (?, ?, ?, ?)
        """, (
            username,
            password_hash,
            role,
            student_id
        ))

        conn.commit()

        print("\n✅ User successfully created!")
        print("Username:", username)
        print("Role:", role)

        if role == "student":
            print("Student ID:", student_id)

    except sqlite3.IntegrityError:
        print("\n❌ Ye username already exist karta hai.")


conn = sqlite3.connect(DATABASE)
conn.row_factory = sqlite3.Row

create_users_table(conn)
create_user(conn)

conn.close()