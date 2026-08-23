# Student Activity Tracker

A Flask and MySQL web application for recording daily activities, monitoring productivity, managing categories, viewing progress charts, and exporting reports.

## Features

- Add, edit and delete activities
- Create, rename and delete custom categories
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
CREATE DATABASE study_tracker;

USE study_tracker;

CREATE TABLE study_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    category VARCHAR(50) NOT NULL DEFAULT 'Study',
    subject VARCHAR(100) NOT NULL,
    minutes INT NOT NULL,
    study_date DATE NOT NULL
);

CREATE TABLE categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE
);
```

### 3. Create `.env`

```env
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=study_tracker
```

Never upload the real `.env` file.

### 4. Run the application

```bash
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## Author

Dhiraj Verma