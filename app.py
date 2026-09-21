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
# DATABASE CONNECTION
# =====================================================

def get_db_connection():

    conn = sqlite3.connect(DATABASE)

    conn.row_factory = sqlite3.Row

    return conn


# =====================================================
# LOGIN REQUIRED
# =====================================================

def login_required(view_func):

    @wraps(view_func)
    def wrapped_view(*args, **kwargs):

        if not session.get("user_id"):

            return redirect(
                url_for(
                    "login",
                    next=request.path
                )
            )

        return view_func(*args, **kwargs)

    return wrapped_view


# =====================================================
# ROLE REQUIRED
# =====================================================

def role_required(*allowed_roles):

    def decorator(view_func):

        @wraps(view_func)
        def wrapped_view(*args, **kwargs):

            if not session.get("user_id"):

                return redirect(
                    url_for(
                        "login",
                        next=request.path
                    )
                )

            user_role = session.get("role")

            if user_role not in allowed_roles:

                return """
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Access Denied</title>
                    <meta name="viewport"
                          content="width=device-width, initial-scale=1.0">
                    <style>
                        body {
                            font-family: Arial;
                            background: #f4f6f8;
                            text-align: center;
                            padding: 60px 20px;
                        }

                        .box {
                            background: white;
                            max-width: 500px;
                            margin: auto;
                            padding: 35px;
                            border-radius: 15px;
                            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
                        }

                        a {
                            display: inline-block;
                            margin-top: 20px;
                            padding: 12px 20px;
                            background: #2563eb;
                            color: white;
                            text-decoration: none;
                            border-radius: 8px;
                        }
                    </style>
                </head>

                <body>

                    <div class="box">

                        <h1>🚫 Access Denied</h1>

                        <p>
                            Aapko is page ki permission nahi hai.
                        </p>

                        <a href="/dashboard">
                            Go to Dashboard
                        </a>

                    </div>

                </body>
                </html>
                """, 403

            return view_func(*args, **kwargs)

        return wrapped_view

    return decorator


# =====================================================
# ROLE SHORTCUTS
# =====================================================

def hod_required(view_func):
    return role_required("hod")(view_func)


def teacher_or_hod_required(view_func):
    return role_required(
        "hod",
        "teacher"
    )(view_func)


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
    # OLD ADMINS TABLE
    # -------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admins (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT UNIQUE NOT NULL,

            password_hash TEXT NOT NULL

        )
    """)


    # -------------------------------------------------
    # USERS TABLE
    # -------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT UNIQUE NOT NULL,

            password_hash TEXT NOT NULL,

            role TEXT NOT NULL
                CHECK(role IN ('hod', 'teacher', 'student')),

            student_id INTEGER,

            FOREIGN KEY(student_id)
            REFERENCES students(id)

        )
    """)


    # -------------------------------------------------
    # MIGRATE OLD ADMIN ACCOUNTS TO HOD
    # -------------------------------------------------

    old_admins = cursor.execute("""
        SELECT
            username,
            password_hash
        FROM admins
    """).fetchall()


    for admin in old_admins:

        existing_user = cursor.execute("""
            SELECT id
            FROM users
            WHERE username = ?
        """, (
            admin[0],
        )).fetchone()


        if not existing_user:

            cursor.execute("""
                INSERT INTO users
                (
                    username,
                    password_hash,
                    role,
                    student_id
                )
                VALUES (?, ?, 'hod', NULL)
            """, (
                admin[0],
                admin[1]
            ))


    conn.commit()

    conn.close()


# =====================================================
# LOGIN
# =====================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
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


        user = conn.execute("""
            SELECT
                id,
                username,
                password_hash,
                role,
                student_id
            FROM users
            WHERE username = ?
        """, (
            username,
        )).fetchone()


        conn.close()


        if user and check_password_hash(
            user["password_hash"],
            password
        ):

            session.clear()

            session["user_id"] = user["id"]

            session["username"] = user["username"]

            session["role"] = user["role"]

            session["student_id"] = user["student_id"]


            # -----------------------------------------
            # HOD
            # -----------------------------------------

            if user["role"] == "hod":

                return redirect(
                    url_for("dashboard")
                )


            # -----------------------------------------
            # TEACHER
            # -----------------------------------------

            if user["role"] == "teacher":

                return redirect(
                    url_for("dashboard")
                )


            # -----------------------------------------
            # STUDENT
            # -----------------------------------------

            if user["role"] == "student":

                return redirect(
                    url_for("student_portal")
                )


        return render_template(
            "login.html",
            error="Username ya password galat hai."
        )


    return render_template(
        "login.html"
    )


# =====================================================
# LOGOUT
# =====================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# =====================================================
# DASHBOARD
# HOD + TEACHER
# =====================================================

@app.route("/dashboard")
@teacher_or_hod_required
def dashboard():

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
    # TODAY PERCENTAGE
    # -------------------------------------------------

    total_today = (
        present_today +
        absent_today
    )


    if total_today > 0:

        attendance_percentage = round(
            (present_today / total_today) * 100,
            2
        )

    else:

        attendance_percentage = 0


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
        "dashboard.html",

        total_students=total_students,

        present_today=present_today,

        absent_today=absent_today,

        attendance_percentage=
            attendance_percentage,

        recent_attendance=
            recent_attendance
    )


# =====================================================
# HOME
# =====================================================

