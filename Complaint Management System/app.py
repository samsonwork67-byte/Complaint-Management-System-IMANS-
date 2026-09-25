from flask import Flask, render_template, request, redirect, session, url_for, send_file
from postgres_client import db_client, generate_complaint_ref_and_accept
from flask import request, jsonify
from datetime import datetime
import random, string, uuid
from werkzeug.utils import secure_filename
import os
from dotenv import load_dotenv
import uuid
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash
from functools import wraps
from email_service import send_complaint_notifications, send_email
import json
import traceback
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from io import BytesIO
from email_receiver import fetch_unread_emails
import threading
import time
from time import time as _time
load_dotenv()

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.environ.get("SMTP_USER", "samsonwork67@gmail.com")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
IMAP_USER = os.environ.get("IMAP_USER", "samsonwork67@gmail.com")
IMAP_PASSWORD = os.environ.get("IMAP_PASSWORD", "")
ADMIN_EMAIL = "samsonwork67@gmail.com"
INTEGRITY_EVENTS_FILE = os.path.join("static", "uploads", "integrity_events.json")
AUDIT_FEED_CACHE = {"ts": 0, "limit": 0, "data": None}

app = Flask(__name__)
ADMIN_CACHE = {}
AUDIT_FEED_CACHE = {}

import secrets
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_COOKIE_NAME"] = "my_session"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Strict"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_ENV") == "production"
app.config["PERMANENT_SESSION_LIFETIME"] = 1800  # 30 minutes

# CSRF Protection
app.config["WTF_CSRF_ENABLED"] = True
app.config["WTF_CSRF_TIME_LIMIT"] = None
app.config["WTF_CSRF_SSL_STRICT"] = os.environ.get("FLASK_ENV") == "production"

try:
    from flask_wtf.csrf import CSRFProtect, generate_csrf
    csrf = CSRFProtect(app)
    app.jinja_env.globals['csrf_token'] = generate_csrf
except ImportError:
    # Fallback simple CSRF if flask-wtf not installed
    csrf = None
    def generate_csrf():
        if "_csrf_token" not in session:
            session["_csrf_token"] = secrets.token_hex(32)
        return session["_csrf_token"]
    app.jinja_env.globals['csrf_token'] = generate_csrf
    
    def validate_csrf(token):
        return token and session.get("_csrf_token") == token
    
    @app.before_request
    def csrf_protect():
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            if request.path.startswith("/api/"):
                token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
                if not validate_csrf(token):
                    return jsonify({"success": False, "message": "CSRF token missing or invalid"}), 403
            elif request.path in ["/login", "/logout"]:
                token = request.form.get("csrf_token")
                if not validate_csrf(token):
                    return render_template("login.html", error="Session expired, please try again"), 403

# -----------------------
# AUTH / ROLE HELPERS
# -----------------------
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not session.get("is_admin"):
                return redirect(url_for("login"))
            role = (session.get("admin_role") or "").upper()
            if role not in allowed_roles:
                accept = request.headers.get('Accept', '')
                is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                wants_json = is_xhr or ('application/json' in accept and 'text/html' not in accept)

                if wants_json:
                    return jsonify({"success": False, "message": "Forbidden"}), 403
                if session.get('is_admin'):
                    return redirect(url_for('admin_dashboard'))
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return wrapper
    return decorator


def super_admin_required(f):
    return role_required(["SUPER_ADMIN"])(f)


def full_access_required(f):
    return role_required(["FULL_ACCESS", "SUPER_ADMIN"])(f)


def dashboard_editor_required(f):
    return role_required(["DASHBOARD_EDITOR", "FULL_ACCESS", "SUPER_ADMIN"])(f)


def landing_editor_required(f):
    return role_required(["LANDING_EDITOR", "FULL_ACCESS", "SUPER_ADMIN"])(f)

# -----------------------
# DATETIME FORMATTER
# -----------------------
def format_datetime(iso_value):
    """Format ISO datetime (or datetime) to '%d %B %Y, %I:%M %p'.

    Returns empty string for falsy values and falls back to str() on parse error.
    """
    if not iso_value:
        return ''
    try:
        if isinstance(iso_value, datetime):
            dt = iso_value
        else:
            dt = datetime.fromisoformat(str(iso_value))
        return dt.strftime("%d %B %Y, %I:%M %p")
    except Exception:
        try:
            # last-resort: try parsing without microseconds
            base = str(iso_value)
            if '.' in base:
                base = base.split('.')[0]
            dt = datetime.fromisoformat(base)
            return dt.strftime("%d %B %Y, %I:%M %p")
        except Exception:
            return str(iso_value)

# register for Jinja templates
app.jinja_env.filters['format_datetime'] = format_datetime
app.jinja_env.globals['format_datetime'] = format_datetime


def _safe_row_value(row, key, default=None):
    if isinstance(row, dict):
        return row.get(key, default)
    return default


