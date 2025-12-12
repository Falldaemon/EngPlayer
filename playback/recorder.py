# playback/recorder.py

import logging
import subprocess
import signal
import os
import threading
from gi.repository import GLib

class Recorder:
    def __init__(self, stream_url, output_filepath):
        self.stream_url = stream_url
        self.output_filepath = output_filepath
        self.process = None
        self.log_thread = None
        logging.info(f"Recorder (FFmpeg Mode) initialized. URL: {self.stream_url}")

    def _log_reader_thread(self):
        try:
            for line in self.process.stderr:
                if 'frame=' in line:
                    logging.debug(f"(FFmpeg Live) {line.strip()}")
                else:
                    logging.info(f"(FFmpeg Live) {line.strip()}")
        except Exception as e:
            logging.warning(f"Error in FFmpeg log reader thread: {e}")

    def start(self):
        if self.process:
            logging.warning("Attempted to start recording, but a process is already running.")
            return
        command = [
            'ffmpeg', '-y',
            '-user_agent', 'Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0',
            '-reconnect_on_network_error', '1',
            '-reconnect_on_http_error', '4xx,5xx',
            '-reconnect', '1',
            '-reconnect_streamed', '1',
            '-reconnect_delay_max', '5',
            '-i', self.stream_url,
            '-c', 'copy',
            self.output_filepath
        ]
        try:
            logging.info(f"(FFmpeg) Starting recording. Command: {' '.join(command)}")
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                errors='ignore'
            )
            self.log_thread = threading.Thread(target=self._log_reader_thread)
            self.log_thread.daemon = True
            self.log_thread.start()
            logging.info(f"FFmpeg process started. PID: {self.process.pid}")
        except FileNotFoundError:
            logging.error("CRITICAL ERROR: 'ffmpeg' command not found. Please install FFmpeg on your system.")
            raise
        except Exception as e:
            logging.error(f"An error occurred while starting the FFmpeg process: {e}")
            raise

    def stop(self, on_finished_callback=None):
        """
        Stops the FFmpeg process, checks the file, and returns the result.
        """
        was_successful = False
        final_return_code = None
        def _notify_main_thread():
            if on_finished_callback:
                GLib.idle_add(on_finished_callback)
        if not self.process:
            logging.warning("Recorder.stop: No FFmpeg process to stop.")
            _notify_main_thread()
            return False
        pid = self.process.pid
        logging.info(f"Recorder.stop: Terminating FFmpeg process (PID: {pid}) (SIGINT)...")
        try:
            if self.process.poll() is None:
                self.process.send_signal(signal.SIGINT)
                logging.debug(f"Recorder.stop: SIGINT signal sent to PID {pid}.")
            else:
                logging.warning(f"Recorder.stop: Process (PID: {pid}) had already finished before signal was sent.")
            wait_timeout = 30
            logging.debug(f"Recorder.stop: Waiting {wait_timeout}s for FFmpeg (PID: {pid}) to finish...")
            self.process.wait(timeout=wait_timeout)
            final_return_code = self.process.returncode
            logging.info(f"Recorder.stop: FFmpeg process (PID: {pid}) finished. Exit Code: {final_return_code}")
            success_codes = [0, 255, -signal.SIGINT, 130]
            if final_return_code in success_codes:
                logging.info(f"Recorder.stop: FFmpeg (PID: {pid}) stopped successfully with an expected code ({final_return_code}).")
                was_successful = True
            else:
                logging.warning(f"Recorder.stop: FFmpeg (PID: {pid}) stopped with an unexpected code ({final_return_code}). File check will be performed.")
        except subprocess.TimeoutExpired:
            logging.warning(f"Recorder.stop: FFmpeg (PID: {pid}) did not close within {wait_timeout}s, forcing kill...")
            try:
                if self.process: self.process.kill()
            except Exception as kill_err:
                 logging.error(f"Recorder.stop: Error while killing FFmpeg (PID: {pid}): {kill_err}")
            was_successful = False
        except Exception as e:
            logging.error(f"Recorder.stop: Error while stopping/waiting for FFmpeg (PID: {pid}): {e}")
            was_successful = False
        finally:
            if not was_successful:
                logging.debug(f"Recorder.stop: Appears unsuccessful, checking file: {self.output_filepath}")
                try:
                    if os.path.isfile(self.output_filepath) and os.path.getsize(self.output_filepath) > 0:
                        logging.info(f"Recorder.stop: Although FFmpeg exit code/timeout was problematic, the output file ({self.output_filepath}) exists and is not empty. Accepting as SUCCESS.")
                        was_successful = True
                    else:
                        logging.error(f"Recorder.stop: Output file ({self.output_filepath}) not found or is empty. Remaining as FAILED.")
                except Exception as file_err:
                    logging.error(f"Recorder.stop: Error during file check: {file_err}")
            self.process = None
            self.log_thread = None
            _notify_main_thread()
            logging.info(f"Recorder.stop: Result (PID: {pid}): {'SUCCESS' if was_successful else 'FAILED'}")
        return was_successful
