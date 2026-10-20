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
from core.config import PROVIDER_USER_AGENT
import gzip
import re
import time
import gettext
_ = gettext.gettext

def _parse_single_source(xml_content, already_covered_channel_ids):
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
    newly_covered_channel_ids = set()
    skipped_channel_ids = set()
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
            if channel_id in already_covered_channel_ids:
                skipped_channel_ids.add(channel_id)
                elem.clear()
                root.clear()
                continue
            title_elem = elem.find('title')
            desc_elem = elem.find('desc')
            icon_elem = elem.find('icon')
            title = title_elem.text if (title_elem is not None and title_elem.text) else _("No Title")
            desc = desc_elem.text if (desc_elem is not None and desc_elem.text) else ""
            poster_url = icon_elem.get('src') if icon_elem is not None else None
            start_time_str = elem.get('start')
            stop_time_str = elem.get('stop')
            try:
                 start_time = parse_time(start_time_str)
                 stop_time = parse_time(stop_time_str)
                 start_ts = int(start_time.timestamp())
                 stop_ts = int(stop_time.timestamp())
            except (ValueError, TypeError) as e:
                 logging.warning(f"[EPG] Invalid time format for EPG program. Skipping. Error: {e}")
                 elem.clear()
                 root.clear()
                 continue
            batch_data.append((channel_id, title, desc, start_ts, stop_ts, poster_url))
            newly_covered_channel_ids.add(channel_id)
            program_count += 1
            if len(batch_data) >= 10000:
                database.insert_epg_batch(batch_data)
                batch_data.clear()
            elem.clear()
            root.clear()
    if batch_data:
        database.insert_epg_batch(batch_data)
    already_covered_channel_ids.update(newly_covered_channel_ids)
    return program_count, skipped_channel_ids

def parse_epg_sources(xml_contents, profile_id):
    xml_contents = [c for c in xml_contents if c]
    if not xml_contents:
        logging.info("[EPG] No EPG source content to parse for this profile.")
        return False
    try:
        database.init_epg_db()
        combined_hash = hashlib.md5(
            "\x1e".join(xml_contents).encode('utf-8', errors='ignore')
        ).hexdigest()
        hash_config_key = f"last_epg_hash_{profile_id}"
        last_hash = database.get_config_value(hash_config_key)
        conn = database.get_epg_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM epg_programs")
            program_count_in_db = cursor.fetchone()[0]
        except Exception as e:
            logging.error(f"[EPG] Error checking epg_programs count: {e}")
            program_count_in_db = 0
        conn.close()
        logging.debug(f"[EPG HASH CHECK] Last Hash: {last_hash}, Current Hash: {combined_hash}, DB Count: {program_count_in_db}")
        if last_hash == combined_hash and program_count_in_db > 10:
            logging.info("[EPG] Combined EPG content is unchanged since last run. Skipping re-parse for this profile.")
            return True
        logging.info(f"[EPG] Merging {len(xml_contents)} EPG source(s) for this profile (priority order 1 -> {len(xml_contents)})...")
        database.clear_epg_db()
        seen_channel_ids = set()
        total_program_count = 0
        for index, xml_content in enumerate(xml_contents, start=1):
            logging.info(f"[EPG] Parsing source {index}/{len(xml_contents)} (priority {index})...")
            added, skipped_channels = _parse_single_source(xml_content, seen_channel_ids)
            total_program_count += added
            logging.info(
                f"[EPG] Source {index}/{len(xml_contents)}: {added} programs added, "
                f"{len(skipped_channels)} channel(s) skipped (already covered by a higher-priority source)."
            )
        database.set_config_value(hash_config_key, combined_hash)
        logging.info(f"[EPG] Successfully merged {total_program_count} EPG programs from {len(xml_contents)} source(s).")
        return True
    except Exception as e:
        logging.error(f"[EPG] Unexpected error while merging EPG sources: {e}")
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
    user_agents = ["IPTVSmartersPro", PROVIDER_USER_AGENT]
    max_attempts = 3
    retry_delay = 5
    total_budget = 120
    min_speed = 50 * 1024
    started = time.monotonic()
    ua_index = 0
    attempt = 0
    last_error = None
    raw_bytes = None
    while attempt < max_attempts:
        attempt += 1
        ua = user_agents[ua_index]
        headers = {
            "User-Agent": ua,
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate"
        }
        try:
            logging.debug(f"Trying EPG download (attempt {attempt}/{max_attempts}, User-Agent: {ua}).")
            with requests.get(url, timeout=(5, 30), headers=headers, stream=True) as response:
                code = response.status_code
                if code in (401, 403, 406) and ua_index + 1 < len(user_agents):
                    last_error = f"HTTP {code}"
                    logging.warning(f"Server rejected User-Agent '{ua}' ({last_error}). Trying the next one...")
                    ua_index += 1
                    attempt -= 1
                    continue
                if code in (401, 403, 404, 406):
                    last_error = f"HTTP {code}"
                    logging.warning(f"EPG request rejected ({last_error}). Not retrying.")
                    break
                response.raise_for_status()
                chunks = []
                received = 0
                for chunk in response.iter_content(chunk_size=8192):
                    chunks.append(chunk)
                    received += len(chunk)
                    elapsed = time.monotonic() - started
                    if elapsed > total_budget and received / elapsed < min_speed:
                        raise requests.exceptions.Timeout(
                            f"EPG download too slow ({received // 1024} KB in {int(elapsed)} s)")
                raw_bytes = b"".join(chunks)
            logging.info(f"EPG downloaded successfully (attempt {attempt}, User-Agent: {ua}).")
            break
        except requests.exceptions.RequestException as e:
            last_error = str(e)
            logging.warning(f"EPG download attempt {attempt}/{max_attempts} failed: {e}")
        if attempt < max_attempts and time.monotonic() - started + retry_delay < total_budget:
            time.sleep(retry_delay)
        else:
            break
    if not raw_bytes:
        logging.error(f"EPG download failed. Last error: {last_error}")
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
