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
import traceback
from email_validator import validate_email, EmailNotValidError
from india_locations import india_locations

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-123')
app.debug = True # FORCE DEBUG MODE

# --- DATABASE CONFIG ---
DATABASE_URL = os.getenv('DATABASE_URL')
IS_POSTGRES = DATABASE_URL and DATABASE_URL.startswith('postgres')

def get_db_connection():
    if IS_POSTGRES:
        try:
            # Force SSL for Render
            protocol_fixed_url = DATABASE_URL.replace('postgres://', 'postgresql://')
            if 'sslmode' not in protocol_fixed_url:
                protocol_fixed_url += '&sslmode=require' if '?' in protocol_fixed_url else '?sslmode=require'
            
            conn = psycopg2.connect(protocol_fixed_url, cursor_factory=RealDictCursor, connect_timeout=10)
            return conn
        except Exception as e:
            print(f"DATABASE_CONNECTION_CRITICAL_FAIL: {e}")
            raise e
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

# REMOVED CUSTOM ERROR HANDLER TEMPORARILY TO SEE REAL ERRORS

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
        
        # Insert Dummy Data if empty
        execute_db(cursor, "SELECT COUNT(*) as count FROM complaints")
        if cursor.fetchone()['count'] == 0:
            print("LOG: INSERTING_DUMMY_DATA")
            execute_db(cursor, "INSERT INTO complaints (citizen_name, citizen_email, state, district, area, issue_type, description, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       ('System', 'admin@civic.com', 'Karnataka', 'Bangalore', 'Indiranagar', 'Road & Infrastructure', 'System test complaint', 'Pending'))
            conn.commit()
            
        conn.close()
    except Exception as e:
        print(f"LOG: SCHEMA_INIT_FAIL: {e}")
        traceback.print_exc()

def get_stats():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
        execute_db(cursor, "SELECT COUNT(*) as total FROM complaints")
        total = cursor.fetchone()['total']
        execute_db(cursor, "SELECT COUNT(*) as resolved FROM complaints WHERE status = 'Resolved'")
        resolved = cursor.fetchone()['resolved']
        execute_db(cursor, "SELECT COUNT(*) as active FROM complaints WHERE status != 'Resolved'")
        active = cursor.fetchone()['active']
        
        execute_db(cursor, "SELECT issue_type, COUNT(*) as count FROM complaints GROUP BY issue_type ORDER BY count DESC LIMIT 1")
        res = cursor.fetchone()
        top_issue = res['issue_type'] if res else "N/A"
        
        conn.close()
        return {'total': total, 'resolved': resolved, 'active': active, 'pending': active, 'top_issue': top_issue}
    except: return {'total': 0, 'resolved': 0, 'active': 0, 'pending': 0, 'top_issue': "N/A"}

# --- AUTH ---
def admin_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session or session['user']['role'] != 'admin': 
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_user(): return dict(user=session.get('user'))

# --- ROUTES ---
@app.route('/')
def index():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
        execute_db(cursor, "SELECT c.*, (SELECT COUNT(*) FROM votes v WHERE v.complaint_id = c.complaint_id) as vote_count FROM complaints c ORDER BY vote_count DESC LIMIT 3")
        top_priority = cursor.fetchall()
        for c in top_priority: c['display_id'] = format_display_id(c['complaint_id'])
        execute_db(cursor, "SELECT c.*, (SELECT COUNT(*) FROM votes v WHERE v.complaint_id = c.complaint_id) as vote_count FROM complaints c ORDER BY date_submitted DESC LIMIT 30")
        all_c = cursor.fetchall()
        def safe_cat(list_c, term): return [c for c in list_c if c.get('issue_type') and term.lower() in c['issue_type'].lower()]
        categories = {
            'Road & Infrastructure': safe_cat(all_c, 'road'),
            'Water Supply': safe_cat(all_c, 'water'),
            'Electricity': safe_cat(all_c, 'electr'),
            'Garbage': safe_cat(all_c, 'garbag')
        }
        for cat in categories.values():
            for c in cat: c['display_id'] = format_display_id(c['complaint_id'])
        conn.close()
        return render_template('index.html', top_priority=top_priority, categories=categories, active_page='index')
    except Exception as e:
        print("INDEX_CRASH:", e)
        traceback.print_exc()
        return render_template('index.html', top_priority=[], categories={}, active_page='index')

@app.route('/submit', methods=['GET', 'POST'])
def submit():
    if request.method == 'POST':
        try:
            p = request.form
            lat, lng = area_coords.get(p['area'], area_coords.get(p['district'], (12.9716, 77.5946)))
            conn = get_db_connection()
            cursor = conn.cursor()
            execute_db(cursor, "INSERT INTO complaints (citizen_name, citizen_email, state, district, area, issue_type, description, latitude, longitude) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", 
                       (p['name'], p['email'], p['state'], p['district'], p['area'], p['issue_type'], p['description'], lat, lng))
            conn.commit()
            conn.close()
            flash('Complaint submitted successfully!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            print("SUBMIT_CRASH:", e)
            traceback.print_exc()
            flash(f'Error: {e}', 'error')
            return redirect(url_for('submit'))
    return render_template('submit.html', active_page='submit')

@app.route('/analytics')
def analytics():
    try:
        # DEBUG: Print data before rendering
        stats = get_stats()
        print("LOG: ANALYTICS_STATS_FETCHED", stats)
        return render_template('analytics.html', stats=stats, issues_data=[], locations_data=[], active_page='analytics')
    except Exception as e:
        print("ANALYTICS_PAGE_CRASH_REPORT:")
        traceback.print_exc()
        return f"<h1>ANALYTICS CRASH: {e}</h1><pre>{traceback.format_exc()}</pre>"

@app.route('/api/analytics')
def api_analytics():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
        execute_db(cursor, "SELECT issue_type, COUNT(*) as count FROM complaints GROUP BY issue_type")
        by_issue = cursor.fetchall() or []
        execute_db(cursor, "SELECT area, COUNT(*) as count FROM complaints GROUP BY area")
        by_area = cursor.fetchall() or []
        if IS_POSTGRES: execute_db(cursor, "SELECT TO_CHAR(date_submitted, 'YYYY-MM') as month, COUNT(*) as count FROM complaints GROUP BY month ORDER BY month")
        else: execute_db(cursor, "SELECT strftime('%Y-%m', date_submitted) as month, COUNT(*) as count FROM complaints GROUP BY month ORDER BY month")
        trends = cursor.fetchall() or []
        conn.close()
        return jsonify({
            'issue_types': {'labels': [r.get('issue_type', 'N/A') for r in by_issue], 'data': [r.get('count', 0) for r in by_issue]},
            'areas': {'labels': [r.get('area', 'N/A') for r in by_area], 'data': [r.get('count', 0) for r in by_area]},
            'monthly': {'labels': [r.get('month', 'N/A') for r in trends], 'data': [r.get('count', 0) for r in trends]},
            'total_complaints': sum(r.get('count', 0) for r in by_issue)
        })
    except Exception as e:
        print("API_ANALYTICS_CRASH:", e)
        traceback.print_exc()
        return jsonify({'error': str(e), 'trace': traceback.format_exc()})

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
        execute_db(cursor, "SELECT * FROM complaints WHERE status = 'Pending' ORDER BY date_submitted DESC LIMIT 5")
        urgent = cursor.fetchall()
        for c in urgent: c['display_id'] = format_display_id(c['complaint_id'])
        conn.close()
        return render_template('admin/dashboard.html', stats=get_stats(), urgent_complaints=urgent, alerts=[], active_page='dashboard')
    except Exception as e:
        print("ADMIN_DASHBOARD_CRASH:", e)
        traceback.print_exc()
        return render_template('admin/dashboard.html', stats=get_stats(), urgent_complaints=[], alerts=[], active_page='dashboard')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            email, password = request.form.get('email'), request.form.get('password')
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor) if IS_POSTGRES else conn.cursor()
            execute_db(cursor, "SELECT * FROM users WHERE email = ?", (email,))
            user = cursor.fetchone()
            conn.close()
            if user and check_password_hash(user['password_hash'], password):
                session['user'] = dict(user)
                return redirect(url_for('admin_dashboard' if user['role'] == 'admin' else 'index'))
            flash('Invalid credentials.', 'error')
        except Exception as e: flash(f'Login Error: {e}', 'error')
    return render_template('login.html')

# --- INIT ---
safe_init = init_db()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
