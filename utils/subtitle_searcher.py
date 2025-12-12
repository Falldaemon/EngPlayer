# utils/subtitle_searcher.py

import requests
import logging
import os
from gi.repository import GLib
import zipfile
import io
import tempfile
import gettext
import locale
_ = gettext.gettext
API_SEARCH_URL = "https://api.opensubtitles.com/api/v1/subtitles"
API_DOWNLOAD_URL = "https://api.opensubtitles.com/api/v1/download"
HEADERS = {
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    'User-Agent': 'EngPlayer v0.1'
}

def search_subtitles_online(file_path, title_for_search, api_key, callback_on_main_thread, tmdb_id=None, year=None):
    """
    Searches for subtitles using the OpenSubtitles API (by TMDb ID, title, or year)
    and sends the results to the main thread via callback.
    """
    logging.info(f"Starting subtitle search. Title='{title_for_search}', Year='{year}', TMDb ID='{tmdb_id}'")
    results = []
    error = None
    try:
        search_headers = HEADERS.copy()
        search_headers['Api-Key'] = api_key
        params = {}
        if tmdb_id:
            params['tmdb_id'] = tmdb_id
            search_mode_log = f"TMDb ID ({tmdb_id})"
        elif title_for_search:
            params['query'] = title_for_search
            search_mode_log = f"Query ('{title_for_search}')"
            if year:
                params['year'] = year
                search_mode_log += f", Year ({year})"
        else:
            logging.error("TMDb ID or Title required to search for subtitles!")
            error = _("Not enough information to perform a search.")
            raise ValueError("Missing search parameters")
        system_lang_code = 'en'
        env_lang = os.environ.get("LANG", "") or os.environ.get("LANGUAGE", "")
        if env_lang and len(env_lang) >= 2:
            system_lang_code = env_lang.split('_')[0].split('.')[0].lower()
        else:
            try:
                loc = locale.getdefaultlocale()
                if loc and loc[0]: system_lang_code = loc[0].split('_')[0].lower()
            except Exception: pass
        params['languages'] = f"{system_lang_code},en" if system_lang_code != 'en' else 'en'
        logging.info(f"Parameter(s) being used for search: {search_mode_log}")
        logging.info(f"Languages being searched for subtitles: {params['languages']}")
        logging.debug(f"Sending OpenSubtitles API request. URL: {API_SEARCH_URL}, Parameters: {params}")
        response = requests.get(API_SEARCH_URL, headers=search_headers, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
        logging.debug(f"OpenSubtitles API response received: {len(data.get('data', []))} results found.")
        if data and 'data' in data and data['data']:
            logging.debug("API Response ('data' content): %s", data['data'])
            for item in data['data']:
                attributes = item.get('attributes', {})
                files = attributes.get('files', [])
                if attributes and item.get('id'):
                    first_file_name = 'N/A'
                    file_id_to_save = None
                    if files and isinstance(files, list) and len(files) > 0:
                         first_file_name = files[0].get('file_name', 'N/A')
                         file_id_to_save = files[0].get('file_id')
                    sub_info = {
                        'language': attributes.get('language', 'N/A'),
                        'release_name': attributes.get('release', ''),
                        'file_name': first_file_name,
                        'download_count': attributes.get('download_count', 0),
                        'rating': attributes.get('ratings', 0),
                        'upload_date': attributes.get('upload_date', ''),
                        'feature_type': attributes.get('feature_type', ''),
                        'subtitle_id': item.get('id'),
                        'file_id': file_id_to_save,
                        'fps': attributes.get('fps', 0.0)
                    }
                    if file_id_to_save:
                        results.append(sub_info)
                        logging.debug(f"Processed subtitle added: {sub_info}")
                    else:
                        logging.warning(f"API result skipped (missing file_id): {item}")
                else:
                    logging.warning(f"API result skipped (missing attributes or ID): {item}")
        else:
            logging.info(f"No subtitles found for '{title_for_search}'.")
            error = _("No subtitles found.")
    except requests.exceptions.Timeout:
        logging.error("OpenSubtitles API request timed out.")
        error = _("Search timed out.")
    except requests.exceptions.RequestException as e:
        logging.error(f"OpenSubtitles API request failed: {e}")
        if e.response is not None:
             if e.response.status_code == 401:
                 error = _("API Key is invalid or authorization failed.")
             elif e.response.status_code == 429:
                 error = _("API usage limit exceeded. Please try again later.")
             else:
                 error = _("Could not communicate with API (Error: {}).").format(e.response.status_code)
        else:
            error = _("Network error or API unreachable.")
    except Exception as e:
        logging.exception("An unexpected error occurred while searching for subtitles.")
        error = _("An unknown error occurred.")
    logging.debug(f"Search complete. Sending results to main thread (Error: {error})")
    GLib.idle_add(callback_on_main_thread, results, error)

def download_subtitle_file(file_id, api_key, callback_on_main_thread):
    """
    Gets the download link for the given file_id, downloads the file,
    extracts it from ZIP if necessary, and returns the path to the temporary SRT file via callback.
    (This function remains unchanged)
    """
    logging.info(f"Subtitle download process started: file_id={file_id}")
    temp_srt_path = None
    error = None
    try:
        download_headers = HEADERS.copy()
        download_headers['Api-Key'] = api_key
        payload = {'file_id': file_id}
        logging.debug(f"Requesting download link: URL={API_DOWNLOAD_URL}, Payload={payload}")
        response_link = requests.post(API_DOWNLOAD_URL, headers=download_headers, json=payload, timeout=15)
        response_link.raise_for_status()
        link_data = response_link.json()
        download_link = link_data.get('link')
        remaining = link_data.get('remaining')
        if remaining is not None:
            logging.info(f"Remaining downloads: {remaining}")
        if not download_link:
            logging.error("Download link ('link') not found in API response.")
            error = _("Could not retrieve subtitle download link.")
            raise ValueError("No download link found")
        logging.info(f"Download link received: {download_link}")
        response_file = requests.get(download_link, headers={'User-Agent': HEADERS['User-Agent']}, timeout=30, stream=True)
        response_file.raise_for_status()
        content_type = response_file.headers.get('Content-Type', '').lower()
        content = response_file.content
        logging.debug(f"File downloaded. Content-Type: {content_type}, Size: {len(content)} bytes")
        srt_content = None
        if 'zip' in content_type or download_link.lower().endswith('.zip'):
            logging.info("ZIP file detected, extracting content...")
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zip_ref:
                    srt_files_in_zip = [name for name in zip_ref.namelist() if name.lower().endswith('.srt')]
                    if not srt_files_in_zip:
                        logging.error("No .srt file found inside ZIP.")
                        error = _("No subtitle file found inside the downloaded ZIP.")
                        raise ValueError("No SRT file in ZIP")
                    srt_content = zip_ref.read(srt_files_in_zip[0])
                    logging.info(f"Successfully extracted '{srt_files_in_zip[0]}' from ZIP.")
            except zipfile.BadZipFile:
                logging.error("Downloaded file is a corrupt ZIP.")
                error = _("The downloaded ZIP file is corrupt.")
                raise
        else:
            srt_content = content
        if srt_content:
            try:
                srt_text = srt_content.decode('utf-8', errors='ignore')
            except UnicodeDecodeError:
                try:
                    srt_text = srt_content.decode('cp1252', errors='ignore')
                except Exception as decode_err:
                     logging.error(f"Could not decode SRT content: {decode_err}")
                     error = _("Could not read subtitle file (encoding error).")
                     raise ValueError("SRT decode failed") from decode_err
            with tempfile.NamedTemporaryFile(mode='w', suffix=".srt", delete=False, encoding='utf-8') as temp_file:
                temp_file.write(srt_text)
                temp_srt_path = temp_file.name
            logging.info(f"Subtitle saved to temporary file: {temp_srt_path}")
        else:
            if not error: error = _("Could not retrieve subtitle content.")
    except requests.exceptions.Timeout:
        logging.error("Subtitle download request timed out.")
        error = _("Download timed out.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Subtitle download request failed: {e}")
        if e.response is not None:
             if e.response.status_code == 401:
                 error = _("API Key is invalid or authorization failed.")
             elif e.response.status_code == 429:
                 error = _("API usage limit exceeded.")
             elif e.response.status_code == 404:
                 error = _("Subtitle file not found on server.")
             else:
                 error = _("API error during download ({}).").format(e.response.status_code)
        else:
            error = _("Network error during download.")
    except Exception as e:
        logging.exception("Unexpected error while downloading/saving subtitle.")
        if not error: error = _("Could not download subtitle (unknown error).")
    logging.debug(f"Download complete. Sending result to main thread (Error: {error})")
    GLib.idle_add(callback_on_main_thread, temp_srt_path, error)
