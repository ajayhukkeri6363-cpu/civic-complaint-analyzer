import requests
try:
    r = requests.get('http://127.0.0.1:5000/api/insights')
    if r.status_code == 200:
        data = r.json()
        print(f"Clusters: {len(data['clusters'])}")
        for c in data['clusters']:
            print(f" - {c['area']}: {c['issue_type']} ({c['count']})")
        print(f"Predictions: {len(data['predictions'])}")
        for p in data['predictions']:
            print(f" - {p['area']}: {p['risk_level']} (+{p['growth']}%)")
    else:
        print(f"Error {r.status_code}")
except Exception as e:
    print(f"Failed: {e}")
