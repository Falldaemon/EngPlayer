# core/config.py

import os
import base64
from gi.repository import GLib

APP_ID = "io.github.falldaemon.engplayer"
VERSION = "0.1.0"

current_dir = os.path.dirname(os.path.abspath(__file__))
base_dir = os.path.dirname(current_dir)
LOCALE_DIR = os.path.join(base_dir, "resources", "locale")

user_config_dir = GLib.get_user_config_dir()
APP_CONFIG_DIR = os.path.join(user_config_dir, "EngPlayer")
PROFILES_PATH = os.path.join(APP_CONFIG_DIR, "profiles.json")
_OBFUSCATED_TMDB_KEY = "=czNxE2YlFGO1cTYhZ2YhhzMhVTN2UzN5YjNwMGZ2UTY"

def get_fallback_tmdb_key():
    try:
        if not _OBFUSCATED_TMDB_KEY or _OBFUSCATED_TMDB_KEY == "PASTE_HERE":
            return None
        reversed_str = _OBFUSCATED_TMDB_KEY[::-1]
        decoded_bytes = base64.b64decode(reversed_str)
        return decoded_bytes.decode("utf-8")
    except Exception:
        return None

_OBFUSCATED_TRAKT_ID = "==AN2ATOxQDNzAzNhNTZ1ATNhhjNwATZihTOiVTO3Y2YxITO3cDO4cTY3AjYkZGZ0EjZkN2YkRDZxkzN3cjM1cTN"

def get_trakt_client_id():
    """Decodes the obfuscated Trakt Client ID."""
    try:
        if not _OBFUSCATED_TRAKT_ID or _OBFUSCATED_TRAKT_ID == "PASTE_YOUR_OBFUSCATED_TRAKT_CODE_HERE":
            return None
        reversed_str = _OBFUSCATED_TRAKT_ID[::-1]
        decoded_bytes = base64.b64decode(reversed_str)
        return decoded_bytes.decode("utf-8")
    except Exception:
        return None
