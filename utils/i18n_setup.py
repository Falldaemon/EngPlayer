# utils/i18n_setup.py

import gettext
import logging
from core.config import LOCALE_DIR

def setup_translation():
    """Initializes the gettext translation system."""
    try:
        gettext.bindtextdomain('engplayer', LOCALE_DIR)
        gettext.textdomain('engplayer')
        logging.info("Translation system initialized.")
    except Exception as e:
        logging.error(f"Could not set up translation system: {e}")
        logging.warning("Application will continue without full translation support.")
