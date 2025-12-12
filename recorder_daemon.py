# recorder_daemon.py

import time
import logging
import os
import signal
from datetime import datetime
import sqlite3
import glob
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from database import APP_CONFIG_DIR, get_recordings_path, get_config_db_connection
except ImportError:
    logging.warning("Failed to import database module, setting paths manually.")
    from gi.repository import GLib
    user_config_dir = GLib.get_user_config_dir()
    APP_CONFIG_DIR = os.path.join(user_config_dir, "EngPlayer")

    def get_config_db_connection():
        config_db_path = os.path.join(APP_CONFIG_DIR, "config.db")
        conn = sqlite3.connect(config_db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def get_recordings_path():
        conn = get_config_db_connection()
        value = conn.cursor().execute("SELECT value FROM config WHERE key = ?", ('recordings_path',)).fetchone()
        conn.close()
        if value:
            return value[0]
        else:
            return GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_VIDEOS)
from playback.recorder import Recorder
log_format = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=log_format)
active_recordings = {}

def find_profile_databases():
    """Finds all profile_*.db files and returns their paths as a list."""
    search_path = os.path.join(APP_CONFIG_DIR, "profile_*.db")
    profile_dbs = glob.glob(search_path)
    if not profile_dbs:
        logging.info("No profile databases found.")
    return profile_dbs

def _connect_to_profile_db(db_path):
    """Connects to a specific profile database file."""
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except sqlite3.Error as e:
        logging.error(f"Failed to connect to profile database: {db_path} | Error: {e}")
        return None

def check_for_due_recordings():
    """Checks ALL profile databases and starts recordings that are due."""
    logging.info("Checking for due recordings across all profiles...")
    profile_dbs = find_profile_databases()
    now = int(time.time())
    for db_path in profile_dbs:
        conn = _connect_to_profile_db(db_path)
        if not conn:
            continue
        logging.debug(f"Checking: {db_path}")
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM scheduled_recordings WHERE status = 'pending' AND start_time <= ?", (now,)
            )
            jobs_to_start = cursor.fetchall()
            if not jobs_to_start:
                conn.close()
                continue
            logging.info(f"Found {len(jobs_to_start)} due jobs in {db_path}.")
            recordings_dir = get_recordings_path()
            os.makedirs(recordings_dir, exist_ok=True)
            for job in jobs_to_start:
                job_id = job['id']
                channel_name = job['channel_name']
                channel_url = job['channel_url']
                job_dict = dict(job)
                program_name = job_dict.get('program_name')               
                timestamp = datetime.now().strftime("%d-%m-%Y_%H-%M")                
                if program_name:
                    safe_prog = program_name.replace(" ", "_").replace("/", "-")
                    safe_chan = channel_name.replace(" ", "_").replace("/", "-")
                    file_name = f"{safe_prog}_{safe_chan}_{timestamp}.mkv"
                else:
                    safe_channel_name = channel_name.replace(" ", "_").replace("/", "-")
                    file_name = f"{safe_channel_name}_{timestamp}.mkv"
                output_path = os.path.join(recordings_dir, file_name)
                try:
                    recorder = Recorder(channel_url, output_path)
                    recorder.start()
                    active_recordings[job_id] = recorder
                    cursor.execute("UPDATE scheduled_recordings SET status = ? WHERE id = ?", ('recording', job_id))
                    logging.info(f"Recording for '{channel_name}' started successfully. File: {file_name}")
                except Exception as e:
                    logging.error(f"ERROR starting recording for '{channel_name}': {e}")
                    cursor.execute("UPDATE scheduled_recordings SET status = ? WHERE id = ?", ('failed', job_id))
            conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Database error while processing {db_path}: {e}")
        finally:
            conn.close()

def check_for_finished_recordings():
    """Checks active recordings in ALL profile databases and stops those whose end time has come."""
    now = int(time.time())
    logging.info("Checking for finished recordings across all profiles...")
    profile_dbs = find_profile_databases()
    for db_path in profile_dbs:
        conn = _connect_to_profile_db(db_path)
        if not conn:
            continue
        logging.debug(f"Checking for finished tasks: {db_path}")
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scheduled_recordings WHERE status = 'recording'")
            active_jobs_from_db = cursor.fetchall()
            if not active_jobs_from_db:
                conn.close()
                continue
            needs_commit = False
            for job in active_jobs_from_db:
                job_id = job['id']
                end_time = job['end_time']
                if now >= end_time:
                    logging.info(f"Recording time for '{job['channel_name']}' (ID: {job_id}) has expired. Stopping recording...")
                    recorder_to_stop = active_recordings.get(job_id)
                    final_status = 'failed'
                    if recorder_to_stop:
                        was_successful = recorder_to_stop.stop()
                        if was_successful:
                            final_status = 'completed'
                        del active_recordings[job_id]
                        logging.info(f"Recording process with ID {job_id} stopped. Final Status: {final_status}")
                    else:
                        logging.warning(f"No active recording process found for ID {job_id}, but it appears as 'recording' in the database. Correcting status to 'failed'.")
                        final_status = 'failed'
                    cursor.execute("UPDATE scheduled_recordings SET status = ? WHERE id = ?", (final_status, job_id))
                    needs_commit = True
            if needs_commit:
                conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Database error while processing {db_path} (finished recordings): {e}")
        finally:
            conn.close()

def main_loop():
    """The main working loop of the daemon."""
    logging.info("Background Recording Service (Daemon) started.")
    try:
        while True:
            check_for_due_recordings()
            check_for_finished_recordings()
            logging.info("Next check in 60 seconds.")
            time.sleep(60)
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt detected. Stopping service.")
        for job_id, recorder in active_recordings.items():
            logging.info(f"Stopping recording with ID {job_id}...")
            recorder.stop()
        logging.info("All active recordings stopped. Exiting.")

if __name__ == "__main__":
    main_loop()
