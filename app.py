import os
import random
import functools
import threading
import time
import socket
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import smtplib
import json
from email.mime.text import MIMEText
from authlib.integrations.flask_client import OAuth
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor
import sqlite3
from dotenv import load_dotenv
import logging
from email_validator import validate_email, EmailNotValidError
from india_locations import india_locations 

# Configure Logging
import logging
from logging.handlers import RotatingFileHandler

log_handler = RotatingFileHandler('system.log', maxBytes=100000, backupCount=3)
log_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
logging.getLogger().addHandler(log_handler)
logging.getLogger().setLevel(logging.INFO)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-123')

# --- DATABASE CONFIG ---
DATABASE_URL = os.getenv('DATABASE_URL')
IS_POSTGRES = DATABASE_URL and DATABASE_URL.startswith('postgres')

def get_db_connection():
    if IS_POSTGRES:
        try:
            protocol_fixed_url = DATABASE_URL.replace('postgres://', 'postgresql://')
            conn = psycopg2.connect(protocol_fixed_url, cursor_factory=RealDictCursor)
            return conn
        except Exception as e:
            logging.error(f"Postgres Connection Error: {e}")
            try:
                conn = psycopg2.connect(protocol_fixed_url, cursor_factory=RealDictCursor, sslmode='require')
                return conn
            except:
                raise e
    else:
        db_path = os.path.join('database', 'database.db')
        os.makedirs('database', exist_ok=True)
        conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES, check_same_thread=False)
        conn.row_factory = dict_factory
        return conn

def get_db_type():
    if IS_POSTGRES: return "PostgreSQL (Render Production)"
    return "SQLite (Local/Ephemeral)"

def execute_db(cursor, query, params=(), fetch_id=False):
    if IS_POSTGRES:
        query = query.replace('%', '%%').replace('?', '%s')
        if "CREATE TABLE" in query.upper():
            query = query.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY").replace("AUTOINCREMENT", "")
        if fetch_id and "INSERT" in query.upper() and "RETURNING" not in query.upper():
            q_lower = query.lower()
            if "complaints" in q_lower: id_col = "complaint_id"
            elif "resolution" in q_lower: id_col = "resolution_id"
            elif "votes" in q_lower: id_col = "vote_id"
            else: id_col = "id"
            query += f" RETURNING {id_col}"
        cursor.execute(query, params)
        if fetch_id:
            res = cursor.fetchone()
            return res[id_col] if res else None
        return cursor
    else:
        cursor.execute(query, params)
        if fetch_id: return cursor.lastrowid
        return cursor

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description): d[col[0]] = row[idx]
    return d

@app.before_request
def sync_user_session():
    if 'user' in session:
        try:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
            execute_db(cursor, "SELECT * FROM users WHERE email = ?", (session['user']['email'],))
            updated_user = cursor.fetchone()
            conn.close()
            if updated_user: session['user'] = dict(updated_user)
        except: pass

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

BLOCKED_DOMAINS = {'mailinator.com', '10minutemail.com', 'tempmail.com', 'guerrillamail.com', 'sharklasers.com', 'getnada.com', 'dispostable.com', 'yopmail.com'}

area_coords = {
    'Karnataka': (15.3173, 75.7139), 'Delhi': (28.7041, 77.1025), 'Maharashtra': (19.7515, 75.7139),
    'Bangalore': (12.9716, 77.5946), 'Mumbai': (19.0760, 72.8777), 'Chennai': (13.0827, 80.2707)
}

