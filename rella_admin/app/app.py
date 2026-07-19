from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
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
    from datetime import date, timedelta

    user = current_user()
    q = request.args.get('q', '').strip()
    start = request.args.get('start')
    end = request.args.get('end')
    quick = request.args.get('quick')

    today = date.today()

    # --- QUICK FILTERS ---
    if quick == "today":
        start = today
        end = today

    elif quick == "yesterday":
        start = today - timedelta(days=1)
        end = today - timedelta(days=1)

    elif quick == "last7":
        start = today - timedelta(days=7)
        end = today

    elif quick == "current_week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)

    elif quick == "last_week":
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=6)

    elif quick == "current_month":
        start = today.replace(day=1)
        end = today

    elif quick == "last_month":
        first_this_month = today.replace(day=1)
        last_month_end = first_this_month - timedelta(days=1)
        start = last_month_end.replace(day=1)
        end = last_month_end

    elif quick == "current_year":
        start = date(today.year, 1, 1)
        end = today

    elif quick == "last_year":
        start = date(today.year - 1, 1, 1)
        end = date(today.year - 1, 12, 31)

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

    # --- Order newest first ---
    sql += " ORDER BY s.created_at DESC"

    rows = query_all(sql, params)

    # --- Totals ---
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

    totals = query_one(totals_sql, totals_params)

    return render_template(
        'records.html',
        records=rows,
        totals=totals,
        user=user,
        q=q,
        start=start,
        end=end,
        quick=quick
    )


