import os
import re

class PlaylistParser:
    @staticmethod
    def parse_m3u(file_path):
        channels = []
        if not os.path.exists(file_path): return channels
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for i in range(len(lines)):
                line = lines[i].strip()
                if line.startswith("#EXTINF"):
                    group_match = re.search(r'group-title="([^"]+)"', line)
                    group = group_match.group(1) if group_match else "General"                  
                    if group == "Undefined":
                        group = "General" 
                    tvg_id_match = re.search(r'tvg-id="([^"]+)"', line)
                    tvg_id = tvg_id_match.group(1) if tvg_id_match else ""                  
                    tvg_logo_match = re.search(r'tvg-logo="([^"]+)"', line)
                    tvg_logo = tvg_logo_match.group(1) if tvg_logo_match else ""                    
                    name_parts = line.split(',', 1)
                    name = name_parts[1] if len(name_parts) > 1 else "Unknown"                  
                    url = lines[i+1].strip() if i+1 < len(lines) else ""                 
                    channels.append({
                        "name": name, 
                        "group": group, 
                        "url": url,
                        "tvg-id": tvg_id,   
                        "tvg-logo": tvg_logo 
                    })
        return channels

    @staticmethod
    def parse_xtream_data(data_dict):
        channels = []
        for category, items in data_dict.get("bouquets", {}).items():
            for item in items:
                item["group"] = category
                channels.append(item)
        return channels
