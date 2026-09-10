from functools import wraps
from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
import csv
import io
import os

import mysql.connector
from dotenv import load_dotenv


load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

if not app.secret_key:
    raise RuntimeError("SECRET_KEY is missing from the .env file")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)


def get_database_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        port=int(os.getenv("DB_PORT", "3306")),
    )


def get_available_categories(cursor, user_id):
    # Keep the shared catalog intact; removal is a preference for one account.
    cursor.execute(
        """
        SELECT categories.id, categories.name
        FROM categories
        WHERE NOT EXISTS (
            SELECT 1 FROM user_hidden_categories
            WHERE user_hidden_categories.category_id = categories.id
              AND user_hidden_categories.user_id = %s
        )
        ORDER BY categories.name
        """,
        (user_id,),
    )
    return cursor.fetchall()


def login_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view_function(*args, **kwargs)

    return wrapped_view


def safe_csv_value(value):
    text = str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


@app.route("/")
def landing():
    return render_template("welcome.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("home"))

    error = ""

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email or not password or not confirm_password:
            error = "All fields are required."
        elif len(password) < 8:
            error = "Password must contain at least 8 characters."
        elif password != confirm_password:
            error = "Passwords do not match."
        else:
            connection = get_database_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute(
                "SELECT id FROM users WHERE email = %s",
                (email,),
            )
            existing_user = cursor.fetchone()

            if existing_user:
                error = "An account with this email already exists."
            else:
                hashed_password = generate_password_hash(password)
                cursor.execute(
                    """
                    INSERT INTO users (name, email, password)
                    VALUES (%s, %s, %s)
                    """,
                    (name, email, hashed_password),
                )
                connection.commit()
                cursor.close()
                connection.close()
                return redirect(url_for("login", registered="1"))

            cursor.close()
            connection.close()

    return render_template("register.html", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("home"))

    error = ""
    success = (
        "Account created successfully! Please login."
        if request.args.get("registered") == "1"
        else ""
    )

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        connection = get_database_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM users WHERE email = %s",
            (email,),
        )
        user = cursor.fetchone()
        cursor.close()
        connection.close()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            return redirect(url_for("home"))

        error = "Invalid email address or password."

    return render_template("login.html", error=error, success=success)


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/dashboard", methods=["GET", "POST"])
@login_required
def home():
    message = ""
    user_id = session["user_id"]
    connection = get_database_connection()
    cursor = connection.cursor(dictionary=True)
    categories = get_available_categories(cursor, user_id)
    available_names = {category["name"] for category in categories}

    if request.method == "POST":
        category = request.form.get("category", "").strip()
        subject = request.form.get("subject", "").strip()
        minutes_text = request.form.get("minutes", "").strip()
        study_date = request.form.get("study_date", "").strip()

        if category in available_names and subject and minutes_text.isdigit() and study_date:
            minutes = int(minutes_text)
            if minutes > 0:
                cursor.execute(
                    """
                    INSERT INTO study_records
                        (user_id, category, subject, minutes, study_date)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (user_id, category, subject, minutes, study_date),
                )
                connection.commit()
                cursor.close()
                connection.close()
                return redirect(url_for("home", saved="1"))

        message = "Please enter valid activity details."

    if request.args.get("saved") == "1":
        message = "Activity saved successfully!"

    selected_category = request.args.get("filter_category", "").strip()
    selected_date = request.args.get("filter_date", "").strip()

    cursor.execute(
        """
        SELECT * FROM study_records
        WHERE user_id = %s
        ORDER BY study_date DESC, id DESC
        """,
        (user_id,),
    )
    all_records = cursor.fetchall()

    total_sessions = len(all_records)
    total_minutes = sum(record["minutes"] for record in all_records)
    total_hours = round(total_minutes / 60, 1)

    history_sql = """
        SELECT * FROM study_records
        WHERE user_id = %s
    """
    history_values = [user_id]

    if selected_category:
        history_sql += " AND category = %s"
        history_values.append(selected_category)

    if selected_date:
        history_sql += " AND study_date = %s"
        history_values.append(selected_date)

    history_sql += " ORDER BY study_date DESC, id DESC"
    cursor.execute(history_sql, tuple(history_values))
    records = cursor.fetchall()

    cursor.execute(
        """
        SELECT
            COUNT(*) AS today_activities,
            COALESCE(SUM(minutes), 0) AS today_minutes
        FROM study_records
        WHERE user_id = %s AND study_date = CURDATE()
        """,
        (user_id,),
    )
    today_summary = cursor.fetchone()
    today_activities = int(today_summary["today_activities"])
    today_minutes = int(today_summary["today_minutes"])

    cursor.execute(
        """
        SELECT study_date, SUM(minutes) AS daily_minutes
        FROM study_records
        WHERE user_id = %s
        GROUP BY study_date
        ORDER BY study_date
        """,
        (user_id,),
    )
    daily_records = cursor.fetchall()
    chart_labels = [
        record["study_date"].strftime("%d %b")
        for record in daily_records
    ]
    chart_data = [int(record["daily_minutes"]) for record in daily_records]

    cursor.execute(
        """
        SELECT category, SUM(minutes) AS category_minutes
        FROM study_records
        WHERE user_id = %s
        GROUP BY category
        ORDER BY category_minutes DESC
        """,
        (user_id,),
    )
    category_records = cursor.fetchall()
    category_labels = [record["category"] for record in category_records]
    category_data = [
        int(record["category_minutes"])
        for record in category_records
    ]

    # Removed categories must remain usable when filtering existing history.
    history_names = {record["category"] for record in all_records}
    filter_categories = [
        {"name": name}
        for name in sorted(available_names | history_names, key=str.casefold)
    ]
    cursor.close()
    connection.close()

    return render_template(
        "index.html",
        message=message,
        records=records,
        categories=categories,
        filter_categories=filter_categories,
        total_sessions=total_sessions,
        total_minutes=total_minutes,
        total_hours=total_hours,
        today_activities=today_activities,
        today_minutes=today_minutes,
        chart_labels=chart_labels,
        chart_data=chart_data,
        category_labels=category_labels,
        category_data=category_data,
        selected_category=selected_category,
        selected_date=selected_date,
        user_name=session.get("user_name", "User"),
    )


@app.route("/edit/<int:record_id>", methods=["GET", "POST"])
@login_required
def edit_record(record_id):
    user_id = session["user_id"]
    connection = get_database_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM study_records WHERE id = %s AND user_id = %s",
        (record_id, user_id),
    )
    record = cursor.fetchone()

    if record is None:
        cursor.close()
        connection.close()
        return redirect(url_for("home"))

    categories = get_available_categories(cursor, user_id)
    available_names = {category["name"] for category in categories}
    # Editing an old activity must not silently replace its removed category.
    if record["category"] not in available_names:
        categories.append({"name": record["category"]})
        available_names.add(record["category"])

    if request.method == "POST":
        category = request.form.get("category", "").strip()
        subject = request.form.get("subject", "").strip()
        minutes_text = request.form.get("minutes", "").strip()
        study_date = request.form.get("study_date", "").strip()

        if category in available_names and subject and minutes_text.isdigit() and study_date:
            minutes = int(minutes_text)
            if minutes > 0:
                cursor.execute(
                    """
                    UPDATE study_records
                    SET category = %s, subject = %s,
                        minutes = %s, study_date = %s
                    WHERE id = %s AND user_id = %s
                    """,
                    (
                        category,
                        subject,
                        minutes,
                        study_date,
                        record_id,
                        user_id,
                    ),
                )
                connection.commit()
                cursor.close()
                connection.close()
                return redirect(url_for("home"))

    cursor.close()
    connection.close()
    return render_template("edit.html", record=record, categories=categories)


@app.route("/delete/<int:record_id>", methods=["POST"])
@login_required
def delete_record(record_id):
    connection = get_database_connection()
    cursor = connection.cursor()
    cursor.execute(
        "DELETE FROM study_records WHERE id = %s AND user_id = %s",
        (record_id, session["user_id"]),
    )
    connection.commit()
    cursor.close()
    connection.close()
    return redirect(url_for("home"))


@app.route("/categories", methods=["GET", "POST"])
@login_required
def manage_categories():
    connection = get_database_connection()
    cursor = connection.cursor(dictionary=True)

    if request.method == "POST":
        category_name = request.form.get("name", "").strip()
        if category_name and len(category_name) <= 50:
            cursor.execute(
                "SELECT id FROM categories WHERE name = %s",
                (category_name,),
            )
            existing_category = cursor.fetchone()
            if existing_category is None:
                cursor.execute(
                    "INSERT INTO categories (name) VALUES (%s)",
                    (category_name,),
                )
            else:
                # Adding the same name restores this account's removed choice.
                cursor.execute(
                    """
                    DELETE FROM user_hidden_categories
                    WHERE user_id = %s AND category_id = %s
                    """,
                    (session["user_id"], existing_category["id"]),
                )
            connection.commit()
            flash("Category is available in your list.", "success")
        else:
            flash("Enter a category name with 1 to 50 characters.", "error")

        cursor.close()
        connection.close()
        return redirect(url_for("manage_categories"))

    categories = get_available_categories(cursor, session["user_id"])
    cursor.close()
    connection.close()
    return render_template("categories.html", categories=categories)


@app.route("/categories/edit/<int:category_id>", methods=["GET", "POST"])
@login_required
def edit_category(category_id):
    connection = get_database_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT * FROM categories
        WHERE id = %s AND NOT EXISTS (
            SELECT 1 FROM user_hidden_categories
            WHERE user_hidden_categories.category_id = categories.id
              AND user_hidden_categories.user_id = %s
        )
        """,
        (category_id, session["user_id"]),
    )
    category = cursor.fetchone()

    if category is None:
        cursor.close()
        connection.close()
        return redirect(url_for("manage_categories"))

    if request.method == "POST":
        new_name = request.form.get("name", "").strip()
        old_name = category["name"]

        if new_name:
            cursor.execute(
                """
                SELECT id FROM categories
                WHERE name = %s AND id != %s
                """,
                (new_name, category_id),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    "UPDATE categories SET name = %s WHERE id = %s",
                    (new_name, category_id),
                )
                cursor.execute(
                    """
                    UPDATE study_records
                    SET category = %s
                    WHERE category = %s
                    """,
                    (new_name, old_name),
                )
                connection.commit()

        cursor.close()
        connection.close()
        return redirect(url_for("manage_categories"))

    cursor.close()
    connection.close()
    return render_template("edit_category.html", category=category)


