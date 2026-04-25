import os
from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def index():
    return "<h1>🌌 CINEMATIC ENGINE: HEARTBEAT ACTIVE</h1><p>If you see this, the server is ALIVE. The error is in the database connection or logic. Standby for restoration...</p>"

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