def _parse_audit_timestamp(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.replace(tzinfo=None)
    except Exception:
        return None


# -----------------------
# LANDING PAGE
# -----------------------
@app.route("/")
def landing():
    return render_template(
        "landing.html",
        is_admin=session.get("is_admin", False),
        admin_role=session.get("admin_role", None)
    )

@app.route("/api/me")
def me():
    return jsonify({
        "is_admin": bool(session.get("is_admin")),
        "admin_role": session.get("admin_role", None)
    })

# -----------------------
# GOVERNANCE API
# -----------------------
@app.route("/api/governance", methods=["GET"])
def get_governance_docs():
    response = db_client.table("governance").select("*").execute()
    return jsonify(response.data)

@app.route("/api/governance", methods=["POST"])
@landing_editor_required
def add_governance_doc():

    try:
        title = request.form.get("title")
        description = request.form.get("description")
        file = request.files.get("file")

        if not file:
            return jsonify({"success": False, "message": "No file uploaded"}), 400

        filename = secure_filename(file.filename)
        upload_dir = os.path.join("static", "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        filepath = os.path.join(upload_dir, filename)
        file.save(filepath)

        file_url = url_for("static", filename=f"uploads/{filename}")

        response = db_client.table("governance").insert({
            "title": title,
            "description": description,
            "file_url": file_url
        }).execute()

        print("DEBUG insert response:", response)
        return jsonify({"success": True, "message": "Document added", "file_url": file_url})

    except Exception as e:
        print("ERROR in add_governance_doc:", e)
        return jsonify({"success": False, "message": str(e)}), 500

# -----------------------
# INTEGRITY API
# -----------------------
@app.route("/api/governance/<int:doc_id>", methods=["DELETE"])
@landing_editor_required
def delete_governance_doc(doc_id):

    response = db_client.table("governance").delete().eq("id", doc_id).execute()
    return jsonify({"success": True})


@app.route("/api/governance/<int:doc_id>", methods=["PUT"])
@landing_editor_required
def update_governance_doc(doc_id):

    try:
        updates = {
            "title": request.form.get("title"),
            "description": request.form.get("description")
        }
        file = request.files.get("file")

        if file and file.filename:
            filename = secure_filename(file.filename)
            upload_dir = os.path.join("static", "uploads")
            os.makedirs(upload_dir, exist_ok=True)
            filepath = os.path.join(upload_dir, filename)
            file.save(filepath)
            updates["file_url"] = url_for("static", filename=f"uploads/{filename}")

        response = db_client.table("governance").update(updates).eq("id", doc_id).execute()
        if response.data:
            return jsonify({"success": True, "message": "Document updated"})
        return jsonify({"success": False, "message": "Document not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/integrity-events", methods=["GET"])
def get_integrity_events():
    response = db_client.table("integrity_events").select("*").order("id").execute()
    return jsonify(response.data)


@app.route("/api/integrity-events", methods=["POST"])
@landing_editor_required
def create_integrity_event():

    data = request.json or {}
    new_event = {
        "date": data.get("date", ""),
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "images": []
    }
    response = db_client.table("integrity_events").insert(new_event).execute()
    return jsonify({"success": True, "event": response.data[0]})


@app.route("/api/integrity-events/<int:event_id>", methods=["PUT"])
@landing_editor_required
def update_integrity_event(event_id):

    data = request.json or {}
    updates = {
        "date": data.get("date"),
        "title": data.get("title"),
        "description": data.get("description")
    }
    updates = {k: v for k, v in updates.items() if v is not None}

    response = db_client.table("integrity_events").update(updates).eq("id", event_id).execute()
    if not response.data:
        return jsonify({"success": False, "message": "Event not found"}), 404
    return jsonify({"success": True, "event": response.data[0]})


@app.route("/api/integrity-events/<int:event_id>", methods=["DELETE"])
@landing_editor_required
def delete_integrity_event(event_id):

    existing = db_client.table("integrity_events").select("images").eq("id", event_id).execute()
    if not existing.data:
        return jsonify({"success": False, "message": "Event not found"}), 404

    for image_url in existing.data[0].get("images", []):
        filename = image_url.split("/uploads/integrity/")[-1]
        filepath = os.path.join("static", "uploads", "integrity", filename)
        if os.path.exists(filepath):
            os.remove(filepath)

    db_client.table("integrity_events").delete().eq("id", event_id).execute()
    return jsonify({"success": True})


@app.route("/api/integrity-events/<int:event_id>/images", methods=["POST"])
@landing_editor_required
def upload_integrity_event_images(event_id):

    files = request.files.getlist("images")
    if not files:
        return jsonify({"success": False, "message": "No images uploaded"}), 400

    existing = db_client.table("integrity_events").select("images").eq("id", event_id).execute()
    if not existing.data:
        return jsonify({"success": False, "message": "Event not found"}), 404

    image_urls = existing.data[0].get("images", [])

    upload_dir = os.path.join("static", "uploads", "integrity")
    os.makedirs(upload_dir, exist_ok=True)

    for file in files:
        if not file or not file.filename:
            continue
        filename = secure_filename(file.filename)
        extension = os.path.splitext(filename)[1].lower()
        if extension not in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
            return jsonify({"success": False, "message": "Only image files can be uploaded"}), 400
        stored_filename = f"event-{event_id}-{uuid.uuid4().hex[:8]}-{filename}"
        file.save(os.path.join(upload_dir, stored_filename))
        image_urls.append(url_for("static", filename=f"uploads/integrity/{stored_filename}"))

    db_client.table("integrity_events").update({"images": image_urls}).eq("id", event_id).execute()
    return jsonify({"success": True, "images": image_urls})


@app.route("/api/integrity-events/<int:event_id>/images", methods=["DELETE"])
@landing_editor_required
def delete_integrity_event_image(event_id):

    data = request.json or {}
    image_url = data.get("image_url")
    if not image_url:
        return jsonify({"success": False, "message": "Image URL required"}), 400

    existing = db_client.table("integrity_events").select("images").eq("id", event_id).execute()
    if not existing.data:
        return jsonify({"success": False, "message": "Event not found"}), 404

    image_urls = [url for url in existing.data[0].get("images", []) if url != image_url]
    db_client.table("integrity_events").update({"images": image_urls}).eq("id", event_id).execute()
    return jsonify({"success": True, "images": image_urls})

# -----------------------
# LANDING PAGE (COMPLAINT STATISTICS)
# -----------------------
def _normalize_complaint_status(value):
    if value is None:
        return "ONGOING"

    text = str(value).strip().upper()
    if not text:
        return "ONGOING"

    if text in {"RESOLVED", "CLOSED", "DONE", "COMPLETED", "SUCCESS"}:
        return "RESOLVED"

    if text in {"REJECTED", "NFA", "NO FURTHER ACTION", "NO_FURTHER_ACTION", "KIV", "DECLINED", "DISMISSED"}:
        return "REJECTED"

    return "ONGOING"


def _extract_month_label(complaint):
    raw_value = complaint.get("Timestamp") or complaint.get("Date of Incident") or complaint.get("Last Updated Date")
    if not raw_value:
        return None

    try:
        dt = datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.strptime(str(raw_value), "%Y-%m-%d")
        except ValueError:
            return None

    return dt.strftime("%b %Y")


@app.route("/api/complaint-stats", methods=["GET"])
def get_complaint_stats():
    total = db_client.table("complaint").select("id", count="exact").execute()

    resolved = db_client.table("complaint").select(
        "id", count="exact"
    ).eq("Status", "RESOLVED").execute()

    nfa = db_client.table("complaint").select(
        "id", count="exact"
    ).eq("Status", "NFA").execute()

    received_count = total.count or 0
    resolved_count = resolved.count or 0
    nfa_count = nfa.count or 0
    ongoing_count = received_count - resolved_count - nfa_count

    return jsonify({
        "received": received_count,
        "resolved": resolved_count,
        "ongoing": max(ongoing_count, 0),
        "no_further_action": nfa_count
    })


@app.route("/api/analytics/dashboard", methods=["GET"])
@admin_required
def get_admin_analytics_dashboard():
    response = db_client.table("complaint").select("*").execute()
    complaints = response.data or []

    monthly_counts = {}
    category_counts = {}
    status_counts = {
        "RESOLVED": 0,
        "ONGOING": 0,
        "REJECTED": 0,
    }

    for complaint in complaints:
        month_label = _extract_month_label(complaint)
        if month_label:
            monthly_counts[month_label] = monthly_counts.get(month_label, 0) + 1

        category = complaint.get("Type of Complaint") or "Unspecified"
        category_counts[category] = category_counts.get(category, 0) + 1

        normalized_status = _normalize_complaint_status(complaint.get("Status"))
        if normalized_status in status_counts:
            status_counts[normalized_status] += 1

    sorted_months = [month for month, _ in sorted(monthly_counts.items(), key=lambda item: item[0])]
    monthly_series = [
        {"label": month, "value": monthly_counts[month]}
        for month in sorted_months
    ]

    category_series = [
        {"label": category, "value": count}
        for category, count in sorted(category_counts.items(), key=lambda item: item[1], reverse=True)
    ]

    status_series = [
        {"label": label, "value": status_counts[label]}
        for label in ["RESOLVED", "ONGOING", "REJECTED"]
    ]

    return jsonify({
        "summary": {
            "total": len(complaints),
            "ongoing": status_counts["ONGOING"],
            "resolved": status_counts["RESOLVED"],
            "rejected": status_counts["REJECTED"],
        },
        "monthly": monthly_series,
        "categories": category_series,
        "statuses": status_series,
    })


@app.route("/admin-analytics")
@admin_required
def admin_analytics():
    return render_template("admin_analytics.html")

# -----------------------
# LANDING PAGE (RESOURCES)
# -----------------------
@app.route("/api/resources", methods=["GET"])
def get_resources():
    response = db_client.table("resources").select("*").order("id").execute()
    return jsonify(response.data)


@app.route("/api/resources", methods=["POST"])
@landing_editor_required
def create_resource():

    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"success": False, "message": "File is required"}), 400

    filename = secure_filename(file.filename)
    file_size = f"{round(len(file.read()) / (1024 * 1024), 1)} MB"
    file.seek(0)
    upload_dir = os.path.join("static", "uploads", "resources")
    os.makedirs(upload_dir, exist_ok=True)
    stored_filename = f"resource-{uuid.uuid4().hex[:8]}-{filename}"
    file.save(os.path.join(upload_dir, stored_filename))
    file_url = url_for("static", filename=f"uploads/resources/{stored_filename}")

    new_resource = {
        "title": request.form.get("title"),
        "description": request.form.get("description"),
        "icon": request.form.get("icon", "document"),
        "updated_date": request.form.get("updated_date"),
        "file_url": file_url,
        "file_size": file_size
    }
    response = db_client.table("resources").insert(new_resource).execute()
    return jsonify({"success": True, "resource": response.data[0]})


@app.route("/api/resources/<int:resource_id>", methods=["PUT"])
@landing_editor_required
def update_resource(resource_id):

    updates = {
        "title": request.form.get("title"),
        "description": request.form.get("description"),
        "icon": request.form.get("icon", "document"),
        "updated_date": request.form.get("updated_date")
    }
    updates = {k: v for k, v in updates.items() if v is not None}

    file = request.files.get("file")
    if file and file.filename:
        filename = secure_filename(file.filename)
        file_size = f"{round(len(file.read()) / (1024 * 1024), 1)} MB"
        file.seek(0)
        upload_dir = os.path.join("static", "uploads", "resources")
        os.makedirs(upload_dir, exist_ok=True)
        stored_filename = f"resource-{uuid.uuid4().hex[:8]}-{filename}"
        file.save(os.path.join(upload_dir, stored_filename))
        updates["file_url"] = url_for("static", filename=f"uploads/resources/{stored_filename}")
        updates["file_size"] = file_size

    response = db_client.table("resources").update(updates).eq("id", resource_id).execute()
    if not response.data:
        return jsonify({"success": False, "message": "Resource not found"}), 404
    return jsonify({"success": True, "resource": response.data[0]})


@app.route("/api/resources/<int:resource_id>", methods=["DELETE"])
@landing_editor_required
def delete_resource(resource_id):

    existing = db_client.table("resources").select("file_url").eq("id", resource_id).execute()
    if not existing.data:
        return jsonify({"success": False, "message": "Resource not found"}), 404

    file_url = existing.data[0].get("file_url", "")
    if "/uploads/resources/" in file_url:
        filename = file_url.split("/uploads/resources/")[-1]
        filepath = os.path.join("static", "uploads", "resources", filename)
        if os.path.exists(filepath):
            os.remove(filepath)

    db_client.table("resources").delete().eq("id", resource_id).execute()
    return jsonify({"success": True})

# -----------------------
# LANDING PAGE (CONTACT)
# -----------------------
@app.route("/api/contact", methods=["POST"])
def contact():
    try:
        data = request.get_json()

        name = data.get("name")
        email = data.get("email")
        message = data.get("message")

        if not name or not email or not message:
            return jsonify({"error": "Missing fields"}), 400

        response = db_client.table("contact_messages").insert({
            "name": name,
            "email": email,
            "message": message
        }).execute()

        # 🔥 ADD THIS DEBUG LINE
        print("DB response:", response)

        if response.data is None:
            return jsonify({"error": "Insert failed", "details": response}), 500

        return jsonify({"success": True, "data": response.data})

    except Exception as e:
        print("ERROR:", str(e))
        return jsonify({"error": str(e)}), 500
    
    data = request.get_json()
    print("RAW DATA:", data)
# -----------------------
# COMPLAINT PAGE
# -----------------------
@app.route("/complaint")
def complaint():
    return render_template("complaint.html", is_admin=session.get("is_admin", False))

# -----------------------
# LOGIN PAGE (ADMIN ONLY)
# -----------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    
    if request.method == "POST":
        try:
            username = request.form.get("username")
            password = request.form.get("password")

            print("USERNAME:", username)

            # perform DB lookup with small retry to handle transient errors
            res = None
            for attempt in range(1, 4):
                try:
                    res = db_client.table("admin_users") \
                        .select("*") \
                        .eq("username", username) \
                        .eq("is_active", True) \
                        .execute()
                    # log both data and any error field for debugging
                    print(f"[LOGIN] DB attempt={attempt} data={getattr(res, 'data', None)} error={getattr(res, 'error', None)}")
                    break
                except Exception as e:
                    print(f"[LOGIN DB ERROR] attempt={attempt} err={e}")
                    time.sleep(0.1)
            if res is None:
                print("[LOGIN] DB lookup failed after retries")
                session.clear()
                return render_template("login.html", error="Service temporarily unavailable")

            if not res.data:
                session.clear()
                return render_template("login.html", error="Invalid credentials")

            user = res.data[0]

            # verify password
            try:
                if not check_password_hash(user["password_hash"], password):
                    session.clear()
                    return render_template("login.html", error="Invalid credentials")
            except Exception as e:
                print(f"[LOGIN PASSWORD ERROR] {e}")
                session.clear()
                return render_template("login.html", error="Invalid credentials")

            # session setup
            session.clear()
            session["is_admin"] = True
            session["admin_id"] = user["id"]
            role_val = user.get('permission_level') or user.get('role') or 'VIEW_ONLY'
            session["admin_role"] = str(role_val).upper()
            session["admin_username"] = user["username"]
            session["session_id"] = str(uuid.uuid4())
            session.modified = True

            # make audit logging non-blocking so slow DB/network doesn't delay login
            try:
                admin_id = session.get("admin_id")
                session_id = session.get("session_id")
                threading.Thread(
                    target=audit_log_async,
                    args=("LOGIN", admin_id, session_id, user.get("username"), None),
                    daemon=True,
                ).start()
            except Exception:
                # never fail login if auditing fails to start
                pass

            return redirect(url_for("admin_dashboard"))
        except Exception as e:
            print(f"[LOGIN ERROR] {e}")
            traceback.print_exc()
            session.clear()
            return render_template("login.html", error="Service temporarily unavailable")

    return render_template("login.html")

# -----------------------
# ADMIN USERS
# -----------------------
@app.route('/admin-users')
@super_admin_required
def admin_users():
    return render_template('admin_users.html')


@app.route('/api/admin-users', methods=['GET'])
@super_admin_required
def api_list_admin_users():
    try:
        # select only necessary columns to avoid schema issues
        res = db_client.table('admin_users').select('id, username, role, is_active, created_at').order('created_at', desc=False).execute()
        if getattr(res, 'error', None):
            print('[DB ERROR] list admin users:', res.error)
            return jsonify({'success': False, 'message': str(res.error)}), 500
        users = res.data or []
        # Format timestamps for frontend display (do not modify DB)
        formatted_users = []
        for u in users:
            item = dict(u)
            item['created_at'] = format_datetime(item.get('created_at'))
            formatted_users.append(item)
        return jsonify({'success': True, 'users': formatted_users})
    except Exception as e:
        print('[ERROR] api_list_admin_users:', e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin-users', methods=['POST'])
@super_admin_required
def api_create_admin_user():
    try:
        data = request.json or {}
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        permission = data.get('role') or data.get('permission_level') or 'VIEW_ONLY'

        if not username or not password:
            return jsonify({'success': False, 'message': 'username and password required'}), 400

        pw_hash = generate_password_hash(password)
        payload = {
            'username': username,
            'password_hash': pw_hash,
            'role': permission,
            'is_active': True
        }
        res = db_client.table('admin_users').insert(payload).execute()
        # DB client may return an error object
        if getattr(res, 'error', None):
            err_msg = str(res.error)
            print('[DB ERROR] create admin user:', err_msg)
            if 'username' in err_msg and ('already exists' in err_msg or 'duplicate key' in err_msg):
                return jsonify({'success': False, 'message': 'Username already exists'}), 400
            if 'email' in err_msg and ('already exists' in err_msg or 'duplicate key' in err_msg):
                return jsonify({'success': False, 'message': 'Email already exists'}), 400
            return jsonify({'success': False, 'message': err_msg}), 500

        if res.data:
            return jsonify({'success': True, 'user': res.data[0]})
        return jsonify({'success': False, 'message': 'Failed to create user'}), 500
    except Exception as e:
        print('[ERROR] api_create_admin_user:', e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin-users/<user_id>', methods=['GET'])
@super_admin_required
def api_get_admin_user(user_id):
    res = db_client.table('admin_users').select('*').eq('id', user_id).execute()
    if not res.data:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    return jsonify({'success': True, 'user': res.data[0]})


@app.route('/api/admin-users/<user_id>', methods=['PUT'])
@super_admin_required
def api_update_admin_user(user_id):
    try:
        data = request.json or {}
        updates = {}
        if 'username' in data:
            updates['username'] = data['username']
        if 'email' in data:
            updates['email'] = data['email']
        if 'role' in data or 'permission_level' in data:
            perm = data.get('role') or data.get('permission_level')
            updates['role'] = perm
        if 'password' in data and data['password']:
            updates['password_hash'] = generate_password_hash(data['password'])

        if not updates:
            return jsonify({'success': False, 'message': 'No updates provided'}), 400

        existing = db_client.table('admin_users').select('*').eq('id', user_id).execute()
        if not existing.data:
            return jsonify({'success': False, 'message': 'User not found'}), 404

        # If trying to change permission away from SUPER_ADMIN, ensure another exists
        current_perm = existing.data[0].get('role') or existing.data[0].get('permission_level')
        if str(current_perm).upper() == 'SUPER_ADMIN' and updates.get('role') and updates.get('role') != 'SUPER_ADMIN':
            others = db_client.table('admin_users').select('*').neq('id', user_id).eq('role', 'SUPER_ADMIN').execute()
            if not others.data:
                return jsonify({'success': False, 'message': 'Cannot demote the only SUPER_ADMIN'}), 400

        res = db_client.table('admin_users').update(updates).eq('id', user_id).execute()
        if res.data:
            return jsonify({'success': True, 'user': res.data[0]})
        return jsonify({'success': False, 'message': 'Update failed'}), 500
    except Exception as e:
        print('[ERROR] api_update_admin_user:', e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin-users/<user_id>/activate', methods=['POST'])
@super_admin_required
def api_activate_admin_user(user_id):
    try:
        data = request.json or {}
        activate = bool(data.get('activate', True))

        existing = db_client.table('admin_users').select('*').eq('id', user_id).execute()
        if not existing.data:
            return jsonify({'success': False, 'message': 'User not found'}), 404

        # Prevent deactivating the only SUPER_ADMIN
        current_perm = existing.data[0].get('role') or existing.data[0].get('permission_level')
        if str(current_perm).upper() == 'SUPER_ADMIN' and not activate:
            others = db_client.table('admin_users').select('*').neq('id', user_id).eq('role', 'SUPER_ADMIN').execute()
            if not others.data:
                return jsonify({'success': False, 'message': 'Cannot deactivate the only SUPER_ADMIN'}), 400

        res = db_client.table('admin_users').update({'is_active': activate}).eq('id', user_id).execute()
        if res.data:
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Failed to update status'}), 500
    except Exception as e:
        print('[ERROR] api_activate_admin_user:', e)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin-users/<user_id>/reset-password', methods=['POST'])
@super_admin_required
def api_reset_admin_password(user_id):
    try:
        data = request.json or {}
        password = data.get('password')
        if not password:
            return jsonify({'success': False, 'message': 'Password required'}), 400

        existing = db_client.table('admin_users').select('*').eq('id', user_id).execute()
        if not existing.data:
            return jsonify({'success': False, 'message': 'User not found'}), 404

        pw_hash = generate_password_hash(password)
        res = db_client.table('admin_users').update({'password_hash': pw_hash}).eq('id', user_id).execute()
        if res.data:
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Failed to reset password'}), 500
    except Exception as e:
        print('[ERROR] api_reset_admin_password:', e)
        return jsonify({'success': False, 'message': str(e)}), 500

# -----------------------
# ADMIN DASHBOARD (protected)
# -----------------------
@app.route("/admin_dashboard")
def admin_dashboard():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    response = db_client.table("complaint").select("*").execute()
    complaints = response.data or []

    stats = {
        "total": len(complaints),
        "resolved": sum(1 for c in complaints if c.get("Status") == "RESOLVED"),
        "nfa": sum(1 for c in complaints if c.get("Status") == "NFA"),
        "failed": sum(1 for c in complaints if c.get("Status") == "KIV"),
        "ongoing": sum(1 for c in complaints if c.get("Status") == "ONGOING"),
    }

    return render_template(
        "admin_dashboard.html",
        complaints=complaints,
        stats=stats
    )

def generate_complaint_ref_id():
    """Generate reference ID using atomic database sequence."""
    return _generate_ref_id_atomic(db_client)

# -----------------------
# MANUAL COMPLAINT ENTRY (Admin only)
# -----------------------
@app.route("/api/manual-complaint", methods=["POST"])
@role_required(["DASHBOARD_EDITOR", "FULL_ACCESS", "SUPER_ADMIN"])
def manual_complaint_entry():
    try:
        data = request.form
        file = request.files.get("file")

        required = ["name", "email", "accused", "category", "details"]
        missing = [f for f in required if not data.get(f, "").strip()]
        if missing:
            return jsonify({"success": False, "message": f"Missing required fields: {', '.join(missing)}"}), 400

        # Validate email
        import re
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, data.get("email", "")):
            return jsonify({"success": False, "message": "Invalid email format"}), 400

        tracking_id = generate_tracking_id()
        ref_id = generate_complaint_ref_id()

        file_ref = None
        if file and file.filename:
            filename = secure_filename(file.filename)
            upload_dir = os.path.join("static", "uploads")
            os.makedirs(upload_dir, exist_ok=True)
            stored_filename = f"manual-{uuid.uuid4().hex[:8]}-{filename}"
            file.save(os.path.join(upload_dir, stored_filename))
            file_ref = stored_filename

        payload = {
            "Timestamp": datetime.now().isoformat(),
            "Tracking ID": tracking_id,
            "Complaint Reference ID": ref_id,
            "Your Name": data.get("name"),
            "Email address": data.get("email"),
            "Your Phone Number": data.get("phone") or None,
            "Name of The Accused": data.get("accused"),
            "Position of The Accused": data.get("position") or None,
            "Company of The Accused": data.get("company") or None,
            "Type of Complaint": data.get("category"),
            "Date of Incident": data.get("incident_date") or None,
            "Time of Incident (General)": data.get("incident_time") or None,
            "Location of Incident": data.get("location") or None,
            "Details of Complaint": data.get("details"),
            "Other involved parties (If applicable)": data.get("other_parties") or None,
            "Upload file if there are evidences": file_ref,
            "Status": "ONGOING"
        }

        response = db_client.table("complaint").insert(payload).execute()

        if not response.data:
            return jsonify({"success": False, "message": "Failed to save complaint"}), 400

        source = data.get("entry_source") or "Manual Entry"
        audit_log(
            "MANUAL_COMPLAINT_CREATED",
            target=f"Complaint {ref_id}",
            details={
                "tracking_id": tracking_id,
                "entry_source": source,
                "accused": data.get("accused"),
                "category": data.get("category")
            }
        )

        try:
            send_complaint_notifications(payload, tracking_id)
        except Exception as ex:
            print(f"[MANUAL COMPLAINT] Notification error: {ex}")

        return jsonify({
            "success": True,
            "tracking_id": tracking_id,
            "complaint_ref_id": ref_id
        })

    except Exception as e:
        print("[MANUAL COMPLAINT ERROR]", e)
        return jsonify({"success": False, "message": str(e)}), 500

# -----------------------
# COMPLAIN DETAILS (protected)
# -----------------------
@app.route("/complaint/<complaint_id>")
def complaint_detail(complaint_id):
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    # Fetch the complaint row from DB
    response = db_client.table("complaint").select("*").eq("id", complaint_id).execute()
    if not response.data:
        return "Complaint not found", 404

    complaint = response.data[0]
    is_accepted = True

    uploaded_file = complaint.get("Upload file if there are evidences")
    evidence_files = []
    if uploaded_file:
        evidence_files.append(build_evidence_file(uploaded_file))

    followup_files = complaint.get("FollowupFiles") or []
    if isinstance(followup_files, str):
        followup_files = [followup_files]
    for file_ref in followup_files:
        evidence_files.append(build_evidence_file(file_ref))

    # Build display_fields dict for template loop
    display_fields = {
        "Timestamp": complaint.get("Timestamp"),
        "Name of The Accused": complaint.get("Name of The Accused"),
        "Position of The Accused": complaint.get("Position of The Accused"),
        "Company of The Accused": complaint.get("Company of The Accused"),
        "Type of Complaint": complaint.get("Type of Complaint"),
        "Details of Complaint": complaint.get("Details of Complaint"),
        "Date of Incident": complaint.get("Date of Incident"),
        "Location of Incident": complaint.get("Location of Incident"),
        "Email address": complaint.get("Email address"),
        "Your Phone Number": complaint.get("Your Phone Number"),
        "Your Name": complaint.get("Your Name"),
        "Follow-up Response": complaint.get("FollowupResponse"),
        # add other fields you want to show
    }

    editable_fields = [
        "Name of The Accused", "Position of The Accused", "Company of The Accused",
        "Type of Complaint", "Details of Complaint", "Date of Incident",
        "Location of Incident", "Email address", "Your Phone Number",
        "Your Name", "Follow-up Response", "Tracking ID", "Timestamp"
    ]

    return render_template(
        "complaint_detail.html",
        complaint_id=complaint_id,
        complaint=complaint,
        display_fields=display_fields,
        evidence_files=evidence_files,
        is_accepted=is_accepted,
        editable_fields=editable_fields
    )


def build_evidence_file(file_ref):
    file_ref = str(file_ref)
    file_url = file_ref if file_ref.startswith(("http://", "https://", "/static/")) else url_for("static", filename=f"uploads/{file_ref}")
    extension = os.path.splitext(file_ref.split("?")[0])[1].lower()
    return {
        "name": os.path.basename(file_ref),
        "url": file_url,
        "is_image": extension in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"],
        "is_pdf": extension == ".pdf",
        "extension": extension.replace(".", "").upper() if extension else "FILE"
    }

# -----------------------
# COMPLAINT SECTIONS (Admin sidebar notes)
# -----------------------
SECTION_EDIT_ROLES = ["DASHBOARD_EDITOR", "FULL_ACCESS", "SUPER_ADMIN"]

@app.route("/api/complaint/<complaint_id>/sections", methods=["GET"])
@role_required(SECTION_EDIT_ROLES)
def get_complaint_sections(complaint_id):
    try:
        sections_res = db_client.table("complaint_sections").select("*").eq(
            "complaint_id", complaint_id
        ).order("created_at").execute()
        sections = sections_res.data or []

        section_ids = [s["id"] for s in sections]
        files_by_section = {}
        if section_ids:
            files_res = db_client.table("complaint_section_files").select("*").in_(
                "section_id", section_ids
            ).execute()
            for f in files_res.data or []:
                files_by_section.setdefault(f["section_id"], []).append(f)

        for s in sections:
            s["files"] = files_by_section.get(s["id"], [])

        return jsonify({"success": True, "sections": sections})
    except Exception as e:
        print("[GET SECTIONS ERROR]", e)
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/complaint/<complaint_id>/sections", methods=["POST"])
@role_required(SECTION_EDIT_ROLES)
def create_complaint_section(complaint_id):
    try:
        data = request.json or {}
        section_type = data.get("section_type", "custom")
        title = data.get("title", "").strip()
        content = data.get("content", "")

        if not title:
            return jsonify({"success": False, "message": "Title is required"}), 400

        payload = {
            "complaint_id": complaint_id,
            "section_type": section_type,
            "title": title,
            "content": content,
            "created_by": session.get("admin_username"),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }

        res = db_client.table("complaint_sections").insert(payload).execute()
        if not res.data:
            return jsonify({"success": False, "message": "Failed to create section"}), 400

        audit_log("CREATE", target=f"Section: {title}", details={"complaint_id": complaint_id})

        return jsonify({"success": True, "section": res.data[0]})
    except Exception as e:
        print("[CREATE SECTION ERROR]", e)
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/sections/<section_id>", methods=["PUT"])
@role_required(SECTION_EDIT_ROLES)
def update_complaint_section(section_id):
    try:
        data = request.json or {}
        updates = {"updated_at": datetime.now().isoformat()}

        if "title" in data:
            updates["title"] = data["title"]
        if "content" in data:
            updates["content"] = data["content"]

        res = db_client.table("complaint_sections").update(updates).eq("id", section_id).execute()
        if not res.data:
            return jsonify({"success": False, "message": "Section not found"}), 404

        audit_log("UPDATE", target=f"Section {section_id}", details=updates)

        return jsonify({"success": True, "section": res.data[0]})
    except Exception as e:
        print("[UPDATE SECTION ERROR]", e)
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/sections/<section_id>", methods=["DELETE"])
@role_required(SECTION_EDIT_ROLES)
def delete_complaint_section(section_id):
    try:
        files_res = db_client.table("complaint_section_files").select("file_url").eq(
            "section_id", section_id
        ).execute()

        for f in files_res.data or []:
            file_url = f.get("file_url", "")
            if "/uploads/sections/" in file_url:
                filename = file_url.split("/uploads/sections/")[-1]
                filepath = os.path.join("static", "uploads", "sections", filename)
                if os.path.exists(filepath):
                    os.remove(filepath)

        db_client.table("complaint_section_files").delete().eq("section_id", section_id).execute()
        res = db_client.table("complaint_sections").delete().eq("id", section_id).execute()

        audit_log("DELETE", target=f"Section {section_id}")

        return jsonify({"success": True})
    except Exception as e:
        print("[DELETE SECTION ERROR]", e)
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/sections/<section_id>/files", methods=["POST"])
@role_required(SECTION_EDIT_ROLES)
def upload_section_file(section_id):
    try:
        file = request.files.get("file")
        if not file or not file.filename:
            return jsonify({"success": False, "message": "No file provided"}), 400

        filename = secure_filename(file.filename)
        extension = os.path.splitext(filename)[1].lower()
        allowed = ['.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.xlsx']
        if extension not in allowed:
            return jsonify({"success": False, "message": "File type not allowed"}), 400

        upload_dir = os.path.join("static", "uploads", "sections")
        os.makedirs(upload_dir, exist_ok=True)
        stored_filename = f"sec-{uuid.uuid4().hex[:8]}-{filename}"
        file.save(os.path.join(upload_dir, stored_filename))
        file_url = url_for("static", filename=f"uploads/sections/{stored_filename}")

        payload = {
            "section_id": section_id,
            "file_name": filename,
            "file_url": file_url,
            "file_type": extension.replace(".", ""),
            "uploaded_by": session.get("admin_username"),
            "uploaded_at": datetime.now().isoformat()
        }

        res = db_client.table("complaint_section_files").insert(payload).execute()

        audit_log("CREATE", target=f"File upload: {filename}", details={"section_id": section_id})

        return jsonify({"success": True, "file": res.data[0]})
    except Exception as e:
        print("[UPLOAD SECTION FILE ERROR]", e)
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/section-files/<file_id>", methods=["DELETE"])
@role_required(SECTION_EDIT_ROLES)
def delete_section_file(file_id):
    try:
        existing = db_client.table("complaint_section_files").select("*").eq("id", file_id).execute()
        if not existing.data:
            return jsonify({"success": False, "message": "File not found"}), 404

        file_url = existing.data[0].get("file_url", "")
        if "/uploads/sections/" in file_url:
            filename = file_url.split("/uploads/sections/")[-1]
            filepath = os.path.join("static", "uploads", "sections", filename)
            if os.path.exists(filepath):
                os.remove(filepath)

        db_client.table("complaint_section_files").delete().eq("id", file_id).execute()

        audit_log("DELETE", target=f"File {existing.data[0].get('file_name')}")

        return jsonify({"success": True})
    except Exception as e:
        print("[DELETE SECTION FILE ERROR]", e)
        return jsonify({"success": False, "message": str(e)}), 500
        
# -----------------------
# UPDATE COMPLAINT FIELDS
# -----------------------
@app.route("/api/update-complaint/<complaint_id>", methods=["POST"])
@role_required(["DASHBOARD_EDITOR", "FULL_ACCESS", "SUPER_ADMIN"])
def update_complaint(complaint_id):
    try:
        data = request.json or {}
        field_map = {
            "name": "Name of The Accused",
            "position": "Position of The Accused",
            "company": "Company of The Accused",
            "category": "Type of Complaint",
            "details": "Details of Complaint",
            "incident_date": "Date of Incident",
            "location": "Location of Incident",
            "email": "Email address",
            "phone": "Your Phone Number",
            "complainant_name": "Your Name",
            "followup_response": "FollowupResponse",
            "tracking_id": "Tracking ID",
            "timestamp": "Timestamp",
            "complaint_ref_id": "Complaint Reference ID"
        }

        updates = {}
        for key, db_col in field_map.items():
            if key in data:
                updates[db_col] = data[key]

        if not updates:
            return jsonify({"success": False, "message": "No valid fields to update"}), 400

        # capture old values before update
        old_row = db_client.table("complaint").select("*").eq("id", complaint_id).execute()
        old_values = old_row.data[0] if old_row.data else {}

        updates["Last Updated Date"] = datetime.now().isoformat()
        response = db_client.table("complaint").update(updates).eq("id", complaint_id).execute()

        if not response.data:
            return jsonify({"success": False, "message": "Complaint not found"}), 404

        changes = []

        for field, new_value in updates.items():
            old_value = old_values.get(field)

            if old_value != new_value:
                changes.append({
                    "field": field,
                    "old": old_value,
                    "new": new_value
                })

        audit_log(
            "UPDATE",
            target=f"Complaint {old_values.get('Complaint Reference ID', complaint_id)}",
            details={
                "changes": changes
            }
        )

        return jsonify({"success": True})
    except Exception as e:
        print("[UPDATE COMPLAINT ERROR]", e)
        return jsonify({"success": False, "message": str(e)}), 500

# -----------------------
# COMPLAINT PDF DOWNLOAD
# -----------------------
@app.route("/download/<complaint_id>")
def download_complaint_pdf(complaint_id):
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    resp = db_client.table("complaint").select("*").eq("id", complaint_id).execute()
    if not resp.data:
        return "Complaint not found", 404

    complaint = resp.data[0]
    ref_id = complaint.get('Complaint Reference ID') or complaint.get('Tracking ID') or complaint_id

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )

    styles = getSampleStyleSheet()
    elements = []

    # --- Header ---
    header_style = ParagraphStyle('Header', parent=styles['Normal'],
        fontSize=14, fontName='Helvetica-Bold',
        textColor=colors.HexColor('#0f172a'), alignment=TA_CENTER, spaceAfter=4)
    sub_style = ParagraphStyle('Sub', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor('#475569'), alignment=TA_CENTER, spaceAfter=2)
    ref_style = ParagraphStyle('Ref', parent=styles['Normal'],
        fontSize=10, fontName='Helvetica-Bold',
        textColor=colors.HexColor('#0d9488'), alignment=TA_CENTER, spaceAfter=8)

    elements.append(Paragraph("INTEGRITY & GOVERNANCE DIVISION", header_style))
    elements.append(Paragraph("Kumpulan Sawit Kinabalu", sub_style))
    elements.append(Paragraph("COMPLAINT REPORT", header_style))
    elements.append(Spacer(1, 0.2*cm))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#0d9488')))
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph(f"Reference ID: {ref_id}", ref_style))
    elements.append(Spacer(1, 0.3*cm))

    # --- Label style inside table ---
    label_para = ParagraphStyle('LabelP', parent=styles['Normal'],
        fontSize=9, fontName='Helvetica-Bold',
        textColor=colors.HexColor('#475569'))
    value_para = ParagraphStyle('ValueP', parent=styles['Normal'],
        fontSize=9, textColor=colors.HexColor('#0f172a'))

    def lbl(text):
        return Paragraph(text, label_para)

    def val(text):
        return Paragraph(str(text) if text else '—', value_para)

    col_widths = [5.5*cm, 11*cm]
    row_bg_alt = colors.HexColor('#f8fafc')
    row_bg_white = colors.white
    border_color = colors.HexColor('#e2e8f0')
    header_bg = colors.HexColor('#0f172a')

    def section_header_row(title):
        return [
            Paragraph(f'<font color="white"><b>{title}</b></font>', ParagraphStyle(
                'SH', parent=styles['Normal'], fontSize=9, fontName='Helvetica-Bold')),
            Paragraph('', styles['Normal'])
        ]

    # --- Build table rows ---
    rows = []

    # Section: Complainant
    rows.append(section_header_row("COMPLAINANT INFORMATION"))
    rows.append([lbl("Full Name"), val(complaint.get('Your Name'))])
    rows.append([lbl("Email Address"), val(complaint.get('Email address'))])
    rows.append([lbl("Phone Number"), val(complaint.get('Your Phone Number'))])
    rows.append([lbl("Date Submitted"), val(format_datetime(complaint.get('Timestamp')))])
    rows.append([lbl("Tracking ID"), val(complaint.get('Tracking ID'))])

    # Section: Accused
    rows.append(section_header_row("DETAILS OF THE ACCUSED"))
    rows.append([lbl("Name of Accused"), val(complaint.get('Name of The Accused'))])
    rows.append([lbl("Position"), val(complaint.get('Position of The Accused'))])
    rows.append([lbl("Company"), val(complaint.get('Company of The Accused'))])

    # Section: Incident
    rows.append(section_header_row("INCIDENT INFORMATION"))
    rows.append([lbl("Type of Complaint"), val(complaint.get('Type of Complaint'))])
    rows.append([lbl("Date of Incident"), val(format_datetime(complaint.get('Date of Incident')))])
    rows.append([lbl("Time of Incident"), val(complaint.get('Time of Incident (General)'))])
    rows.append([lbl("Location"), val(complaint.get('Location of Incident'))])
    rows.append([lbl("Other Involved Parties"), val(complaint.get('Other involved parties (If applicable)'))])

    # Section: Complaint Details
    rows.append(section_header_row("COMPLAINT DETAILS"))
    rows.append([lbl("Details of Complaint"), val(complaint.get('Details of Complaint'))])

    # Section: Case Status
    rows.append(section_header_row("CASE STATUS"))
    rows.append([lbl("Current Status"), val(complaint.get('Status') or 'ONGOING')])
    rows.append([lbl("Last Updated"), val(format_datetime(complaint.get('Last Updated Date')))])

    # Build table
    table = Table(rows, colWidths=col_widths, repeatRows=0)

    # Identify section header row indices
    section_indices = [i for i, r in enumerate(rows)
                       if isinstance(r[0], Paragraph) and 'INFORMATION' in (r[0].text or '')
                       or isinstance(r[0], Paragraph) and any(
                           x in (r[0].text or '') for x in ['ACCUSED', 'INCIDENT', 'DETAILS', 'STATUS'])]

    # Build table style
    ts = [
        ('GRID', (0, 0), (-1, -1), 0.5, border_color),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]

    for i, row in enumerate(rows):
        # detect section headers by checking if both cells exist and first cell has white font
        cell = row[0]
        is_header = False
        if hasattr(cell, 'text'):
            text = cell.text or ''
            is_header = any(x in text for x in [
                'COMPLAINANT', 'ACCUSED', 'INCIDENT', 'DETAILS', 'STATUS'
            ])
        if is_header:
            ts.append(('BACKGROUND', (0, i), (-1, i), header_bg))
            ts.append(('SPAN', (0, i), (-1, i)))
            ts.append(('TOPPADDING', (0, i), (-1, i), 8))
            ts.append(('BOTTOMPADDING', (0, i), (-1, i), 8))
        else:
            bg = row_bg_white if i % 2 == 0 else row_bg_alt
            ts.append(('BACKGROUND', (0, i), (-1, i), bg))
            ts.append(('TEXTCOLOR', (0, i), (0, i), colors.HexColor('#475569')))

    table.setStyle(TableStyle(ts))
    elements.append(table)
    elements.append(Spacer(1, 1.5*cm))

    # --- Signature Section ---
    elements.append(HRFlowable(width="100%", thickness=0.5, color=border_color))
    elements.append(Spacer(1, 0.5*cm))

    sig_label = ParagraphStyle('SigLabel', parent=styles['Normal'],
        fontSize=9, textColor=colors.HexColor('#475569'), alignment=TA_LEFT)
    sig_name = ParagraphStyle('SigName', parent=styles['Normal'],
        fontSize=9, fontName='Helvetica-Bold',
        textColor=colors.HexColor('#0f172a'), alignment=TA_LEFT)

    sig_data = [
        [
            Paragraph("Prepared by:", sig_label)
        ],
        [
            Paragraph("\n\n\n", styles['Normal'])
        ],
        [
            Paragraph("_______________________________", sig_label)
        ],
        [
            Paragraph("Manager, IGD Complaint Management", sig_name)
        ],
        [
            Paragraph("Integrity & Governance Division", sig_label)
        ],
        [
            Paragraph(f"Date: ___________________", sig_label)
        ],
    ]

    sig_table = Table(sig_data, colWidths=[10*cm])
    sig_table.hAlign = 'LEFT'
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(sig_table)

    elements.append(Spacer(1, 0.8*cm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=border_color))
    elements.append(Spacer(1, 0.2*cm))

    generated_at = datetime.now().strftime("%d %B %Y, %I:%M %p UTC")
    elements.append(Paragraph(
        f"This document is confidential. Generated on {generated_at}.",
        ParagraphStyle('Footer', parent=styles['Normal'],
            fontSize=7, textColor=colors.HexColor('#94a3b8'), alignment=TA_CENTER)
    ))

    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=False,
        download_name=f"complaint-{ref_id}.pdf",
        mimetype='application/pdf'
    )

