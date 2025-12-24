from flask import Flask, render_template, request, redirect, url_for, flash, g
import sqlite3
from datetime import datetime

# --- Configuration ---
DATABASE = "bdms.db"
SECRET_KEY = "dev-secret-key"

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
    db = get_db()
    cur = db.cursor()
    if request.method == "POST":
        name = request.form.get("name").strip()
        blood_type = request.form.get("blood_type").strip().upper()
        contact = request.form.get("contact").strip()
        last_donation = request.form.get("last_donation_date") or None
        city = request.form.get("city").strip()

        cur.execute("SELECT * FROM Donors WHERE name = ? AND contact = ?", (name, contact))
        if cur.fetchone():
            flash("Donor already registered!", "error")
            return redirect(url_for("register_donor"))

        cur.execute(
            "INSERT INTO Donors (name, blood_type, contact, last_donation_date, city) VALUES (?, ?, ?, ?, ?)",
            (name, blood_type, contact, last_donation, city)
        )
        db.commit()
        flash("Donor registered successfully!", "success")
        return redirect(url_for("home"))

    return render_template("register_donor.html")

# Update donor
@app.route("/donor/update", methods=["GET", "POST"])
def update_donor():
    db = get_db()
    cur = db.cursor()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        contact = request.form.get("contact", "").strip()
        city = request.form.get("city", "").strip() or None
        last_donation_date = request.form.get("last_donation_date") or None

        if not name or not contact:
            flash("Both Name and Contact are required.", "error")
            return redirect(url_for("update_donor"))

        cur.execute("SELECT * FROM Donors WHERE name=? AND contact=?", (name, contact))
        donor = cur.fetchone()
        if not donor:
            flash("Donor not found.", "error")
            return redirect(url_for("update_donor"))

        updates = []
        params = []
        if city:
            updates.append("city=?")
            params.append(city)
        if last_donation_date:
            updates.append("last_donation_date=?")
            params.append(last_donation_date)

        if updates:
            sql = f"UPDATE Donors SET {', '.join(updates)} WHERE name=? AND contact=?"
            params.extend([name, contact])
            cur.execute(sql, tuple(params))
            db.commit()
            flash("Donor profile updated successfully.", "success")
        else:
            flash("No changes provided.", "error")

    return render_template("update_profile.html")

# View donation history
@app.route("/donor/view", methods=["GET", "POST"])
def view_donations():
    db = get_db()
    cur = db.cursor()
    donor = None
    donations = []

    if request.method == "POST":
        donor_name = request.form.get("donor_name", "").strip()
        donor_contact = request.form.get("donor_contact", "").strip()

        if not donor_name or not donor_contact:
            flash("Both donor name and contact are required.", "danger")
            return redirect(url_for("view_donations"))

        cur.execute("SELECT * FROM Donors WHERE name=? AND contact=?", (donor_name, donor_contact))
        donor = cur.fetchone()

        if donor:
            cur.execute("""
                SELECT d.donation_date, d.blood_type, d.units,
                       b.name AS bank_name, b.city AS bank_city
                FROM Donations d
                LEFT JOIN blood_banks b ON d.bank_id = b.id
                WHERE d.donor_name=? AND d.donor_contact=?
                ORDER BY d.donation_date DESC
            """, (donor_name, donor_contact))
            donations = cur.fetchall()
        else:
            flash("Donor not found.", "danger")

    return render_template("view_donation_history.html", donor=donor, donations=donations)

# Record donation (updated to update stock automatically)
@app.route("/donation/record", methods=["GET", "POST"])
def record_donation():
    db = get_db()
    cur = db.cursor()

    if request.method == "POST":
        donor_name = request.form.get("donor_name").strip()
        donor_contact = request.form.get("donor_contact").strip()
        blood_type = request.form.get("blood_type").strip().upper()
        units = request.form.get("units", "").strip()
        donation_date = request.form.get("donation_date") or datetime.utcnow().date().isoformat()
        bank_id = request.form.get("bank_select")

        if not units.isdigit() or int(units) <= 0:
            flash("Enter a valid number of units.", "danger")
            return redirect(url_for("record_donation"))
        units = int(units)

        # Check donor exists
        cur.execute("SELECT * FROM Donors WHERE name=? AND contact=?", (donor_name, donor_contact))
        if not cur.fetchone():
            flash("Donor not found. Please register first.", "danger")
            return redirect(url_for("register_donor"))

        # Handle new bank creation
        if bank_id == "new":
            new_name = request.form.get("new_bank_name", "").strip()
            new_city = request.form.get("new_bank_city", "").strip()
            if new_name and new_city:
                cur.execute("INSERT INTO blood_banks (name, city) VALUES (?, ?)", (new_name, new_city))
                bank_id = cur.lastrowid
            else:
                bank_id = None

        # Insert donation record
        cur.execute("""
            INSERT INTO Donations (donor_name, donor_contact, bank_id, donation_date, blood_type, units)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (donor_name, donor_contact, bank_id, donation_date, blood_type, units))

        # Update blood stock automatically
        update_stock_add(blood_type, units)

        # Update donor last donation date
        cur.execute("""
            UPDATE Donors SET last_donation_date=? WHERE name=? AND contact=?
        """, (donation_date, donor_name, donor_contact))

        db.commit()
        flash(f"Donation of {units} units of {blood_type} recorded successfully!", "success")
        return redirect(url_for("record_donation"))

    # GET: fetch banks for dropdown
    cur.execute("SELECT id, name, city FROM blood_banks")
    banks = cur.fetchall()
    default_date = datetime.utcnow().date().isoformat()
    return render_template("record_donation.html", banks=banks, default_date=default_date)

# Manage stock manually
@app.route("/stock/manage", methods=["GET", "POST"])
def manage_stock():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS blood_stock (
            blood_type TEXT PRIMARY KEY,
            total_units INTEGER DEFAULT 0
        )
    """)
    db.commit()

    if request.method == "POST":
        blood_type = request.form.get("blood_type").strip().upper()
        units = int(request.form.get("quantity"))
        update_stock_add(blood_type, units)
        flash("Stock updated successfully.", "success")
        return redirect(url_for("stock_report"))

    return render_template("manage_stock.html")

