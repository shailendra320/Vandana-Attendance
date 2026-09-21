from flask import (
    Flask,
    render_template,
    request,
    redirect,
    Response,
    session,
    url_for
)

import sqlite3
from datetime import date
import csv
import io
import os
from functools import wraps
from werkzeug.security import check_password_hash
from datetime import datetime

# =====================================================
# FLASK APP
# =====================================================

app = Flask(__name__)

DATABASE = "database.db"


# =====================================================
# SECURITY / SESSION
# =====================================================

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "CHANGE_THIS_SECRET_KEY_FOR_VANDANA_ATTENDANCE"
)

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


# =====================================================
# ADMIN AUTHENTICATION
# =====================================================

def admin_required(view_func):

    @wraps(view_func)
    def wrapped_view(*args, **kwargs):

        if not session.get("admin_logged_in"):
            return redirect(
                url_for(
                    "login",
                    next=request.path
                )
            )

        return view_func(*args, **kwargs)

    return wrapped_view


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


    # -------------------------------------------------
    # STUDENTS TABLE
    # -------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            class_name TEXT NOT NULL,

            roll_number TEXT,

            guardian_name TEXT,

            guardian_phone TEXT,

            section TEXT

        )
    """)


    # -------------------------------------------------
    # OLD DATABASE MIGRATION
    # -------------------------------------------------

    columns = [

        row[1]

        for row in cursor.execute(
            "PRAGMA table_info(students)"
        ).fetchall()

    ]


    if "guardian_name" not in columns:

        cursor.execute("""
            ALTER TABLE students
            ADD COLUMN guardian_name TEXT
        """)


    if "guardian_phone" not in columns:

        cursor.execute("""
            ALTER TABLE students
            ADD COLUMN guardian_phone TEXT
        """)


    if "section" not in columns:

        cursor.execute("""
            ALTER TABLE students
            ADD COLUMN section TEXT
        """)


    # -------------------------------------------------
    # ATTENDANCE TABLE
    # -------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            student_id INTEGER NOT NULL,

            attendance_date TEXT NOT NULL,

            status TEXT NOT NULL,

            FOREIGN KEY (student_id)
            REFERENCES students(id)

        )
    """)


    # -------------------------------------------------
    # ADMINS TABLE
    # -------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admins (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT UNIQUE NOT NULL,

            password_hash TEXT NOT NULL

        )
    """)


    conn.commit()

    conn.close()


# =====================================================
# ADMIN LOGIN
# =====================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )


        conn = get_db_connection()

        admin = conn.execute("""
            SELECT *
            FROM admins
            WHERE username = ?
        """, (
            username,
        )).fetchone()

        conn.close()


        if admin and check_password_hash(
            admin["password_hash"],
            password
        ):

            session.clear()

            session["admin_logged_in"] = True

            session["admin_username"] = username


            next_page = request.args.get(
                "next"
            )


            if next_page and next_page.startswith("/"):
                return redirect(next_page)


            return redirect(
                url_for("home")
            )


        return render_template(
            "login.html",
            error="Username ya password galat hai."
        )


    return render_template(
        "login.html"
    )


# =====================================================
# ADMIN LOGOUT
# =====================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("home")
    )


# =====================================================
# DASHBOARD
# =====================================================
@app.route("/dashboard")
def dashboard():
    conn = get_db_connection()

    total_students = conn.execute(
        "SELECT COUNT(*) FROM students"
    ).fetchone()[0]

    today = datetime.now().strftime("%Y-%m-%d")

    present_today = conn.execute(
        "SELECT COUNT(*) FROM attendance WHERE date = ? AND status = 'Present'",
        (today,)
    ).fetchone()[0]

    absent_today = conn.execute(
        "SELECT COUNT(*) FROM attendance WHERE date = ? AND status = 'Absent'",
        (today,)
    ).fetchone()[0]

    total_today = present_today + absent_today

    if total_today > 0:
        attendance_percentage = round(
            (present_today / total_today) * 100, 1
        )
    else:
        attendance_percentage = 0

    recent_attendance = conn.execute("""
        SELECT attendance.date, students.name, attendance.status
        FROM attendance
        JOIN students ON students.id = attendance.student_id
        ORDER BY attendance.id DESC
        LIMIT 10
    """).fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        total_students=total_students,
        present_today=present_today,
        absent_today=absent_today,
        attendance_percentage=attendance_percentage,
        recent_attendance=recent_attendance
    )
@app.route("/")
def home():

    today = date.today().isoformat()

    conn = get_db_connection()


    # -------------------------------------------------
    # TOTAL STUDENTS
    # -------------------------------------------------

    total_students = conn.execute("""
        SELECT COUNT(*) AS count
        FROM students
    """).fetchone()["count"]


    # -------------------------------------------------
    # TODAY PRESENT
    # -------------------------------------------------

    present_today = conn.execute("""
        SELECT COUNT(*) AS count
        FROM attendance
        WHERE attendance_date = ?
        AND status = 'Present'
    """, (
        today,
    )).fetchone()["count"]


    # -------------------------------------------------
    # TODAY ABSENT
    # -------------------------------------------------

    absent_today = conn.execute("""
        SELECT COUNT(*) AS count
        FROM attendance
        WHERE attendance_date = ?
        AND status = 'Absent'
    """, (
        today,
    )).fetchone()["count"]


    # -------------------------------------------------
    # TODAY ATTENDANCE PERCENTAGE
    # -------------------------------------------------

    total_today = present_today + absent_today

    if total_today > 0:

        attendance_percentage = round(
            (present_today / total_today) * 100,
            2
        )

    else:

        attendance_percentage = 0


    # -------------------------------------------------
    # CLASS-WISE ATTENDANCE
    # -------------------------------------------------

    class_data = conn.execute("""
        SELECT

            students.class_name,

            COUNT(attendance.id) AS total,

            SUM(
                CASE
                    WHEN attendance.status = 'Present'
                    THEN 1
                    ELSE 0
                END
            ) AS present

        FROM students

        LEFT JOIN attendance

        ON students.id = attendance.student_id

        AND attendance.attendance_date = ?

        GROUP BY students.class_name

        ORDER BY students.class_name

    """, (
        today,
    )).fetchall()


    class_attendance = []


    for row in class_data:

        total = row["total"] or 0

        present = row["present"] or 0


        if total > 0:

            percentage = round(
                (present / total) * 100,
                2
            )

        else:

            percentage = 0


        class_attendance.append({

            "class_name":
                row["class_name"],

            "total":
                total,

            "present":
                present,

            "absent":
                total - present,

            "percentage":
                percentage

        })


    # -------------------------------------------------
    # RECENT ATTENDANCE
    # -------------------------------------------------

    recent_attendance = conn.execute("""
        SELECT

            students.name,

            students.class_name,

            students.roll_number,

            attendance.attendance_date,

            attendance.status

        FROM attendance

        JOIN students

        ON students.id = attendance.student_id

        ORDER BY attendance.id DESC

        LIMIT 10

    """).fetchall()


    conn.close()


    return render_template(

        "index.html",

        total_students=total_students,

        present_today=present_today,

        absent_today=absent_today,

        attendance_percentage=
            attendance_percentage,

        class_attendance=
            class_attendance,

        recent_attendance=
            recent_attendance,

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


    # -------------------------------------------------
    # SEARCH
    # -------------------------------------------------

    if search:

        query += """
            AND (

                name LIKE ?

                OR roll_number LIKE ?

                OR guardian_name LIKE ?

                OR guardian_phone LIKE ?

                OR section LIKE ?

            )
        """


        search_value = f"%{search}%"


        params.extend([

            search_value,

            search_value,

            search_value,

            search_value,

            search_value

        ])


    # -------------------------------------------------
    # CLASS FILTER
    # -------------------------------------------------

    if selected_class:

        query += """
            AND class_name = ?
        """

        params.append(
            selected_class
        )


    # -------------------------------------------------
    # ORDER
    # -------------------------------------------------

    query += """
        ORDER BY

            class_name,

            roll_number,

            name
    """


    students = conn.execute(
        query,
        params
    ).fetchall()


    # -------------------------------------------------
    # CLASSES
    # -------------------------------------------------

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
# ADD STUDENT - ADMIN ONLY
# =====================================================

@app.route(
    "/add_student",
    methods=["POST"]
)
@admin_required
def add_student():

    name = request.form.get(
        "name",
        ""
    ).strip()


    class_name = request.form.get(
        "class_name",
        ""
    ).strip()


    roll_number = request.form.get(
        "roll_number",
        ""
    ).strip()


    guardian_name = request.form.get(
        "guardian_name",
        ""
    ).strip()


    guardian_phone = request.form.get(
        "guardian_phone",
        ""
    ).strip()


    section = request.form.get(
        "section",
        ""
    ).strip()


    if not name or not class_name:

        return redirect(
            "/students"
        )


    conn = get_db_connection()


    conn.execute("""
        INSERT INTO students

        (

            name,

            class_name,

            roll_number,

            guardian_name,

            guardian_phone,

            section

        )

        VALUES (?, ?, ?, ?, ?, ?)

    """, (

        name,

        class_name,

        roll_number,

        guardian_name,

        guardian_phone,

        section

    ))


    conn.commit()

    conn.close()


    return redirect(
        "/students"
    )


# =====================================================
# EDIT STUDENT - ADMIN ONLY
# =====================================================

@app.route(
    "/edit_student/<int:student_id>",
    methods=["GET", "POST"]
)
@admin_required
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


    # -------------------------------------------------
    # UPDATE STUDENT
    # -------------------------------------------------

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()


        class_name = request.form.get(
            "class_name",
            ""
        ).strip()


        roll_number = request.form.get(
            "roll_number",
            ""
        ).strip()


        guardian_name = request.form.get(
            "guardian_name",
            ""
        ).strip()


        guardian_phone = request.form.get(
            "guardian_phone",
            ""
        ).strip()


        section = request.form.get(
            "section",
            ""
        ).strip()


        if not name or not class_name:

            conn.close()

            return (
                "Name and Class are required"
            )


        conn.execute("""
            UPDATE students

            SET

                name = ?,

                class_name = ?,

                roll_number = ?,

                guardian_name = ?,

                guardian_phone = ?,

                section = ?

            WHERE id = ?

        """, (

            name,

            class_name,

            roll_number,

            guardian_name,

            guardian_phone,

            section,

            student_id

        ))


        conn.commit()

        conn.close()


        return redirect(
            "/students"
        )


    conn.close()


    return render_template(

        "edit_student.html",

        student=student

    )


# =====================================================
# DELETE STUDENT - ADMIN ONLY
# =====================================================

@app.route(
    "/delete_student/<int:student_id>"
)
@admin_required
def delete_student(student_id):

    conn = get_db_connection()


    # Student ki attendance bhi delete hogi

    conn.execute("""
        DELETE FROM attendance

        WHERE student_id = ?

    """, (
        student_id,
    ))


    conn.execute("""
        DELETE FROM students

        WHERE id = ?

    """, (
        student_id,
    ))


    conn.commit()

    conn.close()


    return redirect(
        "/students"
    )


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

        ORDER BY

            class_name,

            roll_number,

            name

    """).fetchall()


    attendance_records = conn.execute("""
        SELECT

            student_id,

            status

        FROM attendance

        WHERE attendance_date = ?

    """, (
        selected_date,
    )).fetchall()


    conn.close()


    attendance_dict = {

        record["student_id"]:
            record["status"]

        for record in attendance_records

    }


    return render_template(

        "attendance.html",

        students=students,

        selected_date=selected_date,

        attendance_dict=attendance_dict

    )


