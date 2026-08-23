from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    Response
)

import mysql.connector
import os
import csv
import io

from dotenv import load_dotenv


load_dotenv()

app = Flask(__name__)


def get_database_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )


def safe_csv_value(value):
    text = str(value)

    if text.startswith(("=", "+", "-", "@")):
        return "'" + text

    return text


# Home dashboard

@app.route("/", methods=["GET", "POST"])
def home():
    message = ""

    connection = get_database_connection()
    cursor = connection.cursor(dictionary=True)

    # Add activity

    if request.method == "POST":
        category = request.form["category"]
        subject = request.form["subject"].strip()
        minutes = int(request.form["minutes"])
        study_date = request.form["study_date"]

        cursor.execute("""
            INSERT INTO study_records
            (category, subject, minutes, study_date)
            VALUES (%s, %s, %s, %s)
        """, (
            category,
            subject,
            minutes,
            study_date
        ))

        connection.commit()
        message = "Activity saved successfully!"

    # Read filters

    selected_category = request.args.get(
        "filter_category",
        ""
    ).strip()

    selected_date = request.args.get(
        "filter_date",
        ""
    ).strip()

    # Overall totals

    cursor.execute("""
        SELECT *
        FROM study_records
        ORDER BY study_date DESC, id DESC
    """)

    all_records = cursor.fetchall()

    total_sessions = len(all_records)

    total_minutes = sum(
        record["minutes"] for record in all_records
    )

    total_hours = round(total_minutes / 60, 1)

    # Filtered history

    history_sql = """
        SELECT *
        FROM study_records
        WHERE 1 = 1
    """

    history_values = []

    if selected_category:
        history_sql += " AND category = %s"
        history_values.append(selected_category)

    if selected_date:
        history_sql += " AND study_date = %s"
        history_values.append(selected_date)

    history_sql += " ORDER BY study_date DESC, id DESC"

    cursor.execute(
        history_sql,
        tuple(history_values)
    )

    records = cursor.fetchall()

    # Today's summary

    cursor.execute("""
        SELECT
            COUNT(*) AS today_activities,
            COALESCE(SUM(minutes), 0) AS today_minutes
        FROM study_records
        WHERE study_date = CURDATE()
    """)

    today_summary = cursor.fetchone()

    today_activities = int(
        today_summary["today_activities"]
    )

    today_minutes = int(
        today_summary["today_minutes"]
    )

    # Daily line graph

    cursor.execute("""
        SELECT
            study_date,
            SUM(minutes) AS daily_minutes
        FROM study_records
        GROUP BY study_date
        ORDER BY study_date
    """)

    daily_records = cursor.fetchall()

    chart_labels = [
        record["study_date"].strftime("%d %b")
        for record in daily_records
    ]

    chart_data = [
        int(record["daily_minutes"])
        for record in daily_records
    ]

    # Category bar graph

    cursor.execute("""
        SELECT
            category,
            SUM(minutes) AS category_minutes
        FROM study_records
        GROUP BY category
        ORDER BY category_minutes DESC
    """)

    category_records = cursor.fetchall()

    category_labels = [
        record["category"]
        for record in category_records
    ]

    category_data = [
        int(record["category_minutes"])
        for record in category_records
    ]

    # Dynamic categories

    cursor.execute("""
        SELECT *
        FROM categories
        ORDER BY name
    """)

    categories = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "index.html",
        message=message,
        records=records,
        categories=categories,
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
        selected_date=selected_date
    )


# Edit activity

@app.route("/edit/<int:record_id>", methods=["GET", "POST"])
def edit_record(record_id):
    connection = get_database_connection()
    cursor = connection.cursor(dictionary=True)

    if request.method == "POST":
        category = request.form["category"]
        subject = request.form["subject"].strip()
        minutes = int(request.form["minutes"])
        study_date = request.form["study_date"]

        cursor.execute("""
            UPDATE study_records
            SET
                category = %s,
                subject = %s,
                minutes = %s,
                study_date = %s
            WHERE id = %s
        """, (
            category,
            subject,
            minutes,
            study_date,
            record_id
        ))

        connection.commit()
        cursor.close()
        connection.close()

        return redirect(url_for("home"))

    cursor.execute(
        "SELECT * FROM study_records WHERE id = %s",
        (record_id,)
    )

    record = cursor.fetchone()

    cursor.execute("""
        SELECT *
        FROM categories
        ORDER BY name
    """)

    categories = cursor.fetchall()

    cursor.close()
    connection.close()

    if record is None:
        return redirect(url_for("home"))

    return render_template(
        "edit.html",
        record=record,
        categories=categories
    )