# Stock report
@app.route("/stock/report")
def stock_report():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT blood_type, total_units FROM blood_stock ORDER BY blood_type")
    report = cur.fetchall()
    return render_template("stock_report.html", stock_report=report)

# Search eligible donors
@app.route("/donors/search", methods=["GET", "POST"])
def search_eligible_donors():
    db = get_db()
    cur = db.cursor()
    results = []
    searched = False
    if request.method == "POST":
        searched = True
        blood_type = request.form.get("blood_type", "").strip().upper()
        city = request.form.get("city", "").strip()
        cur.execute("SELECT * FROM Donors WHERE blood_type=? AND city=?", (blood_type, city))
        results = cur.fetchall()
    return render_template("search_eligible_donors.html", eligible_donors=results, searched=searched)

# Submit blood request
@app.route("/requests/submit", methods=["GET", "POST"])
def submit_blood_request():
    db = get_db()
    cur = db.cursor()
    if request.method == "POST":
        hospital_name = request.form.get("hospital_name", "").strip()
        hospital_city = request.form.get("hospital_city", "").strip()
        hospital_contact = request.form.get("hospital_contact", "").strip()
        blood_type = request.form.get("blood_type", "").strip().upper()
        quantity = int(request.form.get("quantity", 0))
        request_date = datetime.utcnow().date().isoformat()
        status = "Pending"

        # Ensure blood_stock exists
        cur.execute("INSERT OR IGNORE INTO blood_stock (blood_type, total_units) VALUES (?, ?)", (blood_type, 0))
        db.commit()

        cur.execute("SELECT total_units FROM blood_stock WHERE blood_type=?", (blood_type,))
        current_stock = cur.fetchone()["total_units"]

        if current_stock >= quantity:
            status = "Accepted"
            update_stock_subtract(blood_type, quantity)
            flash(f"✅ Request accepted! {quantity} units of {blood_type} deducted from stock.", "success")
        else:
            status = "Rejected"
            flash("❌ Request rejected. Insufficient blood stock.", "error")

        cur.execute("""
            INSERT INTO Blood_Requests
            (hospital_name, hospital_city, hospital_contact, blood_type, quantity, request_date, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)        """, (hospital_name, hospital_city, hospital_contact, blood_type, quantity, request_date, status))
        db.commit()
        return redirect(url_for("view_requests"))

    return render_template("submit_blood.html")


# View all blood requests
@app.route("/requests/view")
def view_requests():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM Blood_Requests ORDER BY request_date DESC")
    requests = cur.fetchall()
    return render_template("view_requests.html", requests=requests)


# Add a blood bank (admin)
@app.route("/banks/add", methods=["GET", "POST"])
def add_bank():
    db = get_db()
    cur = db.cursor()
    if request.method == "POST":
        name = request.form.get("name").strip()
        city = request.form.get("city").strip()
        contact = request.form.get("contact").strip() or None

        cur.execute("INSERT INTO blood_banks (name, city, contact) VALUES (?, ?, ?)", (name, city, contact))
        db.commit()
        flash("Blood bank added successfully.", "success")
        return redirect(url_for("home"))

    return render_template("add_bank.html")


# Run the app
if __name__ == "__main__":
    # Ensure stock table exists on startup
    db = sqlite3.connect(DATABASE)
    cur = db.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS blood_stock (
            blood_type TEXT PRIMARY KEY,
            total_units INTEGER DEFAULT 0
        )
    """)
    db.commit()
    db.close()

    app.run(debug=True)

       
