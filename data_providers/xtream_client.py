# data_providers/xtream_client.py

import requests
import logging

def _get_api_data(profile_info, action):
    """A helper function to make requests to the Xtream Codes player API."""
    host = profile_info.get("host")
    username = profile_info.get("username")
    password = profile_info.get("password")
    if not all([host, username, password]):
        logging.error(f"Xtream client: Profile information is incomplete for action '{action}'.")
        return None, None
    try:
        if action:
            url = f"{host}/player_api.php?username={username}&password={password}&action={action}"
        else:
            url = f"{host}/player_api.php?username={username}&password={password}"
        headers = {"User-Agent": "EngPlayer/1.0"}
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        json_response = response.json()
        user_info = None
        if isinstance(json_response, dict):
            user_info = json_response.get("user_info")
            auth_status = user_info.get("auth") if user_info else None
            if auth_status == 0:
                logging.error("Xtream API authentication failed. Check username/password.")
                return None, user_info
        return json_response, user_info
    except requests.exceptions.RequestException as e:
        logging.error(f"Xtream API request failed for action '{action}': {e}")
        return None, None
    except ValueError:
        logging.error(f"Failed to decode JSON from Xtream API for action '{action}'.")
        return None, None
def get_user_authentication(profile_info):
    """
    Fetches only the user_info block (status, exp_date, created_at)
    by making an action-less authentication call.
    """
    json_response, user_info = _get_api_data(profile_info, "")
    if user_info:
        logging.info("Successfully fetched user_info (exp_date, etc.).")
        return user_info
    logging.warning("Could not fetch user_info block.")
    return None

def get_series_categories(profile_info):
    """Fetches the list of series categories."""
    data, _ = _get_api_data(profile_info, "get_series_categories")
    if isinstance(data, list):
        logging.info(f"Successfully fetched {len(data)} series categories.")
        return data
    return []

def get_live_categories(profile_info):
    """Fetches the list of live stream categories."""
    data, _ = _get_api_data(profile_info, "get_live_categories")
    if isinstance(data, list):
        logging.info(f"Successfully fetched {len(data)} live categories.")
        return data
    return []

def get_vod_categories(profile_info):
    """Fetches the list of VOD categories."""
    data, _ = _get_api_data(profile_info, "get_vod_categories")
    if isinstance(data, list):
        logging.info(f"Successfully fetched {len(data)} VOD categories.")
        return data
    return []

def get_live_streams(profile_info):
    """Fetches all live streams."""
    data, _ = _get_api_data(profile_info, "get_live_streams")
    if isinstance(data, list):
        logging.info(f"Successfully fetched {len(data)} live streams.")
        return data
    if isinstance(data, dict) and isinstance(data.get('data'), list):
        return data.get('data')
    return []

def get_vod_streams(profile_info):
    """Fetches all VOD streams."""
    data, _ = _get_api_data(profile_info, "get_vod_streams")
    if isinstance(data, list):
        logging.info(f"Successfully fetched {len(data)} VOD streams.")
        return data
    if isinstance(data, dict) and isinstance(data.get('data'), list):
        return data.get('data')
    return []

def get_series_streams(profile_info, category_id):
    """Fetches all series streams for a specific category."""
    action_params = f"get_series&category_id={category_id}"
    data, _ = _get_api_data(profile_info, action_params)
    if isinstance(data, list):
        logging.info(f"Successfully fetched {len(data)} series for category ID {category_id}.")
        return data
    return []

def get_series_info(profile_info, series_id):
    """Fetches detailed information for a single series, including episodes."""
    action_params = f"get_series_info&series_id={series_id}"
    data, _ = _get_api_data(profile_info, action_params)
    if isinstance(data, dict):
        logging.info(f"Successfully fetched details for series ID {series_id}.")
        return data
    return None

def get_vod_info(profile_info, vod_id):
    """Fetches detailed information for a single VOD stream."""
    action_params = f"get_vod_info&vod_id={vod_id}"
    data, _ = _get_api_data(profile_info, action_params)
    if isinstance(data, dict):
        logging.info(f"Successfully fetched details for VOD ID {vod_id}.")
        return data
    return None