# Delete activity

@app.route("/delete/<int:record_id>", methods=["POST"])
def delete_record(record_id):
    connection = get_database_connection()
    cursor = connection.cursor()

    cursor.execute(
        "DELETE FROM study_records WHERE id = %s",
        (record_id,)
    )

    connection.commit()
    cursor.close()
    connection.close()

    return redirect(url_for("home"))


# Add and view categories

@app.route("/categories", methods=["GET", "POST"])
def manage_categories():
    connection = get_database_connection()
    cursor = connection.cursor(dictionary=True)

    if request.method == "POST":
        category_name = request.form["name"].strip()

        if category_name:
            cursor.execute(
                "SELECT id FROM categories WHERE name = %s",
                (category_name,)
            )

            existing_category = cursor.fetchone()

            if existing_category is None:
                cursor.execute(
                    "INSERT INTO categories (name) VALUES (%s)",
                    (category_name,)
                )

                connection.commit()

        cursor.close()
        connection.close()

        return redirect(url_for("manage_categories"))

    cursor.execute("""
        SELECT *
        FROM categories
        ORDER BY name
    """)

    categories = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "categories.html",
        categories=categories
    )


# Edit category

@app.route(
    "/categories/edit/<int:category_id>",
    methods=["GET", "POST"]
)
def edit_category(category_id):
    connection = get_database_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM categories WHERE id = %s",
        (category_id,)
    )

    category = cursor.fetchone()

    if category is None:
        cursor.close()
        connection.close()

        return redirect(url_for("manage_categories"))

    if request.method == "POST":
        new_name = request.form["name"].strip()
        old_name = category["name"]

        if new_name:
            cursor.execute("""
                SELECT id
                FROM categories
                WHERE name = %s
                AND id != %s
            """, (
                new_name,
                category_id
            ))

            duplicate = cursor.fetchone()

            if duplicate is None:
                cursor.execute("""
                    UPDATE categories
                    SET name = %s
                    WHERE id = %s
                """, (
                    new_name,
                    category_id
                ))

                cursor.execute("""
                    UPDATE study_records
                    SET category = %s
                    WHERE category = %s
                """, (
                    new_name,
                    old_name
                ))

                connection.commit()

        cursor.close()
        connection.close()

        return redirect(url_for("manage_categories"))

    cursor.close()
    connection.close()

    return render_template(
        "edit_category.html",
        category=category
    )


# Delete category

@app.route(
    "/categories/delete/<int:category_id>",
    methods=["POST"]
)
def delete_category(category_id):
    connection = get_database_connection()
    cursor = connection.cursor()

    cursor.execute(
        "DELETE FROM categories WHERE id = %s",
        (category_id,)
    )

    connection.commit()
    cursor.close()
    connection.close()

    return redirect(url_for("manage_categories"))


# Export CSV report

@app.route("/export")
def export_csv():
    selected_category = request.args.get(
        "filter_category",
        ""
    ).strip()

    selected_date = request.args.get(
        "filter_date",
        ""
    ).strip()

    connection = get_database_connection()
    cursor = connection.cursor(dictionary=True)

    export_sql = """
        SELECT *
        FROM study_records
        WHERE 1 = 1
    """

    export_values = []

    if selected_category:
        export_sql += " AND category = %s"
        export_values.append(selected_category)

    if selected_date:
        export_sql += " AND study_date = %s"
        export_values.append(selected_date)

    export_sql += " ORDER BY study_date DESC, id DESC"

    cursor.execute(
        export_sql,
        tuple(export_values)
    )

    records = cursor.fetchall()

    cursor.close()
    connection.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "ID",
        "Category",
        "Activity",
        "Duration (Minutes)",
        "Date"
    ])

    for record in records:
        writer.writerow([
            record["id"],
            safe_csv_value(record["category"]),
            safe_csv_value(record["subject"]),
            record["minutes"],
            record["study_date"].isoformat()
        ])

    csv_data = "\ufeff" + output.getvalue()

    return Response(
        csv_data,
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition":
                "attachment; filename=activity_report.csv"
        }
    )


if __name__ == "__main__":
    app.run(debug=True)