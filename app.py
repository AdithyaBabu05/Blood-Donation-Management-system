from flask import Flask, render_template, request, redirect, url_for, flash, g
import sqlite3
from datetime import datetime

# --- Configuration ---
DATABASE = "bdms.db"
SECRET_KEY = "dev-secret-key"  # change in production

app = Flask(__name__)
app.config.from_mapping(
    SECRET_KEY=SECRET_KEY,
    DATABASE=DATABASE
)

# --- Database helpers ---
def get_db():
    if 'db' not in g:
        conn = sqlite3.connect(app.config['DATABASE'])
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def db_init():
    db = get_db()
    cur = db.cursor()
    # donors: id, name, blood_type, contact, last_donation_date, city
    cur.execute("""
    CREATE TABLE IF NOT EXISTS donors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        blood_type TEXT NOT NULL,
        contact TEXT,
        last_donation_date TEXT,
        city TEXT
    );
    """)
    # donations: id, donor_id, donation_date, blood_type, units, bank_id
    cur.execute("""
    CREATE TABLE IF NOT EXISTS donations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        donor_id INTEGER,
        donation_date TEXT NOT NULL,
        blood_type TEXT NOT NULL,
        units INTEGER NOT NULL,
        bank_id INTEGER,
        FOREIGN KEY(donor_id) REFERENCES donors(id)
    );
    """)
    # blood_stock: blood_type PRIMARY KEY, total_units
    cur.execute("""
    CREATE TABLE IF NOT EXISTS blood_stock (
        blood_type TEXT PRIMARY KEY,
        total_units INTEGER NOT NULL DEFAULT 0
    );
    """)
    # blood_banks: id, name, location
    cur.execute("""
    CREATE TABLE IF NOT EXISTS blood_banks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        location TEXT
    );
    """)
    # requests: id, requester_name, blood_type, units, city, contact, status, created_at
    cur.execute("""
    CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        requester_name TEXT,
        blood_type TEXT,
        units INTEGER,
        city TEXT,
        contact TEXT,
        status TEXT DEFAULT 'Pending',
        created_at TEXT
    );
    """)
    db.commit()

# initialize DB on startup
with app.app_context():
    db_init()

# --- Utility functions ---
def update_stock_add(blood_type, units):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT total_units FROM blood_stock WHERE blood_type = ?", (blood_type,))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE blood_stock SET total_units = total_units + ? WHERE blood_type = ?", (units, blood_type))
    else:
        cur.execute("INSERT INTO blood_stock (blood_type, total_units) VALUES (?, ?)", (blood_type, units))
    db.commit()

def update_stock_subtract(blood_type, units):
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE blood_stock SET total_units = CASE WHEN total_units - ? >= 0 THEN total_units - ? ELSE 0 END WHERE blood_type = ?", (units, units, blood_type))
    db.commit()

# --- Routes ---
@app.route("/")
def home():
    return render_template("home.html")
# Register donor
@app.route("/donor/register", methods=["GET", "POST"])
def register_donor():
    if request.method == "POST":
        name = request.form.get("name").strip()
        blood_type = request.form.get("blood_type").strip().upper()
        contact = request.form.get("contact").strip()
        last_donation = request.form.get("last_donation_date") or None
        city = request.form.get("city").strip()
        db = get_db()
        cur = db.cursor()
        cur.execute(
            "INSERT INTO donors (name, blood_type, contact, last_donation_date, city) VALUES (?, ?, ?, ?, ?)",
            (name, blood_type, contact, last_donation, city)
        )
        db.commit()
        flash("Donor registered successfully!", "success")
        return redirect(url_for("home"))
    return render_template("register_donor.html")