# -----------------------
# COMPLAINT SUBMISSION (protected)
# -----------------------
@app.route("/api/submit-complaint", methods=["POST"])
def submit_complaint():
    try:
        if request.content_type and 'multipart/form-data' in request.content_type:
            data = request.form
            file = request.files.get("file")
        else:
            data = request.json
            file = None

        # Validate required fields
        required_fields = ["name", "email", "accused", "category", "details"]
        missing = [f for f in required_fields if not data.get(f, "").strip()]
        if missing:
            return jsonify({"success": False, "message": f"Missing required fields: {', '.join(missing)}"}), 400

        # Validate email format
        import re
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, data.get("email", "")):
            return jsonify({"success": False, "message": "Invalid email format"}), 400

        phone = data.get("phone") or None

        tracking_id = generate_tracking_id()
        # Do not generate Complaint Reference ID at submission time.
        # Reference IDs are generated only when a complaint is accepted.
        complaint_ref_id = None

        file_ref = None
        if file and file.filename:
            filename = secure_filename(file.filename)
            # Validate file size
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)
            MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
            if file_size > MAX_FILE_SIZE:
                return jsonify({"success": False, "message": "File size exceeds 10MB limit"}), 400
            
            # Validate file extension
            allowed_extensions = {'.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.xlsx'}
            file_ext = os.path.splitext(filename)[1].lower()
            if file_ext not in allowed_extensions:
                return jsonify({"success": False, "message": "File type not allowed"}), 400
            
            upload_dir = os.path.join("static", "uploads")
            os.makedirs(upload_dir, exist_ok=True)
            file.save(os.path.join(upload_dir, filename))
            file_ref = filename

        payload = {
            "Timestamp": datetime.now().isoformat(),
            "Tracking ID": tracking_id,
            "Complaint Reference ID": complaint_ref_id,
            "Your Name": data.get("name"),
            "Email address": data.get("email"),
            "Your Phone Number": data.get("phone") or None,
            "Name of The Accused": data.get("accused"),
            "Position of The Accused": data.get("position"),
            "Company of The Accused": data.get("company"),
            "Type of Complaint": data.get("category"),
            "Date of Incident": data.get("incident_date"),
            "Time of Incident (General)": data.get("incident_time"),
            "Location of Incident": data.get("location"),
            "Details of Complaint": data.get("details"),
            "Other involved parties (If applicable)": data.get("other_parties"),
            "Upload file if there are evidences": file_ref,
            "Status": "ONGOING"
        }
        
        response = db_client.table("complaint").insert(payload).execute()
        if response.data:
            # Use tracking_id for initial notifications since a reference ID is not yet assigned
            try:
                send_complaint_notifications(payload, tracking_id)
            except Exception as e:
                app.logger.error(f"Email notification failed: {e}")
            return jsonify({"success": True, "tracking_id": tracking_id})
        else:
            return jsonify({"success": False, "message": str(response)}), 400

    except Exception as e:
        # Always return JSON, not HTML
        return jsonify({"success": False, "message": str(e)}), 500


