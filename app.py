from datetime import datetime, timedelta
import os
import sqlite3
from flask import Flask, flash, redirect, render_template, request, url_for

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "transaction_safety.db")
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-development-key")

# Demonstration rules. These thresholds are prototype assumptions, not bank policy.
AMOUNT_THRESHOLD = 50_000
ODD_HOUR_START = 0   # midnight, inclusive
ODD_HOUR_END = 5     # 5 AM, exclusive
FREQUENCY_WINDOW_MINUTES = 60
FREQUENT_TRANSFER_COUNT = 3
LOW_MAX = 29
MEDIUM_MAX = 59


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            recipient TEXT NOT NULL,
            account_id TEXT,
            amount REAL NOT NULL CHECK(amount > 0),
            location TEXT NOT NULL,
            transaction_time TEXT NOT NULL,
            transaction_type TEXT NOT NULL DEFAULT 'Person-to-person transfer',
            risk_score INTEGER NOT NULL,
            risk_level TEXT NOT NULL,
            decision TEXT NOT NULL,
            explanation TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_transactions_sender_time ON transactions(sender, transaction_time)")


def assess_transaction(sender, recipient, amount, location, transaction_time):
    """Evaluate from the submitted transaction and saved sender history; no risk inputs from the user."""
    score = 0
    reasons = []
    when = datetime.fromisoformat(transaction_time)

    if amount > AMOUNT_THRESHOLD:
        score += 40
        reasons.append("Transfer amount is above ₹50,000 (+40)")

    if ODD_HOUR_START <= when.hour < ODD_HOUR_END:
        score += 20
        reasons.append("Transfer time falls between 12:00 AM and 4:59 AM (+20)")

    with get_db() as conn:
        # Compare this location with this sender's previously saved locations.
        known_locations = conn.execute(
            "SELECT DISTINCT LOWER(TRIM(location)) AS location FROM transactions WHERE LOWER(TRIM(sender)) = LOWER(TRIM(?))",
            (sender,)
        ).fetchall()
        prior_count = conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE LOWER(TRIM(sender)) = LOWER(TRIM(?)) AND transaction_time >= ? AND transaction_time < ?",
            (sender, (when - timedelta(minutes=FREQUENCY_WINDOW_MINUTES)).isoformat(timespec="minutes"), when.isoformat(timespec="minutes"))
        ).fetchone()[0]

    if known_locations and location.strip().casefold() not in {r["location"] for r in known_locations}:
        score += 30
        reasons.append("Location has not appeared in this sender's saved transaction history (+30)")

    if prior_count >= FREQUENT_TRANSFER_COUNT:
        score += 20
        reasons.append(f"Sender has {prior_count} earlier saved transfer(s) in the previous {FREQUENCY_WINDOW_MINUTES} minutes (+20)")

    if score <= LOW_MAX:
        level, decision = "Low", "Approve"
    elif score <= MEDIUM_MAX:
        level, decision = "Medium", "Review"
    else:
        level, decision = "High", "Block"
    explanation = "; ".join(reasons) if reasons else "No configured risk rules were triggered by the available transaction data."
    return score, level, decision, explanation


@app.route("/")
def dashboard():
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        low = conn.execute("SELECT COUNT(*) FROM transactions WHERE risk_level='Low'").fetchone()[0]
        medium = conn.execute("SELECT COUNT(*) FROM transactions WHERE risk_level='Medium'").fetchone()[0]
        high = conn.execute("SELECT COUNT(*) FROM transactions WHERE risk_level='High'").fetchone()[0]
        recent = conn.execute("SELECT * FROM transactions ORDER BY id DESC LIMIT 6").fetchall()
    return render_template("dashboard.html", total=total, low=low, medium=medium, high=high, recent=recent)


@app.route("/evaluate", methods=["GET", "POST"])
def evaluate():
    form = request.form if request.method == "POST" else {}
    if request.method == "POST":
        sender = request.form.get("sender", "").strip()
        recipient = request.form.get("recipient", "").strip()
        amount_raw = request.form.get("amount", "").strip()
        location = request.form.get("location", "").strip()
        transaction_time = request.form.get("transaction_time", "").strip()
        account_id = request.form.get("account_id", "").strip() or None
        if not sender or not recipient:
            flash("Enter both sender and recipient names or IDs.", "error")
            return render_template("evaluate.html", form=form)
        if sender.casefold() == recipient.casefold():
            flash("Sender and recipient must be different.", "error")
            return render_template("evaluate.html", form=form)
        try:
            amount = float(amount_raw)
            if amount <= 0 or amount != amount or amount == float("inf"):
                raise ValueError
        except ValueError:
            flash("Enter a valid transfer amount greater than zero.", "error")
            return render_template("evaluate.html", form=form)
        if not location or not transaction_time:
            flash("Location and transaction date/time are required.", "error")
            return render_template("evaluate.html", form=form)
        try:
            parsed_time = datetime.fromisoformat(transaction_time)
            transaction_time = parsed_time.isoformat(timespec="minutes")
        except ValueError:
            flash("Choose a valid transaction date and time.", "error")
            return render_template("evaluate.html", form=form)

        score, level, decision, explanation = assess_transaction(sender, recipient, amount, location, transaction_time)
        created_at = datetime.now().isoformat(timespec="seconds")
        with get_db() as conn:
            cur = conn.execute("""INSERT INTO transactions
                (sender, recipient, account_id, amount, location, transaction_time, transaction_type,
                 risk_score, risk_level, decision, explanation, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sender, recipient, account_id, amount, location, transaction_time,
                 "Person-to-person transfer", score, level, decision, explanation, created_at))
            record_id = cur.lastrowid
        return redirect(url_for("result", transaction_id=record_id))
    return render_template("evaluate.html", form=form)


@app.route("/result/<int:transaction_id>")
def result(transaction_id):
    with get_db() as conn:
        record = conn.execute("SELECT * FROM transactions WHERE id=?", (transaction_id,)).fetchone()
    if record is None:
        flash("That transaction record could not be found.", "error")
        return redirect(url_for("history"))
    return render_template("result.html", record=record)


@app.route("/history")
def history():
    q = request.args.get("q", "").strip()
    risk = request.args.get("risk", "").strip()
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []
    if q:
        query += " AND (sender LIKE ? OR recipient LIKE ? OR location LIKE ? OR COALESCE(account_id,'') LIKE ? OR CAST(id AS TEXT) LIKE ?)"
        params.extend([f"%{q}%"] * 5)
    if risk in {"Low", "Medium", "High"}:
        query += " AND risk_level=?"
        params.append(risk)
    query += " ORDER BY id DESC"
    with get_db() as conn:
        records = conn.execute(query, params).fetchall()
    return render_template("history.html", records=records, q=q, risk=risk)


@app.route("/about")
def about():
    return render_template("about.html")


init_db()

if __name__ == "__main__":
    app.run(debug=True)
