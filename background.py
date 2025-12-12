# background.py

import threading
import logging
from gi.repository import GObject, GLib
from concurrent.futures import ThreadPoolExecutor
from data_providers import scanner
class BackgroundTaskManager(GObject.Object):
    """
    A class to manage background tasks like scanning libraries.
    It uses GObject signals to communicate with the UI thread.
    """
    __gsignals__ = {
        "scan-finished": (GObject.SignalFlags.RUN_FIRST, None, ())
    }

    def __init__(self):
        super().__init__()

    def start_library_scan(self):
        """Starts the library scanning process in a new thread."""
        thread = threading.Thread(target=self._scan_task)
        thread.start()

    def _scan_task(self):
        """
        The actual task that runs in the background.
        Scans libraries and emits a signal when done.
        """
        logging.info("Background task: Starting library scan.")
        scanner.scan_all_libraries()
        logging.info("Background task: Scan finished.")
        GLib.idle_add(self.emit, "scan-finished")

task_manager = BackgroundTaskManager()
logging.info("Initializing global image download ThreadPool (max_workers=8)...")
image_download_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix='ImagePool')

import atexit
def shutdown_image_pool():
    logging.info("Shutting down image download ThreadPool...")
    image_download_pool.shutdown(wait=True)
    logging.info("Image download ThreadPool shut down.")
atexit.register(shutdown_image_pool)