# -----------------------
# TRACKING ID GENERATOR
# -----------------------
def generate_tracking_id(length=12):
    # Character set: uppercase, lowercase, digits, and safe symbols
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    
    # Random string of given length
    rand_part = ''.join(random.choice(chars) for _ in range(length))
    
    return rand_part

# -----------------------
# COMPLAINT TRACKING
# -----------------------
@app.route("/api/track-complaint", methods=["POST"])
def track_complaint():
    try:
        data = request.json
        tracking_id = data.get("tracking_id")

        if not tracking_id:
            return jsonify({"success": False, "message": "Tracking ID required"}), 400

        response = db_client.table("complaint").select("*").eq("Tracking ID", tracking_id).execute()

        if response.data and len(response.data) > 0:
            complaint = response.data[0]
            last_raw = complaint.get("Last Updated Date") or complaint.get("Timestamp")
            return jsonify({
                "success": True,
                "complaint": {
                    "tracking_id": complaint.get("Tracking ID", "N/A"),
                    "status": complaint.get("Status") or "Ongoing",
                    "remarks": complaint.get("Remarks") or "No remarks yet",
                    "last_updated": format_datetime(last_raw) if last_raw else "N/A"
                }
            })
        else:
            return jsonify({"success": False, "message": "Complaint not found"}), 404

    except Exception as e:
        print("[TRACK ERROR]", e)
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500

