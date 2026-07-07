import json
import requests
import re
import io
import os
import tempfile
import logging
import hashlib
import concurrent.futures
import pyzipper
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify, send_file

# --- CRYPTOGRAPHY IMPORTS ---
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend

# -------------------------------------------------------------------
# SETUP & CONFIG
# -------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://www.procyclingstats.com/'
}

SECRET_KEY = "WellDoneMF"
ZIP_PASSWORD = b"5121f408-274f-4d56-8a2d-373ce8d033db"

# -------------------------------------------------------------------
# ENCRYPTION LOGIC
# -------------------------------------------------------------------
def encrypt_data(data_bytes: bytes, secret_passphrase: str) -> bytes:
    key = hashlib.sha256(secret_passphrase.encode('utf-8')).digest()
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded_data = padder.update(data_bytes) + padder.finalize()
    
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()
    return iv + ciphertext

# -------------------------------------------------------------------
# SCRAPING LOGIC
# -------------------------------------------------------------------
def extract_riders(table, class_name):
    riders_data = []
    tbody = table.find('tbody')
    if not tbody: return []

    for row in tbody.find_all('tr'):
        cols = row.find_all('td')
        if not cols: continue
        try:
            rank_text = cols[0].text.strip()
            if not rank_text.isdigit(): continue
            rank = int(rank_text)

            rider_td = row.find('td', class_='ridername')
            if not rider_td: continue

            country_code = ""
            flag_span = rider_td.find('span', class_='flag')
            if flag_span and len(flag_span.get('class', [])) > 1:
                country_code = flag_span.get('class')[1].upper()

            name_a = rider_td.find('a')
            if name_a:
                rider_id = name_a.get('href', '').replace('rider/', '').strip()
                last_name_span = name_a.find('span', class_='uppercase')
                if last_name_span:
                    last_name = last_name_span.text.strip()
                    first_name = name_a.text.replace(last_name, '').strip()
                    full_name = f"{first_name} {last_name}".strip()
                else:
                    full_name = name_a.text.strip()
            else:
                rider_id = "unknown"
                full_name = "Unknown"

            team_td = row.find('td', class_='cu600')
            team_name = team_td.text.strip() if team_td else ""

            metric = ""
            if class_name in ['points', 'mountain']:
                pnt_td = row.find('td', class_='pnt')
                if pnt_td:
                    next_td = pnt_td.find_next_sibling('td')
                    if next_td: metric = next_td.text.strip()
            else:
                time_td = row.find('td', class_='time')
                if time_td:
                    hide_span = time_td.find('span', class_='hide')
                    metric = hide_span.text.strip() if hide_span else time_td.text.strip()
                    if rank > 1 and metric and ':' in metric and not metric.startswith('+'):
                        metric = f"+ {metric}"

            riders_data.append({
                "id": rider_id, "rank": rank, "name": full_name,
                "team": team_name, "country": country_code, "metric": metric
            })
        except Exception:
            continue
    return riders_data

def extract_teams(table):
    teams_data = []
    tbody = table.find('tbody')
    if not tbody: return []

    for row in tbody.find_all('tr'):
        cols = row.find_all('td')
        if not cols: continue
        try:
            rank_text = cols[0].text.strip()
            if not rank_text.isdigit(): continue
            rank = int(rank_text)

            team_a = row.find(lambda tag: tag.name == 'a' and 'team/' in tag.get('href', ''))
            if not team_a: continue

            team_id = team_a.get('href', '').replace('team/', '').strip()
            team_name = team_a.text.strip()

            team_td = team_a.find_parent('td')
            country_code = ""
            flag_span = team_td.find('span', class_='flag')
            if flag_span and len(flag_span.get('class', [])) > 1:
                country_code = flag_span.get('class')[1].upper()

            time_td = row.find('td', class_='time')
            metric = ""
            if time_td:
                hide_span = time_td.find('span', class_='hide')
                metric = hide_span.text.strip() if hide_span else time_td.text.strip()
                if rank > 1 and metric and ':' in metric and not metric.startswith('+'):
                    metric = f"+ {metric}"

            teams_data.append({
                "id": team_id, "rank": rank, "name": team_name,
                "team": "Team", "country": country_code, "metric": metric
            })
        except Exception:
            continue
    return teams_data