def validate_email_rigorous(email):
    try:
        validation = validate_email(email, check_deliverability=True)
        domain = validation.domain.lower()
        if domain in BLOCKED_DOMAINS: return False, "Fake or temporary email providers are not allowed."
        return True, ""
    except EmailNotValidError as e: return False, str(e)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    execute_db(cursor, "CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT, role TEXT DEFAULT 'citizen', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    execute_db(cursor, "CREATE TABLE IF NOT EXISTS complaints (complaint_id SERIAL PRIMARY KEY, citizen_name TEXT NOT NULL, citizen_email TEXT NOT NULL, state TEXT NOT NULL, district TEXT NOT NULL, area TEXT NOT NULL, issue_type TEXT NOT NULL, description TEXT NOT NULL, image_path TEXT, latitude REAL, longitude REAL, date_submitted TIMESTAMP DEFAULT CURRENT_TIMESTAMP, status TEXT DEFAULT 'Pending')")
    execute_db(cursor, "CREATE TABLE IF NOT EXISTS votes (vote_id SERIAL PRIMARY KEY, complaint_id INTEGER NOT NULL, voter_identifier TEXT NOT NULL, date_voted TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (complaint_id) REFERENCES complaints(complaint_id) ON DELETE CASCADE)")
    execute_db(cursor, "CREATE TABLE IF NOT EXISTS resolution (resolution_id SERIAL PRIMARY KEY, complaint_id INTEGER NOT NULL UNIQUE, action_taken TEXT NOT NULL, resolved_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (complaint_id) REFERENCES complaints(complaint_id) ON DELETE CASCADE)")
    conn.commit()
    conn.close()

def keep_alive():
    url = os.getenv('RENDER_EXTERNAL_URL', 'https://civic-complaint-analyzer.onrender.com')
    while True:
        try: requests.get(url, timeout=15)
        except: pass
        time.sleep(600)

def safe_init():
    try: init_db()
    except Exception as e: logging.error(f"Init Error: {e}")

@app.errorhandler(500)
def internal_error(e):
    import traceback
    return render_template('error_500.html', error=traceback.format_exc()), 500

def format_display_id(c_id):
    return f"CIV-{1000 + int(c_id)}" if c_id else "CIV-ERR"

def get_stats():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
    execute_db(cursor, "SELECT COUNT(*) as total FROM complaints")
    total = cursor.fetchone()['total']
    execute_db(cursor, "SELECT COUNT(*) as resolved FROM complaints WHERE status = 'Resolved'")
    resolved = cursor.fetchone()['resolved']
    execute_db(cursor, "SELECT COUNT(*) as pending FROM complaints WHERE status IN ('Pending', 'In Progress')")
    pending = cursor.fetchone()['pending']
    conn.close()
    return {'total': total, 'resolved': resolved, 'pending': pending, 'active': pending}

def get_intelligence():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
    execute_db(cursor, "SELECT area, issue_type, COUNT(*) as count FROM complaints WHERE status != 'Resolved' GROUP BY area, issue_type HAVING COUNT(*) >= 1")
    clusters = cursor.fetchall()
    conn.close()
    return {'clusters': clusters, 'predictions': [], 'recommendations': []}

def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session: return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session or session['user']['role'] != 'admin': return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_user(): return dict(user=session.get('user'))

@app.route('/')
def index():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
    execute_db(cursor, "SELECT * FROM complaints ORDER BY date_submitted DESC LIMIT 5")
    recent = cursor.fetchall()
    for c in recent: c['display_id'] = format_display_id(c['complaint_id'])
    conn.close()
    return render_template('index.html', top_priority=recent, categories={}, active_page='index')

@app.route('/submit', methods=['GET', 'POST'])
def submit():
    if request.method == 'POST':
        # Extraction & Validation Logic
        p = request.form
        conn = get_db_connection()
        cursor = conn.cursor()
        execute_db(cursor, "INSERT INTO complaints (citizen_name, citizen_email, state, district, area, issue_type, description) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                   (p['name'], p['email'], p['state'], p['district'], p['area'], p['issue_type'], p['description']))
        conn.commit()
        conn.close()
        flash('Submitted successfully!', 'success')
        return redirect(url_for('index'))
    return render_template('submit.html', active_page='submit')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email, password = request.form.get('email'), request.form.get('password')
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
        execute_db(cursor, "SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        conn.close()
        if user and check_password_hash(user['password_hash'], password):
            session['user'] = dict(user)
            return redirect(url_for('admin_dashboard' if user['role'] == 'admin' else 'index'))
        flash('Invalid credentials', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        p = request.form
        hashed_pw = generate_password_hash(p['password'])
        conn = get_db_connection()
        cursor = conn.cursor()
        execute_db(cursor, "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)", (p['name'], p['email'], hashed_pw, p.get('role', 'citizen')))
        conn.commit()
        conn.close()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    return render_template('admin/dashboard.html', stats=get_stats(), active_page='dashboard')

@app.route('/admin/complaints')
@admin_required
def admin_complaints():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
    execute_db(cursor, "SELECT * FROM complaints ORDER BY date_submitted DESC")
    complaints = cursor.fetchall()
    for c in complaints: c['display_id'] = format_display_id(c['complaint_id'])
    conn.close()
    return render_template('admin/complaints.html', complaints=complaints, active_page='complaints')

@app.route('/analytics')
def analytics():
    return render_template('analytics.html', stats=get_stats(), active_page='analytics')

@app.route('/api/analytics')
def api_analytics():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
    execute_db(cursor, """
        SELECT issue_type, COUNT(*) as count FROM complaints GROUP BY issue_type
    """)
    by_issue = cursor.fetchall()
    execute_db(cursor, "SELECT area, COUNT(*) as count FROM complaints GROUP BY area")
    by_area = cursor.fetchall()
    
    # Trends
    if IS_POSTGRES:
        execute_db(cursor, "SELECT TO_CHAR(date_submitted, 'YYYY-MM') as month, COUNT(*) as count FROM complaints GROUP BY month ORDER BY month")
    else:
        execute_db(cursor, "SELECT strftime('%Y-%m', date_submitted) as month, COUNT(*) as count FROM complaints GROUP BY month ORDER BY month")
    trends = cursor.fetchall()
    conn.close()
    
    return jsonify({
        'issue_types': {'labels': [r['issue_type'] for r in by_issue], 'data': [r['count'] for r in by_issue]},
        'areas': {'labels': [r['area'] for r in by_area], 'data': [r['count'] for r in by_area]},
        'monthly': {'labels': [r['month'] for r in trends], 'data': [r['count'] for r in trends]},
        'total_complaints': len(by_issue)
    })

@app.route('/api/heatmap')
def api_heatmap():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
    execute_db(cursor, "SELECT area, COUNT(*) as volume FROM complaints GROUP BY area")
    areas = cursor.fetchall()
    conn.close()
    return jsonify([{'area': a['area'], 'volume': a['volume'], 'coords': area_coords.get(a['area'], (12.97, 77.59))} for a in areas])

@app.route('/track/<id>')
def track(id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
    import re
    c_id = int(re.sub(r'\D', '', id)) - 1000
    execute_db(cursor, "SELECT * FROM complaints WHERE complaint_id = ?", (c_id,))
    complaint = cursor.fetchone()
    conn.close()
    return render_template('track.html', complaint=complaint)

@app.route('/api/admin/update-status', methods=['POST'])
@admin_required
def update_status():
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    execute_db(cursor, "UPDATE complaints SET status = ? WHERE complaint_id = ?", (data['status'], data['complaint_id']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

safe_init()
threading.Thread(target=keep_alive, daemon=True).start()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