# --- Print Records ---
@app.route('/print-records')
@require_login
def print_records():
    from datetime import datetime, date, timedelta
    from io import BytesIO
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    q = request.args.get('q', '').strip()
    start = request.args.get('start')
    end = request.args.get('end')
    quick = request.args.get('quick')

    # --- Quick filters ---
    today = date.today()
    if quick == "last7":
        start = today - timedelta(days=7)
        end = today
    elif quick == "today":
        start = today
        end = today
    elif quick == "yesterday":
        start = today - timedelta(days=1)
        end = today - timedelta(days=1)
    elif quick == "current_week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
    elif quick == "current_month":
        start = today.replace(day=1)
        end = today

    # --- Query ---
    sql = """
        SELECT 
            s.invoice_no,
            c.name AS client_name,
            s.subtotal,
            s.vat,
            s.total,
            s.created_at,
            u.username AS user_name
        FROM sales s
        LEFT JOIN clients c ON s.client_id = c.id
        LEFT JOIN users u ON s.created_by = u.id
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

    # --- Calculate grand total (Total Incl VAT) ---
    grand_total = sum(float(r["total"] or 0) for r in rows)

    # --- PDF Generation ---
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # --- Header ---
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(30, height - 50, "Sales Records Report")
    pdf.setFont("Helvetica", 10)
    pdf.line(30, height - 55, width - 30, height - 55)

    # --- Filter range + timestamp + totals ---
    printed_on = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pdf.drawString(30, height - 70, f"Filter Range: {start or '—'}  to  {end or '—'}")
    pdf.drawString(250, height - 70, f"Totals: R{grand_total:,.2f}")  # 👈 Added line
    pdf.drawRightString(width - 30, height - 70, f"Printed on: {printed_on}")

    # --- Column titles ---
    pdf.setFont("Helvetica-Bold", 10)
    y = height - 90
    pdf.drawString(30, y, "Invoice No")
    pdf.drawString(160, y, "Client")
    pdf.drawRightString(280, y, "Subtotal")
    pdf.drawRightString(340, y, "VAT")
    pdf.drawRightString(420, y, "Total Incl VAT")
    pdf.drawRightString(500, y, "Created At")
    pdf.drawRightString(580, y, "Created By")
    pdf.line(30, y - 5, width - 30, y - 5)

    # --- Table rows ---
    pdf.setFont("Helvetica", 9)
    y -= 20
    for r in rows:
        invoice_no = str(r["invoice_no"] or "—")
        client_name = str(r["client_name"] or "—")
        subtotal = f"{r['subtotal']:.2f}" if r["subtotal"] is not None else "0.00"
        vat = f"{r['vat']:.2f}" if r["vat"] is not None else "0.00"
        total = f"{r['total']:.2f}" if r["total"] is not None else "0.00"
        created_at = r["created_at"].strftime("%Y-%m-%d %H:%M") if r["created_at"] else "—"
        user_name = str(r["user_name"] or "—")

        pdf.drawString(30, y, invoice_no)
        pdf.drawString(160, y, client_name)
        pdf.drawRightString(280, y, subtotal)
        pdf.drawRightString(340, y, vat)
        pdf.drawRightString(420, y, total)
        pdf.drawRightString(500, y, created_at)
        pdf.drawRightString(580, y, user_name)
        y -= 18

        # --- Page break ---
        if y < 50:
            pdf.setFont("Helvetica-Bold", 9)
            pdf.drawRightString(width - 30, 30, f"Page {pdf.getPageNumber()}")
            pdf.showPage()
            pdf.setFont("Helvetica-Bold", 18)
            pdf.drawString(30, height - 50, "Sales Records Report (continued)")
            pdf.setFont("Helvetica", 10)
            pdf.line(30, height - 55, width - 30, height - 55)
            pdf.setFont("Helvetica-Bold", 10)
            y = height - 80
            pdf.drawString(30, y, "Invoice No")
            pdf.drawString(160, y, "Client")
            pdf.drawRightString(280, y, "Subtotal")
            pdf.drawRightString(340, y, "VAT")
            pdf.drawRightString(420, y, "Total Incl VAT")
            pdf.drawRightString(500, y, "Created At")
            pdf.drawRightString(580, y, "Created By")
            pdf.line(30, y - 5, width - 30, y - 5)
            pdf.setFont("Helvetica", 9)
            y -= 20

    # --- Footer ---
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawRightString(width - 30, 30, f"Page {pdf.getPageNumber()}")
    
    pdf.save()
    buffer.seek(0)
    
    # --- Dynamic filename ---
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"sales_report_{timestamp}.pdf"
    
    return Response(
        buffer,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )





# --- Export Records CSV ---
@app.route('/export-records-csv')
@require_login
def export_records_csv():
    from datetime import datetime, date, timedelta
    import csv
    from io import StringIO

    q = request.args.get('q', '').strip()
    start = request.args.get('start')
    end = request.args.get('end')
    quick = request.args.get('quick')

    today = date.today()

    # --- QUICK FILTERS ---
    if quick == "today":
        start = today
        end = today
    elif quick == "yesterday":
        start = today - timedelta(days=1)
        end = today - timedelta(days=1)
    elif quick == "last7":
        start = today - timedelta(days=7)
        end = today
    elif quick == "current_week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
    elif quick == "last_week":
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=6)
    elif quick == "current_month":
        start = today.replace(day=1)
        end = today
    elif quick == "last_month":
        first_this_month = today.replace(day=1)
        last_month_end = first_this_month - timedelta(days=1)
        start = last_month_end.replace(day=1)
        end = last_month_end
    elif quick == "current_year":
        start = date(today.year, 1, 1)
        end = today
    elif quick == "last_year":
        start = date(today.year - 1, 1, 1)
        end = date(today.year - 1, 12, 31)

    # --- Base query (use client name instead of client ID) ---
    sql = """
        SELECT 
            s.id,
            s.invoice_no,
            c.name AS client_name,
            s.subtotal,
            s.vat,
            s.total,
            s.created_at
        FROM sales s
        LEFT JOIN clients c ON s.client_id = c.id
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

    # --- Order newest first ---
    sql += " ORDER BY s.created_at DESC"

    rows = query_all(sql, params)

    # --- Build CSV ---
    output = StringIO()
    writer = csv.writer(output)

    writer.writerow(["ID", "Invoice No", "Client Name", "Subtotal", "VAT", "Total", "Created At"])

    for r in rows:
        writer.writerow([
            r["id"],
            r["invoice_no"],
            r["client_name"] or "—",
            f"{r['subtotal']:.2f}" if r["subtotal"] else "0.00",
            f"{r['vat']:.2f}" if r["vat"] else "0.00",
            f"{r['total']:.2f}" if r["total"] else "0.00",
            r["created_at"].strftime("%Y-%m-%d %H:%M") if r["created_at"] else "—"
        ])

    output.seek(0)

    # --- Timestamped filename ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"sales_records_{timestamp}.csv"

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )




