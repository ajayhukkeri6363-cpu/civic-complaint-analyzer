
import os
import sys
from datetime import datetime

# Add current directory to path so we can import app
sys.path.append(os.getcwd())

from app import get_db_connection, execute_db, IS_POSTGRES, init_db

def force_repair():
    print(f"--- CIVIC ANALYZER DB REPAIR ---")
    print(f"Timestamp: {datetime.now()}")
    print(f"Environment: {'Postgres' if IS_POSTGRES else 'SQLite'}")
    
    try:
        # Run the full init_db sequence
        print("Step 1: Running init_db()...")
        init_db()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verify counts
        print("Step 2: Verifying data...")
        execute_db(cursor, "SELECT COUNT(*) as count FROM complaints")
        res = cursor.fetchone()
        count = res['count'] if res else 0
        
        print(f"Result: {count} complaints found in database.")
        
        if count == 0:
            print("WARNING: Database is still empty after init_db.")
        else:
            print("SUCCESS: Database is populated and ready.")
            
        conn.close()
        
    except Exception as e:
        print(f"CRITICAL ERROR during repair: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    force_repair()
