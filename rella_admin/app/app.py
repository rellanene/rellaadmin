from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
import mysql.connector

app = Flask(__name__)
app.secret_key = "rella-admin-secret"  # required for sessions


# --- Database connection ---
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="Clement-88",
        database="rella"
    )
    
def query_all(sql, params=None):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql, params or [])
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def query_one(sql, params=None):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql, params or [])
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row
    


# --- Landing page (login) ---
@app.route("/", methods=["GET", "POST"])
def login():
    # If already logged in, go to dashboard
    if "user_id" in session and session.get("role") == "admin":
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM users WHERE username=%s AND is_active=1 AND is_approved=1",
            (username,)
        )
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and user["role"] == "admin" and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["theme"] = session.get("theme", "light")  # default theme
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid credentials or unauthorized access.", "error")

    return render_template("login.html")

from functools import wraps

def require_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def current_user():
    return {
        "id": session.get("user_id"),
        "username": session.get("username"),
        "role": session.get("role"),
        "theme": session.get("theme", "light")
    }




# --- Admin dashboard ---
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session or session.get("role") != "admin":
        flash("Access denied. Admins only.", "error")
        return redirect(url_for("login"))

    theme = session.get("theme", "light")
    return render_template(
        "admin_dashboard.html",
        username=session.get("username"),
        theme=theme
    )


# --- Theme toggle ---
@app.route("/toggle-theme")
def toggle_theme():
    current = session.get("theme", "light")
    session["theme"] = "dark" if current == "light" else "light"
    return redirect(url_for("dashboard"))


# --- Logout ---
@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

def current_user():
    return {
        "id": session.get("user_id"),
        "username": session.get("username"),
        "role": session.get("role"),
        "theme": session.get("theme", "light")
    }


# --- Records ---
@app.route('/records')
@require_login
def records():
    user = current_user()
    q = request.args.get('q', '').strip()
    start = request.args.get('start')
    end = request.args.get('end')

    # --- Base query ---
    sql = """
        SELECT 
            s.id,
            s.invoice_no,
            s.client_id,
            s.subtotal,
            s.vat,
            s.total,
            s.created_at,
            c.name AS client_name,
            u.username AS user_name
        FROM sales s
        LEFT JOIN clients c ON s.client_id = c.id
        LEFT JOIN users u ON s.created_by = u.id
        WHERE 1=1
    """
    params = []

    # --- Invoice search ---
    if q:
        sql += " AND s.invoice_no LIKE %s"
        params.append(f"%{q}%")

    # --- Date range filters ---
    if start:
        sql += " AND DATE(s.created_at) >= %s"
        params.append(start)
    if end:
        sql += " AND DATE(s.created_at) <= %s"
        params.append(end)

    # --- Default range (last 30 days) if no filters ---
    if not start and not end:
        sql += " AND DATE(s.created_at) >= CURDATE() - INTERVAL 30 DAY"

    # --- Order newest first ---
    sql += " ORDER BY s.created_at DESC"

    rows = query_all(sql, params)

    # --- Totals for finances integration ---
    totals_sql = """
        SELECT 
            COALESCE(SUM(s.subtotal), 0) AS total_subtotal,
            COALESCE(SUM(s.vat), 0) AS total_vat,
            COALESCE(SUM(s.total), 0) AS total_incl_vat
        FROM sales s
        WHERE 1=1
    """
    totals_params = []

    if q:
        totals_sql += " AND s.invoice_no LIKE %s"
        totals_params.append(f"%{q}%")
    if start:
        totals_sql += " AND DATE(s.created_at) >= %s"
        totals_params.append(start)
    if end:
        totals_sql += " AND DATE(s.created_at) <= %s"
        totals_params.append(end)
    if not start and not end:
        totals_sql += " AND DATE(s.created_at) >= CURDATE() - INTERVAL 30 DAY"

    totals = query_one(totals_sql, totals_params)

    # --- Render page ---
    return render_template(
        'records.html',
        records=rows,
        totals=totals,
        user=user,
        q=q,
        start=start,
        end=end
    )


@app.route('/export-records-csv')
@require_login
def export_records_csv():
    q = request.args.get('q', '')
    start = request.args.get('start')
    end = request.args.get('end')

    sql = """
        SELECT 
            s.id,
            s.invoice_no,
            s.client_id,
            s.subtotal,
            s.vat,
            s.total,
            s.created_at
        FROM sales s
        WHERE 1=1
    """

    params = []

    if q:
        sql += " AND s.invoice_no LIKE %s"
        params.append(f"%{q}%")

    if start:
        sql += " AND DATE(s.created_at) >= %s"
        params.append(start)

    if end:
        sql += " AND DATE(s.created_at) <= %s"
        params.append(end)

    sql += " ORDER BY s.created_at DESC"

    rows = query_all(sql, params)

    # Build CSV
    import csv
    from io import StringIO

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow(["ID", "Invoice No", "Client ID", "Subtotal", "VAT", "Total", "Created At"])

    for r in rows:
        writer.writerow([
            r["id"],
            r["invoice_no"],
            r["client_id"],
            r["subtotal"],
            r["vat"],
            r["total"],
            r["created_at"]
        ])

    output.seek(0)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=sales_records.csv"}
    )


@app.route('/records/visuals')
@require_login
def records_visuals():
    q = request.args.get('q', '')
    start = request.args.get('start')
    end = request.args.get('end')

    # Same filtering logic as /records
    sql = """
        SELECT DATE(s.created_at) AS date, SUM(s.total) AS total_sales
        FROM sales s
        WHERE 1=1
    """
    params = []

    if q:
        sql += " AND s.invoice_no LIKE %s"
        params.append(f"%{q}%")
    if start:
        sql += " AND DATE(s.created_at) >= %s"
        params.append(start)
    if end:
        sql += " AND DATE(s.created_at) <= %s"
        params.append(end)

    sql += " GROUP BY DATE(s.created_at) ORDER BY DATE(s.created_at)"

    data = query_all(sql, params)

    return render_template('records_visuals.html', data=data)



if __name__ == "__main__":
    app.run(debug=True)
