import requests
import pandas as pd
import io
import json
import os

state_urls = [
    'https://en.wikipedia.org/wiki/16th_Andhra_Pradesh_Assembly',
    'https://en.wikipedia.org/wiki/11th_Arunachal_Pradesh_Assembly',
    'https://en.wikipedia.org/wiki/15th_Assam_Assembly',
    'https://en.wikipedia.org/wiki/17th_Bihar_Assembly',
    'https://en.wikipedia.org/wiki/6th_Chhattisgarh_Assembly',
    'https://en.wikipedia.org/wiki/8th_Goa_Assembly',
    'https://en.wikipedia.org/wiki/15th_Gujarat_Assembly',
    'https://en.wikipedia.org/wiki/14th_Haryana_Assembly',
    'https://en.wikipedia.org/wiki/14th_Himachal_Pradesh_Assembly',
    'https://en.wikipedia.org/wiki/5th_Jharkhand_Assembly',
    'https://en.wikipedia.org/wiki/16th_Karnataka_Assembly',
    'https://en.wikipedia.org/wiki/15th_Kerala_Legislative_Assembly',
    'https://en.wikipedia.org/wiki/16th_Madhya_Pradesh_Assembly',
    'https://en.wikipedia.org/wiki/14th_Maharashtra_Assembly',
    'https://en.wikipedia.org/wiki/12th_Manipur_Assembly',
    'https://en.wikipedia.org/wiki/11th_Meghalaya_Assembly',
    'https://en.wikipedia.org/wiki/9th_Mizoram_Assembly',
    'https://en.wikipedia.org/wiki/14th_Nagaland_Assembly',
    'https://en.wikipedia.org/wiki/17th_Odisha_Assembly',
    'https://en.wikipedia.org/wiki/16th_Punjab_Assembly',
    'https://en.wikipedia.org/wiki/16th_Rajasthan_Assembly',
    'https://en.wikipedia.org/wiki/11th_Sikkim_Assembly',
    'https://en.wikipedia.org/wiki/16th_Tamil_Nadu_Assembly',
    'https://en.wikipedia.org/wiki/3rd_Telangana_Assembly',
    'https://en.wikipedia.org/wiki/13th_Tripura_Assembly',
    'https://en.wikipedia.org/wiki/18th_Uttar_Pradesh_Assembly',
    'https://en.wikipedia.org/wiki/5th_Uttarakhand_Assembly',
    'https://en.wikipedia.org/wiki/17th_West_Bengal_Assembly',
    'https://en.wikipedia.org/wiki/7th_Delhi_Assembly',
    'https://en.wikipedia.org/wiki/15th_Puducherry_Assembly'
]

headers = {'User-Agent': 'Mozilla/5.0'}
mla_map = {}
district_map = {}

for url in state_urls:
    try:
        html = requests.get(url, headers=headers, timeout=10).text
        tables = pd.read_html(io.StringIO(html))
        found = False
        for t in tables:
            # Flatten MultiIndex columns if necessary
            if isinstance(t.columns, pd.MultiIndex):
                t.columns = t.columns.droplevel(0)
            
            # Find the constituency column
            const_col = None
            member_col = None
            
            district_col = None
            for c in t.columns:
                c_str = str(c).lower()
                if 'constituency' in c_str and const_col is None:
                    const_col = c
                if ('member' in c_str or 'name' in c_str or 'mla' in c_str) and member_col is None and 'party' not in c_str and 'district' not in c_str:
                    member_col = c
                if 'district' in c_str and district_col is None:
                    district_col = c
                    
            if const_col and member_col and len(t) > 10: # ensure it's a large table
                for _, row in t.iterrows():
                    try:
                        c_val = str(row[const_col]).split('[')[0].strip().lower()
                        m_val = str(row[member_col]).split('[')[0].strip()
                        if c_val and c_val != 'nan' and m_val and m_val != 'nan':
                            mla_map[c_val] = m_val
                            if district_col:
                                d_val = str(row[district_col]).split('[')[0].strip().lower()
                                if d_val and d_val != 'nan':
                                    if d_val not in district_map:
                                        district_map[d_val] = m_val
                    except:
                        pass
                print(f"Scraped {len(t)} MLAs from {url.split('/')[-1]}")
                found = True
                break
        if not found:
            print(f"No suitable table found in {url.split('/')[-1]}")
    except Exception as e:
        print(f"Failed {url}: {e}")

print(f"\nTotal MLAs extracted: {len(mla_map)}")

# Merge with existing india_reps.json
if os.path.exists('india_reps.json'):
    with open('india_reps.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
else:
    data = {'mlas': {}, 'mps': {}}

for c, m in mla_map.items():
    data['mlas'][c] = m
data['district_mlas'] = district_map

with open('india_reps.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=4)
    
print("Saved to india_reps.json")