# -----------------------
# Update Status Remarks
# -----------------------    
@app.route("/api/update-status/<complaint_id>", methods=["POST"])
def update_status(complaint_id):
    try:
        data = request.json or {}

        remarks = data.get("remarks")
        status = data.get("status")
        notify = data.get("notify", False)

        updates = {}

        if remarks is not None:
            updates["Remarks"] = remarks
            updates["Last Updated Date"] = datetime.now().isoformat()

        if status:
            updates["Status"] = status

        response = db_client.table("complaint") \
            .update(updates) \
            .eq("id", complaint_id) \
            .execute()

        if not response.data:
            return jsonify({"success": False, "message": "Not found"}), 404

        # 🔥 EMAIL LOGIC ADDED HERE
        if notify:
            complaint = response.data[0]

            try:
                send_email(
                    complaint.get("Email address"),
                    f"Update on Your Complaint",
                    f"""
Hello {complaint.get('Your Name')},

There is an update on your complaint:

Remarks:
{remarks}

Thank you.
                    """
                )
            except Exception as e:
                print("[EMAIL ERROR]", e)

        return jsonify({"success": True})

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# -----------------------
# Request Info
# -----------------------
@app.route("/api/review-complaint/<complaint_id>/request-info", methods=["POST"])
@role_required(["DASHBOARD_EDITOR", "FULL_ACCESS", "SUPER_ADMIN"])
def api_request_info(complaint_id):
    try:
        data = request.json or {}
        message = data.get("message")
        if not message or not message.strip():
            return jsonify({"success": False, "message": "Message is required."}), 400

        # Fetch complaint
        resp = db_client.table("complaint").select("*").eq("id", complaint_id).maybe_single().execute()
        if not resp or not resp.data:
            return jsonify({"success": False, "message": "Complaint not found."}), 404
        
        complaint = resp.data
        email = complaint.get("Email address")
        if not email:
            return jsonify({"success": False, "message": "Complainant email not found."}), 400

        # Generate FollowupToken
        token = str(uuid.uuid4())
        
        # Update complaint in DB
        db_client.table("complaint").update({
            "FollowupToken": token,
            "Last Updated Date": datetime.now().isoformat()
        }).eq("id", complaint_id).execute()

        # Send email to complainant
        link = f"{request.host_url.rstrip('/')}/complaint/followup/{token}"
        email_body = f"""Hello {complaint.get('Your Name', 'Complainant')},

An admin has requested additional information regarding your complaint (Reference ID: {complaint.get('Complaint Reference ID') or 'N/A'}).

Message from Admin:
{message}

Please click the following link to submit the requested information:
{link}
Thank you."""
        try:
            send_email(
                email,
                f"Information Request - {complaint.get('Complaint Reference ID') or 'Complaint Follow-up'}",
                email_body
            )
        except Exception as e:
            print("[EMAIL ERROR]", e)

        return jsonify({"success": True})
    except Exception as e:
        print("[REQUEST INFO ERROR]", e)
        return jsonify({"success": False, "message": str(e)}), 500

