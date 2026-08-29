import math
import os
import json
import re
from datetime import datetime
from PIL import Image, ExifTags
try:
    import numpy as np
    import cv2
except ImportError:
    np = None
    cv2 = None

AI_SIGNATURE_KEYWORDS = [
    'c2pa', 'synthid', 'dall-e', 'dalle', 'midjourney', 'stable diffusion',
    'stablediffusion', 'comfyui', 'automatic1111', 'novelai', 'flux',
    'invokeai', 'civitai', 'leonardo.ai', 'leonardo', 'ideogram',
    'adobe firefly', 'firefly', 'bing image creator', 'bingimagecreator',
    'chatgpt', 'openai', 'negative prompt', 'steps:', 'sampler:', 'cfg scale:',
    'sd-metadata', 'fooocus', 'wombo', 'nightcafe', 'krea', 'kling', 'pika',
    'sora', 'runway', 'luma', 'recraft', 'freepik ai', 'canva ai', 'deepai',
    'craiyon', 'playground ai'
]

KNOWN_CAMERA_BRANDS = [
    'apple', 'samsung', 'google', 'xiaomi', 'redmi', 'poco', 'oneplus',
    'vivo', 'oppo', 'realme', 'motorola', 'moto', 'sony', 'huawei', 'honor',
    'asus', 'nokia', 'lg', 'canon', 'nikon', 'fujifilm', 'olympus',
    'panasonic', 'gopro', 'infinix', 'tecno', 'iqoo'
]

GPS_APP_KEYWORDS = [
    'gmap', 'gmap app', 'gmap camera', 'gps map camera', 'gps map', 'google map',
    'google maps', 'gpsmap', 'gpsmapcamera', 'map camera', 'mapcamera',
    'com.gpsmapcamera', 'gps photo', 'timestamp camera', 'notecam', 'solocator',
    'geotag', 'open camera', 'gps camera', 'timestamp photo', 'spotlens',
    'autostamper', 'surveycam', 'geocam', 'mapcam', 'camera timestamp', 'gps geotag'
]

EDITING_TOOLS = [
    'photoshop', 'gimp', 'paint.net', 'pixlr', 'lightroom', 'snapseed',
    'vsco', 'afterlight', 'picsart'
]

def _convert_to_degrees(value):
    try:
        if isinstance(value, (int, float)):
            return float(value)
        d = float(value[0])
        m = float(value[1])
        s = float(value[2])
        return d + (m / 60.0) + (s / 3600.0)
    except Exception:
        return None

def scan_ai_signatures(file_path):
    detected_signatures = []
    if not file_path or not os.path.exists(file_path) or os.path.isdir(file_path):
        return detected_signatures

    try:
        # Scan raw bytes (header + trailer) for C2PA, SynthID, and AI generator manifests
        with open(file_path, 'rb') as f:
            file_size = os.path.getsize(file_path)
            header_and_meta = f.read(min(file_size, 1024 * 1024 * 3))
            trailer = b''
            if file_size > 1024 * 256:
                f.seek(max(0, file_size - (1024 * 256)))
                trailer = f.read()
            combined_bytes = (header_and_meta + trailer).lower()

            for kw in AI_SIGNATURE_KEYWORDS:
                if kw.encode('utf-8') in combined_bytes:
                    detected_signatures.append(kw)
    except Exception as e:
        print("Raw signature scan notice:", e)

    return list(set(detected_signatures))