@app.route("/")
def home():

    # Student ko public dashboard nahi dikhana
    if session.get("role") == "student":

        return redirect(
            url_for("student_portal")
        )


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


    total_today = (
        present_today +
        absent_today
    )


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
# HOD + TEACHER
# =====================================================

@app.route("/students")
@teacher_or_hod_required
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


    students_list = conn.execute(
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

        students=students_list,

        classes=classes,

        search=search,

        selected_class=
            selected_class
    )


# =====================================================
# ADD STUDENT
# HOD ONLY
# =====================================================

@app.route(
    "/add_student",
    methods=["POST"]
)
@hod_required
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
# EDIT STUDENT
# HOD ONLY
# =====================================================

@app.route(
    "/edit_student/<int:student_id>",
    methods=["GET", "POST"]
)
@hod_required
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
    # UPDATE
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

            return "Name and Class are required"


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
# DELETE STUDENT
# HOD ONLY
# =====================================================

@app.route(
    "/delete_student/<int:student_id>"
)
@hod_required
def delete_student(student_id):

    conn = get_db_connection()


    # Student ki attendance delete hogi
    conn.execute("""
        DELETE FROM attendance
        WHERE student_id = ?
    """, (
        student_id,
    ))


    # Student delete
    conn.execute("""
        DELETE FROM students
        WHERE id = ?
    """, (
        student_id,
    ))


    # Student login bhi delete
    conn.execute("""
        DELETE FROM users
        WHERE student_id = ?
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
# HOD + TEACHER
# =====================================================

@app.route("/attendance")
@teacher_or_hod_required
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

        attendance_dict=
            attendance_dict
    )


# =====================================================
# SAVE ATTENDANCE
# HOD + TEACHER
# =====================================================

@app.route(
    "/save_attendance",
    methods=["POST"]
)
@teacher_or_hod_required
def save_attendance():

    attendance_date = request.form.get(
        "attendance_date",
        ""
    )


    if not attendance_date:

        return redirect(
            "/attendance"
        )


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


        # Only valid status allowed
        if status not in [
            "Present",
            "Absent"
        ]:

            status = "Absent"


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
# HOD + TEACHER
# =====================================================

@app.route("/reports")
@teacher_or_hod_required
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

        selected_month=
            selected_month
    )


# =====================================================
# INDIVIDUAL STUDENT REPORT
# HOD + TEACHER
# STUDENT = OWN ONLY
# =====================================================

@app.route(
    "/student_report/<int:student_id>"
)
@login_required
def student_report(student_id):

    user_role = session.get("role")

    user_student_id = session.get(
        "student_id"
    )


    # Student sirf apna report dekh sakta hai
    if user_role == "student":

        if user_student_id != student_id:

            return """
            <h2 style="text-align:center;margin-top:50px;">
                🚫 Access Denied
            </h2>
            """, 403


    # Teacher/HOD allowed
    elif user_role not in [
        "hod",
        "teacher"
    ]:

        return "Access Denied", 403


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

        return "Student not found", 404


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
# HOD + TEACHER
# STUDENT = OWN ONLY
# =====================================================

@app.route(
    "/student_profile/<int:student_id>"
)
@login_required
def student_profile(student_id):

    user_role = session.get("role")

    user_student_id = session.get(
        "student_id"
    )


    # Student sirf apni profile
    if user_role == "student":

        if user_student_id != student_id:

            return """
            <h2 style="text-align:center;margin-top:50px;">
                🚫 Access Denied
            </h2>
            """, 403


    # Teacher/HOD
    elif user_role not in [
        "hod",
        "teacher"
    ]:

        return "Access Denied", 403


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

        return "Student not found", 404


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
# STUDENT PORTAL
# STUDENT ONLY
# =====================================================

@app.route("/student_portal")
@role_required("student")
def student_portal():

    student_id = session.get(
        "student_id"
    )


    if not student_id:

        return """
        <h2 style="text-align:center;margin-top:50px;">
            Student account kisi student se linked nahi hai.
        </h2>
        """, 400


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

        return "Student record nahi mila.", 404


    attendance = conn.execute("""
        SELECT
            attendance_date,
            status

        FROM attendance

        WHERE student_id = ?

        ORDER BY attendance_date DESC
    """, (
        student_id,
    )).fetchall()


    total_days = len(
        attendance
    )


    present_days = sum(

        1

        for row in attendance

        if row["status"] == "Present"

    )


    absent_days = sum(

        1

        for row in attendance

        if row["status"] == "Absent"

    )


    if total_days > 0:

        percentage = round(
            (present_days / total_days) * 100,
            2
        )

    else:

        percentage = 0


    conn.close()


    return render_template(

        "student_portal.html",

        student=student,

        attendance=attendance,

        total_days=total_days,

        present_days=present_days,

        absent_days=absent_days,

        percentage=percentage

    )


# =====================================================
# CSV EXPORT
# HOD ONLY
# =====================================================

@app.route("/export_csv")
@hod_required
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


    writer.writerow([

        "Roll Number",

        "Student Name",

        "Class",

        "Guardian Name",

        "Guardian Phone",

        "Section",

        "Date",

        "Status"

    ])


    for record in records:

        writer.writerow([

            record["roll_number"],

            record["name"],

            record["class_name"],

            record["guardian_name"],

            record["guardian_phone"],

            record["section"],

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