# -----------------------
# FOLLOWUP
# -----------------------
@app.route("/complaint/followup/<token>")
def followup_page(token):
    res = db_client.table("complaint").select("*").eq("FollowupToken", token).execute().data
    if not res:
        return "Invalid token or link already used.", 404
    return render_template("followup.html", complaint=res[0])

@app.route("/api/followup/<token>", methods=["POST"])
def followup_submit(token):
    try:
        res = db_client.table("complaint").select("*").eq("FollowupToken", token).execute()
        data = res.data

        if not data:
            return jsonify({"success": False, "message": "Invalid token"}), 404

        complaint = data[0]
        ref_id = complaint.get("Complaint Reference ID") or "UNKNOWN"
        remarks = request.form.get("remarks")
        files = request.files.getlist("files")

        # Check file size limit (50MB total)
        total_size = 0
        valid_files = []

        for file in files:
            if file and file.filename:
                file.seek(0, os.SEEK_END)
                size = file.tell()
                file.seek(0)

                total_size += size
                valid_files.append(file)

        if total_size > 50 * 1024 * 1024:
            return jsonify({"success": False, "message": "Total file size exceeds 50MB limit."}), 400

        upload_dir = os.path.join("static", "uploads", "followup", ref_id)
        os.makedirs(upload_dir, exist_ok=True)


        file_urls = complaint.get("FollowupFiles")
        if not file_urls:
            file_urls = []
        elif isinstance(file_urls, str):
            try:
                file_urls = json.loads(file_urls)
            except:
                file_urls = [file_urls]

        for file in valid_files:
            filename = secure_filename(file.filename)
            stored_filename = f"{uuid.uuid4().hex[:8]}-{filename}"
            filepath = os.path.join(upload_dir, stored_filename)
            file.save(filepath)
            file_urls.append(f"/static/uploads/followup/{ref_id}/{stored_filename}")

        db_client.table("complaint").update({
            "FollowupResponse": remarks,
            "FollowupFiles": file_urls,
            "FollowupToken": None
        }).eq("id", complaint["id"]).execute()

        try:
            file_list_str = "\n".join(file_urls) if file_urls else "None"
            send_email(
                ADMIN_EMAIL,
                f"Follow-up Received - {ref_id}",
                f"The complainant has submitted additional information for complaint {ref_id}.\n\n"
                f"Remarks:\n{remarks}\n\n"
                f"Uploaded Files:\n{file_list_str}"
            )
        except Exception as e:
            print(f"[ERROR] Failed to send admin notification for followup: {e}")

        return jsonify({"success": True})


    except Exception as e:
        print("[FOLLOWUP ERROR]", e)
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500