def detect_visual_gps_banner(file_path):
    result = {
        'has_visual_banner': False,
        'banner_location': None,
        'banner_confidence': 0.0,
        'detected_app_type': None
    }
    
    if not file_path or not os.path.exists(file_path) or cv2 is None or np is None:
        return result
        
    try:
        img_bgr = cv2.imread(file_path)
        if img_bgr is None:
            return result
            
        h, w, _ = img_bgr.shape
        if h < 120 or w < 120:
            return result
            
        # Check bottom and top strips specifically for rectangular GPS HUD cards or map overlays
        strips = [
            ('Bottom Overlay', img_bgr[int(h * 0.65):h, 0:w]),
            ('Top Overlay', img_bgr[0:int(h * 0.35), 0:w])
        ]
        
        for loc_name, strip in strips:
            gray_strip = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
            sh, sw = gray_strip.shape
            
            # Check for high contrast bounding rectangle/box of GPS HUD cards
            edges = cv2.Canny(gray_strip, 60, 160)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for cnt in contours:
                x, y, cw, ch = cv2.boundingRect(cnt)
                aspect = cw / float(ch + 1e-5)
                area_ratio = (cw * ch) / float(sh * sw)
                cnt_area = cv2.contourArea(cnt)
                rectangularity = cnt_area / float(cw * ch + 1e-5)
                
                # A genuine HUD card must be a convex polygon with 4-8 vertices
                peri = cv2.arcLength(cnt, True)
                approx = cv2.approxPolyDP(cnt, 0.03 * peri, True)
                
                if (aspect > 1.8 and area_ratio > 0.15 and cw > int(sw * 0.40) and 
                    rectangularity > 0.65 and 4 <= len(approx) <= 8 and cv2.isContourConvex(approx)):
                    card_roi = gray_strip[y:y+ch, x:x+cw]
                    # Verify text horizontal row periodicity inside the card
                    row_means = np.mean(card_roi, axis=1)
                    row_diff = np.abs(np.diff(row_means))
                    peaks = np.sum(row_diff > np.std(row_diff) * 1.5)
                    
                    if peaks >= 4:
                        result['has_visual_banner'] = True
                        result['banner_location'] = loc_name
                        result['banner_confidence'] = 0.95
                        result['detected_app_type'] = 'GPS Map Camera / HUD Card Overlay'
                        return result
                        
    except Exception as e:
        print('Visual banner notice:', e)
        
    return result

def detect_ai_cv_forensics(file_path):
    result = {
        'ai_texture_risk': 0,
        'fft_high_freq_ratio': 0.0,
        'sensor_noise_variance': 0.0,
        'laplacian_variance': 0.0,
        'saturation_mean': 0.0,
        'ai_cv_indicators': []
    }
    
    if not file_path or not os.path.exists(file_path) or cv2 is None or np is None:
        return result
        
    try:
        img_bgr = cv2.imread(file_path)
        if img_bgr is None:
            return result
            
        img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        
        # 1. Laplacian sharpness / micro-texture
        patch = cv2.resize(img_gray, (512, 512))
        lap_var = cv2.Laplacian(patch, cv2.CV_64F).var()
        result['laplacian_variance'] = round(float(lap_var), 2)
        
        # 2. FFT Spectral High-Frequency Distribution
        f = np.fft.fft2(patch)
        fshift = np.fft.fftshift(f)
        magnitude_spectrum = 20 * np.log(np.abs(fshift) + 1e-6)
        
        center_x, center_y = 256, 256
        y, x = np.ogrid[:512, :512]
        dist_from_center = np.sqrt((x - center_x)**2 + (y - center_y)**2)
        
        low_freq_mask = dist_from_center <= 64
        high_freq_mask = dist_from_center >= 160
        
        low_freq_energy = np.mean(magnitude_spectrum[low_freq_mask])
        high_freq_energy = np.mean(magnitude_spectrum[high_freq_mask])
        
        freq_ratio = (high_freq_energy / (low_freq_energy + 1e-6))
        result['fft_high_freq_ratio'] = round(float(freq_ratio), 4)
        
        # 3. Sensor Noise Floor / Residual PRNU Analysis
        # Smooth patches (low gradient) in real camera photos have non-zero sensor photon noise
        blurred = cv2.GaussianBlur(patch, (3, 3), 0)
        residual = np.abs(patch.astype(np.float32) - blurred.astype(np.float32))
        
        # Find flat areas (where Sobel gradient is low)
        grad_x = cv2.Sobel(patch, cv2.CV_32F, 1, 0)
        grad_y = cv2.Sobel(patch, cv2.CV_32F, 0, 1)
        grad_mag = np.sqrt(grad_x**2 + grad_y**2)
        flat_mask = grad_mag < 15.0
        
        if np.sum(flat_mask) > 1000:
            noise_var = float(np.var(residual[flat_mask]))
        else:
            noise_var = float(np.var(residual))
        result['sensor_noise_variance'] = round(noise_var, 3)
        
        # 4. Color Saturation Forensics
        hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        sat_mean = float(np.mean(hsv[:, :, 1]))
        result['saturation_mean'] = round(sat_mean, 2)
        
        # Scoring CV risk
        risk_score = 0
        if freq_ratio < 0.28:
            risk_score += 35
            result['ai_cv_indicators'].append("High-frequency Fourier spectrum decay (Diffusion VAE profile)")
        elif freq_ratio > 0.72:
            risk_score += 25
            result['ai_cv_indicators'].append("Abnormal high-frequency grid harmonics")
            
        if noise_var < 0.35:
            risk_score += 35
            result['ai_cv_indicators'].append("Missing natural camera sensor noise floor (Synthetic smooth latent rendering)")
            
        if sat_mean > 160.0:
            risk_score += 20
            result['ai_cv_indicators'].append("Hyper-saturated color dynamics typical of AI generative models")
            
        result['ai_texture_risk'] = min(80, risk_score)
        
    except Exception as e:
        print('AI CV Forensics notice:', e)
        
    return result

