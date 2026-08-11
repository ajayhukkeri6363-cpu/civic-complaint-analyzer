import json
import concurrent.futures
import urllib.request
import urllib.parse
import time
import os

def clean_area_name(area):
    suffixes_to_remove = [" City", " Town", " Rural", " Urban", " North", " South", " East", " West", " Central"]
    clean_name = area
    for s in suffixes_to_remove:
        if clean_name.endswith(s):
            clean_name = clean_name[:-len(s)]
    return clean_name.strip()

def fetch_url(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) CivicAnalyzer/1.0'})
    return json.loads(urllib.request.urlopen(req, timeout=4).read().decode('utf-8'))

def fetch_mla(area):
    try:
        search_term = clean_area_name(area)
        
        search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(search_term + ' Assembly constituency')}&utf8=&format=json"
        res = fetch_url(search_url)
        
        if not res.get('query', {}).get('search'):
            search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(search_term)}&utf8=&format=json"
            res = fetch_url(search_url)
            
        if not res.get('query', {}).get('search'):
            return area, "MLA Data Unavailable"
            
        pageid = res['query']['search'][0]['pageid']
        page_url = f"https://en.wikipedia.org/w/api.php?action=query&prop=revisions&rvprop=content&rvslots=main&pageids={pageid}&format=json"
        res2 = fetch_url(page_url)
        content = res2['query']['pages'][str(pageid)]['revisions'][0]['slots']['main']['*']
        
        for line in content.split('\n'):
            if '| mla ' in line.lower() or '| member ' in line.lower() or '| name ' in line.lower():
                val = line.split('=')[-1].strip().split('<')[0].split('{')[0].replace('[[', '').replace(']]', '').split('|')[-1].strip()
                if len(val) > 3 and val.lower() != 'nan':
                    return area, val
        return area, "MLA Data Unavailable"
    except Exception as e:
        return area, "MLA Data Unavailable"

def main():
    print("Loading india_locations.json...")
    with open('static/data/india_locations.json', 'r', encoding='utf-8') as f:
        india_locs = json.load(f)
        
    areas_to_search = set()
    for state, districts in india_locs.items():
        for district, areas in districts.items():
            for area in areas:
                areas_to_search.add(area)
                
    areas_to_search = list(areas_to_search)
    print(f"Total unique areas: {len(areas_to_search)}")
    
    existing_data = {'mlas': {}, 'mps': {}}
    if os.path.exists('india_reps.json'):
        with open('india_reps.json', 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
            
    mlas = existing_data.get('mlas', {})
    areas_to_fetch = [a for a in areas_to_search if a.lower() not in mlas or mlas[a.lower()] in ["MLA Data Unavailable", "Pending Allocation", "Unassigned"]]
    print(f"Areas to fetch: {len(areas_to_fetch)}")
    
    start_time = time.time()
    count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_area = {executor.submit(fetch_mla, area): area for area in areas_to_fetch}
        for future in concurrent.futures.as_completed(future_to_area):
            area, mla = future.result()
            mlas[area.lower()] = mla
            count += 1
            if count % 100 == 0:
                print(f"Progress: {count}/{len(areas_to_fetch)}")
                
    print(f"Scraping finished in {time.time() - start_time:.2f} seconds")
    existing_data['mlas'] = mlas
    with open('india_reps.json', 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, indent=4)
        
if __name__ == '__main__':
    main()
    
    # Load existing india_reps.json to not lose the MP data!
    existing_data = {'mlas': {}, 'mps': {}}
    if os.path.exists('india_reps.json'):
        with open('india_reps.json', 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
            
    # We will only fetch MLAs that are missing or "MLA Data Unavailable"
    # Actually, let's fetch all of them to be 100% sure the name cleaning works and finds Araria!
    # But maybe we can skip existing ones that are NOT "MLA Data Unavailable" to save time?
    # User said "DO IT FAST". So let's skip ones we already have successfully scraped!
    areas_to_fetch = []
    mlas = existing_data.get('mlas', {})
    
    for area in areas_to_search:
        area_lower = area.lower()
        if area_lower not in mlas or mlas[area_lower] in ["MLA Data Unavailable", "Pending Allocation", "Unassigned"]:
            areas_to_fetch.append(area)
            
    print(f"Areas that need to be scraped/re-scraped: {len(areas_to_fetch)}")
    
    start_time = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        results = list(executor.map(fetch_mla, areas_to_fetch))
        
    for area, mla in results:
        mlas[area.lower()] = mla
        
    print(f"Scraping finished in {time.time() - start_time:.2f} seconds")
    
    existing_data['mlas'] = mlas
    
    with open('india_reps.json', 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, indent=4)
        
    print(f"Successfully saved india_reps.json with {len(mlas)} MLAs.")

if __name__ == '__main__':
    main()