# -----------------------
# AUDIT LOG DASHBOARD (SUPER_ADMIN only)
# -----------------------
@app.route("/audit-log")
@super_admin_required
def audit_log_page():
    return render_template("audit_log.html")


@app.route("/api/audit-log/summary")
@super_admin_required
def api_audit_summary():
    try:
        today_start = datetime.now().strftime("%Y-%m-%dT00:00:00")

        today_logs = db_client.table("audit_logs").select("*").gte(
            "timestamp", today_start
        ).execute().data or []

        logins = [r for r in today_logs if str(_safe_row_value(r, "action_type", "")).upper() == "LOGIN"]
        logouts = [r for r in today_logs if str(_safe_row_value(r, "action_type", "")).upper() == "LOGOUT"]

        login_sessions = {}
        for row in logins:
            sid = _safe_row_value(row, "session_id")
            if sid:
                login_sessions[sid] = row

        logout_sessions = {row.get("session_id") for row in logouts if row.get("session_id")}
        active_sessions = [sid for sid in login_sessions if sid not in logout_sessions]
        active_admin_ids = []
        for sid in active_sessions:
            admin_id = _safe_row_value(login_sessions[sid], "admin_id")
            if admin_id:
                active_admin_ids.append(admin_id)
        active_admin_ids = list(dict.fromkeys(active_admin_ids))

        durations = []
        for sid, login_row in login_sessions.items():
            logout_row = next((r for r in logouts if _safe_row_value(r, "session_id") == sid), None)
            if logout_row:
                t1 = _parse_audit_timestamp(_safe_row_value(login_row, "timestamp"))
                t2 = _parse_audit_timestamp(_safe_row_value(logout_row, "timestamp"))
                if t1 and t2:
                    durations.append((t2 - t1).total_seconds() / 60)
        avg_duration = round(sum(durations) / len(durations), 1) if durations else 0

        counts = {}
        for row in today_logs:
            admin_id = _safe_row_value(row, "admin_id")
            if admin_id:
                counts[str(admin_id)] = counts.get(str(admin_id), 0) + 1
        most_active = max(counts, key=counts.get) if counts else None

        admin_ids = [a for a in set(list(active_admin_ids) + ([most_active] if most_active else [])) if a]
        names = {}
        if admin_ids:
            users = db_client.table("admin_users").select("id, username").in_("id", admin_ids).execute().data or []
            names = {str(u.get("id")): u.get("username") for u in users if u.get("id")}

        return jsonify({
            "success": True,
            "active_admins": len(active_admin_ids),
            "active_admin_names": [names.get(str(a), str(a)) for a in active_admin_ids],
            "total_actions_today": len(today_logs),
            "avg_session_minutes": avg_duration,
            "most_active_admin": names.get(str(most_active), str(most_active)) if most_active else "—"
        })
    except Exception as e:
        print("[AUDIT SUMMARY ERROR]", e)
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/audit-log/feed")
@super_admin_required
def api_audit_feed():
    # keep endpoint resilient under load — never return 500
    try:
        limit = int(request.args.get("limit", 100))
    except Exception:
        limit = 100

    try:
        cache = AUDIT_FEED_CACHE

        now_ts = _time()
        # serve cache when fresh (2s) and satisfies requested limit
        if isinstance(cache, dict) and cache.get("data") is not None and (now_ts - cache.get("ts", 0) < 2) and cache.get("limit", 0) >= limit:
            rows = cache.get("data")[:limit]
        else:
            try:
                res = db_client.table("audit_logs").select("*").order(
                    "timestamp", desc=True
                ).limit(limit).execute()
                rows = res.data or []
                # update cache
                AUDIT_FEED_CACHE.update({"ts": now_ts, "limit": limit, "data": rows})
            except Exception as e:
                print(f"[AUDIT FEED ERROR] {e}")
                rows = []

        admin_ids = [str(r.get("admin_id")) for r in rows if r and r.get("admin_id")] if rows else []
        admin_ids = list(dict.fromkeys(admin_ids))
        names = {}
        if admin_ids:
            try:
                users = db_client.table("admin_users").select("id, username").in_("id", admin_ids).execute().data or []
                names = {str(u.get("id")): u.get("username") for u in users if u.get("id")}
            except Exception as e:
                print(f"[AUDIT FEED NAMES ERROR] {e}")
                names = {}

        for r in rows:
            try:
                admin_id = _safe_row_value(r, "admin_id")
                r["admin_name"] = names.get(str(admin_id), admin_id or "Unknown")
                r["action_type"] = str(_safe_row_value(r, "action_type", "UNKNOWN")).upper()
                r["target"] = _safe_row_value(r, "target") or "—"
                r["details"] = _safe_row_value(r, "details") or {}
            except Exception:
                # skip malformed row
                continue

        return jsonify({"success": True, "logs": rows})
    except Exception as e:
        print(f"[AUDIT FEED UNEXPECTED ERROR] {e}")
        traceback.print_exc()
        return jsonify({"success": True, "logs": []})