def extract_exif_data(file_path):
    result = {
        'has_exif': False,
        'camera_make': None,
        'camera_model': None,
        'device_name': 'Unknown Device',
        'software': None,
        'datetime_taken': None,
        'gps_lat': None,
        'gps_lng': None,
        'gps_altitude': None,
        'image_format': None,
        'dimensions': None,
        'has_sensor_telemetry': False,
        'iso_speed': None,
        'exposure_time': None,
        'f_number': None,
        'focal_length': None,
        'lens_model': None,
        'pil_info_ai_signatures': [],
        'exif_raw_tags': []
    }
    
    if not file_path or not os.path.exists(file_path):
        return result

    try:
        with Image.open(file_path) as img:
            result['image_format'] = img.format
            result['dimensions'] = f"{img.width}x{img.height}"
            
            # Check PIL info for AI chunks
            if hasattr(img, 'info') and img.info:
                for k, v in img.info.items():
                    k_lower = str(k).lower()
                    v_lower = str(v).lower() if isinstance(v, (str, bytes)) else ''
                    for kw in AI_SIGNATURE_KEYWORDS:
                        if kw in k_lower or kw in v_lower:
                            result['pil_info_ai_signatures'].append(f"{k}: {kw}")
            
            exif_raw = img.getexif()
            if not exif_raw:
                return result
            
            result['has_exif'] = True
            
            for tag_id, value in exif_raw.items():
                tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                result['exif_raw_tags'].append(tag_name)
                
                if tag_name == 'Make':
                    result['camera_make'] = str(value).strip()
                elif tag_name == 'Model':
                    result['camera_model'] = str(value).strip()
                elif tag_name == 'Software':
                    result['software'] = str(value).strip()
                elif tag_name in ('DateTime', 'DateTimeOriginal', 'DateTimeDigitized'):
                    if not result['datetime_taken']:
                        result['datetime_taken'] = str(value).strip()
                        
            # Check SubIFD for camera hardware sensor telemetry
            try:
                sub_ifd = exif_raw.get_ifd(ExifTags.IFD.Exif)
                if sub_ifd:
                    for s_tag, s_val in sub_ifd.items():
                        s_name = ExifTags.TAGS.get(s_tag, str(s_tag))
                        if s_name in ('ISOSpeedRatings', 'PhotographicSensitivity'):
                            result['iso_speed'] = str(s_val)
                            result['has_sensor_telemetry'] = True
                        elif s_name == 'ExposureTime':
                            result['exposure_time'] = str(s_val)
                            result['has_sensor_telemetry'] = True
                        elif s_name == 'FNumber':
                            result['f_number'] = str(s_val)
                            result['has_sensor_telemetry'] = True
                        elif s_name == 'FocalLength':
                            result['focal_length'] = str(s_val)
                            result['has_sensor_telemetry'] = True
                        elif s_name == 'LensModel':
                            result['lens_model'] = str(s_val)
                        elif s_name in ('DateTimeOriginal', 'DateTimeDigitized') and not result['datetime_taken']:
                            result['datetime_taken'] = str(s_val).strip()
            except Exception:
                pass
            
            make = result['camera_make'] or ''
            model = result['camera_model'] or ''
            if make and model:
                if make.lower() in model.lower():
                    result['device_name'] = model
                else:
                    result['device_name'] = f"{make} {model}"
            elif model:
                result['device_name'] = model
            elif make:
                result['device_name'] = make
                
            # GPS
            gps_info_ifd = None
            try:
                gps_info_ifd = exif_raw.get_ifd(ExifTags.IFD.GPSInfo)
            except Exception:
                pass
                
            if not gps_info_ifd and hasattr(img, '_getexif'):
                _legacy_exif = img._getexif()
                if _legacy_exif and 34853 in _legacy_exif:
                    gps_info_ifd = _legacy_exif[34853]
            
            if gps_info_ifd:
                gps_dict = {}
                for g_tag_id, g_value in gps_info_ifd.items():
                    g_tag_name = ExifTags.GPSTAGS.get(g_tag_id, str(g_tag_id))
                    gps_dict[g_tag_name] = g_value
                
                lat_val = gps_dict.get('GPSLatitude')
                lat_ref = gps_dict.get('GPSLatitudeRef', 'N')
                if lat_val:
                    dec_lat = _convert_to_degrees(lat_val)
                    if dec_lat is not None:
                        if str(lat_ref).upper() == 'S':
                            dec_lat = -dec_lat
                        result['gps_lat'] = round(dec_lat, 6)
                
                lng_val = gps_dict.get('GPSLongitude')
                lng_ref = gps_dict.get('GPSLongitudeRef', 'E')
                if lng_val:
                    dec_lng = _convert_to_degrees(lng_val)
                    if dec_lng is not None:
                        if str(lng_ref).upper() == 'W':
                            dec_lng = -dec_lng
                        result['gps_lng'] = round(dec_lng, 6)
                        
                alt_val = gps_dict.get('GPSAltitude')
                if alt_val:
                    try:
                        result['gps_altitude'] = round(float(alt_val), 1)
                    except Exception:
                        pass
    except Exception as e:
        print('EXIF notice:', e)
    return result

