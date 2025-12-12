# data_providers/m3u_provider.py

import re
from collections import defaultdict
import logging

import gettext
_ = gettext.gettext

def parse_m3u_content(lines):
    """
    Parses a list of M3U lines and returns channels/VODs.
    """
    bouquets = defaultdict(list)
    vods = defaultdict(list)
    VOD_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.mov'}
    try:
        line_num = 0
        while line_num < len(lines):
            line = lines[line_num].strip()
            if line.startswith("#EXTINF:"):
                channel_info = line
                next_line_num = line_num + 1
                url_line = None
                while next_line_num < len(lines):
                    potential_url = lines[next_line_num].strip()
                    if potential_url and not potential_url.startswith("#"):
                        url_line = potential_url
                        break
                    next_line_num += 1
                if url_line:
                    channel_name = channel_info.split(",")[-1].strip()
                    group_match = re.search(r'group-title="([^"]+)"', channel_info, re.IGNORECASE)
                    group_title = group_match.group(1) if group_match else _("Others")
                    logo_match = re.search(r'tvg-logo="([^"]+)"', channel_info, re.IGNORECASE)
                    logo_url = logo_match.group(1) if logo_match else None
                    tvg_id_match = re.search(r'tvg-id="([^"]+)"', channel_info, re.IGNORECASE)
                    tvg_id = tvg_id_match.group(1) if tvg_id_match else None
                    is_vod = any(url_line.lower().endswith(ext) for ext in VOD_EXTENSIONS)
                    archive_match = re.search(r'tv_archive="([^"]+)"', channel_info, re.IGNORECASE)
                    duration_match = re.search(r'tv_archive_duration="([^"]+)"', channel_info, re.IGNORECASE)
                    item_data = {
                        "name": channel_name,
                        "url": url_line,
                        "logo": logo_url,
                        "tvg-id": tvg_id
                    }
                    if archive_match:
                        item_data["tv_archive"] = archive_match.group(1)
                    if duration_match:
                         item_data["tv_archive_duration"] = duration_match.group(1)
                    if is_vod:
                        vods[group_title].append(item_data)
                    else:
                        bouquets[group_title].append(item_data)
                    line_num = next_line_num
                else:
                    line_num += 1
            else:
                line_num += 1
        logging.info(f"Successfully parsed {len(bouquets)} bouquets and {len(vods)} VOD categories.")
        return dict(bouquets), dict(vods)
    except Exception as e:
        logging.error(f"An error occurred while parsing M3U content: {e}")
        return {}, {}

def load_from_file(filepath):
    """
    Loads an M3U file from a path and parses its content.
    """
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        return parse_m3u_content(lines)
    except Exception as e:
        logging.error(f"Error loading M3U from file '{filepath}': {e}")
        return {}, {}

