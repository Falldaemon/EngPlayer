# data_providers/tmdb_client.py

import requests
import logging
import locale
import json
import re
import os
from core.config import VERSION

import gettext
_ = gettext.gettext

try:
    from thefuzz import fuzz, process
    logging.info("Loaded 'thefuzz' library for smart searching.")
    FUZZ_AVAILABLE = True
except ImportError:
    try:
        from fuzzywuzzy import fuzz, process
        logging.info("Loaded fallback 'fuzzywuzzy' library for smart searching.")
        FUZZ_AVAILABLE = True
    except ImportError:
        logging.warning("Smart search library ('thefuzz' or 'fuzzywuzzy') not found!")
        logging.warning("'Fuzzy' search will be skipped for Logo/EPG/TMDb matching.")
        logging.warning("For better results, install 'python3-thefuzz' (Debian/Ubuntu) or 'python3-fuzzywuzzy' (Fedora) package.")
        fuzz = None
        process = None
        FUZZ_AVAILABLE = False

API_BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
HEADERS = {"User-Agent": f"EngPlayer/{VERSION}", "Accept": "application/json"}

def get_system_language():
    """
    Detects system language robustly for ALL languages.
    Parses environment variables like 'de_DE.UTF-8' to 'de'.
    """
    env_lang = os.environ.get("LANG", "") or os.environ.get("LANGUAGE", "")
    if env_lang and len(env_lang) >= 2:
        return env_lang.split('_')[0].split('.')[0].lower()
    try:
        lang_code = locale.getdefaultlocale()[0]
        if lang_code:
            return lang_code.split('_')[0]
    except Exception:
        pass
    return "en"

SYSTEM_LANGUAGE = get_system_language()
MIN_MATCH_SCORE = 75

def _perform_tmdb_search(api_key, query, endpoint, language=None, year=None):
    """ Helper function: Performs a TMDb search in a specific language and year. """
    search_url = f"{API_BASE_URL}/search/{endpoint}"
    params = {"api_key": api_key, "query": query}
    lang_for_log = language if language else "global"
    if language:
        params["language"] = language
    if year:
        try:
            year_int = int(year)
            if endpoint == "movie":
                params["primary_release_year"] = year_int
                logging.debug(f"Added year filter for search (movie): {year_int}")
            elif endpoint == "tv":
                params["first_air_date_year"] = year_int
                logging.debug(f"Added year filter for search (tv): {year_int}")
        except (ValueError, TypeError):
             logging.warning(f"Invalid year format ({year}), could not be added as a filter.")
    try:
        logging.debug(f"TMDb API request ({lang_for_log}): Query='{query}', Lang='{language}', Year='{year or '?'}'")
        logging.debug(f"🚀 OUTGOING HEADERS: {HEADERS}")
        response = requests.get(search_url, params=params, headers=HEADERS, timeout=10)
        response.raise_for_status()
        results = response.json().get("results", [])
        logging.debug(f"TMDb API response ({lang_for_log}): {len(results)} results found.")
        return results
    except requests.exceptions.RequestException as e:
        logging.error(f"TMDb API ({lang_for_log}) request failed: {e} | Query: {query}, Year: {year or '?'}")
        raise e

def _find_best_match(original_title, year, results):
    """
    Finds the best match using fuzzy matching.
    """
    if not results:
        return None, 0
    if not FUZZ_AVAILABLE:
        logging.warning("Fuzzy library not available, taking first result (low confidence).")
        return results[0], MIN_MATCH_SCORE -1
    best_match = None
    highest_score = 0
    for result in results:
        tmdb_title = result.get("title") or result.get("name")
        if not tmdb_title:
            continue
        score = fuzz.token_set_ratio(original_title.lower(), tmdb_title.lower())
        result_year_str = ""
        if year:
            result_year = (result.get("release_date") or result.get("first_air_date", ""))
            result_year_str = result_year.split('-')[0]
            if result_year_str == year: score += 15
            elif result_year_str:
                try:
                    year_diff = abs(int(year) - int(result_year_str))
                    if year_diff == 1: score -= 10
                    elif year_diff > 1: score -= 30
                except ValueError: score -= 30
        logging.debug(f"-> Score: {score}% | Original: '{original_title}' ({year or '?'}) | TMDb: '{tmdb_title}' ({result_year_str or '?'})")
        if score > highest_score:
            highest_score = score
            best_match = result
    return best_match, highest_score

