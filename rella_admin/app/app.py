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


if __name__ == "__main__":
    app.run(debug=True)
