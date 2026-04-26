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
from werkzeug.utils import secure_filename
import psycopg2
from psycopg2.extras import RealDictCursor
import sqlite3
from dotenv import load_dotenv
import logging
import traceback
from email_validator import validate_email, EmailNotValidError
from india_locations import india_locations

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-123')

# --- STORAGE CONFIG ---
UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- DATABASE CONFIG ---
DATABASE_URL = os.getenv('DATABASE_URL')
IS_POSTGRES = DATABASE_URL and DATABASE_URL.startswith('postgres')

def get_db_connection():
    if IS_POSTGRES:
        try:
            protocol_fixed_url = DATABASE_URL.replace('postgres://', 'postgresql://')
            if 'sslmode' not in protocol_fixed_url:
                protocol_fixed_url += '&sslmode=require' if '?' in protocol_fixed_url else '?sslmode=require'
            conn = psycopg2.connect(protocol_fixed_url, cursor_factory=RealDictCursor, connect_timeout=10)
            return conn
        except Exception as e: raise e
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
            id_col = "complaint_id" if "complaints" in q_lower else ("resolution_id" if "resolution" in q_lower else "id")
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
    return render_template('error_500.html', error=traceback.format_exc()), 500

# --- HELPERS ---
area_coords = {
    'Karnataka': (15.3173, 75.7139), 'Delhi': (28.7041, 77.1025), 'Maharashtra': (19.7515, 75.7139),
    'Bangalore': (12.9716, 77.5946), 'Mumbai': (19.0760, 72.8777), 'Chennai': (13.0827, 80.2707)
}

def format_display_id(c_id):
    try: return f"CIV-{1000 + int(c_id)}" if c_id else "CIV-ERR"
    except: return "CIV-ERR"

def init_db():
    try:
        conn = get_db_connection(); cursor = conn.cursor()
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
        conn.commit(); conn.close()
    except: pass

def get_stats():
    try:
        conn = get_db_connection(); cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
        execute_db(cursor, "SELECT COUNT(*) as total FROM complaints"); total = cursor.fetchone().get('total', 0)
        execute_db(cursor, "SELECT COUNT(*) as resolved FROM complaints WHERE status = 'Resolved'"); resolved = cursor.fetchone().get('resolved', 0)
        execute_db(cursor, "SELECT COUNT(*) as active FROM complaints WHERE status != 'Resolved'"); active = cursor.fetchone().get('active', 0)
        execute_db(cursor, "SELECT issue_type, COUNT(*) as count FROM complaints GROUP BY issue_type ORDER BY count DESC LIMIT 1"); res = cursor.fetchone(); top_issue = res['issue_type'] if res else "N/A"
        conn.close(); return {'total': total, 'resolved_complaints': resolved, 'active': active, 'pending': active, 'top_issue': top_issue}
    except: return {'total': 0, 'resolved_complaints': 0, 'active': 0, 'pending': 0, 'top_issue': "N/A"}

# --- AUTH ---
def admin_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session or session['user']['role'] != 'admin': return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_user(): return dict(user=session.get('user'))

# --- ROUTES ---
@app.route('/')
def index():
    try:
        conn = get_db_connection(); cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
        execute_db(cursor, "SELECT c.*, (SELECT COUNT(*) FROM votes v WHERE v.complaint_id = c.complaint_id) as vote_count FROM complaints c ORDER BY vote_count DESC LIMIT 3")
        top_priority = cursor.fetchall() or []
        for c in top_priority: c['display_id'] = format_display_id(c['complaint_id'])
        execute_db(cursor, "SELECT c.*, (SELECT COUNT(*) FROM votes v WHERE v.complaint_id = c.complaint_id) as vote_count FROM complaints c ORDER BY date_submitted DESC LIMIT 30")
        all_c = cursor.fetchall() or []
        def safe_cat(list_c, term): return [c for c in list_c if c.get('issue_type') and term.lower() in c['issue_type'].lower()]
        categories = {'Road & Infrastructure': safe_cat(all_c, 'road'), 'Water Supply': safe_cat(all_c, 'water'), 'Electricity': safe_cat(all_c, 'electr'), 'Garbage': safe_cat(all_c, 'garbag')}
        for cat in categories.values():
            for c in cat: c['display_id'] = format_display_id(c['complaint_id'])
        conn.close(); return render_template('index.html', top_priority=top_priority, categories=categories, active_page='index')
    except: return render_template('index.html', top_priority=[], categories={}, active_page='index')

