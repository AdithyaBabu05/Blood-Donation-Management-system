import sqlite3

# Connect to SQLite database (creates file if it doesn't exist)
conn = sqlite3.connect('bdms.db')
cursor = conn.cursor()

# Create Donors table
cursor.execute('''
CREATE TABLE IF NOT EXISTS Donors (
    donor_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    blood_type TEXT,
    contact TEXT,
    last_donation_date TEXT,
    city TEXT
)
''')

# Create Hospitals table
cursor.execute('''
CREATE TABLE IF NOT EXISTS Hospitals (
    hospital_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    city TEXT,
    contact TEXT
)
''')

# Create Blood Banks table
cursor.execute('''
CREATE TABLE IF NOT EXISTS Blood_Banks (
    bank_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    city TEXT,
    contact TEXT
)
''')

# Create Blood Requests table
cursor.execute('''
CREATE TABLE IF NOT EXISTS Blood_Requests (
    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
    hospital_id INTEGER,
    blood_type TEXT,
    quantity INTEGER,
    request_date TEXT,
    status TEXT
)
''')

# Create Donations table
# Create Donations table (updated)
# Donations table
cursor.execute('''
CREATE TABLE IF NOT EXISTS donations (
    donor_id INTEGER,
    bank_id INTEGER,
    donation_date TEXT,
    blood_type TEXT,
    units INTEGER
)
''')

conn.commit()
conn.close()

print("All tables created successfully in SQLite!")
