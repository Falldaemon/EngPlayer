# data_providers/trakt_client.py

import requests
import logging
import time
import threading
import webbrowser
import socket
import hashlib
import base64
import os
import re
from gi.repository import GLib
import database
from core.config import get_trakt_client_id

import gettext
_ = gettext.gettext

TRAKT_CLIENT_ID = get_trakt_client_id()
TRAKT_REDIRECT_URI = "http://localhost:12345"
TRAKT_REDIRECT_PORT = 12345
TRAKT_API_URL = "https://api.trakt.tv"
HEADERS = {
    'Content-Type': 'application/json',
    'trakt-api-version': '2'
}

def _generate_code_verifier():
    """Generates a 64-byte random verifier for PKCE."""
    return base64.urlsafe_b64encode(os.urandom(64)).decode('utf-8').rstrip('=')

def _generate_code_challenge(verifier):
    """Generates a SHA256 code challenge from the given verifier."""
    challenge_bytes = hashlib.sha256(verifier.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(challenge_bytes).decode('utf-8').rstrip('=')

def _start_local_server_for_callback(verifier, final_callback_on_main):
    """
    (Background Thread)
    Starts a temporary localhost server to capture the code redirected by Trakt.tv.
    """
    server_socket = None
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('127.0.0.1', TRAKT_REDIRECT_PORT))
        server_socket.listen(1)
        logging.info(f"PKCE: Callback server started at {TRAKT_REDIRECT_URI}.")
        conn, addr = server_socket.accept()
        request_data = conn.recv(1024).decode('utf-8')
        code = None
        match = re.search(r'GET /\?code=([^\s&]+)', request_data)
        if match:
            code = match.group(1)
            logging.info("PKCE: Authorization code successfully received from browser.")
            title_success = _("Login Successful")
            msg_success = _("You can return to EngPlayer. You may close this window.")
            response = (
                f"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"
                f"<html><head><title>{title_success}</title></head><body><h1>{title_success}!</h1>"
                f"<p>{msg_success}</p></body></html>"
            )
            conn.sendall(response.encode('utf-8'))
        else:
            logging.error(f"PKCE: Callback request received but 'code' parameter was not found. Data: {request_data}")
            title_fail = _("Login Failed")
            msg_fail = _("Could not retrieve code.")
            response = (
                f"HTTP/1.1 400 Bad Request\r\nContent-Type: text/html\r\n\r\n"
                f"<html><body><h1>{title_fail}</h1><p>{msg_fail}</p></body></html>"
            )
            conn.sendall(response.encode('utf-8'))
        conn.close()
        server_socket.close()
        logging.info("PKCE: Callback server shut down.")
        if code:
            _exchange_code_for_token(code, verifier, final_callback_on_main)
        else:
            GLib.idle_add(final_callback_on_main, None, _("Could not retrieve authorization code from browser."))
    except socket.error as e:
        logging.error(f"PKCE: Local server error (Could port {TRAKT_REDIRECT_PORT} be busy?): {e}")
        GLib.idle_add(final_callback_on_main, None, _("Port {port} is unavailable.").format(port=TRAKT_REDIRECT_PORT))
    except Exception as e:
        logging.error(f"PKCE: Unexpected error in callback server: {e}")
        if server_socket: server_socket.close()
        GLib.idle_add(final_callback_on_main, None, _("Unknown server error."))