# Update donor profile
@app.route("/donor/update", methods=["POST"])
def update_donor_post():
    db = get_db()
    cur = db.cursor()
    donor_id = request.form.get("donor_id")
    if not donor_id:
        flash("Donor ID is required.", "error")
        return redirect(url_for("update_profile"))  # if you keep a GET view for the page

    try:
        donor_id = int(donor_id)
    except ValueError:
        flash("Donor ID must be a number.", "error")
        return redirect(url_for("update_profile"))

    # fetch donor to ensure exists
    cur.execute("SELECT * FROM donors WHERE id = ?", (donor_id,))
    donor = cur.fetchone()
    if donor is None:
        flash(f"No donor found with ID {donor_id}.", "error")
        return redirect(url_for("update_profile"))

    # fields (optional)
    contact = request.form.get("contact", "").strip() or None
    city = request.form.get("city", "").strip() or None
    last_donation_date = request.form.get("last_donation_date") or None

    # Build dynamic update only for provided fields
    updates = []
    params = []
    if contact is not None:
        updates.append("contact = ?")
        params.append(contact)
    if city is not None:
        updates.append("city = ?")
        params.append(city)
    if last_donation_date:
        # optionally validate date format here
        updates.append("last_donation_date = ?")
        params.append(last_donation_date)

    if not updates:
        flash("No changes provided. Update cancelled.", "error")
        return redirect(url_for("update_profile"))

    # finalize and execute
    sql = f"UPDATE donors SET {', '.join(updates)} WHERE id = ?"
    params.append(donor_id)
    cur.execute(sql, tuple(params))
    db.commit()

    flash("Donor profile updated successfully.", "success")
    # optionally redirect to donor history or profile page
    return redirect(url_for("donor_history", donor_id=donor_id))

# View donation history for a donor
@app.route("/donor/<int:donor_id>/history")
def donor_history(donor_id):
    db = get_db()
    cur = db.cursor()

    # fetch donor
    cur.execute("SELECT * FROM donors WHERE id = ?", (donor_id,))
    donor = cur.fetchone()
    if donor is None:
        flash(f"No donor found with ID {donor_id}.", "danger")
        return redirect(url_for("home"))

    # fetch donations with optional bank name (left join)
    cur.execute("""
        SELECT d.id AS donation_id,
               d.donation_date,
               d.blood_type,
               d.units,
               COALESCE(b.name, '') AS bank_name
        FROM donations d
        LEFT JOIN blood_banks b ON d.bank_id = b.id
        WHERE d.donor_id = ?
        ORDER BY d.donation_date DESC
    """, (donor_id,))
    donations = cur.fetchall()

    # pass donor and donations to template
    # donor is sqlite3.Row so you can access donor['name'], donor['city'], etc.
    return render_template(
        "view_donation_history.html",
        donor=donor,
        donations=donations
    )


# Record donation
@app.route("/donation/record", methods=["GET", "POST"])
def record_donation():
    db = get_db()
    cur = db.cursor()
    if request.method == "POST":
        donor_id = request.form.get("donor_id")
        bank_id = request.form.get("bank_id") or None
        donation_date = request.form.get("donation_date") or datetime.utcnow().date().isoformat()
        units = int(request.form.get("quantity"))
        # look up donor blood type if donor_id provided
        blood_type = request.form.get("blood_type")
        if not blood_type and donor_id:
            # try to find donor blood type
            cur.execute("SELECT blood_type FROM donors WHERE id = ?", (donor_id,))
            row = cur.fetchone()
            blood_type = row["blood_type"] if row else None
        if blood_type is None:
            flash("Blood type not provided and donor not found.", "danger")
            return redirect(url_for("record_donation"))
        # insert
        cur.execute("""
            INSERT INTO donations (donor_id, donation_date, blood_type, units, bank_id)
            VALUES (?, ?, ?, ?, ?)
        """, (donor_id, donation_date, blood_type, units, bank_id))
        # update donor last donation date
        if donor_id:
            cur.execute("UPDATE donors SET last_donation_date = ? WHERE id = ?", (donation_date, donor_id))
        # update stock
        update_stock_add(blood_type.upper(), units)
        db.commit()
        flash("Donation recorded and stock updated.", "success")
        return redirect(url_for("home"))
       # GET: show form with banks
    cur.execute("SELECT * FROM blood_banks")
    banks = cur.fetchall()
    default_date = datetime.utcnow().date().isoformat()
    return render_template("record_donation.html", banks=banks, default_date=default_date)


