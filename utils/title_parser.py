# utils/title_parser.py

import re
import logging

try:
    from guessit import guessit
    GUESSIT_AVAILABLE = True
    logging.info("Loaded 'guessit' library for professional title parsing.")
except ImportError:
    logging.warning("'guessit' library not found! A less successful method will be used.")
    logging.warning("For better results, install the 'python3-guessit' package.")
    guessit = None
    GUESSIT_AVAILABLE = False
YEAR_REGEX = re.compile(r'\b(19\d{2}|20\d{2})\b')
SQUARE_BRACKET_REGEX = re.compile(r'\s*\[.*?\]\s*')
POST_GUESSIT_JUNK = [
    'x264', 'x265', 'h264', 'h265', 'hevc', 'avc', 'xvid',
    'ac3', 'eac3', 'dts', 'dts-hd', 'truehd', 'atmos', 'ddp5', 'ddp7', 'aac', 'aac5', 'aac2', 'ma',
    '4k', 'uhd', '8k', '2160p', '1080p', '720p', '480p', 'hd', 'hdr', 'dv', 'sdr',
    'bluray', 'blu-ray', 'bdrip', 'brrip', 'web-dl', 'webdl', 'webrip', 'hdrip', 'remux', 'web', 'hmax',
    'amzn', 'amz', 'nf', 'dsnp', 'hulu', 'hbo', 'max', 'd+',
    '10bit', '8bit', 'imax', '3d', 'hsbs', 'sbs',
    'fgt', 'sparks', 'geckos', 'yts', 'yify', 'rarbg', 'publichd', 'shiv', 'top-do',
    'bluworld', 'din', 'mrcs', 'evo', 'etrg', 'cmrg', 'ntg', 'ion10',
    'ita', 'eng', 'multi', 'dual', 'tr', 'us', 'de',
    'extended', 'remastered', 'directors cut', 'unrated', 'final cut', 'theatrical',
    'repack', 'proper', 'internal', 'limited', 'criterion', 'edition', 'complete',
    'atmos', '7 1',
]
POST_GUESSIT_CLEANUP_REGEX = re.compile(r'(?i)\b(?:' + '|'.join(re.escape(word) for word in POST_GUESSIT_JUNK) + r')\b')

def parse_title_for_search(original_title):
    lower_original_title = original_title.lower()
    if re.search(r'\b(vod|xxx)\b', lower_original_title):
        logging.warning(f"Original title ('{original_title}') contains filtered word (VOD/XXX). Skipping TMDb search.")
        return None, None
    cleaned_title = re.sub(r'\.\w+$', '', original_title).strip()
    if not cleaned_title:
         return None, None
    final_title_to_search = None
    final_year_to_search = None
    if GUESSIT_AVAILABLE:
        try:
            logging.debug(f"Guessit input (raw): '{cleaned_title}'")
            guess = guessit(cleaned_title)
            guess_title = guess.get('title')
            guess_year_str = str(guess.get('year')) if guess.get('year') else None
            if guess_title and len(guess_title) > 1:
                logging.info(f"Guessit Raw Result: '{guess_title}' (Year: {guess_year_str})")
                cleaned_guess_title = POST_GUESSIT_CLEANUP_REGEX.sub('', guess_title).strip()
                cleaned_guess_title = re.sub(r'\s+', ' ', cleaned_guess_title).strip()
                cleaned_guess_title = re.sub(r'^[\s\-_\.:]+|[\s\-_\.:]+$', '', cleaned_guess_title).strip()
                if cleaned_guess_title and len(cleaned_guess_title) > 1:
                     logging.info(f"Cleaned Title (Post-Guessit): '{cleaned_guess_title}'")
                     final_title_to_search = cleaned_guess_title
                     final_year_to_search = guess_year_str
                else:
                     logging.warning("Cleaning after guessit resulted in an empty title, using fallback.")
            else:
                logging.warning(f"Guessit did not find a useful title for '{cleaned_title}', using fallback.")
        except Exception as e:
            logging.error(f"Guessit error ({e}), using fallback.")
    if not final_title_to_search:
        logging.info("Using Fallback (Simple Clean).")
        title_fallback = SQUARE_BRACKET_REGEX.sub(' ', cleaned_title).strip()
        title_fallback = re.sub(r'[-_\.:\(\)]', ' ', title_fallback)
        title_fallback = re.sub(r'\s+', ' ', title_fallback).strip()
        year_match = YEAR_REGEX.search(title_fallback)
        year_fb = year_match.group(1) if year_match else None
        if year_fb:
            title_fallback = YEAR_REGEX.sub('', title_fallback).strip()
            title_fallback = re.sub(r'\s+', ' ', title_fallback).strip()
        title_fallback = POST_GUESSIT_CLEANUP_REGEX.sub('', title_fallback).strip()
        title_fallback = re.sub(r'\s+', ' ', title_fallback).strip()
        title_fallback = re.sub(r'^[\s\-_\.:]+|[\s\-_\.:]+$', '', title_fallback).strip()
        if title_fallback and len(title_fallback) > 1:
             final_title_to_search = title_fallback
             final_year_to_search = year_fb
        else:
             logging.warning(f"Even the fallback title is empty/short after cleaning. Cancelling search.")
             return None, None
    logging.info(f"Result for TMDb Search: Title='{final_title_to_search}', Year='{final_year_to_search}'")
    return final_title_to_search, final_year_to_search
