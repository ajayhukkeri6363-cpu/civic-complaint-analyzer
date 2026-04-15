import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

# We connect without specifying a database first to create it
try:
    conn = mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', '1234')
    )
    cursor = conn.cursor()
    
    # Read the schema file
    with open('database/schema.sql', 'r') as f:
        sql_script = f.read()
    
    # Execute the SQL statements
    # mysql.connector's execute accepts multi statements with multi=True
    for result in cursor.execute(sql_script, multi=True):
        if result.with_rows:
            print("Rows produced by statement '{}':".format(result.statement))
            print(result.fetchall())
        else:
            print("Number of rows affected by statement '{}': {}".format(
                result.statement, result.rowcount))

    conn.commit()
    print("Database schema executed successfully.")
    
except mysql.connector.Error as err:
    print(f"Error: {err}")
finally:
    if 'cursor' in locals() and cursor:
        cursor.close()
    if 'conn' in locals() and conn.is_connected():
        conn.close()