@app.route('/submit', methods=['GET', 'POST'])
def submit():
    if request.method == 'POST':
        try:
            p = request.form; lat, lng = area_coords.get(p['area'], area_coords.get(p['district'], (12.9716, 77.5946)))
            image_filename = None
            if 'image' in request.files:
                file = request.files['image']
                if file and allowed_file(file.filename):
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    image_filename = f"{uuid.uuid4().hex}.{ext}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
            conn = get_db_connection(); cursor = conn.cursor()
            execute_db(cursor, "INSERT INTO complaints (citizen_name, citizen_email, state, district, area, issue_type, description, image_path, latitude, longitude) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (p['name'], p['email'], p['state'], p['district'], p['area'], p['issue_type'], p['description'], image_filename, lat, lng))
            conn.commit(); conn.close(); flash('Complaint submitted successfully!', 'success'); return redirect(url_for('index'))
        except Exception as e: flash(f'Error: {e}', 'error'); return redirect(url_for('submit'))
    return render_template('submit.html', active_page='submit')

@app.route('/analytics')
def analytics(): return render_template('analytics.html', stats=get_stats(), active_page='analytics')

@app.route('/api/analytics')
def api_analytics():
    try:
        conn = get_db_connection(); cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
        execute_db(cursor, "SELECT issue_type, COUNT(*) as count FROM complaints GROUP BY issue_type"); by_issue = cursor.fetchall() or []
        execute_db(cursor, "SELECT area, COUNT(*) as count FROM complaints GROUP BY area"); by_area = cursor.fetchall() or []
        if IS_POSTGRES: execute_db(cursor, "SELECT TO_CHAR(date_submitted, 'YYYY-MM') as month, COUNT(*) as count FROM complaints GROUP BY month ORDER BY month")
        else: execute_db(cursor, "SELECT strftime('%Y-%m', date_submitted) as month, COUNT(*) as count FROM complaints GROUP BY month ORDER BY month")
        trends = cursor.fetchall() or []; conn.close(); stats = get_stats()
        return jsonify({'by_issue': by_issue, 'by_area': by_area, 'trends': trends, 'total_complaints': stats['total'], 'resolved_complaints': stats['resolved_complaints'], 'issue_types': {'labels': [r['issue_type'] for r in by_issue], 'data': [r['count'] for r in by_issue]}, 'areas': {'labels': [r['area'] for r in by_area], 'data': [r['count'] for r in by_area]}, 'monthly': {'labels': [r['month'] for r in trends], 'data': [r['count'] for r in trends]}})
    except: return jsonify({'error': 'api fail'})

@app.route('/api/live_complaints')
@app.route('/api/heatmap')
@app.route('/get-complaints')
def api_live_complaints():
    try:
        conn = get_db_connection(); cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
        execute_db(cursor, "SELECT * FROM complaints"); data = cursor.fetchall() or []; conn.close()
        for c in data:
            c['lat'] = c.get('latitude'); c['lng'] = c.get('longitude'); c['type'] = c.get('issue_type')
        return jsonify(data)
    except: return jsonify([])

@app.route('/api/insights')
def api_insights():
    try:
        conn = get_db_connection(); cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
        execute_db(cursor, "SELECT area, COUNT(*) as count FROM complaints GROUP BY area ORDER BY count DESC LIMIT 3"); top_areas = cursor.fetchall() or []
        execute_db(cursor, "SELECT issue_type, COUNT(*) as count FROM complaints GROUP BY issue_type ORDER BY count DESC LIMIT 3"); top_issues = cursor.fetchall() or []; conn.close()
        return jsonify({'predictions': [f"Critical {a['area']} infrastructure vector indicates 85% risk" for a in top_areas], 'clusters': [f"{i['issue_type']} detected in {len(top_areas)} sectors" for i in top_issues], 'recommendations': ["Deploy preventative maintenance in high-risk zones", "Increase sector-wide infrastructure redundancy"]})
    except: return jsonify({'error': 'insights fail'})

@app.route('/api/vote/<int:complaint_id>', methods=['POST'])
def vote_complaint(complaint_id):
    try:
        voter_id = request.remote_addr
        conn = get_db_connection(); cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
        # Check if already voted
        execute_db(cursor, "SELECT * FROM votes WHERE complaint_id = ? AND voter_identifier = ?", (complaint_id, voter_id))
        if cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': 'You have already prioritized this issue!'})
        
        execute_db(cursor, "INSERT INTO votes (complaint_id, voter_identifier) VALUES (?, ?)", (complaint_id, voter_id))
        conn.commit(); conn.close()
        return jsonify({'success': True, 'message': 'Priority vote recorded!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/track')
@app.route('/track/<id>')
def track(id=None):
    search_id = id or request.args.get('id'); complaint = None
    if search_id:
        try:
            raw_id = re.sub(r'\D', '', search_id)
            if raw_id:
                c_id = int(raw_id) - 1000; conn = get_db_connection(); cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
                execute_db(cursor, "SELECT c.*, r.action_taken FROM complaints c LEFT JOIN resolution r ON c.complaint_id = r.complaint_id WHERE c.complaint_id = ?", (c_id,))
                complaint = cursor.fetchone()
                if complaint: complaint['display_id'] = format_display_id(complaint['complaint_id'])
                conn.close()
        except: pass
    return render_template('track.html', complaint=complaint, search_id=search_id, active_page='track')

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    try:
        conn = get_db_connection(); cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
        execute_db(cursor, "SELECT * FROM complaints WHERE status = 'Pending' ORDER BY date_submitted DESC LIMIT 5"); urgent = cursor.fetchall() or []
        for c in urgent: c['display_id'] = format_display_id(c['complaint_id'])
        conn.close(); return render_template('admin/dashboard.html', stats=get_stats(), urgent_complaints=urgent, alerts=[], active_page='dashboard')
    except: return render_template('admin/dashboard.html', stats=get_stats(), urgent_complaints=[], alerts=[], active_page='dashboard')

@app.route('/admin/complaints')
@admin_required
def admin_complaints():
    try:
        conn = get_db_connection(); cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
        execute_db(cursor, "SELECT * FROM complaints ORDER BY date_submitted DESC"); complaints = cursor.fetchall() or []
        for c in complaints: c['display_id'] = format_display_id(c['complaint_id'])
        conn.close(); return render_template('admin/complaints.html', complaints=complaints, active_page='complaints')
    except: return render_template('admin/complaints.html', complaints=[], active_page='complaints')

@app.route('/admin/analytics')
@admin_required
def admin_analytics(): return render_template('admin/analytics.html', stats=get_stats(), active_page='analytics')

@app.route('/admin/users')
@admin_required
def admin_users():
    try:
        conn = get_db_connection(); cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
        execute_db(cursor, "SELECT * FROM users ORDER BY created_at DESC"); users = cursor.fetchall() or []; conn.close(); return render_template('admin/users.html', users=users, active_page='users')
    except: return render_template('admin/users.html', users=[], active_page='users')

@app.route('/admin/settings')
@admin_required
def admin_settings(): return render_template('admin/settings.html', active_page='settings')

@app.route('/api/admin/update-status', methods=['POST'])
@admin_required
def admin_update_status():
    try:
        data = request.json; c_id = data.get('complaint_id'); status = data.get('status'); action = data.get('action_taken')
        conn = get_db_connection(); cursor = conn.cursor(); execute_db(cursor, "UPDATE complaints SET status = ? WHERE complaint_id = ?", (status, c_id))
        if action:
            if IS_POSTGRES: execute_db(cursor, "INSERT INTO resolution (complaint_id, action_taken) VALUES (?, ?) ON CONFLICT (complaint_id) DO UPDATE SET action_taken = EXCLUDED.action_taken", (c_id, action))
            else: execute_db(cursor, "INSERT OR REPLACE INTO resolution (complaint_id, action_taken) VALUES (?, ?)", (c_id, action))
        conn.commit(); conn.close(); return jsonify({'success': True})
    except Exception as e: return jsonify({'success': False, 'message': str(e)})

@app.route('/api/admin/delete-complaint/<int:id>', methods=['DELETE'])
@admin_required
def admin_delete_complaint(id):
    try:
        conn = get_db_connection(); cursor = conn.cursor(); execute_db(cursor, "DELETE FROM complaints WHERE complaint_id = ?", (id,)); execute_db(cursor, "DELETE FROM resolution WHERE complaint_id = ?", (id,)); execute_db(cursor, "DELETE FROM votes WHERE complaint_id = ?", (id,))
        conn.commit(); conn.close(); return jsonify({'success': True})
    except Exception as e: return jsonify({'success': False, 'message': str(e)})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            email, password = request.form.get('email'), request.form.get('password'); conn = get_db_connection(); cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
            execute_db(cursor, "SELECT * FROM users WHERE email = ?", (email,)); user = cursor.fetchone(); conn.close()
            if user and check_password_hash(user['password_hash'], password):
                session['user'] = dict(user); return redirect(url_for('admin_dashboard' if user['role'] == 'admin' else 'index'))
            flash('Invalid credentials.', 'error')
        except: flash('Login error', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            p = request.form; hashed_pw = generate_password_hash(p['password']); conn = get_db_connection(); cursor = conn.cursor(); execute_db(cursor, "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)", (p['name'], p['email'], hashed_pw, p.get('role', 'citizen')))
            conn.commit(); conn.close(); flash('Account created! Please login.', 'success'); return redirect(url_for('login'))
        except Exception as e: flash(f'Registration Error: {e}', 'error')
    return render_template('register.html')

@app.route('/logout')
def logout(): session.pop('user', None); return redirect(url_for('index'))

@app.route('/api/locations/districts/<state>')
def api_get_districts(state): return jsonify(list(india_locations.get(state, {}).keys()))

@app.route('/api/locations/areas/<state>/<district>')
def api_get_areas(state, district): return jsonify(india_locations.get(state, {}).get(district, []))

@app.route('/live_map')
def live_map(): return render_template('live_map.html', active_page='live_map')

@app.route('/profile')
def profile():
    if not session.get('user'): return redirect(url_for('login'))
    return render_template('profile.html', active_page='profile')

if __name__ == "__main__":
    init_db(); app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
