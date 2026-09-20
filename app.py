from flask import Flask, render_template, request, redirect, Response
import sqlite3
from datetime import date
import csv
import io

app = Flask(__name__)

DATABASE = "database.db"


# =====================================================
# DATABASE CONNECTION
# =====================================================

def get_db_connection():

    conn = sqlite3.connect(DATABASE)

    conn.row_factory = sqlite3.Row

    return conn


# =====================================================
# INITIALIZE DATABASE
# =====================================================

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

    search = request.args.get(
        "search",
        ""
    ).strip()

    selected_class = request.args.get(
        "class_name",
        ""
    ).strip()

    conn = get_db_connection()

    query = """
        SELECT *
        FROM students
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


# =====================================================
# ADD STUDENT
# =====================================================

@app.route(
    "/add_student",
    methods=["POST"]
)
def add_student():

    name = request.form["name"].strip()

    class_name = request.form["class_name"].strip()

    roll_number = request.form["roll_number"].strip()

    if not name or not class_name:

        return redirect("/students")

    conn = get_db_connection()

    conn.execute("""
        INSERT INTO students
        (
            name,
            class_name,
            roll_number
        )

        VALUES (?, ?, ?)
    """, (
        name,
        class_name,
        roll_number
    ))

    conn.commit()

    conn.close()

    return redirect("/students")


# =====================================================
# EDIT STUDENT
# =====================================================

@app.route(
    "/edit_student/<int:student_id>",
    methods=["GET", "POST"]
)
def edit_student(student_id):

    conn = get_db_connection()

    student = conn.execute("""
        SELECT *
        FROM students
        WHERE id = ?
    """, (
        student_id,
    )).fetchone()

    if not student:

        conn.close()

        return "Student not found"

    # -----------------------------
    # UPDATE STUDENT
    # -----------------------------

    if request.method == "POST":

        name = request.form["name"].strip()

        class_name = request.form["class_name"].strip()

        roll_number = request.form["roll_number"].strip()

        if not name or not class_name:

            conn.close()

            return "Name and Class are required"

        conn.execute("""
            UPDATE students

            SET
                name = ?,
                class_name = ?,
                roll_number = ?

            WHERE id = ?
        """, (
            name,
            class_name,
            roll_number,
            student_id
        ))

        conn.commit()

        conn.close()

        return redirect("/students")

    conn.close()

    return render_template(
        "edit_student.html",
        student=student
    )


# =====================================================
# DELETE STUDENT
# =====================================================

@app.route(
    "/delete_student/<int:student_id>"
)
def delete_student(student_id):

    conn = get_db_connection()

    # Student ki attendance bhi delete hogi

    conn.execute(
        """
        DELETE FROM attendance
        WHERE student_id = ?
        """,
        (student_id,)
    )

    conn.execute(
        """
        DELETE FROM students
        WHERE id = ?
        """,
        (student_id,)
    )

    conn.commit()

    conn.close()

    return redirect("/students")


# =====================================================
# DAILY ATTENDANCE
# =====================================================

@app.route("/attendance")
def attendance():

    selected_date = request.args.get(
        "date",
        date.today().isoformat()
    )

    conn = get_db_connection()

    students = conn.execute("""
        SELECT *
        FROM students
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


# =====================================================
# SAVE ATTENDANCE
# =====================================================

@app.route(
    "/save_attendance",
    methods=["POST"]
)
def save_attendance():

    attendance_date = request.form[
        "attendance_date"
    ]

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
                (
                    student_id,
                    attendance_date,
                    status
                )

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

    # Month filter
    # Example: 2026-09

    selected_month = request.args.get(
        "month",
        ""
    ).strip()

    conn = get_db_connection()

    students = conn.execute("""
        SELECT *
        FROM students
        ORDER BY class_name, roll_number, name
    """).fetchall()

    report_data = []

    for student in students:

        # -----------------------------------------
        # MONTH FILTER
        # -----------------------------------------

        if selected_month:

            total = conn.execute("""
                SELECT COUNT(*)

                FROM attendance

                WHERE student_id = ?

                AND attendance_date LIKE ?
            """, (
                student["id"],
                f"{selected_month}%"
            )).fetchone()[0]

            present = conn.execute("""
                SELECT COUNT(*)

                FROM attendance

                WHERE student_id = ?

                AND status = 'Present'

                AND attendance_date LIKE ?
            """, (
                student["id"],
                f"{selected_month}%"
            )).fetchone()[0]

        else:

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

        if total > 0:

            percentage = round(
                (present / total) * 100,
                2
            )

        else:

            percentage = 0

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

        reports=report_data,

        selected_month=selected_month
    )


# =====================================================
# INDIVIDUAL STUDENT REPORT
# =====================================================

@app.route(
    "/student_report/<int:student_id>"
)
def student_report(student_id):

    conn = get_db_connection()

    student = conn.execute("""
        SELECT *
        FROM students
        WHERE id = ?
    """, (
        student_id,
    )).fetchone()

    attendance_records = conn.execute("""
        SELECT
            attendance_date,
            status

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

    if total > 0:

        percentage = round(
            (present / total) * 100,
            2
        )

    else:

        percentage = 0

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


# =====================================================
# CSV EXPORT
# =====================================================

@app.route("/export_csv")
def export_csv():

    selected_month = request.args.get(
        "month",
        ""
    ).strip()

    conn = get_db_connection()

    query = """
        SELECT
            students.roll_number,
            students.name,
            students.class_name,
            attendance.attendance_date,
            attendance.status

        FROM attendance

        JOIN students
        ON students.id = attendance.student_id
    """

    params = []

    if selected_month:

        query += """
            WHERE attendance.attendance_date LIKE ?
        """

        params.append(
            f"{selected_month}%"
        )

    query += """
        ORDER BY
            attendance.attendance_date DESC,
            students.class_name,
            students.roll_number
    """

    records = conn.execute(
        query,
        params
    ).fetchall()

    conn.close()

    # CSV file memory mein create hoga

    output = io.StringIO()

    writer = csv.writer(output)

    # Header

    writer.writerow([
        "Roll Number",
        "Student Name",
        "Class",
        "Date",
        "Status"
    ])

    # Data

    for record in records:

        writer.writerow([
            record["roll_number"],
            record["name"],
            record["class_name"],
            record["attendance_date"],
            record["status"]
        ])

    csv_data = output.getvalue()

    output.close()

    if selected_month:

        filename = (
            f"attendance_{selected_month}.csv"
        )

    else:

        filename = "attendance_all.csv"

    return Response(

        csv_data,

        mimetype="text/csv",

        headers={
            "Content-Disposition":
            f"attachment; filename={filename}"
        }

    )


# =====================================================
# RUN APPLICATION
# =====================================================

if __name__ == "__main__":

    init_database()

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )