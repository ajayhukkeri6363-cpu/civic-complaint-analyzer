import random

area_coords = {
    # ── State Centers (Smart Fallback) ──
    'andaman and nicobar islands': [11.7401, 92.6586],
    'andhra pradesh': [15.9129, 79.7400],
    'arunachal pradesh': [28.2180, 94.7278],
    'assam': [26.2006, 92.9376],
    'bihar': [25.0961, 85.3131],
    'chandigarh': [30.7333, 76.7794],
    'chhattisgarh': [21.2787, 81.8661],
    'dadra and nagar haveli and daman and diu': [20.1809, 73.0169],
    'delhi': [28.6139, 77.2090],
    'goa': [15.2993, 74.1240],
    'gujarat': [22.2587, 71.1924],
    'haryana': [29.0588, 76.0856],
    'himachal pradesh': [31.1048, 77.1734],
    'jammu and kashmir': [33.7782, 76.5762],
    'jharkhand': [23.6102, 85.2799],
    'karnataka': [15.3173, 75.7139],
    'kerala': [10.8505, 76.2711],
    'ladakh': [34.1526, 77.5771],
    'lakshadweep': [10.5667, 72.6417],
    'madhya pradesh': [22.9734, 78.6569],
    'maharashtra': [19.7515, 75.7139],
    'manipur': [24.6637, 93.9063],
    'meghalaya': [25.4670, 91.3662],
    'mizoram': [23.1645, 92.9376],
    'nagaland': [26.1584, 94.5624],
    'odisha': [20.9517, 85.0985],
    'puducherry': [11.9416, 79.8083],
    'punjab': [31.1471, 75.3412],
    'rajasthan': [27.0238, 74.2179],
    'sikkim': [27.5330, 88.5122],
    'tamil nadu': [11.1271, 78.6569],
    'telangana': [18.1124, 79.0193],
    'tripura': [23.9408, 91.9882],
    'uttar pradesh': [26.8467, 80.9462],
    'uttarakhand': [30.0668, 79.0193],
    'west bengal': [22.9868, 87.8550],

    # ── Major District & City Centers ──
    'bagalkot': [16.1817, 75.6958],
    'ballari': [15.1394, 76.9214],
    'belagavi': [15.8497, 74.4977],
    'bengaluru rural': [13.2131, 77.5816],
    'bengaluru urban': [12.9716, 77.5946],
    'bangalore': [12.9716, 77.5946],
    'bengaluru': [12.9716, 77.5946],
    'mysuru': [12.2958, 76.6394],
    'mysore': [12.2958, 76.6394],
    'hubballi': [15.3647, 75.1240],
    'dharwad': [15.4589, 75.0078],
    'mangaluru': [12.9141, 74.8560],
    'mangalore': [12.9141, 74.8560],
    'shivamogga': [13.9299, 75.5681],
    'tumakuru': [13.3379, 77.1010],
    'davangere': [14.4644, 75.9218],
    'kalaburagi': [17.3297, 76.8343],
    'udupi': [13.3409, 74.7421],
    'vijayapura': [16.8302, 75.7100],
    'hassan': [13.0068, 76.1004],
    'bidar': [17.9104, 77.5199],
    'raichur': [16.2076, 77.3463],
    'koppal': [15.3458, 76.1554],
    'gadag': [15.4167, 75.6333],
    'haveri': [14.7954, 75.3991],
    'chikkamagaluru': [13.3161, 75.7720],
    'chikkaballapur': [13.4325, 77.7275],
    'kolar': [13.1367, 78.1291],
    'mandya': [12.5218, 76.8951],
    'ramanagara': [12.7150, 77.2814],
    'chamarajanagar': [11.9261, 76.9437],
    'kodagu': [12.3375, 75.8069],
    'yadgir': [16.7700, 77.1300],
    'uttara kannada': [14.7954, 74.6853],
    'dakshina kannada': [12.8700, 75.2400],

    'lucknow': [26.8467, 80.9462],
    'kanpur': [26.4499, 80.3319],
    'agra': [27.1767, 78.0081],
    'varanasi': [25.3176, 82.9739],
    'prayagraj': [25.4358, 81.8463],
    'meerut': [28.9845, 77.7064],
    'ghaziabad': [28.6692, 77.4538],
    'noida': [28.5355, 77.3910],
    'aligarh': [27.8974, 78.0880],
    'bareilly': [28.3670, 79.4304],
    'gorakhpur': [26.7606, 83.3732],

    'ahmedabad': [23.0225, 72.5714],
    'surat': [21.1702, 72.8311],
    'vadodara': [22.3072, 73.1812],
    'rajkot': [22.3039, 70.8022],
    'bhavnagar': [21.7645, 72.1519],
    'jamnagar': [22.4707, 70.0577],
    'gandhinagar': [23.2156, 72.6369],

    'mumbai': [19.0760, 72.8777],
    'mumbai city': [18.9220, 72.8347],
    'mumbai suburban': [19.1500, 72.8500],
    'pune': [18.5204, 73.8567],
    'nagpur': [21.1458, 79.0882],
    'thane': [19.2183, 72.9781],
    'nashik': [19.9975, 73.7898],
    'aurangabad': [19.8762, 75.3433],
    'solapur': [17.6599, 75.9064],
    'navi mumbai': [19.0330, 73.0297],
    'kolhapur': [16.7050, 74.2433],

    'chennai': [13.0827, 80.2707],
    'coimbatore': [11.0168, 76.9558],
    'madurai': [9.9252, 78.1198],
    'tiruchirappalli': [10.7905, 78.7047],
    'salem': [11.6643, 78.1460],
    'tirunelveli': [8.7139, 77.7567],
    'tiruppur': [11.1085, 77.3411],
    'vellore': [12.9165, 79.1325],
    'erode': [11.3410, 77.7172],

    'hyderabad': [17.3850, 78.4867],
    'warangal': [17.9689, 79.5941],
    'nizamabad': [18.6725, 78.0941],
    'karimnagar': [18.4386, 79.1288],
    'khammam': [17.2473, 80.1514],

    'visakhapatnam': [17.6868, 83.2185],
    'vijayawada': [16.5062, 80.6480],
    'guntur': [16.3067, 80.4365],
    'nellore': [14.4426, 79.9865],
    'kurnool': [15.8281, 78.0373],
    'rajahmundry': [17.0005, 81.8040],
    'tirupati': [13.6288, 79.4192],

    'kolkata': [22.5726, 88.3639],
    'howrah': [22.5958, 88.2636],
    'asansol': [23.6739, 86.9524],
    'siliguri': [26.7271, 88.3953],
    'durgapur': [23.5204, 87.3119],

    'jaipur': [26.9124, 75.7873],
    'jodhpur': [26.2389, 73.0243],
    'kota': [25.2138, 75.8648],
    'bikaner': [28.0229, 73.3119],
    'ajmer': [26.4499, 74.6399],
    'udaipur': [24.5854, 73.7125],

    'patna': [25.5941, 85.1376],
    'gaya': [24.7914, 85.0002],
    'bhagalpur': [25.2425, 86.9842],
    'muzaffarpur': [26.1209, 85.3647],

    'bhopal': [23.2599, 77.4126],
    'indore': [22.7196, 75.8577],
    'gwalior': [26.2183, 78.1828],
    'jabalpur': [23.1815, 79.9864],
    'ujjain': [23.1765, 75.7885],

    'thiruvananthapuram': [8.5241, 76.9366],
    'kochi': [9.9312, 76.2673],
    'kozhikode': [11.2588, 75.7804],
    'thrissur': [10.5276, 76.2144],
    'kollam': [8.8932, 76.6141],

    'amritsar': [31.6340, 74.8723],
    'ludhiana': [30.9010, 75.8573],
    'jalandhar': [31.3260, 75.5762],
    'patiala': [30.3398, 76.3869],

    'gurugram': [28.4595, 77.0266],
    'faridabad': [28.4089, 77.3178],
    'panipat': [29.3909, 76.9635],
    'ambala': [30.3782, 76.7767],

    'bhubaneswar': [20.2961, 85.8245],
    'cuttack': [20.4625, 85.8828],
    'rourkela': [22.2604, 84.8536],

    'raipur': [21.2514, 81.6296],
    'bilaspur': [22.0797, 82.1409],

    'ranchi': [23.3441, 85.3096],
    'jamshedpur': [22.8046, 86.2029],
    'dhanbad': [23.7957, 86.4304],

    'dehradun': [30.3165, 78.0322],
    'haridwar': [29.9457, 78.1642],

    'shimla': [31.1048, 77.1734],
    'dharamshala': [32.2190, 76.3234],

    'guwahati': [26.1445, 91.7362],
    'shillong': [25.5788, 91.8933],
    'imphal': [24.8170, 93.9368],
    'agartala': [23.8315, 91.2868],
    'aizawl': [23.7271, 92.7176],
    'kohima': [25.6751, 94.1086],
    'gangtok': [27.3389, 88.6065],
    'itanagar': [27.0844, 93.6053],

    # ── Specific Areas (Exact Localities) ──
    'whitefield': [12.9698, 77.7499],
    'yelahanka': [13.1007, 77.5963],
    'btm': [12.9166, 77.6101],
    'indiranagar': [12.9716, 77.6412],
    'koramangala': [12.9352, 77.6244],
    'hsr layout': [12.9116, 77.6389],
    'marathahalli': [12.9592, 77.6974],
    'electronic city': [12.8456, 77.6603],
    'hebbal': [13.0354, 77.5972],
    'jayanagar': [12.9308, 77.5838],
    'rajajinagar': [12.9982, 77.5530],
    'malleshwaram': [13.0031, 77.5643],
    'banashankari': [12.9255, 77.5468],
    'bellandur': [12.9260, 77.6762],
    'sarjapur': [12.8600, 77.7850],
    'bannerghatta': [12.8000, 77.5770],
    'nagavara': [13.0435, 77.6200],
    'kengeri': [12.9177, 77.4838],
    'gokak': [16.1690, 74.8236],
    'chikkodi': [16.4300, 74.6000],
    'nipani': [16.4000, 74.3800],
    'bailhongal': [15.8200, 74.8500],
    'soundatti': [15.7700, 75.1200],
    'khanapur': [15.6300, 74.5200],
    'hukkeri': [16.2300, 74.6000],
    'athani': [16.7300, 75.0600],
    'raybag': [16.4800, 74.7800],
    'ramdurg': [15.9500, 75.3000],

    'andheri': [19.1136, 72.8697],
    'bandra': [19.0596, 72.8295],
    'borivali': [19.2307, 72.8567],
    'dadar': [19.0178, 72.8478],
    'juhu': [19.1075, 72.8263],
    'powai': [19.1176, 72.9060],
    'colaba': [18.9067, 72.8147],
    'hinjewadi': [18.5913, 73.7389],
    'wakad': [18.5987, 73.7652],
    'kothrud': [18.5074, 73.8077],
    'viman nagar': [18.5679, 73.9143],
    'baner': [18.5590, 73.7868],
    'hadapsar': [18.5089, 73.9260],

    't nagar': [13.0405, 80.2337],
    'velachery': [12.9792, 80.2184],
    'adyar': [13.0012, 80.2565],
    'anna nagar': [13.0850, 80.2100],
    'mylapore': [13.0368, 80.2676],
    'omr': [12.8900, 80.2300],

    'connaught place': [28.6315, 77.2167],
    'saket': [28.5244, 77.2100],
    'hauz khas': [28.5494, 77.2001],
    'dwarka': [28.5921, 77.0460],
    'rohini': [28.7495, 77.0565],
    'karol bagh': [28.6517, 77.1906],
    'chandni chowk': [28.6506, 77.2303],
    'lajpat nagar': [28.5677, 77.2433],
}

def get_coords(area='', district='', state='', jitter=True):
    """
    Intelligently resolves latitude and longitude using hierarchy:
    Area -> District -> State -> India Center (20.5937, 78.9629).
    Applies small dispersion so multiple complaints
    in the same locality don't stack invisibly at the exact same pixel.
    """
    def _lookup(name):
        if not name:
            return None
        cleaned = str(name).strip().lower()
        if cleaned in area_coords:
            return list(area_coords[cleaned])
        for k, v in area_coords.items():
            if k in cleaned or cleaned in k:
                return list(v)
        return None

    coords = _lookup(area) or _lookup(district) or _lookup(state) or [20.5937, 78.9629]
    lat, lng = float(coords[0]), float(coords[1])

    if jitter:
        lat += random.uniform(-0.003, 0.003)
        lng += random.uniform(-0.003, 0.003)

    return round(lat, 6), round(lng, 6)

