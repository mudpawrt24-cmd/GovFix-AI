"""
GovFix AI - Secure Government Portal Backend with Admin Override Control
Features:
- Pure-Python AI Diagnostic Engine
- Zero-PII Sanitization Firewall
- Direct Admin Override & Force Approval API
- Live Farmers & Escalation Database
"""

import os
import re
import json
import math
import uuid
import datetime
from pathlib import Path
from collections import Counter
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import smtplib
from email.message import EmailMessage
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'govfix-production-secure-entropy-key-9912'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# -------------------------------------------------------------
# 1. IN-MEMORY DATABASE & ESCALATION QUEUE
# -------------------------------------------------------------
DATABASE = {
    "registered_farmers": [
        {
            "registration_id": "PMK-2026-IND-00812",
            "name": "Rameshwar Prasad Patel",
            "aadhaar_masked": "XXXX-XXXX-1234",
            "mobile_masked": "98XXXXXX10",
            "khasra_no": "142/9",
            "state": "Madhya Pradesh",
            "status": "APPROVED",
            "ekyc_status": "VERIFIED",
            "timestamp": "2026-08-16 18:20:10",
            "admin_notes": "System Auto-Approved via GovFix AI"
        }
    ],
    "telemetry_audit_logs": [],
    "admin_escalations": [
        {
            "escalation_id": "ESC-9021",
            "farmer_name": "Balwinder Singh",
            "aadhaar_masked": "XXXX-XXXX-5541",
            "issue_type": "Land Registry Discrepancy (Tehsil Lock)",
            "status": "PENDING_OFFICER_ACTION",
            "timestamp": "2026-08-16 19:10:45",
            "khasra_no": "90/4-B"
        }
    ]
}

# Admin storage file for persistence
ADMIN_FILE = Path(__file__).parent.joinpath('admins.json')