def scrape_rider_profile(rider_id, images_dir):
    url = f"https://www.procyclingstats.com/rider/{rider_id}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200: return None
        
        soup = BeautifulSoup(response.text, 'lxml')
        profile = {"id": rider_id}

        subtitle = soup.find('div', class_='subtitle')
        profile['current_team'] = subtitle.text.strip() if subtitle else ""

        # Photo
        img_div_parent = soup.find('div', class_='borderbox left w30 mr5')
        img_div = next(img_div_parent.children, None)
        profile['local_image_path'] = None
        profile['photo_url'] = None

        if img_div and img_div.find('img') and 'src' in img_div.find('img').attrs:
            img_src = img_div.find('img')['src']
            img_url = "https://www.procyclingstats.com/" + img_src if not img_src.startswith('http') else img_src
            profile['photo_url'] = img_url
            try:
                img_response = requests.get(img_url, headers=HEADERS, timeout=10)
                if img_response.status_code == 200:
                    filename = f"{rider_id}.img.ftdf"
                    encrypted_image = encrypt_data(img_response.content, SECRET_KEY)
                    with open(os.path.join(images_dir, filename), 'wb') as f:
                        f.write(encrypted_image)
                    profile['local_image_path'] = f"rider_images/{filename}"
            except Exception as e:
                logger.error(f"[{rider_id}] Failed to process image: {e}")

        info_list = soup.find('div', class_='borderbox left w65')
        profile['weight'], profile['height'] = "Unknown", "Unknown"
        if info_list:
            for li in info_list.find_all('li'):
                text = li.text.replace('\n', '').strip()
                if "Date of birth:" in text: profile['date_of_birth'] = text.split("Date of birth:")[1].split("(")[0].strip()
                if "Weight:" in text and "Height:" in text:
                    w_match, h_match = re.search(r'Weight:\s*([\d.]+)\s*kg', text), re.search(r'Height:\s*([\d.]+)\s*m', text)
                    if w_match: profile['weight'] = w_match.group(1) + " kg"
                    if h_match: profile['height'] = h_match.group(1) + " m"
                if "Place of birth:" in text: profile['place_of_birth'] = text.split("Place of birth:")[1].strip()

        specialties, top_results, key_stats, rankings, social = {}, [], {}, {}, {}
        pps_ul = soup.find('ul', class_='pps list')
        if pps_ul:
            for li in pps_ul.find_all('li'):
                v, t = li.find('div', class_='xvalue'), li.find('div', class_='xtitle')
                if v and t: specialties[t.text.strip().lower()] = int(v.text.strip()) if v.text.strip().isdigit() else 0
        profile['specialties'] = specialties

        top_res_ul = soup.find('ul', class_='list topresults')
        if top_res_ul:
            for li in top_res_ul.find_all('li'):
                n, r = li.find('div', class_='nrs'), li.find('div', class_='races')
                if r: top_results.append({"count": n.text.strip().replace('\xa0', ' ') if n else "", "type": (r.find('span', class_='blue').text.strip() if r.find('span', class_='blue') else ""), "race": (r.find('a').text.strip() if r.find('a') else ""), "years": (r.find('span', class_='clr777').text.replace('(', '').replace(')', '').strip() if r.find('span', class_='clr777') else "")})
        profile['top_results'] = top_results

        for a in soup.find_all('a', href=True):
            h = a['href']
            if 'instagram.com' in h: social['instagram'] = h
            elif 'x.com' in h or 'twitter.com' in h: social['twitter'] = h
            elif 'strava.com' in h: social['strava'] = h
        profile['social_links'] = social
        return profile
    except Exception as e:
        logger.error(f"[{rider_id}] ERROR: {e}")
        return None