def haversine_distance(lat1, lon1, lat2, lon2):
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None
    try:
        r = 6371.0
        d_lat = math.radians(lat2 - lat1)
        d_lon = math.radians(lon2 - lon1)
        a = (math.sin(d_lat / 2.0) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(d_lon / 2.0) ** 2)
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return round(r * c, 2)
    except Exception:
        return None

def analyze_photo_authenticity(file_path, reported_lat=None, reported_lng=None):
    exif = extract_exif_data(file_path)
    raw_ai_sigs = scan_ai_signatures(file_path)
    visual_banner = detect_visual_gps_banner(file_path)
    ai_cv = detect_ai_cv_forensics(file_path)
    
    ai_risk_score = 0
    risk_factors = []
    positive_factors = []
    
    software_str = (exif.get('software') or '').lower()
    device_str = (exif.get('device_name') or '').lower()
    make_str = (exif.get('camera_make') or '').lower()
    model_str = (exif.get('camera_model') or '').lower()
    
    # 1. AI Signatures (Metadata / C2PA / Chunks / Raw bytes)
    all_ai_signatures = list(set(raw_ai_sigs + exif.get('pil_info_ai_signatures', [])))
    for kw in AI_SIGNATURE_KEYWORDS:
        if kw in software_str or kw in device_str or kw in make_str or kw in model_str:
            all_ai_signatures.append(kw)
    all_ai_signatures = list(set(all_ai_signatures))
    
    has_ai_metadata = len(all_ai_signatures) > 0
    if has_ai_metadata:
        ai_risk_score = 99
        risk_factors.append(f"CRITICAL AI DETECTED: Synthetic / AI generator signature verified: {', '.join(all_ai_signatures)}")

    # 2. Camera Hardware & Sensor Verification
    has_recognized_brand = any(b in make_str or b in model_str for b in KNOWN_CAMERA_BRANDS)
    has_sensor_telemetry = exif.get('has_sensor_telemetry', False)
    has_camera_device = bool((exif.get('camera_make') or exif.get('camera_model')) and (has_recognized_brand or has_sensor_telemetry))
    has_gps = bool(exif.get('gps_lat') is not None and exif.get('gps_lng') is not None)
    has_timestamp = bool(exif.get('datetime_taken'))
    
    # 3. Gmap & GPS Camera App Detection
    is_gps_app_detected = False
    detected_gmap_app_name = None
    
    for app_kw in GPS_APP_KEYWORDS:
        if app_kw in software_str or app_kw in device_str or app_kw in make_str or app_kw in model_str:
            is_gps_app_detected = True
            detected_gmap_app_name = "Gmap App / GPS Map Camera" if any(x in app_kw for x in ['gmap', 'gps map', 'google map', 'map camera']) else app_kw.title()
            positive_factors.append(f"Verified Gmap/GPS Camera App: '{detected_gmap_app_name}' identified in metadata.")
            break

    # Check filename for Gmap / GPS camera naming convention (common when images sent via messaging apps)
    file_basename = os.path.basename(file_path).lower()
    if not is_gps_app_detected:
        gmap_name_keywords = ['gmap', 'gpsmap', 'gps_map', 'map_camera', 'mapcam', 'geotag', 'gps_photo']
        for fkw in gmap_name_keywords:
            if fkw in file_basename:
                is_gps_app_detected = True
                detected_gmap_app_name = "Gmap App / GPS Map Camera"
                positive_factors.append(f"Gmap App signature identified from photo naming ('{fkw}').")
                break
            
    if visual_banner.get('has_visual_banner') and not has_ai_metadata:
        is_gps_app_detected = True
        if not detected_gmap_app_name:
            detected_gmap_app_name = "Gmap App / GPS Map Camera"
        positive_factors.append(f"Visual Gmap & Location HUD Card detected ({visual_banner['banner_location']}).")
        
    # 4. Image Editing Signature
    has_editor_signature = False
    for tool in EDITING_TOOLS:
        if tool in software_str:
            has_editor_signature = True
            risk_factors.append(f"Image editing software signature detected: '{tool.title()}'")
            break

    # 5. Sensor & Telemetry Validation
    if has_camera_device and not has_ai_metadata:
        positive_factors.append(f"Physical camera hardware sensor: {exif['device_name']}")
        if has_sensor_telemetry:
            positive_factors.append(f"Hardware optical telemetry verified (ISO: {exif.get('iso_speed', 'N/A')}, F/{exif.get('f_number', 'N/A')})")
    elif is_gps_app_detected:
        positive_factors.append("Authentic Gmap App civic evidence upload (Hardware EXIF superseded by GPS App).")
    elif not has_ai_metadata:
        ai_risk_score += 20
        risk_factors.append("Standard camera hardware EXIF missing (Likely compressed or shared photo).")
        
    if has_timestamp and not has_ai_metadata:
        positive_factors.append(f"Original capture timestamp: {exif['datetime_taken']}")
    elif not has_timestamp and not visual_banner.get('has_visual_banner') and not has_ai_metadata:
        ai_risk_score += 10
        risk_factors.append("Missing original capture timestamp (No timing metadata).")

    # 6. Computer Vision Forensics Integration
    if ai_cv.get('ai_cv_indicators') and not has_ai_metadata:
        if is_gps_app_detected or has_gps or has_camera_device:
            # Genuine photos with text/overlays or compression: do not penalize
            pass
        else:
            ai_risk_score += min(25, ai_cv['ai_texture_risk'])
            for ind in ai_cv['ai_cv_indicators']:
                risk_factors.append(f"Forensic CV Notice: {ind}")

    # 7. Geolocation Distance Check
    distance_km = None
    is_location_mismatch = False
    location_match_status = "No GPS Coordinates Found"
    
    if has_gps and reported_lat is not None and reported_lng is not None:
        positive_factors.append(f"GPS Geolocation Tagged: ({exif['gps_lat']}, {exif['gps_lng']})")
        distance_km = haversine_distance(exif['gps_lat'], exif['gps_lng'], reported_lat, reported_lng)
        
        if distance_km is not None:
            if distance_km <= 5.0:
                location_match_status = "GPS Location Verified (Exact Match)"
                positive_factors.append(f"Photo was captured within {distance_km} km of reported area.")
            elif distance_km <= 25.0:
                location_match_status = "GPS Location Acceptable (Regional Match)"
                positive_factors.append(f"Photo was captured {distance_km} km from central area.")
            else:
                is_location_mismatch = True
                location_match_status = f"Location Mismatch Alert ({distance_km} km away)"
                risk_factors.append(f"CRITICAL FRAUD ALERT: Photo GPS is {distance_km} km away from reported location!")
                ai_risk_score += 40
    elif has_gps:
        location_match_status = f"Photo GPS Available: ({exif['gps_lat']}, {exif['gps_lng']})"
    elif is_gps_app_detected:
        location_match_status = "Gmap / GPS Camera Location Stamp Detected on Image"

    has_gps_proof = bool(exif.get('gps_lat') is not None and exif.get('gps_lng') is not None) or is_gps_app_detected

    if has_ai_metadata:
        ai_risk_score = 99
        risk_factors.append("CRITICAL: Synthetic / AI generated image detected.")
    elif has_editor_signature:
        ai_risk_score = max(ai_risk_score, 80)
        risk_factors.append("Image editing software modifications detected.")
    elif not has_gps_proof:
        # STRICT POLICY: Upload photo from GPS map camera app only!
        ai_risk_score = 99
        risk_factors.append("FAKE / UNVERIFIED: Photo was not taken with GPS Map Camera app. Upload photo from GPS map camera app only.")
    else:
        # Verified authentic GPS Map Camera photo
        ai_risk_score = 0

    ai_risk_score = max(0, min(100, ai_risk_score))
    is_fake_or_unverified = not has_gps_proof
    is_ai_suspected = (has_ai_metadata or is_fake_or_unverified or ai_risk_score >= 50)
    
    if has_ai_metadata:
        verification_status = "Suspected AI-Generated / Fake"
        badge_color = "red"
    elif is_fake_or_unverified:
        verification_status = "Fake Photo Blocked (Upload from GPS Map Camera App only)"
        badge_color = "red"
    elif is_location_mismatch:
        verification_status = f"Location Mismatch ({distance_km} km)"
        badge_color = "red"
    elif is_gps_app_detected and has_gps and distance_km is not None and distance_km <= 25.0:
        verification_status = "Verified GPS Map Camera Photo (GPS & Location Match)"
        badge_color = "green"
    elif is_gps_app_detected or has_gps:
        verification_status = "Verified GPS Map Camera Photo"
        badge_color = "green"
    else:
        verification_status = "Fake Photo Blocked (Upload from GPS Map Camera App only)"
        badge_color = "red"

    return {
        'verification_status': verification_status,
        'badge_color': badge_color,
        'ai_risk_score': ai_risk_score,
        'is_ai_suspected': is_ai_suspected,
        'is_fake_or_unverified': is_fake_or_unverified,
        'has_gps_proof': has_gps_proof,
        'is_location_mismatch': is_location_mismatch,
        'is_gps_app_detected': is_gps_app_detected,
        'has_visual_banner': visual_banner.get('has_visual_banner', False),
        'photo_lat': exif.get('gps_lat'),
        'photo_lng': exif.get('gps_lng'),
        'photo_altitude': exif.get('gps_altitude'),
        'distance_km': distance_km,
        'device_name': detected_gmap_app_name or exif.get('device_name'),
        'camera_make': exif.get('camera_make'),
        'camera_model': exif.get('camera_model'),
        'software': exif.get('software'),
        'datetime_taken': exif.get('datetime_taken'),
        'dimensions': exif.get('dimensions'),
        'image_format': exif.get('image_format'),
        'location_match_status': location_match_status,
        'risk_factors': risk_factors,
        'positive_factors': positive_factors,
        'raw_exif_tags': exif.get('exif_raw_tags', [])
    }

