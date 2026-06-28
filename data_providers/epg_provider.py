# data_providers/epg_provider.py

import requests
import logging
import os
import io
import hashlib
from xml.etree import ElementTree as ET
from datetime import datetime, timezone, timedelta
import charset_normalizer
import database
import gzip
import re
import gettext
_ = gettext.gettext

def parse_epg_data(xml_content):
    try:
        database.init_epg_db()
        current_hash = hashlib.md5(xml_content.encode('utf-8', errors='ignore')).hexdigest()
        last_hash = database.get_config_value('last_epg_hash')
        conn = database.get_epg_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM epg_programs")
            program_count_in_db = cursor.fetchone()[0]
        except Exception as e:
            logging.error(f"Error checking epg_programs count: {e}")
            program_count_in_db = 0
        conn.close()
        logging.debug(f"[EPG HASH CHECK] Last Hash: {last_hash}, Current Hash: {current_hash}, DB Count: {program_count_in_db}")
        if last_hash == current_hash and program_count_in_db > 10:
            logging.info("EPG data is exactly the same as the database. Skipping parsing to save time!")
            return True
        logging.info("New EPG data OR empty database detected. Parsing and updating...")
        database.clear_epg_db()

        def parse_time(time_str):
            dt_part = time_str[:-6]
            tz_part = time_str[-5:]
            dt_obj = datetime.strptime(dt_part, '%Y%m%d%H%M%S')
            offset_hours = int(tz_part[1:3])
            offset_minutes = int(tz_part[3:5])
            sign = -1 if tz_part[0] == '-' else 1
            tz_offset = timezone(timedelta(hours=sign * offset_hours, minutes=sign * offset_minutes))
            return dt_obj.replace(tzinfo=tz_offset)            
        program_count = 0
        batch_data = []       
        f = io.StringIO(xml_content)
        context = ET.iterparse(f, events=('start', 'end'))
        _event, root = next(context)
        for event, elem in context:
            if event == 'end' and elem.tag == 'programme':
                channel_id = elem.get('channel')
                if not channel_id:
                    elem.clear()
                    root.clear()
                    continue                  
                title_elem = elem.find('title')
                desc_elem = elem.find('desc')
                title = title_elem.text if (title_elem is not None and title_elem.text) else _("No Title")
                desc = desc_elem.text if (desc_elem is not None and desc_elem.text) else ""               
                start_time_str = elem.get('start')
                stop_time_str = elem.get('stop')              
                try:
                     start_time = parse_time(start_time_str)
                     stop_time = parse_time(stop_time_str)
                     start_ts = int(start_time.timestamp())
                     stop_ts = int(stop_time.timestamp())
                except (ValueError, TypeError) as e:
                     logging.warning(f"Invalid time format for EPG program. Skipping. Error: {e}")
                     elem.clear()
                     root.clear()
                     continue
                batch_data.append((channel_id, title, desc, start_ts, stop_ts))
                program_count += 1
                if len(batch_data) >= 10000:
                    database.insert_epg_batch(batch_data)
                    batch_data.clear()               
                elem.clear()
                root.clear()
        if batch_data:
            database.insert_epg_batch(batch_data)
        database.set_config_value('last_epg_hash', current_hash)          
        logging.info(f"Successfully saved {program_count} EPG programs to SQLite Database.")
        return True       
    except ET.ParseError as e:
        logging.error(f"Failed to parse EPG XML content: {e}")
        return False
    except Exception as e:
        logging.error(f"An unexpected error occurred during EPG parsing: {e}")
        return False
        
def sanitize_xml(xml_string):
    if not xml_string:
        return xml_string       
    xml_string = xml_string.strip()
    if xml_string.startswith('<?xml') or xml_string.startswith('<tv'):
        return xml_string
    match = re.search(r'(<\?xml.*|<tv.*)', xml_string, re.DOTALL)
    if match:
        return match.group(1)       
    return xml_string        

