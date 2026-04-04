# background.py

import threading
import logging
import atexit
from gi.repository import GObject, GLib
from concurrent.futures import ThreadPoolExecutor
from data_providers import scanner
class BackgroundTaskManager(GObject.Object):
    __gsignals__ = {
        "scan-finished": (GObject.SignalFlags.RUN_FIRST, None, ())
    }

    def __init__(self):
        super().__init__()

    def start_library_scan(self):
        thread = threading.Thread(target=self._scan_task)
        thread.start()

    def _scan_task(self):
        logging.info("Background task: Starting library scan.")
        scanner.scan_all_libraries()
        logging.info("Background task: Scan finished.")
        GLib.idle_add(self.emit, "scan-finished")

task_manager = BackgroundTaskManager()
logging.info("Initializing global image download ThreadPool (max_workers=8)...")
image_download_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix='ImagePool')

def shutdown_image_pool():
    logging.info("Shutting down image download ThreadPool...")
    image_download_pool.shutdown(wait=True)
    logging.info("Image download ThreadPool shut down.")
atexit.register(shutdown_image_pool)
