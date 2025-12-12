# utils/profile_manager.py 

import json
import os
import logging
from core.config import PROFILES_PATH

def load_profiles():
    """Loads the profile list from the JSON file."""
    if os.path.exists(PROFILES_PATH):
        try:
            with open(PROFILES_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []

def save_profiles(profiles):
    """Saves the profile list to the JSON file."""
    os.makedirs(os.path.dirname(PROFILES_PATH), exist_ok=True)
    with open(PROFILES_PATH, 'w', encoding='utf-8') as f:
        json.dump(profiles, f, indent=4, ensure_ascii=False)

def update_profile_dates(profile_id, start_date_ts, exp_date_ts):
    """
    Reads and writes profiles.json just to update the date fields
    (created and expiration).
    Does not touch other cache timestamps.
    """
    if not start_date_ts and not exp_date_ts:
        return
    profiles = load_profiles()
    found = False
    for p in profiles:
        if p.get("id") == profile_id:
            if start_date_ts and p.get("created_at") != start_date_ts:
                p["created_at"] = start_date_ts
                found = True
            if exp_date_ts and p.get("exp_date") != exp_date_ts:
                p["exp_date"] = exp_date_ts
                found = True
            break
    if found:
        logging.info(f"Updating expiration dates for profile {profile_id}.")
        save_profiles(profiles)
    else:
        if not any(p.get("id") == profile_id for p in profiles):
             logging.warning(f"update_profile_dates: Profile ID {profile_id} not found.")