def search_media(api_key, title, media_type, year=None):
    """
    Main search function.
    Returns 3 states: (data, "success"), (None, "no_match_found"), (None, "network_error")
    """
    if not api_key: return None, "api_key_missing"
    endpoint = "tv" if media_type == "tv" else "movie"
    search_query = title
    try:
        logging.debug("Performing primary Global (English) search...")
        global_results = _perform_tmdb_search(api_key, search_query, endpoint, language=None, year=year)
        best_match_global, score_global = _find_best_match(title, year, global_results)
        if best_match_global and score_global >= MIN_MATCH_SCORE:
            logging.info(f"Global match found and valid ({score_global}% >= {MIN_MATCH_SCORE}%).")
            return best_match_global, "success"
        logging.warning(f"Global search did not pass the {MIN_MATCH_SCORE}% threshold (Score: {score_global}).")
        if SYSTEM_LANGUAGE != "en":
            logging.debug(f"Global search failed. Performing fallback search in System Language ({SYSTEM_LANGUAGE})...")
            system_lang_results = _perform_tmdb_search(api_key, search_query, endpoint, language=SYSTEM_LANGUAGE, year=year)
            best_match_system, score_system = _find_best_match(title, year, system_lang_results)
            if best_match_system and score_system >= MIN_MATCH_SCORE:
                logging.info(f"System language (fallback) match found and valid ({score_system}% >= {MIN_MATCH_SCORE}%).")
                return best_match_system, "success"
            logging.warning(f"System language (fallback) search also failed to pass the {MIN_MATCH_SCORE}% threshold (Score: {score_system}).")
        logging.warning(f"No match passing MIN={MIN_MATCH_SCORE} score found on TMDb for '{title} {year or ''}'.")
        return None, "no_match_found"
    except requests.exceptions.RequestException:
        logging.warning(f"TMDb search for '{title}' failed due to NETWORK ERROR.")
        return None, "network_error"

def get_poster_url(poster_path):
    if not poster_path: return None
    return f"{IMAGE_BASE_URL}{poster_path}"

