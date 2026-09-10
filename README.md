# Student Activity Tracker

A Flask and MySQL web application for recording daily activities, monitoring productivity, managing categories, viewing progress charts, and exporting reports.

## Features

- Add, edit and delete activities
- Create and rename categories; remove default or custom categories from your own list while keeping saved activities
- Filter activities by category and date
- Overall and daily productivity summary
- Daily progress line chart
- Category-wise bar chart
- Export filtered records as CSV
- Responsive professional interface
- Permanent MySQL storage

## Technologies

- Python
- Flask
- MySQL
- HTML
- CSS
- Jinja
- Chart.js

## Project Structure

```text
student-study-tracker/
├── app.py
├── requirements.txt
├── README.md
├── .env
├── .gitignore
├── static/
│   └── style.css
└── templates/
    ├── index.html
    ├── edit.html
    ├── categories.html
    └── edit_category.html
```

## Installation

### 1. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 2. Create the MySQL database

```sql
CREATE DATABASE IF NOT EXISTS study_tracker;
```

### 3. Create `.env`

```env
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=study_tracker
DB_PORT=3306
SECRET_KEY=replace_with_a_generated_secret
```

Generate a secret with `python -c "import secrets; print(secrets.token_hex(32))"`
and put it in your local `.env` file.

Never upload the real `.env` file.

### 4. Initialize the database and run the application

```bash
python init_db.py
python app.py
```

`init_db.py` creates the required tables and initial categories. Run it before
starting the app after pulling this update. It adds `user_hidden_categories`
without deleting existing users or activities. On Railway, keep
`python init_db.py` as the pre-deploy command.

Removing a category affects only that account's available category list.
Its saved activities remain in history, charts, filters and CSV exports.
An existing activity can keep its original category when edited. Adding the
same category name restores it to your list. Running initialization again
preserves removed choices. Category creation and renaming still use the
existing shared catalog.

Open:

```text
http://127.0.0.1:5000
```

## Category regression checks

```bash
python -m unittest discover -s tests -v
```

These checks use disposable SQLite data through a small adapter for the MySQL
connection. They exercise the Flask category, history and activity routes;
they do not connect to or verify a production MySQL database.

## Author

Dhiraj Verma
