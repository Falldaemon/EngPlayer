# utils/translation_utils.py

import hashlib
import json
import logging
import os
import re
import threading
import time
import requests
from gi.repository import GLib
from deep_translator import GoogleTranslator as _ScrapeGoogleTranslator
from deep_translator import MyMemoryTranslator
from deep_translator.exceptions import RequestError, TooManyRequests, TranslationNotFound

_MYMEMORY_SOURCE_CODE = "en-US"
_MYMEMORY_TARGET_CODES = {
    "ar": "ar-SA", "az": "az-AZ", "be": "be-BY", "bg": "bg-BG",
    "bn": "bn-IN", "bs": "bs-BA", "ca": "ca-ES", "cs": "cs-CZ",
    "cy": "cy-GB", "da": "da-DK", "de": "de-DE", "el": "el-GR",
    "en": "en-US", "es": "es-ES", "et": "et-EE", "eu": "eu-ES",
    "fa": "fa-IR", "fi": "fi-FI", "fr": "fr-FR", "ga": "ga-IE",
    "gl": "gl-ES", "gu": "gu-IN", "he": "he-IL", "hi": "hi-IN",
    "hr": "hr-HR", "hu": "hu-HU", "hy": "hy-AM", "id": "id-ID",
    "is": "is-IS", "it": "it-IT", "ja": "ja-JP", "ka": "ka-GE",
    "kk": "kk-KZ", "km": "km-KH", "kn": "kn-IN", "ko": "ko-KR",
    "ky": "ky-KG", "lo": "lo-LA", "lt": "lt-LT", "lv": "lv-LV",
    "mk": "mk-MK", "ml": "ml-IN", "mn": "mn-MN", "mr": "mr-IN",
    "ms": "ms-MY", "mt": "mt-MT", "my": "my-MM", "nb": "nb-NO",
    "ne": "ne-NP", "nl": "nl-NL", "nn": "nn-NO", "no": "nb-NO",
    "pa": "pa-IN", "pl": "pl-PL", "ps": "ps-PK", "pt": "pt-BR",
    "ro": "ro-RO", "ru": "ru-RU", "si": "si-LK", "sk": "sk-SK",
    "sl": "sl-SI", "sq": "sq-AL", "sr": "sr-Latn-RS", "sv": "sv-SE",
    "sw": "sw-KE", "ta": "ta-IN", "te": "te-IN", "th": "th-TH",
    "tl": "tl-PH", "tr": "tr-TR", "uk": "uk-UA", "ur": "ur-PK",
    "uz": "uz-UZ", "vi": "vi-VN", "xh": "xh-ZA", "yi": "yi-YD",
    "yo": "yo-NG", "zh": "zh-CN", "zu": "zu-ZA",
}
_MYMEMORY_MAX_CHARS = 500  

_CACHE_PATH = os.path.join(GLib.get_user_cache_dir(), "EngPlayer", "translation_cache.json")
_cache_lock = threading.Lock()
_cache = None 
_rate_lock = threading.Lock()
_last_request_time = 0.0
_MIN_REQUEST_INTERVAL = 0.5  
_cooldown_lock = threading.Lock()
_blocked_until = 0.0
_COOLDOWN_SECONDS = 300 
_MAX_CACHE_ENTRIES = 2000 

def _load_cache():
    global _cache
    if _cache is not None:
        return _cache
    try:
        with open(_CACHE_PATH, "r", encoding="utf-8") as f:
            _cache = json.load(f)
    except Exception:
        _cache = {}
    return _cache

def _save_cache():
    global _cache
    try:
        if len(_cache) > _MAX_CACHE_ENTRIES:
            excess = len(_cache) - _MAX_CACHE_ENTRIES
            for old_key in list(_cache.keys())[:excess]:
                del _cache[old_key]
        os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False)
    except Exception as e:
        logging.warning(f"Translation cache save error: {e}")


def _cache_key(text, source, target):
    raw = f"{source}:{target}:{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _throttle_locked():
    global _last_request_time
    now = time.time()
    wait = _MIN_REQUEST_INTERVAL - (now - _last_request_time)
    if wait > 0:
        time.sleep(wait)
    _last_request_time = time.time()

def _is_in_cooldown():
    with _cooldown_lock:
        return time.time() < _blocked_until


def _enter_cooldown():
    global _blocked_until
    with _cooldown_lock:
        _blocked_until = time.time() + _COOLDOWN_SECONDS
        logging.warning(
            f"Translation rate-limited by Google; pausing all translation "
            f"requests for {_COOLDOWN_SECONDS} seconds."
        )

def get_system_language():
    try:
        langs = GLib.get_language_names()
        for lang in langs:
            code = lang[:2].lower()
            if code and code != 'c':
                return code
        import os
        env_lang = os.environ.get('LANG', '')
        if env_lang:
            code = env_lang[:2].lower()
            if code and code != 'c':
                return code
        return 'en'
    except Exception as e:
        logging.error(f"Language detection error: {e}")
        return 'en'

