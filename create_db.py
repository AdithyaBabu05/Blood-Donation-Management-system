
import sqlite3
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "bdms.db")
def init_db():
    db = sqlite3.connect(DATABASE)
    cur = db.cursor()

    cur.execute('''
    CREATE TABLE IF NOT EXISTS Donors (
        name TEXT NOT NULL,
        blood_type TEXT NOT NULL,
        contact TEXT NOT NULL,
        last_donation_date TEXT,
        city TEXT,
        PRIMARY KEY (name, contact)
    )
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS Hospitals (
        name TEXT NOT NULL,
        city TEXT,
        contact TEXT NOT NULL,
        PRIMARY KEY (name, contact)
    )
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS Blood_Banks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        city TEXT,
        contact TEXT
    )
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS Blood_Requests (
        request_id INTEGER PRIMARY KEY AUTOINCREMENT,
        hospital_name TEXT NOT NULL,
        hospital_city TEXT,
        hospital_contact TEXT NOT NULL,
        blood_type TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        request_date TEXT,
        status TEXT,
        FOREIGN KEY (hospital_name, hospital_contact) REFERENCES Hospitals(name, contact)
    )
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS Donations (
        donation_id INTEGER PRIMARY KEY AUTOINCREMENT,
        donor_name TEXT NOT NULL,
        donor_contact TEXT NOT NULL,
        bank_id INTEGER,
        donation_date TEXT NOT NULL,
        blood_type TEXT NOT NULL,
        units INTEGER NOT NULL,
        FOREIGN KEY(donor_name, donor_contact) REFERENCES Donors(name, contact),
        FOREIGN KEY(bank_id) REFERENCES Blood_Banks(id)
    )
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS blood_stock (
        blood_type TEXT PRIMARY KEY NOT NULL,
        total_units INTEGER NOT NULL DEFAULT 0
    )
    ''')

    # Pre-populate blood_stock
    for bt in ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]:
        cur.execute("INSERT OR IGNORE INTO blood_stock (blood_type, total_units) VALUES (?, ?)", (bt, 0))

    db.commit()
    db.close()
    print("✅ Database initialized successfully!")

# Run DB init before starting Flask
init_db()