# =====================================================
# SAVE ATTENDANCE - ADMIN ONLY
# =====================================================

@app.route(
    "/save_attendance",
    methods=["POST"]
)
@admin_required
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

    selected_month = request.args.get(
        "month",
        ""
    ).strip()


    conn = get_db_connection()


    students = conn.execute("""
        SELECT *

        FROM students

        ORDER BY

            class_name,

            roll_number,

            name

    """).fetchall()


    report_data = []


    for student in students:


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

            "id":
                student["id"],

            "name":
                student["name"],

            "class_name":
                student["class_name"],

            "roll_number":
                student["roll_number"],

            "total":
                total,

            "present":
                present,

            "absent":
                absent,

            "percentage":
                percentage

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


    if not student:

        conn.close()

        return "Student not found"


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


    total = len(
        attendance_records
    )


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

        attendance_records=
            attendance_records,

        total=total,

        present=present,

        absent=absent,

        percentage=percentage

    )


# =====================================================
# STUDENT PROFILE
# =====================================================

@app.route(
    "/student_profile/<int:student_id>"
)
def student_profile(student_id):

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


    total = conn.execute("""
        SELECT COUNT(*)

        FROM attendance

        WHERE student_id = ?

    """, (
        student_id,
    )).fetchone()[0]


    present = conn.execute("""
        SELECT COUNT(*)

        FROM attendance

        WHERE student_id = ?

        AND status = 'Present'

    """, (
        student_id,
    )).fetchone()[0]


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

        "student_profile.html",

        student=student,

        total=total,

        present=present,

        absent=absent,

        percentage=percentage

    )


# =====================================================
# CSV EXPORT
# =====================================================

@app.route("/export_csv")
@admin_required
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

            students.guardian_name,

            students.guardian_phone,

            students.section,

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


    output = io.StringIO()


    writer = csv.writer(
        output
    )


    # -------------------------------------------------
    # CSV HEADER
    # -------------------------------------------------

    writer.writerow([

        "Roll Number",

        "Student Name",

        "Class",

        "Section",

        "Guardian Name",

        "Guardian Phone",

        "Date",

        "Status"

    ])


    # -------------------------------------------------
    # CSV DATA
    # -------------------------------------------------

    for record in records:

        writer.writerow([

            record["roll_number"],

            record["name"],

            record["class_name"],

            record["section"],

            record["guardian_name"],

            record["guardian_phone"],

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