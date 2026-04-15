import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_body = """@app.route('/api/live_complaints')
def api_live_complaints():
    from area_coords import area_coords
    import random as rng
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT complaint_id, citizen_name, area, issue_type, description, status, image_path, date_submitted FROM complaints ORDER BY date_submitted DESC LIMIT 100")
    complaints = cursor.fetchall()
    conn.close()
    result = []
    for c in complaints:
        area = c['area'].strip()
        area_lower = area.lower()
        base = None
        # Exact match first
        for key, coords in area_coords.items():
            if key.lower() == area_lower:
                base = coords
                break
        # Fuzzy match fallback
        if not base:
            for key, coords in area_coords.items():
                if key.lower() in area_lower or area_lower in key.lower():
                    base = coords
                    break
        # Default India center
        if not base:
            base = [20.5937, 78.9629]
        jitter_lat = base[0] + rng.uniform(-0.04, 0.04)
        jitter_lng = base[1] + rng.uniform(-0.04, 0.04)
        img_url = f"/static/{c['image_path']}" if c.get('image_path') else None
        desc = c['description']
        result.append({
            'id': format_display_id(c['complaint_id']),
            'area': c['area'],
            'issue_type': c['issue_type'],
            'description': desc[:120] + ('...' if len(desc) > 120 else ''),
            'status': c['status'],
            'lat': round(jitter_lat, 6),
            'lng': round(jitter_lng, 6),
            'image_url': img_url
        })
    return jsonify(result)"""

content = re.sub(
    r"(?s)@app\.route\('/api/live_complaints'\)\ndef api_live_complaints\(\):.*?return jsonify\(result\)",
    new_body,
    content
)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")