# Manage stock (add manual adjustments)
@app.route("/stock/manage", methods=["GET", "POST"])
def manage_stock():
    db = get_db()
    cur = db.cursor()
    if request.method == "POST":
        blood_type = request.form.get("blood_type").strip().upper()
        units = int(request.form.get("quantity"))
        donor_name = request.form.get("donor_name")  # optional
        donation_date = request.form.get("donation_date") or datetime.utcnow().date().isoformat()
        bank = request.form.get("blood_bank")
        if not blood_type and donor_name:
            cur.execute("SELECT blood_type FROM donors WHERE name = ?", (donor_name,))
            row = cur.fetchone()
            blood_type = row["blood_type"] if row else None
        # Insert directly into Donations table
        cur.execute("""
        INSERT INTO donations (donor_id, bank_id, donation_date, blood_type, units)
        VALUES (
        (SELECT donor_id FROM donors WHERE name = ? LIMIT 1),
        (SELECT bank_id FROM blood_banks WHERE name = ? LIMIT 1),
        ?, ?, ?
    )
""", (donor_name, bank, donation_date, blood_type, units))



        db.commit()
        flash("Stock updated successfully.", "success")
        return redirect(url_for("home"))

    # GET:
    return render_template("manage_stock.html")


# Stock report
@app.route("/stock/report")
def stock_report():
    db = get_db()
    cur = db.cursor()

    # Calculate total stock by blood type from Donations table
    cur.execute("""
      SELECT d.blood_type, IFNULL(SUM(d.units), 0) AS total_units
      FROM donations d
      GROUP BY d.blood_type
      ORDER BY d.blood_type
    """)
    report = cur.fetchall()

    return render_template("stock_report.html", stock_report=report)

# Search eligible donors
@app.route("/donors/search", methods=["GET", "POST"])
def search_eligible_donors():
    db = get_db()
    cur = db.cursor()
    results = []
    if request.method == "POST":
        blood_type = request.form.get("blood_type").strip().upper()
        city = request.form.get("city").strip()
        
        # Query donors matching blood_type and city
        cur.execute("""
            SELECT * FROM donors WHERE blood_type = ? AND city = ?
        """, (blood_type, city))
        results = cur.fetchall()

        if not results:
            flash("No eligible donors found for the selected criteria.", "warning")
    
    return render_template("search_eligible_donors.html", eligible_donors=results)


# Submit blood request
@app.route("/requests/submit", methods=["GET", "POST"])
def submit_blood_request():
    db = get_db()
    cur = db.cursor()
    if request.method == "POST":
        requester_name = request.form.get("requester_name")
        blood_type = request.form.get("blood_type").strip().upper()
        units = int(request.form.get("units"))
        city = request.form.get("city")
        contact = request.form.get("contact")
        created_at = datetime.utcnow().isoformat()
        cur.execute("""
            INSERT INTO requests (requester_name, blood_type, units, city, contact, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (requester_name, blood_type, units, city, contact, created_at))
        db.commit()
        flash("Request submitted.", "success")
        return redirect(url_for("home"))
    return render_template("submit_blood.html")

@app.route("/requests/view")
def view_requests():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM requests ORDER BY created_at DESC")
    rows = cur.fetchall()
    return render_template("view_requests.html", requests=rows)

# Simple route to add a blood bank (admin)
@app.route("/banks/add", methods=["GET", "POST"])
def add_bank():
    if request.method == "POST":
        name = request.form.get("name")
        location = request.form.get("location")
        db = get_db()
        cur = db.cursor()
        cur.execute("INSERT INTO blood_banks (name, location) VALUES (?, ?)", (name, location))
        db.commit()
        flash("Bank added.", "success")
        return redirect(url_for("home"))
    return render_template("add_bank.html")

# Run app
if __name__ == "__main__":
    app.run(debug=True)
