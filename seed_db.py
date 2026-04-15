import mysql.connector
import os
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

def seed_data():
    try:
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', '1234'),
            database=os.getenv('DB_NAME', 'civic_complaints')
        )
        cursor = conn.cursor()
        
        # Clear existing to ensure clean demo
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        cursor.execute("TRUNCATE TABLE complaints")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        
        areas = ["Richmond", "Sunset", "Mission", "SoMa", "Noe Valley", "Marina", "Haight-Ashbury", "Nob Hill"]
        issue_types = ["Road", "Water", "Electricity", "Garbage", "Other"]
        statuses = ["Pending", "In Progress", "Resolved"]
        
        complaints_to_add = []
        
        # 1. Create a "RISING RISK" area (Richmond)
        # Previous 7-14 days: 2 complaints
        # Recent 0-7 days: 12 complaints (significant spike)
        for i in range(2):
            complaints_to_add.append(("John Doe", "john@ex.com", "Richmond", "Road", "Old issue", datetime.now() - timedelta(days=10), "Resolved"))
        for i in range(12):
            complaints_to_add.append(("New Reporter", "new@ex.com", "Richmond", "Road", "New pothole cluster", datetime.now() - timedelta(days=2), "Pending"))

        # 2. Create "CLUSTERS" in Mission
        # 5 Garbage issues in Mission
        for i in range(5):
            complaints_to_add.append(("Citizen", "c@ex.com", "Mission", "Garbage", "Garbage pile up", datetime.now() - timedelta(days=1), "Pending"))
        # 4 Water issues in Mission
        for i in range(4):
            complaints_to_add.append(("Citizen", "c@ex.com", "Mission", "Water", "Leaking pipe", datetime.now() - timedelta(days=3), "In Progress"))

        # 3. Create a "CRITICAL VOLUME" area (Sunset)
        # 16 complaints in last 7 days
        for i in range(16):
            complaints_to_add.append(("Resident", "r@ex.com", "Sunset", "Other", "High volume test", datetime.now() - timedelta(days=random.randint(0,6)), "Pending"))

        # 4. Fill in the rest for decent charts
        for i in range(30):
            area = random.choice(areas)
            issue_type = random.choice(issue_types)
            days_ago = random.randint(0, 30)
            date_submitted = datetime.now() - timedelta(days=days_ago)
            status = random.choice(statuses)
            complaints_to_add.append((f"User {i}", "u@ex.com", area, issue_type, "Simulated data", date_submitted, status))

        cursor.executemany('''
            INSERT INTO complaints (citizen_name, citizen_email, area, issue_type, description, date_submitted, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', complaints_to_add)
        
        # Add a vote for each complaint to match new business logic
        cursor.execute("SELECT complaint_id FROM complaints")
        complaint_ids = cursor.fetchall()
        for c in complaint_ids:
            # Use 'System' or random IPs to simulate reporter vote
            voter_id = f"Reporter-{c[0]}"
            cursor.execute("INSERT INTO votes (complaint_id, voter_identifier) VALUES (%s, %s)", (c[0], voter_id))

        conn.commit()
        print(f"Successfully seeded {len(complaints_to_add)} complaints with initial votes.")
        
    except mysql.connector.Error as err:
        print(f"Error: {err}")
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals() and conn.is_connected(): conn.close()

if __name__ == '__main__':
    seed_data()