@app.route('/records/visuals')
@require_login
def records_visuals():
    q = request.args.get('q', '').strip()
    start = request.args.get('start')
    end = request.args.get('end')
    quick = request.args.get('quick')

    from datetime import date, timedelta
    today = date.today()

    # --- Quick filters ---
    if quick == "today":
        start = today
        end = today
    elif quick == "yesterday":
        start = today - timedelta(days=1)
        end = today - timedelta(days=1)
    elif quick == "last7":
        start = today - timedelta(days=7)
        end = today
    elif quick == "current_week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
    elif quick == "current_month":
        start = today.replace(day=1)
        end = today

    # --- Sales over time ---
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

    # --- Sales per client ---
    sql_clients = """
        SELECT c.name AS product, SUM(s.total) AS total
        FROM sales s
        LEFT JOIN clients c ON s.client_id = c.id
        WHERE 1=1
    """
    params_clients = []

    if q:
        sql_clients += " AND s.invoice_no LIKE %s"
        params_clients.append(f"%{q}%")
    if start:
        sql_clients += " AND DATE(s.created_at) >= %s"
        params_clients.append(start)
    if end:
        sql_clients += " AND DATE(s.created_at) <= %s"
        params_clients.append(end)

    sql_clients += " GROUP BY c.name ORDER BY total DESC"
    product_sales = query_all(sql_clients, params_clients)

    # --- Most sold products (from movements table) ---
    sql_products = """
        SELECT p.name AS product, SUM(m.qty) AS total_sold
        FROM movements m
        LEFT JOIN products p ON m.product_id = p.id
        WHERE m.movement_type = 'sale'
    """
    params_products = []

    if start:
        sql_products += " AND DATE(m.created_at) >= %s"
        params_products.append(start)
    if end:
        sql_products += " AND DATE(m.created_at) <= %s"
        params_products.append(end)

    sql_products += " GROUP BY p.name ORDER BY total_sold DESC"
    product_sales_qty = query_all(sql_products, params_products)

    # --- Ensure lists are always defined ---
    if not product_sales:
        product_sales = []
    if not product_sales_qty:
        product_sales_qty = []

    # --- Normalize data for Chart.js ---
    def normalize(rows, key):
        clean = []
        for r in rows:
            value = r.get(key)
            try:
                value = float(value or 0)
            except (TypeError, ValueError):
                value = 0
            clean.append({**r, key: value})
        return clean

    data = normalize(data, 'total_sales')
    product_sales = normalize(product_sales, 'total')
    product_sales_qty = normalize(product_sales_qty, 'total_sold')

    return render_template(
        'records_visuals.html',
        data=data,
        product_sales=product_sales,
        product_sales_qty=product_sales_qty,
        start=start,
        end=end,
        q=q,
        quick=quick
    )

#-----INVOICE CARD-------#
#------------------------#
@app.route('/invoicing')
@require_login
def invoicing():
    sql = """
        SELECT 
            i.invoice_no,
            c.name AS client_name,
            i.amount_due,
            i.amount_paid,
            i.balance,
            i.payment_status,
            i.due_date,
            i.created_at,
            u.username AS created_by
        FROM invoices i
        LEFT JOIN clients c ON i.client_id = c.id
        LEFT JOIN users u ON i.created_by = u.id
        ORDER BY i.created_at DESC
    """
    invoices = query_all(sql)

    return render_template('invoicing.html', invoices=invoices)

@app.route('/laybuys')
@require_login
def laybuys():
    # --- Fetch lay-buy summary ---
    sql = """
        SELECT 
            l.id,
            c.name AS client_name,
            l.laybuy_number,
            l.status,
            l.start_date,
            l.expiry_date,
            l.total_amount,
            l.paid_amount,
            (l.total_amount - l.paid_amount) AS balance,
            l.created_at
        FROM client_laybuys l
        LEFT JOIN clients c ON l.client_id = c.id
        ORDER BY l.created_at DESC
    """
    laybuys = query_all(sql)

    return render_template('laybuys.html', laybuys=laybuys)





if __name__ == "__main__":
    app.run(debug=True)