def get_media_details(api_key, media_id, media_type):
    if not api_key or not media_id: return None
    endpoint = "tv" if media_type == "tv" else "movie"
    details_url = f"{API_BASE_URL}/{endpoint}/{media_id}"
    merged_data = None
    trailer_key = None
    genres_str = ""
    cast_list_with_pics = []
    primary_language = SYSTEM_LANGUAGE
    params = {"api_key": api_key, "language": primary_language, "append_to_response": "credits,videos"}
    logging.debug(f"Fetching TMDb details (Primary: {primary_language}, including videos) for {media_type} ID {media_id}")
    primary_request_successful = False
    try:
        response = requests.get(details_url, params=params, headers=HEADERS, timeout=10)
        if response.status_code == 404 and primary_language != "en":
             logging.warning(f"Details not found in {primary_language} (404), will fallback to English.")
        else:
            response.raise_for_status()
            merged_data = response.json()
            primary_request_successful = True
            if merged_data and 'videos' in merged_data and merged_data['videos'].get('results'):
                videos = merged_data['videos']['results']
                official_trailer = next((v for v in videos if v.get('site') == 'YouTube' and v.get('type') == 'Trailer' and v.get('official')), None)
                if official_trailer:
                    trailer_key = official_trailer.get('key')
                    logging.debug(f"Primary language OFFICIAL trailer found: {trailer_key}")
                else:
                    first_trailer = next((v for v in videos if v.get('site') == 'YouTube' and v.get('type') == 'Trailer'), None)
                    if first_trailer:
                        trailer_key = first_trailer.get('key')
                        logging.debug(f"Primary language non-official trailer found (fallback): {trailer_key}")
    except requests.exceptions.RequestException as e:
        logging.warning(f"TMDb details ({primary_language}) request failed: {e}. Trying English fallback.")
        merged_data = None
    needs_english_fallback = False
    if not primary_request_successful and primary_language != "en":
        needs_english_fallback = True
        logging.debug("Triggering English fallback because primary request failed.")
    elif primary_request_successful and primary_language != "en":
        if not merged_data.get("overview") or not trailer_key:
             needs_english_fallback = True
             reason = "overview is missing" if not merged_data.get("overview") else "trailer key not found"
             logging.debug(f"Triggering English fallback because {reason} in primary language.")
    if needs_english_fallback:
        try:
            params_en = {"api_key": api_key, "language": "en-US", "append_to_response": "credits,videos"}
            logging.debug(f"Fetching TMDb details (English Fallback, including videos) for {media_type} ID {media_id}")
            response_en = requests.get(details_url, params=params_en, headers=HEADERS, timeout=10)
            response_en.raise_for_status()
            data_en = response_en.json()
            if not merged_data:
                merged_data = data_en
            else:
                logging.debug("Merging English fallback data into primary language data.")
                if not merged_data.get('overview') and data_en.get('overview'):
                    merged_data['overview'] = data_en.get('overview')
                    logging.debug("Merging: Overwriting empty primary overview with English overview.")
                if not merged_data.get('credits') and data_en.get('credits'):
                     merged_data['credits'] = data_en.get('credits')
                merged_data.setdefault('title', data_en.get('title'))
                merged_data.setdefault('name', data_en.get('name'))
                if not merged_data.get('genres') and data_en.get('genres'):
                     merged_data['genres'] = data_en.get('genres')
            if not trailer_key and data_en and 'videos' in data_en and data_en['videos'].get('results'):
                logging.debug("Searching for ANY trailer in English fallback video results...")
                videos_en = data_en['videos']['results']
                official_trailer_en = next((v for v in videos_en if v.get('site') == 'YouTube' and v.get('type') == 'Trailer' and v.get('official')), None)
                if official_trailer_en:
                    trailer_key = official_trailer_en.get('key')
                    logging.info(f"English fallback OFFICIAL trailer found: {trailer_key}")
                else:
                    first_trailer_en = next((v for v in videos_en if v.get('site') == 'YouTube' and v.get('type') == 'Trailer'), None)
                    if first_trailer_en:
                        trailer_key = first_trailer_en.get('key')
                        logging.info(f"English fallback non-official trailer found: {trailer_key}")
        except requests.exceptions.RequestException as e_en:
            logging.error(f"TMDb details (English Fallback) request failed: {e_en}")
    title = None
    release_date = None
    vote_average = None
    overview = None
    poster_path = None
    director = _("Unknown")
    cast_names_only_str = ""
    if merged_data:
        genres = merged_data.get('genres', [])
        if genres:
            genres_str = ", ".join([genre.get('name', '') for genre in genres if genre.get('name')])
            logging.debug(f"Genres found: {genres_str}")
        credits_data = merged_data.get('credits', {})
        cast_raw = credits_data.get('cast', [])
        for actor in cast_raw[:6]:
            if actor and actor.get('name') and actor.get('profile_path'):
                cast_list_with_pics.append({
                    "name": actor.get('name'),
                    "profile_path": actor.get('profile_path')
                })
        logging.debug(f"{len(cast_list_with_pics)} cast members (with pictures) found.")
        creators = [member['name'] for member in merged_data.get('created_by', []) if member and 'name' in member]
        if creators: director = ", ".join(creators)
        else:
            crew = credits_data.get('crew', [])
            for member in crew:
                if member and member.get('job') == 'Director' and 'name' in member:
                    director = member['name']; break
        cast_names_only_str = ", ".join([actor['name'] for actor in cast_raw[:5] if actor and 'name' in actor])
        countries_str = ""
        if media_type == "movie":
            countries_list = merged_data.get('production_countries', [])
            if countries_list:
                countries_str = ", ".join([country.get('name', '') for country in countries_list if country.get('name')])
        elif media_type == "tv":
            countries_list = merged_data.get('origin_country', [])
            if countries_list:
                countries_str = ", ".join(countries_list)
        logging.debug(f"Production country found: {countries_str}")
        title = merged_data.get("title") or merged_data.get("name")
        release_date = merged_data.get("release_date") or merged_data.get("first_air_date")
        vote_average = merged_data.get("vote_average")
        overview = merged_data.get("overview")
        poster_path = merged_data.get("poster_path")
    else:
        logging.error(f"TMDb details could not be fetched for {media_type} ID {media_id} in any language.")
        return None
    return {
        "id": merged_data.get("id"),
        "title": title,
        "overview": overview,
        "poster_path": poster_path,
        "release_date": release_date,
        "vote_average": vote_average,
        "director": director,
        "cast": cast_names_only_str,
        "genres": genres_str,
        "cast_with_pics": cast_list_with_pics,
        "trailer_key": trailer_key,
        "countries": countries_str
    }

