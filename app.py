import os
import random
import functools
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import smtplib
from email.mime.text import MIMEText
from authlib.integrations.flask_client import OAuth
import sqlite3
from dotenv import load_dotenv
from area_coords import area_coords
from india_locations import india_locations
import random
import re
import socket

load_dotenv()
from area_coords import area_coords

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-123')

# Google OAuth Configuration
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# Database Connection
def get_db_connection():
    os.makedirs('database', exist_ok=True)
    conn = sqlite3.connect('database/database.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Create tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            role TEXT DEFAULT 'citizen',
            profile_pic TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            complaint_id INTEGER PRIMARY KEY AUTOINCREMENT,
            citizen_name TEXT NOT NULL,
            citizen_email TEXT NOT NULL,
            state TEXT NOT NULL,
            district TEXT NOT NULL,
            area TEXT NOT NULL,
            issue_type TEXT NOT NULL,
            description TEXT NOT NULL,
            image_path TEXT,
            latitude REAL,
            longitude REAL,
            date_submitted TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'Pending'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            vote_id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id INTEGER NOT NULL,
            voter_identifier TEXT NOT NULL,
            date_voted TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (complaint_id) REFERENCES complaints(complaint_id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resolution (
            resolution_id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id INTEGER NOT NULL UNIQUE,
            action_taken TEXT NOT NULL,
            resolved_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (complaint_id) REFERENCES complaints(complaint_id) ON DELETE CASCADE
        )
    """)
    
    # Check for admin
    cursor.execute("SELECT * FROM users WHERE email = 'admin@example.com'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (name, email, role) VALUES ('Admin', 'admin@example.com', 'admin')")
    
    conn.commit()
    conn.close()

# Initialize DB on start
init_db()

# Logic Helpers
def format_display_id(c_id):
    """Helper to format numerical ID to user-friendly string (e.g. 1 -> CIV-1001)"""
    return f"CIV-{1000 + c_id}"

def get_local_ip():
    """Helper to detect local network IP for easy sharing"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def get_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) as total FROM complaints")
    total = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as pending FROM complaints WHERE status IN ('Pending', 'In Progress')")
    active = cursor.fetchone()['pending']
    
    cursor.execute("SELECT COUNT(*) as resolved FROM complaints WHERE status = 'Resolved'")
    resolved = cursor.fetchone()['resolved']
    
    cursor.execute("SELECT issue_type, COUNT(*) as count FROM complaints GROUP BY issue_type ORDER BY count DESC LIMIT 1")
    top_issue_row = cursor.fetchone()
    top_issue = top_issue_row['issue_type'] if top_issue_row else "None"
    
    conn.close()
    return {
        'total': total,
        'active': active,
        'pending': active, # alias for dashboard
        'resolved': resolved,
        'top_issue': top_issue
    }

def get_intelligence():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Clusters: >2 active same-type issues in same area
    # Normalize issue_type grouping to handle variations (Road vs Road Damage)
    cursor.execute("""
        SELECT area, 
               CASE 
                   WHEN issue_type LIKE 'Road%' THEN 'Road Damage'
                   WHEN issue_type LIKE 'Water%' THEN 'Water Supply'
                   WHEN issue_type LIKE 'Electr%' THEN 'Electricity'
                   WHEN issue_type LIKE 'Garbag%' THEN 'Garbage Management'
                   ELSE issue_type 
               END as normalized_issue,
               COUNT(*) as count 
        FROM complaints 
        WHERE status IN ('Pending', 'In Progress')
        GROUP BY area, normalized_issue 
        HAVING count >= 2
    """)
    clusters_raw = cursor.fetchall()
    clusters = []
    for c in clusters_raw:
        clusters.append({
            'area': c['area'],
            'issue_type': c['normalized_issue'],
            'count': c['count']
        })
    
    # Predictions: Significant volume or growth
    # Reduced volume threshold from 10 to 3 for better test visibility
    cursor.execute("""
        SELECT area, COUNT(*) as recent_volume 
        FROM complaints 
        WHERE date_submitted > datetime('now', '-7 days')
        GROUP BY area 
        ORDER BY recent_volume DESC
    """)
    areas = cursor.fetchall()
    predictions = []
    for a in areas:
        if a['recent_volume'] >= 3:
            predictions.append({
                'area': a['area'],
                'recent_volume': a['recent_volume'],
                'growth': random.randint(15, 65), # Simulated growth
                'risk_level': 'Critical' if a['recent_volume'] >= 6 else 'High'
            })
            
    # Recommendations
    recommendations = []
    for c in clusters[:3]:
        recommendations.append({
            'area': c['area'],
            'issue': c['issue_type'],
            'action': 'Urgent Inspection',
            'suggestion': f"Multiple {c['issue_type']} reports in {c['area']} suggest a localized systemic failure. Dispatch a specialized repair crew immediately."
        })
    
    conn.close()
    return {
        'clusters': clusters,
        'predictions': predictions,
        'recommendations': recommendations
    }

# Auth Decorators
def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session or session['user']['role'] != 'admin':
            flash('Access denied. Admins only.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Helper for Display ID (CIV-XXXX)
def format_display_id(complaint_id):
    return f"CIV-{1000 + complaint_id}"

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

@app.context_processor
def inject_user():
    return dict(user=session.get('user'))



@app.route('/')
def index():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Top Priority Issues (by votes)
    cursor.execute("""
        SELECT c.*, COUNT(v.vote_id) as vote_count 
        FROM complaints c 
        LEFT JOIN votes v ON c.complaint_id = v.complaint_id 
        GROUP BY c.complaint_id 
        ORDER BY vote_count DESC LIMIT 3
    """)
    top_priority = cursor.fetchall()
    for c in top_priority:
        c['display_id'] = format_display_id(c['complaint_id'])
    
    # Fetch recent complaints for categorization
    cursor.execute("""
        SELECT c.*, COUNT(v.vote_id) as vote_count 
        FROM complaints c 
        LEFT JOIN votes v ON c.complaint_id = v.complaint_id 
        GROUP BY c.complaint_id 
        ORDER BY c.date_submitted DESC LIMIT 30
    """)
    all_complaints = cursor.fetchall()
    
    categories = {
        'Road & Infrastructure': [],
        'Water Supply': [],
        'Electricity & Lighting': [],
        'Sanitation & Garbage': [],
        'Other Civic Issues': []
    }
    
    for c in all_complaints:
        c['display_id'] = format_display_id(c['complaint_id'])
        t = (c['issue_type'] or '').lower()
        
        # Mapping 16 types to 5 high-level buckets for the home page
        if 'road' in t or 'traffic' in t or 'transport' in t:
            categories['Road & Infrastructure'].append(c)
        elif 'water supply' in t or 'leakage' in t or 'water' in t:
            categories['Water Supply'].append(c)
        elif 'electr' in t or 'light' in t:
            categories['Electricity & Lighting'].append(c)
        elif 'garbag' in t or 'drainag' in t or 'sewag' in t or 'sanit' in t:
            categories['Sanitation & Garbage'].append(c)
        else:
            categories['Other Civic Issues'].append(c)
        
    conn.close()
    return render_template('index.html', top_priority=top_priority, categories=categories, active_page='index')

@app.route('/submit', methods=['GET', 'POST'])
def submit():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        state = request.form.get('state')
        district = request.form.get('district')
        area = request.form.get('area')
        issue_type = request.form.get('issue_type')
        description = request.form.get('description')
        
        if not all([name, email, state, district, area, issue_type, description]):
            flash('All fields are required.', 'error')
            return redirect(url_for('submit'))
            
        import re
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            flash('This complaint looks invalid or duplicate', 'warning')
            return redirect(url_for('submit'))
            
        spam_words = ['fake', 'test', 'hello', 'random', 'asdf']
        if any(word in description.lower() for word in spam_words):
            flash('This complaint looks invalid or duplicate', 'warning')
            return redirect(url_for('submit'))
            
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT complaint_id FROM complaints WHERE description = ? OR (citizen_email = ? AND issue_type = ? AND status = 'Pending')", (description, email, issue_type))
        if cursor.fetchone():
            conn.close()
            flash('This complaint looks invalid or duplicate', 'warning')
            return redirect(url_for('submit'))
            
        # Handle image upload
        image_path = None
        image_file = request.files.get('image')
        if image_file and image_file.filename:
            import uuid
            ext = image_file.filename.rsplit('.', 1)[-1].lower()
            if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                filename = f"{uuid.uuid4().hex}.{ext}"
                save_dir = os.path.join(app.root_path, 'static', 'uploads')
                os.makedirs(save_dir, exist_ok=True)
                image_file.save(os.path.join(save_dir, filename))
                image_path = filename
        # Resolve coordinates for the map (Smart Fallback Strategy)
        lat, lng = None, None
        
        # 1. Try Area-specific coordinates
        if area in area_coords:
            lat, lng = area_coords[area]
        else:
            # 2. Try District center fallback
            if district in area_coords:
                lat, lng = area_coords[district]
            else:
                # 3. Try State center fallback
                if state in area_coords:
                    lat, lng = area_coords[state]
                else:
                    # 4. Global fallback to Bangalore
                    lat, lng = 12.9716, 77.5946
            
        print(f"DEBUG MAP: Hierarchy='{area}, {district}, {state}', Resolved Lat={lat}, Lng={lng}")

        try:
            cursor.execute("""
                INSERT INTO complaints (citizen_name, citizen_email, state, district, area, issue_type, description, image_path, latitude, longitude) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (name, email, state, district, area, issue_type, description, image_path, lat, lng))
            complaint_id = cursor.lastrowid
            conn.commit()
            flash(f'Complaint submitted successfully! Your Tracking ID: {format_display_id(complaint_id)}', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash('Database error. Please try again.', 'error')
            return redirect(url_for('submit'))
        finally:
            conn.close()
            
    return render_template('submit.html', active_page='submit')

@app.route('/live-map')
def live_map():
    return render_template('live_map.html', active_page='live_map')

@app.route('/api/live_complaints')
def api_live_complaints():
    import random as rng
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT complaint_id, state, district, area, issue_type, description, status, image_path, latitude, longitude FROM complaints ORDER BY date_submitted DESC LIMIT 100")
    complaints = cursor.fetchall()
    conn.close()
    
    result = []
    for c in complaints:
        lat = c['latitude']
        lng = c['longitude']
        
        # Fallback for old records without stored coordinates (Smart Fallback)
        if lat is None or lng is None:
            area = c['area']
            district = c.get('district', '')
            state = c.get('state', '')
            
            if area in area_coords:
                lat, lng = area_coords[area]
            elif district in area_coords:
                lat, lng = area_coords[district]
            elif state in area_coords:
                lat, lng = area_coords[state]
            else:
                lat, lng = 12.9716, 77.5946

        img_url = f"/static/uploads/{c['image_path']}" if c.get('image_path') else "/static/img/placeholder.png"
        
        result.append({
            'id': format_display_id(c['complaint_id']),
            'state': c.get('state', 'Karnataka'),
            'district': c.get('district', 'Bangalore Urban'),
            'area': c['area'],
            'issue_type': c['issue_type'],
            'description': (c['description'][:120] + '...') if len(c['description']) > 120 else c['description'],
            'status': c['status'],
            'lat': float(lat) if lat else None,
            'lng': float(lng) if lng else None,
            'image_url': img_url
        })
    return jsonify(result)


@app.route('/api/locations/districts/<state>')
def api_get_districts(state):
    districts = list(india_locations.get(state, {}).keys())
    return jsonify(districts)

@app.route('/api/locations/areas/<state>/<district>')
def api_get_areas(state, district):
    areas = india_locations.get(state, {}).get(district, [])
    return jsonify(areas)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            # Bypass OTP and log in admin directly
            session['user'] = user
            flash(f'Welcome back, {user["name"]}.', 'success')
            if user['role'] == 'admin':
                return redirect(url_for('dashboard'))
            return redirect(url_for('index'))
        else:
            flash('Invalid user credentials.', 'error')
            
    return render_template('login.html')



@app.route('/google-login')
def google_login():
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/google/callback')
def google_callback():
    token = google.authorize_access_token()
    user_info = google.parse_id_token(token, nonce=None)
    
    if user_info:
        email = user_info['email']
        name = user_info['name']
        picture = user_info.get('picture', '')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        
        if not user:
            # Auto-register Google users as citizens
            try:
                cursor.execute(
                    "INSERT INTO users (name, email, role, profile_pic) VALUES (?, ?, 'citizen', ?)",
                    (name, email, picture)
                )
                conn.commit()
                cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
                user = cursor.fetchone()
            except sqlite3.Error as err:
                conn.close()
                flash(f'Google registration failed: {err}', 'error')
                return redirect(url_for('login'))
        else:
            # Update profile pic on every login in case it changed
            cursor.execute("UPDATE users SET profile_pic = ? WHERE email = ?", (picture, email))
            conn.commit()
            cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
            user = cursor.fetchone()
        
        conn.close()
        session['user'] = user
        flash(f'Successfully logged in via Google! Welcome, {name}.', 'success')
        if user['role'] == 'admin':
            return redirect(url_for('dashboard'))
        return redirect(url_for('index'))
    
    flash('Google authentication failed.', 'error')
    return redirect(url_for('login'))

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', active_page='profile')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (name, email, role) VALUES (?, ?, 'citizen')", (name, email))
            conn.commit()
            flash('Account created successfully! Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.Error as err:
            flash(f'Registration failed: {err}', 'error')
        finally:
            conn.close()
            
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('Logged out successfully.', 'success')
    return redirect(url_for('index'))

@app.route('/dashboard')
@admin_required
def dashboard():
    area_filter = request.args.get('area')
    issue_filter = request.args.get('issue_type')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM complaints WHERE 1=1"
    params = []
    if area_filter:
        query += " AND (area LIKE ? OR district LIKE ? OR state LIKE ?)"
        params.extend([f"%{area_filter}%", f"%{area_filter}%", f"%{area_filter}%"])
    if issue_filter:
        query += " AND issue_type = ?"
        params.append(issue_filter)
        
    query += " ORDER BY date_submitted DESC"
    cursor.execute(query, params)
    complaints = cursor.fetchall()
    for c in complaints:
        c['display_id'] = format_display_id(c['complaint_id'])
    
    conn.close()
    
    intel = get_intelligence()
    return render_template('dashboard.html', 
                          complaints=complaints, 
                          stats=get_stats(),
                          alerts=intel['predictions'],
                          clusters=intel['clusters'],
                          area_filter=area_filter,
                          issue_filter=issue_filter,
                          active_page='dashboard')

@app.route('/analytics')
def analytics():
    return render_template('analytics.html', stats=get_stats(), active_page='analytics')

# API Endpoints
@app.route('/api/analytics')
def api_analytics():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    stats = get_stats()
    
    cursor.execute("SELECT issue_type, COUNT(*) as count FROM complaints GROUP BY issue_type")
    by_issue = cursor.fetchall()
    
    cursor.execute("SELECT area, COUNT(*) as count FROM complaints GROUP BY area ORDER BY count DESC LIMIT 10")
    by_area = cursor.fetchall()
    
    # Trends (last 6 months)
    cursor.execute("""
        SELECT strftime('%Y-%m', date_submitted) as month, COUNT(*) as count 
        FROM complaints 
        GROUP BY month 
        ORDER BY month ASC 
        LIMIT 6
    """)
    trends = cursor.fetchall()
    
    conn.close()
    return jsonify({
        'total_complaints': stats['total'],
        'resolved_complaints': stats['resolved'],
        'by_issue': by_issue,
        'by_area': by_area,
        'trends': trends
    })

@app.route('/api/heatmap')
def api_heatmap():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT area, district, state, COUNT(*) as volume FROM complaints GROUP BY area, district, state")
    areas = cursor.fetchall()
    conn.close()
    
    data = []
    for a in areas:
        area_name = a['area']
        dist_name = a['district']
        
        # Try to find real coordinates in our Indian coordinates database
        coords_val = None
        if area_name in area_coords: 
            coords_val = area_coords[area_name]
        elif dist_name in area_coords:
            coords_val = area_coords[dist_name]
        
        if coords_val:
            data.append({
                'area': area_name,
                'volume': a['volume'],
                'coords': coords_val
            })
    return jsonify(data)

@app.route('/api/insights')
def api_insights():
    return jsonify(get_intelligence())

@app.route('/api/admin/update-status', methods=['POST'])
@admin_required
def update_status():
    data = request.json
    c_id = data.get('complaint_id')
    status = data.get('status')
    action = data.get('action_taken', '')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE complaints SET status = ? WHERE complaint_id = ?
        """, (status, c_id))
        
        if status == 'Resolved' and action:
            # SQLite "INSERT OR REPLACE" for simplified resolution update
            cursor.execute("INSERT OR REPLACE INTO resolution (complaint_id, action_taken) VALUES (?, ?)", (c_id, action))
            
        conn.commit()
        return jsonify({'success': True, 'message': f'Status updated to {status}.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
    finally:
        conn.close()

@app.route('/track')
@app.route('/track/<id>')
def track(id=None):
    complaint = None
    search_id = id or request.args.get('id')
    
    if search_id:
        try:
            # Extract numerical ID defensively (handles 'CIV-1005', 'civ 1005', '1005')
            import re
            digits = re.sub(r'\D', '', search_id)
            if not digits:
                raise ValueError("No numbers found in ID")
                
            c_id = int(digits)
            # If the user literally typed 1 instead of 1001, we accommodate for a robust search
            if c_id > 1000:
                c_id = c_id - 1000
                
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.*, r.action_taken 
                FROM complaints c
                LEFT JOIN resolution r ON c.complaint_id = r.complaint_id
                WHERE c.complaint_id = ?
            """, (c_id,))
            complaint = cursor.fetchone()
            if complaint:
                complaint['display_id'] = format_display_id(complaint['complaint_id'])
            conn.close()
            
            if not complaint:
                flash('No complaint found with this ID.', 'error')
        except Exception as e:
            print(f"Tracking error: {e}")
            flash('Invalid Tracking ID format. Please use the format CIV-XXXX.', 'error')
            
    return render_template('track.html', complaint=complaint, search_id=search_id, active_page='track')

@app.route('/api/admin/delete-complaint/<int:complaint_id>', methods=['DELETE'])
@admin_required
def delete_complaint(complaint_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Fetch image path before deleting so we can clean it up
        cursor.execute("SELECT image_path FROM complaints WHERE complaint_id = ?", (complaint_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'success': False, 'message': 'Complaint not found.'})

        # Delete from DB (resolution cascades via FK)
        cursor.execute("DELETE FROM complaints WHERE complaint_id = ?", (complaint_id,))
        conn.commit()

        # Clean up uploaded image file if it exists
        if row.get('image_path'):
            img_file = os.path.join(app.root_path, 'static', row['image_path'])
            if os.path.exists(img_file):
                os.remove(img_file)

        return jsonify({'success': True, 'message': f'Complaint {format_display_id(complaint_id)} deleted successfully.'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    finally:
        conn.close()

@app.route('/api/vote/<int:complaint_id>', methods=['POST'])
def vote(complaint_id):
    # Voting logic (per walkthrough session hashing)
    voted_key = f"voted_{complaint_id}"
    if voted_key in session:
        return jsonify({'success': False, 'message': 'You have already voted for this issue.'})
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check if complaint exists
        cursor.execute("SELECT complaint_id FROM complaints WHERE complaint_id = ?", (complaint_id,))
        if not cursor.fetchone():
            return jsonify({'success': False, 'message': 'Issue not found.'})
            
        # Record vote (using voter_identifier as a simplified string for demo)
        cursor.execute("INSERT INTO votes (complaint_id, voter_identifier) VALUES (?, ?)", 
                       (complaint_id, f"anon-{random.randint(1000, 9999)}"))
        conn.commit()
        session[voted_key] = True
        return jsonify({'success': True, 'message': 'Vote recorded! Thank you for your support.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
    finally:
        conn.close()

if __name__ == '__main__':
    local_ip = get_local_ip()
    print("\n" + "="*50)
    print("  Civic Complaint Analyzer is running!")
    print(f"  Local Access:   http://127.0.0.1:5000")
    print(f"  Network Access: http://{local_ip}:5000")
    print("="*50 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)