def _translate_via_gtx(text, source, target):
    params = {
        "client": "gtx",
        "sl": source,
        "tl": target,
        "dt": "t",
        "q": text,
    }
    response = requests.get(
        "https://translate.google.com/translate_a/single",
        params=params,
        timeout=10,
    )
    if response.status_code == 429:
        raise TooManyRequests()
    if response.status_code != 200:
        raise RequestError()
    data = response.json()
    segments = data[0] or []
    pieces = []
    cursor = 0
    for segment in segments:
        translated_chunk = segment[0] if len(segment) > 0 else None
        original_chunk = segment[1] if len(segment) > 1 else None
        if not translated_chunk:
            continue
        if original_chunk:
            idx = text.find(original_chunk, cursor)
            if idx != -1:
                pieces.append(text[cursor:idx])
                cursor = idx + len(original_chunk)
        pieces.append(translated_chunk)
    pieces.append(text[cursor:])
    translated = "".join(pieces).strip()
    if not translated:
        raise TranslationNotFound(text)
    return translated

def _split_into_chunks(text, max_chars):
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            if len(sentence) <= max_chars:
                current = sentence
            else:
                words = sentence.split(" ")
                piece = ""
                for word in words:
                    cand = f"{piece} {word}".strip() if piece else word
                    if len(cand) <= max_chars:
                        piece = cand
                    else:
                        if piece:
                            chunks.append(piece)
                        piece = word
                current = piece
    if current:
        chunks.append(current)
    return chunks


def _translate_via_mymemory(text, target_lang):
    mm_target = _MYMEMORY_TARGET_CODES.get(target_lang)
    if not mm_target:
        return None
    if len(text) <= _MYMEMORY_MAX_CHARS:
        try:
            return MyMemoryTranslator(source=_MYMEMORY_SOURCE_CODE, target=mm_target).translate(text)
        except Exception as e:
            logging.warning(f"MyMemory fallback failed: {e}")
            return None
    chunks = _split_into_chunks(text, _MYMEMORY_MAX_CHARS)
    translated_chunks = []
    for chunk in chunks:
        try:
            translated = MyMemoryTranslator(source=_MYMEMORY_SOURCE_CODE, target=mm_target).translate(chunk)
        except Exception as e:
            logging.warning(f"MyMemory chunked fallback failed on a chunk: {e}")
            return None
        if not translated:
            return None
        translated_chunks.append(translated)
        time.sleep(0.2)  
    result = " ".join(translated_chunks)
    logging.debug(f"[Translation] MyMemory chunked: {len(chunks)} chunks for {len(text)} chars.")
    return result

def translate_text(text, target_lang, source_lang="auto"):
    if not text or source_lang == target_lang:
        return text
    cache = _load_cache()
    key = _cache_key(text, source_lang, target_lang)
    with _cache_lock:
        cached = cache.get(key)
    if cached is not None:
        logging.debug(f"[Translation] Served from CACHE: '{text[:40]}...' -> '{cached[:40]}...'")
        return cached
    result = None
    engine_used = None
    with _rate_lock:
        if _is_in_cooldown():
            logging.debug("[Translation] Google is in cooldown, skipping gtx/scraping.")
        else:
            _throttle_locked()
            try:
                result = _translate_via_gtx(text, source_lang, target_lang)
                engine_used = "Google (gtx)"
            except TooManyRequests:
                _enter_cooldown()
                logging.debug("[Translation] gtx returned 429, cooldown started.")
            except Exception as gtx_error:
                logging.warning(f"gtx translation failed, falling back to scraping: {gtx_error}")
                try:
                    result = _ScrapeGoogleTranslator(source=source_lang, target=target_lang).translate(text)
                    engine_used = "Google (legacy scraping)"
                except TooManyRequests:
                    _enter_cooldown()
                    logging.debug("[Translation] Scraping also returned 429, cooldown started.")
                except Exception as scrape_error:
                    logging.warning(f"Scraping fallback failed too: {scrape_error}")
    if result is None:
        result = _translate_via_mymemory(text, target_lang)
        if result is not None:
            engine_used = "MyMemory"
    if result is None:
        logging.debug(
            f"[Translation] ALL engines failed ({len(text)} chars), "
            f"returning original text: '{text[:40]}...'"
        )
        return text
    logging.debug(f"[Translation] '{text[:40]}...' -> '{result[:40]}...' (engine: {engine_used})")
    with _cache_lock:
        cache[key] = result
        _save_cache()
    return result

def translate_text_manually(text, callback, button_to_disable=None):
    if not text or len(text.strip()) == 0:
        return
    if button_to_disable:
        button_to_disable.set_sensitive(False)

    def run_translation():
        try:
            target_lang = get_system_language()
            translated = translate_text(text, target_lang)
            GLib.idle_add(callback, translated)
        except Exception as e:
            logging.error(f"Translation error: {e}")
            GLib.idle_add(callback, text)
        finally:
            if button_to_disable:
                GLib.idle_add(button_to_disable.set_sensitive, True)
    threading.Thread(target=run_translation, daemon=True).start()