# -------------------------------------------------------------------
# FLASK ROUTES
# -------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/scrape', methods=['POST'])
def scrape():
    data = request.json
    year = int(data.get('year', 2025))
    target_stage = int(data.get('stage', 1))

    riders_json = []           # Will hold the comprehensive data for the target_stage
    previous_stages_data = {}  # Will hold { stage_number: [stage_classification_data] }
    unique_rider_ids = set()

    # --- SCRAPE STAGES 1 TO TARGET_STAGE ---
    for current_stage in range(1, target_stage + 1):
        url = f'https://www.procyclingstats.com/race/tour-de-france/{year}/stage-{current_stage}'
        logger.info(f"--- Scraping Stage {current_stage} ---")
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            if response.status_code != 200:
                logger.warning(f"Stage {current_stage} not available. Skipping.")
                continue
                
            soup = BeautifulSoup(response.text, 'lxml')
            
            tabs_mapping = {}
            nav_ul = soup.find('ul', class_='tabs tabnav resultTabs')
            if nav_ul:
                for li in nav_ul.find_all('li'):
                    a_tag = li.find('a')
                    if not a_tag: continue
                    text, data_id = a_tag.text.strip().upper(), li.get('data-id')
                    if 'STAGE' in text: tabs_mapping['stage'] = data_id
                    elif 'GC' in text: tabs_mapping['general'] = data_id
                    elif 'POINTS' in text: tabs_mapping['points'] = data_id
                    elif 'KOM' in text: tabs_mapping['mountain'] = data_id
                    elif 'YOUTH' in text: tabs_mapping['youth'] = data_id
                    elif 'TEAMS' in text: tabs_mapping['teams'] = data_id

            # Determine what to scrape based on if it's the target stage or a previous one
            if current_stage == target_stage:
                classifications_to_scrape = ['stage', 'general', 'points', 'mountain', 'youth', 'teams']
            else:
                classifications_to_scrape = ['stage']

            stage_json_data = []
            
            for class_name in classifications_to_scrape:
                tab_id = tabs_mapping.get(class_name)
                if not tab_id: continue
                
                tab_div = soup.find('div', class_='resTab', attrs={'data-id': tab_id})
                if not tab_div: continue
                gen_div = tab_div.find('div', class_='general')
                table = gen_div.find('table', class_='results') if gen_div else tab_div.find('table', class_='results')
                if not table: continue

                if class_name == 'teams':
                    items = extract_teams(table)
                else:
                    items = extract_riders(table, class_name)
                    
                if items:
                    limited = items[:50]
                    stage_json_data.append({"classification": class_name, "ranking": limited})
                    
                    if class_name != 'teams':
                        unique_rider_ids.update([r['id'] for r in limited])

            # Assign to proper variables
            if current_stage == target_stage:
                riders_json = stage_json_data
            else:
                if stage_json_data:
                    previous_stages_data[current_stage] = stage_json_data

        except Exception as e:
            logger.error(f"Failed to scrape Stage {current_stage}: {e}")
            continue

    if not riders_json and not previous_stages_data:
        return jsonify({"success": False, "error": "No data could be extracted."}), 404

    # --- PROCESS FILES IN TEMPORARY DIRECTORY ---
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_folder = os.path.join(temp_dir, "FILA_TOUR_DE_FRANCE")
            images_folder = os.path.join(base_folder, "rider_images")
            os.makedirs(images_folder)

            # 1. Scrape all unique profiles concurrently
            profiles_json = []
            logger.info(f"Scraping {len(unique_rider_ids)} Profiles and Downloading Images...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
                futures = {executor.submit(scrape_rider_profile, r_id, images_folder): r_id for r_id in unique_rider_ids}
                for f in concurrent.futures.as_completed(futures):
                    res = f.result()
                    if res: profiles_json.append(res)

            logger.info("Encrypting Data and Building Archive...")
            
            # 2. Write riders.ftdf (Target Stage Data)
            if riders_json:
                riders_bytes = json.dumps(riders_json, ensure_ascii=False).encode('utf-8')
                with open(os.path.join(base_folder, 'riders.ftdf'), 'wb') as f:
                    f.write(encrypt_data(riders_bytes, SECRET_KEY))

            # 3. Write previous stages (stage_1.ftdf, stage_2.ftdf, etc.)
            for stg_num, stg_data in previous_stages_data.items():
                stg_bytes = json.dumps(stg_data, ensure_ascii=False).encode('utf-8')
                with open(os.path.join(base_folder, f'stage_{stg_num}.ftdf'), 'wb') as f:
                    f.write(encrypt_data(stg_bytes, SECRET_KEY))

            # 4. Write profiles.ftdf
            if profiles_json:
                profiles_bytes = json.dumps(profiles_json, ensure_ascii=False).encode('utf-8')
                with open(os.path.join(base_folder, 'profiles.ftdf'), 'wb') as f:
                    f.write(encrypt_data(profiles_bytes, SECRET_KEY))

            # 5. Zip and Password Protect
            zip_filename = os.path.join(temp_dir, "tour_data.zip")
            with pyzipper.AESZipFile(zip_filename, 'w', compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zf:
                zf.setpassword(ZIP_PASSWORD)
                for folder_name, _, filenames in os.walk(base_folder):
                    for filename in filenames:
                        file_path = os.path.join(folder_name, filename)
                        arcname = os.path.relpath(file_path, temp_dir)
                        zf.write(file_path, arcname)

            # Load ZIP into memory to send
            with open(zip_filename, 'rb') as f:
                return_data = io.BytesIO(f.read())
        
        return send_file(return_data, mimetype='application/zip', as_attachment=True, download_name=f'Tour_Data_Rnd_{target_stage}.zip')

    except Exception as e:
        logger.error("CRITICAL ERROR building files", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
