from flask import Flask, render_template, request, redirect
import sqlite3
from datetime import date

app = Flask(__name__)

DATABASE = "database.db"


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            class_name TEXT NOT NULL,
            roll_number TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            attendance_date TEXT NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES students(id)
        )
    """)

    conn.commit()
    conn.close()


# =====================================================
# DASHBOARD
# =====================================================

@app.route("/")
def home():

    today = date.today().isoformat()

    conn = get_db_connection()

    total_students = conn.execute("""
        SELECT COUNT(*) AS count
        FROM students
    """).fetchone()["count"]

    present_today = conn.execute("""
        SELECT COUNT(*) AS count
        FROM attendance
        WHERE attendance_date = ?
        AND status = 'Present'
    """, (today,)).fetchone()["count"]

    absent_today = conn.execute("""
        SELECT COUNT(*) AS count
        FROM attendance
        WHERE attendance_date = ?
        AND status = 'Absent'
    """, (today,)).fetchone()["count"]

    total_today = present_today + absent_today

    if total_today > 0:
        attendance_percentage = round(
            (present_today / total_today) * 100,
            2
        )
    else:
        attendance_percentage = 0

    conn.close()

    return render_template(
        "index.html",
        total_students=total_students,
        present_today=present_today,
        absent_today=absent_today,
        attendance_percentage=attendance_percentage,
        today=today
    )


# =====================================================
# STUDENTS
# =====================================================

@app.route("/students")
def students():

    search = request.args.get("search", "").strip()
    selected_class = request.args.get("class_name", "").strip()

    conn = get_db_connection()

    query = """
        SELECT * FROM students
        WHERE 1=1
    """

    params = []

    if search:

        query += """
            AND (
                name LIKE ?
                OR roll_number LIKE ?
            )
        """

        params.extend([
            f"%{search}%",
            f"%{search}%"
        ])

    if selected_class:

        query += """
            AND class_name = ?
        """

        params.append(selected_class)

    query += """
        ORDER BY class_name, roll_number, name
    """

    students = conn.execute(
        query,
        params
    ).fetchall()

    classes = conn.execute("""
        SELECT DISTINCT class_name
        FROM students
        ORDER BY class_name
    """).fetchall()

    conn.close()

    return render_template(
        "students.html",
        students=students,
        classes=classes,
        search=search,
        selected_class=selected_class
    )


@app.route("/add_student", methods=["POST"])
def add_student():

    name = request.form["name"].strip()
    class_name = request.form["class_name"].strip()
    roll_number = request.form["roll_number"].strip()

    if not name or not class_name:
        return redirect("/students")

    conn = get_db_connection()

    conn.execute("""
        INSERT INTO students
        (name, class_name, roll_number)
        VALUES (?, ?, ?)
    """, (
        name,
        class_name,
        roll_number
    ))

    conn.commit()
    conn.close()

    return redirect("/students")


@app.route("/delete_student/<int:student_id>")
def delete_student(student_id):

    conn = get_db_connection()

    conn.execute(
        "DELETE FROM attendance WHERE student_id = ?",
        (student_id,)
    )

    conn.execute(
        "DELETE FROM students WHERE id = ?",
        (student_id,)
    )

    conn.commit()
    conn.close()

    return redirect("/students")


# =====================================================
# ATTENDANCE
# =====================================================

@app.route("/attendance")
def attendance():

    selected_date = request.args.get(
        "date",
        date.today().isoformat()
    )

    conn = get_db_connection()

    students = conn.execute("""
        SELECT * FROM students
        ORDER BY class_name, roll_number, name
    """).fetchall()

    attendance_records = conn.execute("""
        SELECT student_id, status
        FROM attendance
        WHERE attendance_date = ?
    """, (
        selected_date,
    )).fetchall()

    conn.close()

    attendance_dict = {
        record["student_id"]: record["status"]
        for record in attendance_records
    }

    return render_template(
        "attendance.html",
        students=students,
        selected_date=selected_date,
        attendance_dict=attendance_dict
    )


@app.route("/save_attendance", methods=["POST"])
def save_attendance():

    attendance_date = request.form["attendance_date"]

    conn = get_db_connection()

    students = conn.execute(
        "SELECT id FROM students"
    ).fetchall()

    for student in students:

        student_id = student["id"]

        status = request.form.get(
            f"status_{student_id}",
            "Absent"
        )

        existing = conn.execute("""
            SELECT id
            FROM attendance
            WHERE student_id = ?
            AND attendance_date = ?
        """, (
            student_id,
            attendance_date
        )).fetchone()

        if existing:

            conn.execute("""
                UPDATE attendance
                SET status = ?
                WHERE student_id = ?
                AND attendance_date = ?
            """, (
                status,
                student_id,
                attendance_date
            ))

        else:

            conn.execute("""
                INSERT INTO attendance
                (student_id, attendance_date, status)
                VALUES (?, ?, ?)
            """, (
                student_id,
                attendance_date,
                status
            ))

    conn.commit()
    conn.close()

    return redirect(
        f"/attendance?date={attendance_date}"
    )


# =====================================================
# REPORTS
# =====================================================

@app.route("/reports")
def reports():

    conn = get_db_connection()

    students = conn.execute("""
        SELECT * FROM students
        ORDER BY class_name, roll_number, name
    """).fetchall()

    report_data = []

    for student in students:

        total = conn.execute("""
            SELECT COUNT(*)
            FROM attendance
            WHERE student_id = ?
        """, (
            student["id"],
        )).fetchone()[0]

        present = conn.execute("""
            SELECT COUNT(*)
            FROM attendance
            WHERE student_id = ?
            AND status = 'Present'
        """, (
            student["id"],
        )).fetchone()[0]

        absent = total - present

        percentage = (
            round((present / total) * 100, 2)
            if total > 0
            else 0
        )

        report_data.append({
            "id": student["id"],
            "name": student["name"],
            "class_name": student["class_name"],
            "roll_number": student["roll_number"],
            "total": total,
            "present": present,
            "absent": absent,
            "percentage": percentage
        })

    conn.close()

    return render_template(
        "reports.html",
        reports=report_data
    )


# =====================================================
# INDIVIDUAL REPORT
# =====================================================

@app.route("/student_report/<int:student_id>")
def student_report(student_id):

    conn = get_db_connection()

    student = conn.execute("""
        SELECT * FROM students
        WHERE id = ?
    """, (
        student_id,
    )).fetchone()

    attendance_records = conn.execute("""
        SELECT attendance_date, status
        FROM attendance
        WHERE student_id = ?
        ORDER BY attendance_date DESC
    """, (
        student_id,
    )).fetchall()

    total = len(attendance_records)

    present = sum(
        1
        for record in attendance_records
        if record["status"] == "Present"
    )

    absent = total - present

    percentage = (
        round((present / total) * 100, 2)
        if total > 0
        else 0
    )

    conn.close()

    return render_template(
        "student_report.html",
        student=student,
        attendance_records=attendance_records,
        total=total,
        present=present,
        absent=absent,
        percentage=percentage
    )


if __name__ == "__main__":

    init_database()

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )