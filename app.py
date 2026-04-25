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
import uuid
import re
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
        except Exception:
            protocol_fixed_url = DATABASE_URL.replace('postgres://', 'postgresql://')
            return psycopg2.connect(protocol_fixed_url, cursor_factory=RealDictCursor, sslmode='require')
    else:
        db_path = os.path.join('database', 'database.db')
        os.makedirs('database', exist_ok=True)
        conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES, check_same_thread=False)
        conn.row_factory = dict_factory
        return conn

def execute_db(cursor, query, params=(), fetch_id=False):
    if IS_POSTGRES:
        query = query.replace('%', '%%').replace('?', '%s')
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

@app.errorhandler(500)
def internal_error(e):
    import traceback
    return render_template('error_500.html', error=traceback.format_exc()), 500

# --- HELPERS ---
area_coords = {
    'Karnataka': (15.3173, 75.7139), 'Delhi': (28.7041, 77.1025), 'Maharashtra': (19.7515, 75.7139),
    'Bangalore': (12.9716, 77.5946), 'Mumbai': (19.0760, 72.8777), 'Chennai': (13.0827, 80.2707),
    'Indiranagar': (12.9784, 77.6408), 'Koramangala': (12.9352, 77.6245), 'New Delhi': (28.6139, 77.2090)
}