@app.route("/api/audit-log/sessions")
@super_admin_required
def api_audit_sessions_active():
    try:
        today_start = datetime.now().strftime("%Y-%m-%dT00:00:00")
        logs = db_client.table("audit_logs").select("*").gte(
            "timestamp", today_start
        ).in_("action_type", ["LOGIN", "LOGOUT"]).order("timestamp").execute().data or []

        sessions = {}
        for row in logs:
            sid = _safe_row_value(row, "session_id")
            if not sid:
                continue
            admin_id = _safe_row_value(row, "admin_id")
            entry = sessions.setdefault(sid, {"admin_id": admin_id})
            entry[str(_safe_row_value(row, "action_type", "")).upper()] = _safe_row_value(row, "timestamp")

        admin_ids = [str(s.get("admin_id")) for s in sessions.values() if s.get("admin_id")]
        admin_ids = list(dict.fromkeys(admin_ids))
        names = {}
        if admin_ids:
            users = db_client.table("admin_users").select("id, username").in_("id", admin_ids).execute().data or []
            names = {str(u.get("id")): u.get("username") for u in users if u.get("id")}

        result = []
        now = datetime.now()
        for sid, data in sessions.items():
            login_at = data.get("LOGIN")
            logout_at = data.get("LOGOUT")
            if not login_at:
                continue
            t1 = _parse_audit_timestamp(login_at)
            end = _parse_audit_timestamp(logout_at) if logout_at else now
            if not t1:
                continue
            duration_min = round(((end or now) - t1).total_seconds() / 60, 1)
            result.append({
                "session_id": sid,
                "admin_name": names.get(str(data.get("admin_id")), data.get("admin_id") or "Unknown"),
                "login_at": login_at,
                "duration_minutes": duration_min,
                "status": "offline" if logout_at else "online"
            })

        result.sort(key=lambda r: r["login_at"], reverse=True)
        return jsonify({"success": True, "sessions": result[:15]})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/audit-log/table")
@super_admin_required
def api_audit_table():
    try:
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 25))
        action_type = request.args.get("action_type")
        admin_id = request.args.get("admin_id")
        search = request.args.get("search", "").strip()
        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to")

        query = db_client.table("audit_logs").select("*", count="exact")

        if action_type:
            query = query.eq("action_type", action_type)
        if admin_id:
            query = query.eq("admin_id", admin_id)
        if date_from:
            query = query.gte("timestamp", date_from)
        if date_to:
            query = query.lte("timestamp", date_to)
        if search:
            query = query.ilike("target", f"%{search}%")

        start = (page - 1) * page_size
        end = start + page_size - 1
        res = query.order("timestamp", desc=True).range(start, end).execute()
        rows = res.data or []

        admin_ids = list({r["admin_id"] for r in rows})
        names = {}
        if admin_ids:
            users = db_client.table("admin_users").select("id, username").in_("id", admin_ids).execute().data or []
            names = {u["id"]: u["username"] for u in users}
        for r in rows:
            r["admin_name"] = names.get(r["admin_id"], r["admin_id"])

        return jsonify({
            "success": True,
            "logs": rows,
            "total": res.count or 0,
            "page": page,
            "page_size": page_size
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/audit-log/admins")
@super_admin_required
def api_audit_admins():
    try:
        res = db_client.table("admin_users").select("id, username").execute()
        return jsonify({"success": True, "admins": res.data or []})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
# -----------------------
# ADMIN AUDIT LOG
# -----------------------
@app.route("/api/audit-log", methods=["POST"])
def api_audit_log():
    if not session.get("is_admin") and not session.get("admin_id"):
        return jsonify({"success": False, "message": "unauthenticated"}), 403
    try:
        data = request.json or {}
        logs = data.get("logs") or [data]  # support single or batch
        rows = []
        for entry in logs:
            rows.append({
                "admin_id": str(session.get("admin_id")),
                "action_type": entry.get("action_type"),
                "target": entry.get("target"),
                "details": entry.get("details") or {},
                "session_id": entry.get("session_id") or session.get("session_id"),
                "timestamp": datetime.now().isoformat()
            })
        if rows:
            db_client.table("audit_logs").insert(rows).execute()
        return jsonify({"success": True})
    except Exception as e:
        print(f"[AUDIT LOG ERROR] {e}")
        return jsonify({"success": False}), 200  # never surface as hard error
    
def audit_log_async(action_type, admin_id, session_id, target=None, details=None):
    """Background-safe audit log using explicit ids (does not access Flask session)."""
    try:
        if not admin_id or not session_id:
            return
        db_client.table("audit_logs").insert({
            "admin_id": str(admin_id),
            "action_type": action_type,
            "target": target,
            "details": details or {},
            "session_id": session_id,
            "timestamp": datetime.now().isoformat()
        }).execute()
    except Exception as e:
        print(f"[AUDIT LOG ERROR async] {e}")


def audit_log(action_type, target=None, details=None):
    """Log an admin action. Never raises — logging failures must not break the app."""
    try:
        admin_id = session.get("admin_id")
        session_id = session.get("session_id")
        if not admin_id or not session_id:
            return
        db_client.table("audit_logs").insert({
            "admin_id": str(admin_id),
            "action_type": action_type,
            "target": target,
            "details": details or {},
            "session_id": session_id,
            "timestamp": datetime.now().isoformat()
        }).execute()
    except Exception as e:
        print(f"[AUDIT LOG ERROR] {e}")

def get_session_durations(admin_id, limit=20):
    """Returns list of {session_id, login_at, logout_at, duration_minutes}."""
    logs = db_client.table("audit_logs").select("*").eq(
        "admin_id", admin_id
    ).in_("action_type", ["LOGIN", "LOGOUT"]).order("timestamp").execute()

    sessions = {}
    for row in logs.data or []:
        sid = row["session_id"]
        sessions.setdefault(sid, {})[row["action_type"]] = row["timestamp"]

    results = []
    for sid, events in sessions.items():
        login_at = events.get("LOGIN")
        logout_at = events.get("LOGOUT")
        duration = None
        if login_at and logout_at:
            t1 = datetime.fromisoformat(login_at)
            t2 = datetime.fromisoformat(logout_at)
            duration = round((t2 - t1).total_seconds() / 60, 1)
        results.append({
            "session_id": sid,
            "login_at": login_at,
            "logout_at": logout_at,
            "duration_minutes": duration
        })

    results.sort(key=lambda r: r.get("login_at") or "", reverse=True)
    return results[:limit]

@app.route("/api/audit-sessions/<admin_id>")
@super_admin_required
def api_audit_sessions(admin_id):
    return jsonify({"success": True, "sessions": get_session_durations(admin_id)})

@app.route("/api/log-view", methods=["POST"])
def log_view():
    if not session.get("admin_id"):
        return jsonify({"success": False, "message": "unauthorized"}), 401
    data = request.json or {}
    audit_log("VIEW", target=data.get("page"))
    return jsonify({"success": True})

# -----------------------
# SESSION TIMEOUT (AUTO LOGOUT)
# -----------------------
SESSION_TIMEOUT_MINUTES = 5

@app.before_request
def check_session_timeout():
    if not session.get("is_admin"):
        return

    if request.path.startswith("/static/") or request.path == "/api/session-heartbeat":
        return

    last_activity_str = session.get("last_activity")
    now = datetime.now()

    if last_activity_str:
        try:
            last_activity = datetime.fromisoformat(last_activity_str)
            elapsed_minutes = (now - last_activity).total_seconds() / 60

            if elapsed_minutes > SESSION_TIMEOUT_MINUTES:
                admin_id = session.get("admin_id")
                session_id = session.get("session_id")
                admin_username = session.get("admin_username")

                try:
                    audit_log_async(
                        "LOGOUT",
                        admin_id,
                        session_id,
                        target=admin_username,
                        details={"reason": "Session expired due to inactivity"}
                    )
                except Exception as e:
                    print(f"[SESSION TIMEOUT] Audit log failed: {e}")

                session.clear()

                accept = request.headers.get('Accept', '')
                is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                wants_json = is_xhr or ('application/json' in accept and 'text/html' not in accept)

                if wants_json:
                    return jsonify({"success": False, "message": "Session expired", "session_expired": True}), 401
                return redirect(url_for("login", expired=1))
        except Exception as e:
            print(f"[SESSION TIMEOUT] Parse error: {e}")

    # Only reset timer on actual user activity, not background auto-polling
    is_api_get = request.path.startswith("/api/") and request.method == "GET"
    is_background_post = request.path == "/api/audit-log" and request.method == "POST"
    if not is_api_get and not is_background_post:
        session["last_activity"] = now.isoformat()
        session.modified = True


@app.route("/api/session-heartbeat", methods=["POST"])
def session_heartbeat():
    if not session.get("is_admin"):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    session["last_activity"] = datetime.now().isoformat()
    session.modified = True

    return jsonify({
        "success": True,
        "timeout_minutes": SESSION_TIMEOUT_MINUTES,
        "remaining_seconds": SESSION_TIMEOUT_MINUTES * 60
    })

# -----------------------
# LOGOUT
# -----------------------
@app.route("/logout")
def logout():
    audit_log("LOGOUT", target=session.get("admin_username"))
    session.clear()
    return redirect(url_for("login"))

def run_email_receiver():
    print("[EMAIL RECEIVER] Starting background email listener...")
    while True:
        try:
            fetch_unread_emails()
        except Exception as e:
            print("[EMAIL RECEIVER LOOP ERROR]", e)
        time.sleep(30)

if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
    threading.Thread(target=run_email_receiver, daemon=True).start()

# With this:
from email_receiver import start_idle_listener

if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
    start_idle_listener()

if __name__ == "__main__":
    app.run(debug=True)