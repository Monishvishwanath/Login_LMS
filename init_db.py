import sqlite3

conn = sqlite3.connect("lms_database.db")
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL
)
''')

cursor.execute("INSERT OR IGNORE INTO users (username, password, name, role) VALUES ('admin', 'admin123', 'Manager Admin', 'manager')")
cursor.execute("INSERT OR IGNORE INTO users (username, password, name, role) VALUES ('john', 'john123', 'John Doe', 'employee')")

cursor.execute('''
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT,
    phone TEXT,
    owner TEXT,
    stage TEXT,
    campaign TEXT,
    date TEXT
)
''')

conn.commit()
conn.close()

print("Database initialized successfully!")