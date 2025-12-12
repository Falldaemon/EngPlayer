# data_providers/epg_provider.py

import requests
import logging
import os
from xml.etree import ElementTree as ET
from datetime import datetime, timezone, timedelta
import gettext
_ = gettext.gettext

def parse_epg_data(xml_content):
    """
    Parses XMLTV format content and returns a dictionary
    containing program lists, keyed by channel ID.
    (Now includes past programs)
    """
    epg_data = {}
    try:
        root = ET.fromstring(xml_content)

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
        for programme in root.findall('programme'):
            channel_id = programme.get('channel')
            if not channel_id:
                continue
            title_elem = programme.find('title')
            desc_elem = programme.find('desc')
            title = title_elem.text if title_elem is not None else _("No Title")
            desc = desc_elem.text if desc_elem is not None else ""
            start_time_str = programme.get('start')
            stop_time_str = programme.get('stop')
            try:
                 start_time = parse_time(start_time_str)
                 stop_time = parse_time(stop_time_str)
            except (ValueError, TypeError) as e:
                 logging.warning(f"Invalid time format for EPG program: {start_time_str} / {stop_time_str}. Skipping. Error: {e}")
                 continue
            if channel_id not in epg_data:
                epg_data[channel_id] = []
            epg_data[channel_id].append({
                "title": title,
                "desc": desc,
                "start": start_time,
                "stop": stop_time
            })
            program_count += 1
        for channel_id in epg_data:
            epg_data[channel_id].sort(key=lambda x: x['start'])
        logging.info(f"Successfully parsed {program_count} EPG programs for {len(epg_data)} channels (including past programs).")
        return epg_data
    except ET.ParseError as e:
        logging.error(f"Failed to parse EPG XML content: {e}")
        return {}
    except Exception as e:
        logging.error(f"An unexpected error occurred during EPG parsing: {e}")
        return {}

def _load_from_url(url):
    """(HELPER FUNCTION) Downloads EPG data from the given URL."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
        }
        response = requests.get(url, timeout=60, headers=headers)
        response.raise_for_status()
        try:
            xml_content = response.content.decode('utf-8')
        except UnicodeDecodeError:
            try:
                xml_content = response.content.decode('iso-8859-9')
            except UnicodeDecodeError:
                 xml_content = response.content.decode(response.apparent_encoding, errors='ignore')
        return xml_content
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to download EPG data from URL: {e}")
        return None

def _load_from_file(file_path):
    """(HELPER FUNCTION) Reads EPG data from the given local file."""
    try:
        if not os.path.exists(file_path):
            logging.error(f"EPG file not found at local path: {file_path}")
            return None
        encodings_to_try = ['utf-8', 'iso-8859-9', 'cp1254']
        xml_content = None
        for enc in encodings_to_try:
             try:
                 with open(file_path, 'r', encoding=enc) as f:
                     xml_content = f.read()
                 logging.info(f"Local EPG file read successfully with encoding: {enc}")
                 break
             except UnicodeDecodeError:
                 logging.warning(f"Failed to read local EPG file with encoding {enc}. Trying next...")
             except Exception as e:
                 logging.error(f"Failed to read local EPG file '{file_path}': {e}")
                 return None
        if xml_content is None:
             logging.error(f"Could not decode local EPG file with any known encoding: {file_path}")
             return None
        return xml_content
    except IOError as e:
        logging.error(f"Failed to open local EPG file '{file_path}': {e}")
        return None

def load_epg_data(path_or_url):
    """
    (MAIN FUNCTION) Detects if the given path is a URL or local file,
    loads the data, and returns the RAW CONTENT (Parsing is not done here).
    """
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