def _exchange_code_for_token(code, verifier, final_callback_on_main):
    """
    (Background Thread)
    Exchanges the received 'code' and 'verifier' for the actual 'access_token'.
    Client Secret IS NOT USED.
    """
    logging.info("PKCE: Exchanging received code for a token...")
    url = f"{TRAKT_API_URL}/oauth/token"
    payload = {
        "code": code,
        "client_id": TRAKT_CLIENT_ID,
        "code_verifier": verifier,
        "redirect_uri": TRAKT_REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    try:
        response = requests.post(url, json=payload, headers=HEADERS, timeout=10)
        response.raise_for_status()
        token_data = response.json()
        logging.info("PKCE: Token successfully received and being saved to database.")
        database.save_trakt_token(token_data)
        GLib.idle_add(final_callback_on_main, token_data, None)
    except Exception as e:
        logging.error(f"PKCE: Token exchange failed: {e}")
        GLib.idle_add(final_callback_on_main, None, _("Could not retrieve token."))

def start_pkce_authentication(final_callback_on_main):
    """
    (Called from Main Thread)
    Starts the PKCE authentication flow.
    """
    if not TRAKT_CLIENT_ID:
        logging.error("PKCE: Trakt Client ID is not set in trakt_client.py!")
        GLib.idle_add(final_callback_on_main, None, _("Application Client ID is not set."))
        return
    try:
        verifier = _generate_code_verifier()
        challenge = _generate_code_challenge(verifier)
        server_thread = threading.Thread(
            target=_start_local_server_for_callback,
            args=(verifier, final_callback_on_main),
            daemon=True
        )
        server_thread.start()
        auth_url = (
            f"https://trakt.tv/oauth/authorize"
            f"?response_type=code"
            f"&client_id={TRAKT_CLIENT_ID}"
            f"&redirect_uri={TRAKT_REDIRECT_URI}"
            f"&code_challenge={challenge}"
            f"&code_challenge_method=S256"
        )
        webbrowser.open(auth_url)
    except Exception as e:
        logging.error(f"PKCE: Browser opening/server starting error: {e}")
        GLib.idle_add(final_callback_on_main, None, _("Authentication could not be initiated."))

def _get_api_headers(access_token):
    """
    Generates the standard headers for all authenticated Trakt API requests.
    Client ID is now added as 'trakt-api-key'.
    """
    headers = HEADERS.copy()
    headers['trakt-api-key'] = TRAKT_CLIENT_ID
    headers['Authorization'] = f"Bearer {access_token}"
    return headers

def _refresh_token(refresh_token):
    """
    Refreshes an expired token with a new one.
    Client Secret IS NOT USED.
    """
    if not refresh_token:
        logging.error("Trakt: Token refresh failed (no refresh_token).")
        return None
    logging.info("Trakt.tv token has expired, refreshing...")
    url = f"{TRAKT_API_URL}/oauth/token"
    payload = {
        "refresh_token": refresh_token,
        "client_id": TRAKT_CLIENT_ID,
        "redirect_uri": TRAKT_REDIRECT_URI,
        "grant_type": "refresh_token"
    }
    try:
        response = requests.post(url, json=payload, headers=HEADERS, timeout=10)
        response.raise_for_status()
        new_token_data = response.json()
        database.save_trakt_token(new_token_data)
        logging.info("Trakt.tv token successfully refreshed.")
        return new_token_data
    except Exception as e:
        logging.error(f"Trakt.tv token refresh failed: {e}")
        database.clear_trakt_token()
        return None

def _get_valid_token_data():
    """
    Gets the token from the database. Tries to refresh if expired.
    (Client Secret info NOT REQUIRED)
    """
    token_data = database.get_trakt_token()
    if not token_data:
        return None
    created_at = token_data['created_at']
    expires_in = token_data['expires_in']
    expires_at = created_at + expires_in
    if (expires_at - time.time()) < 3600:
        if not TRAKT_CLIENT_ID:
             logging.error("Trakt: Client ID not found for token refresh.")
             return None
        new_token_data = _refresh_token(token_data['refresh_token'])
        return new_token_data
    return token_data

def add_to_history(tmdb_id, media_type, callback_on_main=None):
    """
    (Background Thread)
    Adds a media item (movie or episode) to the Trakt.tv watch history.
    """
    logging.info(f"Trakt: Request received to add to history. TMDb ID: {tmdb_id}, Type: {media_type}")
    token_data = _get_valid_token_data()
    if not token_data:
        logging.warning("Trakt: Add to history skipped (user not logged in).")
        if callback_on_main: GLib.idle_add(callback_on_main, None, _("User not logged in."))
        return
    payload = {}
    if media_type == 'movie': payload = {"movies": [{"ids": {"tmdb": tmdb_id}}]}
    elif media_type == 'episode': payload = {"episodes": [{"ids": {"tmdb": tmdb_id}}]}
    else:
        logging.warning(f"Trakt: Invalid media type: {media_type}")
        if callback_on_main: GLib.idle_add(callback_on_main, None, _("Invalid media type."))
        return
    url = f"{TRAKT_API_URL}/sync/history"
    headers = _get_api_headers(token_data['access_token'])
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 401:
            logging.warning("Trakt: 401 Authorization Error received. Forcing token refresh...")
            database.clear_trakt_token()
            new_token_data = _get_valid_token_data()
            if new_token_data:
                logging.info("Trakt: Retrying with new token...")
                headers = _get_api_headers(new_token_data['access_token'])
                response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        logging.info(f"Trakt: Success! Content with ID {tmdb_id} added to history. Response: {response.json()}")
        if callback_on_main: GLib.idle_add(callback_on_main, response.json(), None)
    except Exception as e:
        logging.error(f"Trakt: Failed to add to history: {e}")
        if callback_on_main: GLib.idle_add(callback_on_main, None, str(e))

def get_watched_history(media_type, callback_on_main):
    """
    (Background Thread)
    Fetches the user's ENTIRE watch history (movies or episodes).
    """
    logging.info(f"Trakt: Fetching watch history (Type: {media_type})...")
    token_data = _get_valid_token_data()
    if not token_data:
        logging.warning("Trakt: History fetch skipped (user not logged in).")
        GLib.idle_add(callback_on_main, None, _("User not logged in."))
        return
    url = f"{TRAKT_API_URL}/sync/history/{media_type}"
    headers = _get_api_headers(token_data['access_token'])
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 401:
            logging.warning("Trakt (History): 401 Authorization Error. Forcing token refresh...")
            database.clear_trakt_token()
            new_token_data = _get_valid_token_data()
            if new_token_data:
                logging.info("Trakt (History): Retrying with new token...")
                headers = _get_api_headers(new_token_data['access_token'])
                response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        watched_data = response.json()
        logging.info(f"Trakt: Found {len(watched_data)} watched '{media_type}' items.")
        GLib.idle_add(callback_on_main, watched_data, None)
    except Exception as e:
        logging.error(f"Trakt: Failed to fetch watch history ({media_type}): {e}")
        GLib.idle_add(callback_on_main, None, str(e))
