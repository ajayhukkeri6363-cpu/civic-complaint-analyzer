import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Remove OTP Helpers
content = re.sub(
    r'(?s)# OTP Helpers\ndef generate_otp\(\):.*?print\(f"Failed to send email to \{recipient_email\}: \{e\}"\)',
    '',
    content
)

# 2. Rewrite /submit
new_submit = """@app.route('/submit', methods=['GET', 'POST'])
def submit():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        area = request.form.get('area')
        issue_type = request.form.get('issue_type')
        description = request.form.get('description')
        
        if not all([name, email, area, issue_type, description]):
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
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT complaint_id FROM complaints WHERE description = %s OR (citizen_email = %s AND issue_type = %s AND status = 'Pending')", (description, email, issue_type))
        if cursor.fetchone():
            conn.close()
            flash('This complaint looks invalid or duplicate', 'warning')
            return redirect(url_for('submit'))
            
        try:
            cursor.execute("INSERT INTO complaints (citizen_name, citizen_email, area, issue_type, description) VALUES (%s, %s, %s, %s, %s)", (name, email, area, issue_type, description))
            complaint_id = cursor.lastrowid
            conn.commit()
            flash(f'Complaint submitted successfully! Your Tracking ID: {format_display_id(complaint_id)}', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash('Database error. Please try again.', 'error')
            return redirect(url_for('submit'))
        finally:
            conn.close()
            
    return render_template('submit.html', active_page='submit')"""

content = re.sub(
    r'(?s)@app\.route\(\'/submit\', methods=\[\'GET\', \'POST\'\]\)\ndef submit\(\):.*?return render_template\(\'submit\.html\', active_page=\'submit\'\)',
    new_submit,
    content
)

# 3. Remove /verify-complaint and /resend-otp
content = re.sub(
    r'(?s)@app\.route\(\'/verify-complaint\', methods=\[\'GET\', \'POST\'\]\)\ndef verify_complaint\(\):.*?return jsonify\(\{\'success\': True, \'message\': \'A new OTP has been sent\.\'\}\)',
    '',
    content
)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done updating app.py")