def format_display_id(c_id):
    return f"CIV-{1000 + int(c_id)}" if c_id else "CIV-ERR"

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    if IS_POSTGRES:
        execute_db(cursor, "CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, name TEXT, email TEXT UNIQUE, password_hash TEXT, role TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        execute_db(cursor, "CREATE TABLE IF NOT EXISTS complaints (complaint_id SERIAL PRIMARY KEY, citizen_name TEXT, citizen_email TEXT, state TEXT, district TEXT, area TEXT, issue_type TEXT, description TEXT, image_path TEXT, latitude REAL, longitude REAL, status TEXT DEFAULT 'Pending', date_submitted TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        execute_db(cursor, "CREATE TABLE IF NOT EXISTS votes (vote_id SERIAL PRIMARY KEY, complaint_id INTEGER, voter_identifier TEXT, date_voted TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        execute_db(cursor, "CREATE TABLE IF NOT EXISTS resolution (resolution_id SERIAL PRIMARY KEY, complaint_id INTEGER UNIQUE, action_taken TEXT, resolved_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    else:
        execute_db(cursor, "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE, password_hash TEXT, role TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        execute_db(cursor, "CREATE TABLE IF NOT EXISTS complaints (complaint_id INTEGER PRIMARY KEY AUTOINCREMENT, citizen_name TEXT, citizen_email TEXT, state TEXT, district TEXT, area TEXT, issue_type TEXT, description TEXT, image_path TEXT, latitude REAL, longitude REAL, status TEXT DEFAULT 'Pending', date_submitted TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        execute_db(cursor, "CREATE TABLE IF NOT EXISTS votes (vote_id INTEGER PRIMARY KEY AUTOINCREMENT, complaint_id INTEGER, voter_identifier TEXT, date_voted TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        execute_db(cursor, "CREATE TABLE IF NOT EXISTS resolution (resolution_id INTEGER PRIMARY KEY AUTOINCREMENT, complaint_id INTEGER UNIQUE, action_taken TEXT, resolved_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    conn.commit()
    conn.close()

def get_stats():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
    execute_db(cursor, "SELECT COUNT(*) as total FROM complaints")
    total = cursor.fetchone()['total']
    execute_db(cursor, "SELECT COUNT(*) as resolved FROM complaints WHERE status = 'Resolved'")
    resolved = cursor.fetchone()['resolved']
    execute_db(cursor, "SELECT COUNT(*) as active FROM complaints WHERE status != 'Resolved'")
    active = cursor.fetchone()['active']
    conn.close()
    return {'total': total, 'resolved': resolved, 'active': active, 'pending': active}

# --- AUTH ---
def admin_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session or session['user']['role'] != 'admin': return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_user(): return dict(user=session.get('user'))

# --- ROUTES ---
@app.route('/')
def index():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
    execute_db(cursor, "SELECT c.*, (SELECT COUNT(*) FROM votes v WHERE v.complaint_id = c.complaint_id) as vote_count FROM complaints c ORDER BY vote_count DESC LIMIT 3")
    top_priority = cursor.fetchall()
    for c in top_priority: c['display_id'] = format_display_id(c['complaint_id'])
    execute_db(cursor, "SELECT c.*, (SELECT COUNT(*) FROM votes v WHERE v.complaint_id = c.complaint_id) as vote_count FROM complaints c ORDER BY date_submitted DESC LIMIT 20")
    all_c = cursor.fetchall()
    categories = {
        'Road & Infrastructure': [c for c in all_c if 'road' in c['issue_type'].lower()],
        'Water Supply': [c for c in all_c if 'water' in c['issue_type'].lower()],
        'Electricity': [c for c in all_c if 'electr' in c['issue_type'].lower()],
        'Garbage': [c for c in all_c if 'garbag' in c['issue_type'].lower()]
    }
    for cat in categories.values():
        for c in cat: c['display_id'] = format_display_id(c['complaint_id'])
    conn.close()
    return render_template('index.html', top_priority=top_priority, categories=categories, active_page='index')

@app.route('/submit', methods=['GET', 'POST'])
def submit():
    if request.method == 'POST':
        p = request.form
        image_file = request.files.get('image')
        image_path = None
        if image_file and image_file.filename:
            filename = f"{uuid.uuid4().hex}.{image_file.filename.rsplit('.', 1)[-1].lower()}"
            save_dir = os.path.join(app.root_path, 'static', 'uploads')
            os.makedirs(save_dir, exist_ok=True)
            image_file.save(os.path.join(save_dir, filename))
            image_path = filename
        lat, lng = area_coords.get(p['area'], area_coords.get(p['district'], (12.9716, 77.5946)))
        conn = get_db_connection()
        cursor = conn.cursor()
        execute_db(cursor, "INSERT INTO complaints (citizen_name, citizen_email, state, district, area, issue_type, description, image_path, latitude, longitude) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
                   (p['name'], p['email'], p['state'], p['district'], p['area'], p['issue_type'], p['description'], image_path, lat, lng))
        conn.commit()
        conn.close()
        flash('Complaint submitted successfully!', 'success')
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
            if user['role'] == 'admin':
                if request.form.get('govt_id') != os.getenv('ADMIN_ACCESS_CODE', 'CIVIC_ADMIN_2024'):
                    flash('Invalid Admin Access Code.', 'error')
                    return redirect(url_for('login'))
            session['user'] = dict(user)
            return redirect(url_for('admin_dashboard' if user['role'] == 'admin' else 'index'))
        flash('Invalid credentials.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        p = request.form
        if p.get('role') == 'admin':
            if p.get('govt_id') != os.getenv('ADMIN_ENROLLMENT_CODE', 'TEAM_ENROLL_2024'):
                flash('Invalid Admin Enrollment Key.', 'error')
                return redirect(url_for('register'))
        hashed_pw = generate_password_hash(p['password'])
        conn = get_db_connection()
        cursor = conn.cursor()
        execute_db(cursor, "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)", (p['name'], p['email'], hashed_pw, p.get('role', 'citizen')))
        conn.commit()
        conn.close()
        flash('Account created! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
    execute_db(cursor, "SELECT * FROM complaints WHERE status = 'Pending' ORDER BY date_submitted DESC LIMIT 5")
    urgent = cursor.fetchall()
    for c in urgent: c['display_id'] = format_display_id(c['complaint_id'])
    conn.close()
    return render_template('admin/dashboard.html', stats=get_stats(), urgent_complaints=urgent, alerts=[], active_page='dashboard')

@app.route('/analytics')
def analytics():
    return render_template('analytics.html', stats=get_stats(), active_page='analytics')

@app.route('/api/analytics')
def api_analytics():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
    execute_db(cursor, "SELECT issue_type, COUNT(*) as count FROM complaints GROUP BY issue_type")
    by_issue = cursor.fetchall()
    execute_db(cursor, "SELECT area, COUNT(*) as count FROM complaints GROUP BY area")
    by_area = cursor.fetchall()
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
        'total_complaints': sum(r['count'] for r in by_issue)
    })

@app.route('/api/heatmap')
def api_heatmap():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
    execute_db(cursor, "SELECT area, COUNT(*) as volume FROM complaints GROUP BY area")
    areas = cursor.fetchall()
    conn.close()
    return jsonify([{'area': a['area'], 'volume': a['volume'], 'coords': area_coords.get(a['area'], (12.97, 77.59))} for a in areas])

@app.route('/track')
@app.route('/track/<id>')
def track(id=None):
    search_id = id or request.args.get('id')
    complaint = None
    if search_id:
        c_id = int(re.sub(r'\D', '', search_id)) - 1000
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
        execute_db(cursor, "SELECT c.*, r.action_taken FROM complaints c LEFT JOIN resolution r ON c.complaint_id = r.complaint_id WHERE c.complaint_id = ?", (c_id,))
        complaint = cursor.fetchone()
        if complaint: complaint['display_id'] = format_display_id(complaint['complaint_id'])
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

@app.route('/api/locations/districts/<state>')
def api_get_districts(state):
    return jsonify(list(india_locations.get(state, {}).keys()))

@app.route('/api/locations/areas/<state>/<district>')
def api_get_areas(state, district):
    return jsonify(india_locations.get(state, {}).get(district, []))

# --- INIT ---
def safe_init():
    try: init_db()
    except: pass
safe_init()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
