# utils/catalog_utils.py

import logging
import re
import database
import gettext
_ = gettext.gettext

def all_movies_label():
    return _(" 🎬 All Movies")

def all_series_label():
    return _(" 📺 All Series")

_ADULT_RE = re.compile(
    r"(?<![a-z0-9])(xxx|adults?|porn\w*|erotic\w*|erotik\w*|yeti[sş]kin\w*)(?![a-z0-9])|18\s*\+|\+\s*18(?!\d)",
    re.IGNORECASE,
)

def is_adult_category(name):
    if not name or not isinstance(name, str):
        return False
    return _ADULT_RE.search(name.replace("İ", "i").lower()) is not None

def _excluded_category_names(category_names):
    hidden = set(database.get_hidden_bouquets() or [])
    password_is_set = database.get_config_value('app_password') is not None
    excluded = set()
    adult = []
    for name in category_names:
        if name in hidden:
            excluded.add(name)
        elif password_is_set and database.get_bouquet_lock_status(name):
            excluded.add(name)
        elif is_adult_category(name):
            excluded.add(name)
            adult.append(name)
    if adult:
        logging.info(f"[All Titles] {len(adult)} adult categories skipped by name: {adult[:10]}")
    return excluded

def collect_all_vod(vod_data):
    if not vod_data:
        return []
    excluded = _excluded_category_names(vod_data.keys())
    seen = set()
    result = []
    for category_name, items in vod_data.items():
        if category_name in excluded or not items:
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            key = str(item.get('stream_id') or item.get('url') or '')
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            result.append(item)
    logging.info(
        f"[All Movies] {len(result)} titles collected from {len(vod_data) - len(excluded)} categories "
        f"({len(excluded)} hidden, locked or adult categories skipped)."
    )
    return result

def filter_all_series(series_list, categories):
    if not series_list:
        return []
    names_by_id = {str(cat.get('category_id')): cat.get('category_name') for cat in categories or []}
    excluded = _excluded_category_names([name for name in names_by_id.values() if name])
    excluded_ids = {cat_id for cat_id, name in names_by_id.items() if name in excluded}
    seen = set()
    result = []
    for item in series_list:
        if not isinstance(item, dict):
            continue
        if str(item.get('category_id')) in excluded_ids:
            continue
        key = str(item.get('series_id') or '')
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        result.append(item)
    logging.info(
        f"[All Series] {len(result)} of {len(series_list)} series kept "
        f"({len(excluded_ids)} hidden, locked or adult categories skipped)."
    )
    return result