def get_season_details(api_key, tv_id, season_number):
    if not api_key or not tv_id:
        return None
    url = f"{API_BASE_URL}/tv/{tv_id}/season/{season_number}"
    params = {"api_key": api_key, "language": SYSTEM_LANGUAGE}
    data_primary = None
    try:
        logging.debug(f"Fetching season details (Primary: {SYSTEM_LANGUAGE}): TV ID {tv_id}, Season {season_number}")
        response = requests.get(url, params=params, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            data_primary = response.json()
    except requests.exceptions.RequestException as e:
        logging.warning(f"Primary season details fetch failed: {e}")
    data_en = None
    should_fetch_en = False
    if not data_primary:
        should_fetch_en = True
    elif SYSTEM_LANGUAGE != "en":
        episodes = data_primary.get("episodes", [])
        if any(not ep.get("overview") for ep in episodes):
            should_fetch_en = True
            logging.info(f"Missing overviews detected in {SYSTEM_LANGUAGE}. Will fetch English fallback.")
    if should_fetch_en and SYSTEM_LANGUAGE != "en":
        try:
            params["language"] = "en"
            logging.debug(f"Fetching season details (English Fallback): TV ID {tv_id}, Season {season_number}")
            response_en = requests.get(url, params=params, headers=HEADERS, timeout=10)
            if response_en.status_code == 200:
                data_en = response_en.json()
        except Exception as e:
            logging.error(f"English fallback fetch failed: {e}")
    final_data = data_primary if data_primary else data_en
    if data_primary and data_en:
        primary_eps = {ep.get("episode_number"): ep for ep in data_primary.get("episodes", [])}
        en_eps = {ep.get("episode_number"): ep for ep in data_en.get("episodes", [])}
        for ep_num, p_ep in primary_eps.items():
            if not p_ep.get("overview") and ep_num in en_eps:
                en_overview = en_eps[ep_num].get("overview")
                if en_overview:
                    p_ep["overview"] = en_overview
            if not p_ep.get("name") and ep_num in en_eps:
                 en_name = en_eps[ep_num].get("name")
                 if en_name:
                     p_ep["name"] = en_name
        final_data["episodes"] = list(primary_eps.values())
    if not final_data:
        return None
    episodes = final_data.get("episodes", [])
    processed_episodes = {}
    for ep in episodes:
        ep_num = str(ep.get("episode_number"))
        processed_episodes[ep_num] = {
            "id": ep.get("id"),
            "name": ep.get("name"),
            "overview": ep.get("overview"),
            "still_path": ep.get("still_path"),
            "vote_average": ep.get("vote_average")
        }
    return processed_episodes