@app.route("/categories/delete/<int:category_id>", methods=["POST"])
@login_required
def delete_category(category_id):
    connection = get_database_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        "SELECT name FROM categories WHERE id = %s",
        (category_id,),
    )
    category = cursor.fetchone()

    if category:
        cursor.execute(
            """
            INSERT IGNORE INTO user_hidden_categories (user_id, category_id)
            VALUES (%s, %s)
            """,
            (session["user_id"], category_id),
        )
        connection.commit()
        flash("Category removed from your list. Existing activities were kept.", "success")
    else:
        flash("This category is no longer available.", "error")

    cursor.close()
    connection.close()
    return redirect(url_for("manage_categories"))


@app.route("/export")
@login_required
def export_csv():
    user_id = session["user_id"]
    selected_category = request.args.get("filter_category", "").strip()
    selected_date = request.args.get("filter_date", "").strip()

    export_sql = """
        SELECT * FROM study_records
        WHERE user_id = %s
    """
    export_values = [user_id]

    if selected_category:
        export_sql += " AND category = %s"
        export_values.append(selected_category)

    if selected_date:
        export_sql += " AND study_date = %s"
        export_values.append(selected_date)

    export_sql += " ORDER BY study_date DESC, id DESC"

    connection = get_database_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(export_sql, tuple(export_values))
    records = cursor.fetchall()
    cursor.close()
    connection.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Category", "Activity", "Duration (Minutes)", "Date"])

    for record in records:
        writer.writerow(
            [
                record["id"],
                safe_csv_value(record["category"]),
                safe_csv_value(record["subject"]),
                record["minutes"],
                record["study_date"].isoformat(),
            ]
        )

    csv_data = "\ufeff" + output.getvalue()
    return Response(
        csv_data,
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition":
                "attachment; filename=activity_report.csv"
        },
    )


if __name__ == "__main__":
    app.run(debug=True)