def read_admins():
    if not ADMIN_FILE.exists():
        # create default admin
        default = {
            'admin': {
                'password_hash': generate_password_hash('AdminPass123'),
                'role': 'superadmin',
                'verified': True
            }
        }
        ADMIN_FILE.write_text(json.dumps(default, indent=2), encoding='utf-8')
        return default
    try:
        return json.loads(ADMIN_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {}

def write_admins(admins):
    ADMIN_FILE.write_text(json.dumps(admins, indent=2), encoding='utf-8')

DATABASE['admins'] = read_admins()
DATABASE.setdefault('admin_verifications', {})

# Simple rate-limiting and lockout stores
FAILED_LOGIN_ATTEMPTS = {}  # key -> {'count': int, 'last': ts}
LOCKED_ACCOUNTS = {}  # username -> unlock_ts
RATE_LIMIT = {}  # ip -> [timestamps]

def is_rate_limited(ip, window=60, limit=30):
    now = time.time()
    lst = RATE_LIMIT.get(ip, [])
    lst = [t for t in lst if now - t < window]
    RATE_LIMIT[ip] = lst
    if len(lst) >= limit:
        return True
    RATE_LIMIT[ip].append(now)
    return False

def record_failed_login(username):
    entry = FAILED_LOGIN_ATTEMPTS.get(username, {'count': 0, 'last': 0})
    entry['count'] += 1
    entry['last'] = time.time()
    FAILED_LOGIN_ATTEMPTS[username] = entry
    if entry['count'] >= 5:
        LOCKED_ACCOUNTS[username] = time.time() + 300  # 5 minute lockout

def reset_failed_login(username):
    FAILED_LOGIN_ATTEMPTS.pop(username, None)
    LOCKED_ACCOUNTS.pop(username, None)

def is_locked(username):
    ts = LOCKED_ACCOUNTS.get(username)
    if not ts:
        return False
    if time.time() > ts:
        LOCKED_ACCOUNTS.pop(username, None)
        return False
    return True

# -------------------------------------------------------------
# 2. LOAD ML MODEL
# -------------------------------------------------------------
MODEL_FILE = "govfix_model.json"
if not os.path.exists(MODEL_FILE):
    import train_model
    train_model.train()

with open(MODEL_FILE, "r", encoding="utf-8") as f:
    model_data = json.load(f)
    IDF_MAP = model_data["idf"]
    TRAINED_DOCS = model_data["docs"]
    RESOLUTIONS = model_data["resolutions"]

def predict_error_category(error_text: str) -> str:
    words = re.findall(r'\b[a-zA-Z0-9_]+\b', error_text.lower())
    tokens = list(words)
    for i in range(len(words) - 1):
        tokens.append(f"{words[i]}_{words[i+1]}")
    
    tf = Counter(tokens)
    vec = {term: count * IDF_MAP.get(term, 1.0) for term, count in tf.items()}
    length = math.sqrt(sum(v ** 2 for v in vec.values())) or 1.0
    query_vec = {k: v / length for k, v in vec.items()}

    best_score = -1.0
    best_label = "SERVER_OVERLOAD"
    for doc in TRAINED_DOCS:
        score = sum(val * doc["vector"].get(term, 0.0) for term, val in query_vec.items())
        if score > best_score:
            best_score = score
            best_label = doc["label"]
    return best_label

# -------------------------------------------------------------
# 3. ZERO-PII SANITIZATION FIREWALL
# -------------------------------------------------------------
def pii_scrubber(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\b\d{4}\s?\d{4}\s?\d{4}\b', '[REDACTED_AADHAAR]', text)
    text = re.sub(r'\b[6-9]\d{9}\b', '[REDACTED_MOBILE]', text)
    text = re.sub(r'\b\d{9,18}\b', '[REDACTED_BANK_ACCOUNT]', text)
    text = re.sub(r'\b[A-Z]{4}0[A-Z0-9]{6}\b', '[REDACTED_IFSC]', text)
    return text

# -------------------------------------------------------------
# 4. CITIZEN & ADMIN ROUTES
# -------------------------------------------------------------
@app.route("/")
def index():
    # ensure CSRF token for forms
    if 'csrf_token' not in session:
        session['csrf_token'] = uuid.uuid4().hex
    return render_template("landing.html", csrf_token=session.get('csrf_token'))


@app.route('/landing')
def landing():
    # Landing / homepage showcasing mission and quick links
    if 'csrf_token' not in session:
        session['csrf_token'] = uuid.uuid4().hex
    return render_template('landing.html', csrf_token=session.get('csrf_token'))


@app.route('/intro')
def intro():
    # Introduction page describing mission and vision
    if 'csrf_token' not in session:
        session['csrf_token'] = uuid.uuid4().hex
    return render_template('intro.html', csrf_token=session.get('csrf_token'))


@app.route('/register')
def register():
    # Legacy registration route (moved from root)
    if 'csrf_token' not in session:
        session['csrf_token'] = uuid.uuid4().hex
    return render_template('index.html', csrf_token=session.get('csrf_token'))


# Citizen storage (persistent)
CITIZENS_FILE = Path(__file__).parent.joinpath('citizens.json')

def read_citizens():
    if not CITIZENS_FILE.exists():
        CITIZENS_FILE.write_text(json.dumps({}, indent=2), encoding='utf-8')
        return {}
    try:
        return json.loads(CITIZENS_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {}

def write_citizens(citizens):
    CITIZENS_FILE.write_text(json.dumps(citizens, indent=2), encoding='utf-8')

# load existing citizens into DATABASE store
DATABASE['citizens'] = read_citizens()


@app.route('/auth/signup', methods=['POST'])
def citizen_signup():
    data = request.json or {}
    name = (data.get('name') or '').strip()
    mobile = (data.get('mobile') or '').strip()
    password = data.get('password') or ''
    # CSRF protection
    token = request.headers.get('X-CSRF-Token', '')
    if token != session.get('csrf_token'):
        return jsonify({'status': 'ERROR', 'message': 'CSRF token missing or invalid'}), 403
    # basic validation
    if not name or not mobile or not password:
        return jsonify({'status': 'ERROR', 'message': 'name, mobile and password required'}), 400
    if not re.match(r'^[6-9]\d{9}$', mobile):
        return jsonify({'status': 'ERROR', 'message': 'Invalid mobile number'}), 400
    if len(password) < 8:
        return jsonify({'status': 'ERROR', 'message': 'Password must be at least 8 characters'}), 400

    citizens = DATABASE.get('citizens', {})
    if mobile in citizens:
        return jsonify({'status': 'ERROR', 'message': 'Mobile already registered'}), 409
    citizens[mobile] = {
        'name': name,
        'password_hash': generate_password_hash(password),
        'created': datetime.datetime.now().isoformat()
    }
    write_citizens(citizens)
    session['citizen_user'] = mobile
    return jsonify({'status': 'SUCCESS', 'message': 'Signed up', 'mobile': mobile}), 201


@app.route('/auth/login', methods=['POST'])
def citizen_login():
    data = request.json or {}
    mobile = (data.get('mobile') or '').strip()
    password = data.get('password') or ''
    # CSRF protection
    token = request.headers.get('X-CSRF-Token', '')
    if token != session.get('csrf_token'):
        return jsonify({'status': 'ERROR', 'message': 'CSRF token missing or invalid'}), 403
    citizens = DATABASE.get('citizens', {})
    entry = citizens.get(mobile)
    if not entry or not check_password_hash(entry.get('password_hash', ''), password):
        return jsonify({'status': 'ERROR', 'message': 'Invalid mobile or password'}), 401
    session['citizen_user'] = mobile
    return jsonify({'status': 'SUCCESS', 'message': 'Signed in', 'mobile': mobile}), 200


@app.route('/auth/logout', methods=['POST'])
def citizen_logout():
    token = request.headers.get('X-CSRF-Token', '')
    if token != session.get('csrf_token'):
        return jsonify({'status': 'ERROR', 'message': 'CSRF token missing or invalid'}), 403
    session.pop('citizen_user', None)
    return jsonify({'status': 'SUCCESS', 'message': 'Logged out'}), 200

@app.route("/admin")
def admin_portal():
    # Admin page shows admin dashboard only when authenticated
    admin_authenticated = session.get('admin_user') is not None
    # Ensure CSRF token exists in session
    if 'csrf_token' not in session:
        session['csrf_token'] = uuid.uuid4().hex
    return render_template("admin.html", data=DATABASE, admin_authenticated=admin_authenticated, admin_user=session.get('admin_user'), csrf_token=session.get('csrf_token'))


def require_admin(fn):
    def wrapper(*args, **kwargs):
        # Allow API access with session or Bearer token
        admin_user = session.get('admin_user')
        auth_header = request.headers.get('Authorization', '')
        token_ok = False
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ', 1)[1].strip()
            # In this simple example, allow token equal to hashed password for the user
            for u, v in DATABASE.get('admins', {}).items():
                if token == v.get('password_hash'):
                    token_ok = True
                    admin_user = u
                    break

        if not admin_user and not token_ok:
            return jsonify({'status': 'ERROR', 'message': 'Admin authentication required'}), 401
        # check verified flag
        admins = DATABASE.get('admins', {})
        if admin_user and not admins.get(admin_user, {}).get('verified', False):
            return jsonify({'status': 'ERROR', 'message': 'Admin account not verified'}), 403
        return fn(*args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper


@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    # CSRF protection for state-changing requests
    token = request.headers.get('X-CSRF-Token', '')
    if token != session.get('csrf_token'):
        return jsonify({'status': 'ERROR', 'message': 'CSRF token missing or invalid'}), 403
    # simple rate limit by IP
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if is_rate_limited(ip):
        return jsonify({'status': 'ERROR', 'message': 'Too many requests'}), 429

    # account lockout check
    if is_locked(username):
        return jsonify({'status': 'ERROR', 'message': 'Account temporarily locked due to repeated failures'}), 403

    admin_entry = DATABASE.get('admins', {}).get(username)
    if not admin_entry:
        # record failed attempt
        record_failed_login(username)
        return jsonify({'status': 'ERROR', 'message': 'Invalid admin username or password'}), 401
    if not check_password_hash(admin_entry['password_hash'], password):
        record_failed_login(username)
        return jsonify({'status': 'ERROR', 'message': 'Invalid admin username or password'}), 401
    # only allow login for verified accounts (except superadmin)
    if not admin_entry.get('verified', False) and admin_entry.get('role') != 'superadmin':
        return jsonify({'status': 'ERROR', 'message': 'Account not verified. Check email verification link.'}), 403
    session['admin_user'] = username
    reset_failed_login(username)
    return jsonify({'status': 'SUCCESS', 'message': 'Signed in', 'admin_user': username}), 200


@app.route('/admin/signup', methods=['POST'])
def admin_signup():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    # CSRF protection
    token = request.headers.get('X-CSRF-Token', '')
    if token != session.get('csrf_token'):
        return jsonify({'status': 'ERROR', 'message': 'CSRF token missing or invalid'}), 403
    if not username or not password:
        return jsonify({'status': 'ERROR', 'message': 'username and password required'}), 400
    # password strength check
    if len(password) < 10 or not re.search(r'[A-Z]', password) or not re.search(r'[0-9]', password):
        return jsonify({'status': 'ERROR', 'message': 'Password must be >=10 chars, include an uppercase and a digit'}), 400
    admins = DATABASE.get('admins', {})
    if username in admins:
        return jsonify({'status': 'ERROR', 'message': 'Admin user already exists'}), 409
    # create account as unverified; emit a verification token
    token_id = uuid.uuid4().hex
    admins[username] = {'password_hash': generate_password_hash(password), 'role': 'officer', 'verified': False}
    DATABASE['admin_verifications'][token_id] = {'username': username, 'created': datetime.datetime.now().isoformat()}
    write_admins(admins)
    # In a real system we'd email token link; here return token for dev testing
    return jsonify({'status': 'SUCCESS', 'message': 'Admin created. Verify via token.', 'verification_token': token_id}), 201


@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    session.pop('admin_user', None)
    return jsonify({'status': 'SUCCESS', 'message': 'Logged out'}), 200


@app.route('/admin/verify/<token_id>', methods=['GET'])
def admin_verify(token_id):
    entry = DATABASE.get('admin_verifications', {}).get(token_id)
    if not entry:
        return "Invalid or expired verification token", 404
    username = entry['username']
    admins = DATABASE.get('admins', {})
    if username in admins:
        admins[username]['verified'] = True
        write_admins(admins)
        # remove token
        DATABASE['admin_verifications'].pop(token_id, None)
        return f"Admin {username} verified. You can now sign in.", 200
    return "Account not found", 404


@app.route('/admin/invite', methods=['POST'])
@require_admin
def admin_invite():
    data = request.json or {}
    target = (data.get('username') or '').strip()
    if not target:
        return jsonify({'status': 'ERROR', 'message': 'username required'}), 400
    admins = DATABASE.get('admins', {})
    if target in admins:
        return jsonify({'status': 'ERROR', 'message': 'User already exists'}), 409
    token_id = uuid.uuid4().hex
    admins[target] = {'password_hash': generate_password_hash(uuid.uuid4().hex), 'role': data.get('role', 'officer'), 'verified': False}
    DATABASE['admin_verifications'][token_id] = {'username': target, 'created': datetime.datetime.now().isoformat()}
    write_admins(admins)

    verify_link = url_for('admin_verify', token_id=token_id, _external=True)

    # try send email if SMTP configured
    smtp_host = os.environ.get('SMTP_HOST')
    if smtp_host:
        try:
            msg = EmailMessage()
            msg['Subject'] = 'GovFix Admin Invitation'
            msg['From'] = os.environ.get('MAIL_FROM', 'no-reply@govfix.local')
            msg['To'] = data.get('email') or target
            msg.set_content(f'You have been invited. Verify: {verify_link}')
            with smtplib.SMTP(smtp_host, int(os.environ.get('SMTP_PORT', 25))) as s:
                if os.environ.get('SMTP_USER'):
                    s.starttls()
                    s.login(os.environ.get('SMTP_USER'), os.environ.get('SMTP_PASS'))
                s.send_message(msg)
            return jsonify({'status': 'SUCCESS', 'message': 'Invitation sent via email'}), 200
        except Exception as e:
            return jsonify({'status': 'SUCCESS', 'message': 'Created invite (email failed)', 'verify_link': verify_link, 'error': str(e)}), 200

    return jsonify({'status': 'SUCCESS', 'message': 'Invite created', 'verify_link': verify_link}), 200

@app.route("/api/admin/override-approve", methods=["POST"])
@require_admin
def admin_override_approve():
    """Direct Admin action: Forces approval on difficult/stuck cases."""
    data = request.json or {}
    escalation_id = data.get("escalation_id")
    officer_notes = data.get("notes", "Direct Administrative Override Approval by Nodal Officer")
    
    # Locate escalation and approve
    for esc in DATABASE["admin_escalations"]:
        if esc["escalation_id"] == escalation_id:
            esc["status"] = "RESOLVED_BY_ADMIN"
            # Add to approved farmers
            new_farmer = {
                "registration_id": f"PMK-OVERRIDE-{esc['escalation_id']}",
                "name": esc["farmer_name"],
                "aadhaar_masked": esc["aadhaar_masked"],
                "mobile_masked": "98XXXXXX88",
                "khasra_no": esc["khasra_no"],
                "state": "Punjab",
                "status": "APPROVED (ADMIN OVERRIDE)",
                "ekyc_status": "FORCE_VERIFIED",
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "admin_notes": officer_notes
            }
            DATABASE["registered_farmers"].insert(0, new_farmer)
            return jsonify({"status": "SUCCESS", "message": f"Escalation {escalation_id} Force-Approved & Enrolled!"})
            
    return jsonify({"status": "ERROR", "message": "Escalation ID not found"}), 404

# -------------------------------------------------------------
# 5. GOVFIX AI DIAGNOSTIC API
# -------------------------------------------------------------
@app.route("/api/govfix/diagnose", methods=["POST"])
def diagnose_error():
    payload = request.json or {}
    raw_error = payload.get("error_log", "")
    
    sanitized = pii_scrubber(raw_error)
    category = predict_error_category(sanitized)
    resolution = RESOLUTIONS.get(category, {
        "action_type": "GENERIC_RETRY",
        "en": "A transient portal glitch was detected. Please retry.",
        "hi": "पोर्टल पर एक अस्थायी समस्या आई है। कृपया पुनः प्रयास करें।"
    })
    
    # Audit logging
    log_entry = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sanitized_telemetry": sanitized,
        "predicted_category": category,
        "action_recommended": resolution["action_type"]
    }
    DATABASE["telemetry_audit_logs"].insert(0, log_entry)
    
    print(f"\n[GOVFIX AI TELEMETRY INTERCEPTED]")
    print(f" -> Sanitized: {sanitized}")
    print(f" -> Category: {category} | Action: {resolution['action_type']}\n")

    return jsonify({
        "status": "success",
        "sanitized_telemetry": sanitized,
        "category": category,
        "resolution": resolution
    })

# -------------------------------------------------------------
# 6. NATURAL SERVICE ENDPOINTS
# -------------------------------------------------------------
@app.route("/api/kisan/upload-land-doc", methods=["POST"])
def upload_land_document():
    if "file" not in request.files:
        return jsonify({"error_code": "DOC_CORRUPT", "message": "ERROR: No file attached."}), 400
    
    file = request.files["file"]
    file_bytes = file.read()
    file_size_kb = len(file_bytes) / 1024
    
    if file_size_kb > 100:
        return jsonify({
            "error_code": "ERROR_413_FILE_TOO_LARGE",
            "message": f"ERROR_413_FILE_TOO_LARGE: Uploaded land record exceeds 100KB threshold. Uploaded size: {round(file_size_kb, 1)} KB"
        }), 413
        
    return jsonify({"status": "SUCCESS", "message": f"Document Verified ({round(file_size_kb, 1)} KB)."}), 200

@app.route("/api/kisan/validate-khasra", methods=["POST"])
def validate_khasra():
    data = request.json or {}
    khasra = data.get("khasra_num", "").strip()
    if not re.match(r'^\d{1,5}(/\d{1,5})?$', khasra):
        return jsonify({
            "error_code": "REGEX_MISMATCH_KHASRA",
            "message": f"REGEX_MISMATCH_KHASRA: Land record Khata/Khasra number '{khasra}' does not match district revenue registry pattern."
        }), 422
    return jsonify({"status": "SUCCESS", "message": "Khasra Number Validated"}), 200

@app.route("/api/kisan/process-ekyc-fee", methods=["POST"])
def process_ekyc():
    data = request.json or {}
    acc = data.get("bank_acc", "")
    return jsonify({
        "error_code": "ERR_PAYMENT_TXN_PENDING",
        "message": f"ERR_PAYMENT_TXN_PENDING: Bank account {acc} debited ₹15.00 but NPCI DBT ledger confirmation is pending."
    }), 409

submission_counter = {}

@app.route("/api/kisan/submit-registration", methods=["POST"])
def submit_registration():
    data = request.json or {}
    session_id = data.get("session_id", "user_1")
    
    # Peak traffic simulation on 1st attempt
    if submission_counter.get(session_id, 0) == 0:
        submission_counter[session_id] = 1
        return jsonify({
            "error_code": "HTTP_503_NIC_OVERLOAD",
            "message": "HTTP 503 SERVICE UNAVAILABLE: NIC State Data Center server queue maxed under peak farmer enrollment traffic."
        }), 503
    
    submission_counter[session_id] = 0
    reg_id = f"PMK-2026-IND-{len(DATABASE['registered_farmers']) + 850:05d}"
    
    new_farmer = {
        "registration_id": reg_id,
        "name": data.get("name", "Farmer Citizen"),
        "aadhaar_masked": "XXXX-XXXX-" + str(data.get("aadhaar", "1234"))[-4:],
        "mobile_masked": str(data.get("mobile", "9876543210"))[:2] + "XXXXXX" + str(data.get("mobile", "9876543210"))[-2:],
        "khasra_no": data.get("khasra", "142/9"),
        "state": "Madhya Pradesh",
        "status": "APPROVED",
        "ekyc_status": "COMPLETED",
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "admin_notes": "Enrolled via Citizen Self-Service"
    }
    DATABASE["registered_farmers"].insert(0, new_farmer)

    return jsonify({
        "status": "SUCCESS",
        "registration_id": reg_id,
        "message": "Farmer Registration & e-KYC Completed Successfully!"
    }), 200

if __name__ == "__main__":
    app.run(port=5000, debug=True)