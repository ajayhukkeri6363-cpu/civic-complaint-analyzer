import json
import concurrent.futures
import requests
import pandas as pd
import io
import time

def get_mps():
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_members_of_the_18th_Lok_Sabha'
        html = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15).text
        tables = pd.read_html(io.StringIO(html))
        data = {}
        for df in tables:
            if 'Constituency' in df.columns or ('Constituency' in [str(c[1]) for c in df.columns if isinstance(c, tuple)]):
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.droplevel(0)
                
                const_col = next((c for c in df.columns if 'constituency' in str(c).lower()), None)
                name_col = next((c for c in df.columns if 'member' in str(c).lower() or 'name' in str(c).lower()), None)
                
                if const_col and name_col:
                    for _, row in df.iterrows():
                        try:
                            c = str(row[const_col]).split('[')[0].strip().lower()
                            n = str(row[name_col]).split('[')[0].strip()
                            if c and c != 'nan':
                                data[c] = n
                        except: pass
        return data
    except:
        return {}

def extract_mla_from_url(area):
    try:
        # Step 1: Search for the constituency page
        search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={requests.utils.quote(area + ' Assembly constituency')}&utf8=&format=json"
        res = requests.get(search_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10).json()
        if not res.get('query', {}).get('search'):
            return "Unassigned"
        
        title = res['query']['search'][0]['title']
        
        # Step 2: Fetch the page and parse tables
        page_url = f"https://en.wikipedia.org/wiki/{requests.utils.quote(title.replace(' ', '_'))}"
        html = requests.get(page_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10).text
        tables = pd.read_html(io.StringIO(html))
        
        # Step 3: Find MLA in infobox (usually first table)
        for df in tables[:2]:
            for _, row in df.iterrows():
                row_strs = [str(x).lower() for x in row.values]
                if any('mla' in x or 'member' in x for x in row_strs):
                    # Usually the next cell is the value
                    for val in row.values:
                        val_str = str(val)
                        if 'mla' not in val_str.lower() and 'member' not in val_str.lower() and val_str != 'nan':
                            return val_str.split('[')[0].strip()
        return "Unassigned"
    except:
        return "Unassigned"

def process_area(item):
    area = item['area']
    district = item['district']
    state = item['state']
    mla = extract_mla_from_url(area)
    return (area, mla)

def main():
    print("Fetching MPs...")
    mps = get_mps()
    print(f"Found {len(mps)} MPs")
    
    print("Loading india_locations.json...")
    with open('static/data/india_locations.json') as f:
        india_locs = json.load(f)
    
    areas_to_search = []
    for state, districts in india_locs.items():
        for district, areas in districts.items():
            for area in areas:
                areas_to_search.append({'state': state, 'district': district, 'area': area})
                
    print(f"Total areas to search for MLAs: {len(areas_to_search)}")
    
    mlas = {}
    # Use ThreadPoolExecutor to speed up fetching
    start_time = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(process_area, areas_to_search))
        
    for area, mla in results:
        mlas[area.lower()] = mla
        
    print(f"Finished MLA scraping in {time.time() - start_time:.2f} seconds")
    
    # Also load the karnataka ones to act as a solid base just in case
    try:
        with open('karnataka_reps.json') as f:
            kr = json.load(f)
            mlas.update({k: v['mla'] for k, v in kr.get('mlas', {}).items()})
            mps.update(kr.get('mps_by_district', {}))
    except: pass
    
    final_data = {
        'mlas': mlas,
        'mps': mps
    }
    
    with open('india_reps.json', 'w') as f:
        json.dump(final_data, f, indent=4)
    print("Successfully saved india_reps.json")

if __name__ == '__main__':
    main()
