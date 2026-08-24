import os

import mysql.connector
from dotenv import load_dotenv


load_dotenv()


def get_database_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        port=int(os.getenv("DB_PORT", "3306"))
    )


connection = get_database_connection()
cursor = connection.cursor()


cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        email VARCHAR(150) NOT NULL UNIQUE,
        password VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")


cursor.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(50) NOT NULL UNIQUE
    )
""")


cursor.execute("""
    CREATE TABLE IF NOT EXISTS study_records (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        category VARCHAR(50) NOT NULL,
        subject VARCHAR(100) NOT NULL,
        minutes INT NOT NULL,
        study_date DATE NOT NULL,

        CONSTRAINT fk_study_records_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
    )
""")


default_categories = [
    ("College Study",),
    ("DSA",),
    ("Project Work",),
    ("English Practice",),
    ("Gym",),
    ("Other",)
]


cursor.executemany(
    "INSERT IGNORE INTO categories (name) VALUES (%s)",
    default_categories
)


connection.commit()
cursor.close()
connection.close()

print("Database tables initialized successfully.")