def _load_from_url(url):
    user_agents = [
        "IPTVSmartersPro",    
        "VLC/3.0.9 LibVLC/3.0.9", 
        "curl/8.6.0",        
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36" 
    ]
    last_error = None
    raw_bytes = None
    for ua in user_agents:
        try:
            headers = {
                "User-Agent": ua,
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate"
            }
            logging.debug(f"Trying EPG download. Using User-Agent: {ua}")
            response = requests.get(url, timeout=60, headers=headers)
            if response.status_code == 200:
                raw_bytes = response.content
                logging.info(f"EPG downloaded successfully! Accepted User-Agent: {ua}")
                break
            elif response.status_code in [401, 403, 406]:
                logging.warning(f"Server blocked the request (Code: {response.status_code}). User-Agent: {ua}. Moving to next...")
                last_error = f"HTTP {response.status_code} ({ua})"
                continue
            else:
                response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logging.warning(f"Connection error (User-Agent: {ua}): {e}")
            last_error = str(e)
            continue
    if not raw_bytes:
        logging.error(f"All User-Agent attempts failed. Last Error: {last_error}")
        return None
    if raw_bytes.startswith(b'\x1f\x8b'):
        logging.info("EPG URL: GZIP format detected, decompressing in memory...")
        try:
            raw_bytes = gzip.decompress(raw_bytes)
        except Exception as e:
            logging.error(f"EPG URL: Gzip decompress failed: {e}")
    try:
        prediction = charset_normalizer.detect(raw_bytes)
        correct_encoding = prediction['encoding'] if prediction and prediction.get('encoding') else 'utf-8'
        xml_content = raw_bytes.decode(correct_encoding, errors='replace')
    except Exception as e:
        logging.error(f"EPG URL decode error: {e}")
        xml_content = raw_bytes.decode('utf-8', errors='replace')
    cleaned_xml = sanitize_xml(xml_content)
    if len(cleaned_xml) != len(xml_content):
        logging.info(f"Sanitized garbage characters from XML URL. Original: {len(xml_content)}, Cleaned: {len(cleaned_xml)}")           
    return cleaned_xml        

def _load_from_file(file_path):
    try:
        if not os.path.exists(file_path):
            logging.error(f"EPG file not found at local path: {file_path}")
            return None           
        with open(file_path, 'rb') as f:
            raw_bytes = f.read()
        if raw_bytes.startswith(b'\x1f\x8b'):
            logging.info("Local EPG file: GZIP format detected, decompressing...")
            try:
                raw_bytes = gzip.decompress(raw_bytes)
            except Exception as e:
                logging.error(f"Local EPG file: Gzip decompress failed: {e}")
        try:
            xml_content = raw_bytes.decode('utf-8')
            logging.info("Local EPG file decoded successfully using standard UTF-8.")
        except UnicodeDecodeError:
            try:
                prediction = charset_normalizer.detect(raw_bytes)
                correct_encoding = prediction['encoding'] if prediction and prediction.get('encoding') else 'utf-8'
                logging.info(f"Local EPG file encoding auto-detected as: {correct_encoding}")
                xml_content = raw_bytes.decode(correct_encoding, errors='replace')
            except Exception as e:
                logging.error(f"Local EPG file decode error: {e}")
                xml_content = raw_bytes.decode('utf-8', errors='replace')
        cleaned_xml = sanitize_xml(xml_content)
        if len(cleaned_xml) != len(xml_content):
            logging.info(f"Sanitized garbage characters from Local XML. Original: {len(xml_content)}, Cleaned: {len(cleaned_xml)}")         
        return cleaned_xml        
    except IOError as e:
        logging.error(f"Failed to open local EPG file '{file_path}': {e}")
        return None

def load_epg_data(path_or_url):
    if not path_or_url:
        return None
    logging.info(f"Loading EPG content from: {path_or_url}")
    xml_content = None
    if path_or_url.lower().startswith("http://") or path_or_url.lower().startswith("https://"):
        xml_content = _load_from_url(path_or_url)
    else:
        if not os.path.exists(path_or_url):
             logging.error(f"EPG file path does not exist: {path_or_url}")
             return None
        xml_content = _load_from_file(path_or_url)
    if not xml_content:
        logging.warning("EPG content is empty or could not be loaded.")
        return None
    return xml_content
