# recorder_daemon.py

import time
import logging
import os
import signal
from datetime import datetime
import sqlite3
import glob
import sys
import tarfile
import shutil
import tempfile
import json

try:
    import fcntl
except ImportError:
    fcntl = None

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils import platform_utils
platform_utils.setup_platform_environment()
try:
    from database import APP_CONFIG_DIR, get_recordings_path, get_config_db_connection, get_cache_path
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

    def get_cache_path():
        conn = get_config_db_connection()
        value = conn.cursor().execute("SELECT value FROM config WHERE key = ?", ('cache_path',)).fetchone()
        conn.close()
        if value and value[0]:
            return value[0]
        else:
            return os.path.join(GLib.get_user_cache_dir(), "EngPlayer")
from playback.recorder import Recorder
log_format = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=log_format)
active_recordings = {}

LOCK_FILE_PATH = os.path.join(APP_CONFIG_DIR, "daemon.lock")
_lock_file_handle = None
_lock_file_inode = None

def acquire_single_instance_lock():
    global _lock_file_handle, _lock_file_inode
    if platform_utils.IS_WINDOWS:
        if not platform_utils.acquire_named_mutex(platform_utils.DAEMON_MUTEX_NAME, exclusive=True):
            logging.info("Another daemon instance is already running. Exiting.")
            return False
        logging.info(f"Single-instance mutex acquired (PID {os.getpid()}).")
        return True
    if fcntl is None:
        logging.warning("fcntl is unavailable on this platform; single-instance lock disabled.")
        return True
    try:
        os.makedirs(APP_CONFIG_DIR, exist_ok=True)
        _lock_file_handle = open(LOCK_FILE_PATH, "a+")
    except Exception as e:
        logging.warning(f"Could not open the lock file, continuing without a lock: {e}")
        return True
    try:
        fcntl.flock(_lock_file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError):
        try:
            _lock_file_handle.seek(0)
            holder = _lock_file_handle.read().strip()
        except Exception:
            holder = "unknown"
        logging.info(f"Another daemon instance is already running (PID {holder}). Exiting.")
        try:
            _lock_file_handle.close()
        except Exception:
            pass
        _lock_file_handle = None
        return False
    try:
        _lock_file_handle.seek(0)
        _lock_file_handle.truncate()
        _lock_file_handle.write(str(os.getpid()))
        _lock_file_handle.flush()
    except Exception as e:
        logging.debug(f"Could not record the PID into the lock file: {e}")
    try:
        _lock_file_inode = os.fstat(_lock_file_handle.fileno()).st_ino
    except Exception as e:
        logging.debug(f"Could not read the lock file inode: {e}")
        _lock_file_inode = None    
    logging.info(f"Single-instance lock acquired (PID {os.getpid()}).")
    return True
    
def _lock_is_still_ours():
    if fcntl is None or _lock_file_handle is None or _lock_file_inode is None:
        return True
    try:
        return os.stat(LOCK_FILE_PATH).st_ino == _lock_file_inode
    except FileNotFoundError:
        return False
    except Exception as e:
        logging.debug(f"Could not verify the single-instance lock: {e}")
        return True

def _stop_active_recordings():
    if not active_recordings:
        return
    logging.info(f"Stopping {len(active_recordings)} active recording(s) before shutting down...")
    for job_id, recorder in list(active_recordings.items()):
        try:
            recorder.stop()
        except Exception as e:
            logging.error(f"Error while stopping recording {job_id}: {e}")
    active_recordings.clear()    

def find_profile_databases():
    search_path = os.path.join(APP_CONFIG_DIR, "profile_*.db")
    profile_dbs = glob.glob(search_path)
    if not profile_dbs:
        logging.info("No profile databases found.")
    return profile_dbs

def _connect_to_profile_db(db_path):
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except sqlite3.Error as e:
        logging.error(f"Failed to connect to profile database: {db_path} | Error: {e}")
        return None

def check_for_due_recordings():
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
                    start_ts = job['start_time']
                    end_ts = job['end_time']
                    duration_sec = end_ts - start_ts                  
                    if duration_sec <= 0:
                        logging.warning(f"Invalid duration calculated ({duration_sec}s). Defaulting to 3600s.")
                        duration_sec = 3600 
                    recorder = Recorder(channel_url, output_path, duration_sec=duration_sec)
                    recorder.start()                   
                    active_recordings[job_id] = recorder
                    cursor.execute("UPDATE scheduled_recordings SET status = ? WHERE id = ?", ('recording', job_id))
                    logging.info(f"Recording for '{channel_name}' started successfully. Duration: {duration_sec}s. File: {file_name}")
                except Exception as e:
                    logging.error(f"ERROR starting recording for '{channel_name}': {e}")
                    cursor.execute("UPDATE scheduled_recordings SET status = ? WHERE id = ?", ('failed', job_id))
            conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Database error while processing {db_path}: {e}")
        finally:
            conn.close()

def check_for_finished_recordings():
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
            
APP_RUNNING_LOCK_PATH = os.path.join(APP_CONFIG_DIR, "app.lock")

def _is_main_app_running(main_pid):
    if platform_utils.IS_WINDOWS:
        return platform_utils.named_mutex_exists(platform_utils.APP_MUTEX_NAME)
    if fcntl is not None and os.path.exists(APP_RUNNING_LOCK_PATH):
        try:
            with open(APP_RUNNING_LOCK_PATH, "a") as lock_file:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    return True
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                return False
        except OSError as e:
            logging.debug(f"Could not probe app lock file, falling back to PID check: {e}")
    return _is_pid_alive(main_pid)            

def _is_pid_alive(pid):
    if not pid:
        return False
    if platform_utils.IS_WINDOWS:
        try:
            return platform_utils.is_pid_alive_windows(pid)
        except Exception as e:
            logging.debug(f"Windows PID check failed: {e}")
            return False
    try:
        with open(f"/proc/{pid}/stat", "r") as f:
            contents = f.read()
        state = contents.rsplit(")", 1)[1].split()[0]
        return state != "Z"
    except FileNotFoundError:
        return False
    except Exception:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

def _relaunch_app():
    try:
        platform_utils.launch_app()
        logging.info("[Full Backup/Restore] Application relaunch command issued.")
    except Exception as e:
        logging.error(f"[Full Backup/Restore] Could not relaunch application: {e}")

def _set_config_key(key, value):
    try:
        conn = get_config_db_connection()
        conn.execute(
            "INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"[Full Backup/Restore] Could not write config key '{key}': {e}")

def _clear_config_key(key):
    try:
        conn = get_config_db_connection()
        conn.execute("DELETE FROM config WHERE key = ?", (key,))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"[Full Backup/Restore] Could not clear config key '{key}': {e}")

def check_for_pending_backup():
    try:
        conn = get_config_db_connection()
        row = conn.cursor().execute("SELECT value FROM config WHERE key = ?", ('pending_full_backup',)).fetchone()
        conn.close()
    except Exception as e:
        logging.error(f"[Full Backup] Could not read pending backup request: {e}")
        return
    if not row or not row['value']:
        return
    try:
        request = json.loads(row['value'])
        destination_folder = request.get("destination")
        main_pid = request.get("pid")
    except Exception as e:
        logging.error(f"[Full Backup] Invalid backup request data: {e}")
        _clear_config_key('pending_full_backup')
        return
    logging.info(f"[Full Backup] Pending backup request found. Waiting for main app (PID {main_pid}) to close...")
    waited = 0
    while _is_main_app_running(main_pid) and waited < 60:
        time.sleep(1)
        waited += 1
    if _is_main_app_running(main_pid):
        logging.warning("[Full Backup] Main app did not close in time. Will retry on next cycle.")
        return
    _clear_config_key('pending_full_backup')
    cache_path = get_cache_path()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    dest_file = os.path.join(destination_folder, f"engplayer-backup-{timestamp}.tar.gz")
    try:
        os.makedirs(destination_folder, exist_ok=True)
        with tarfile.open(dest_file, "w:gz") as tar:
            if os.path.isdir(APP_CONFIG_DIR):
                tar.add(APP_CONFIG_DIR, arcname="config")
            if os.path.isdir(cache_path):
                tar.add(cache_path, arcname="cache")
        result = {"success": True, "path": dest_file}
        logging.info(f"[Full Backup] Backup completed successfully: {dest_file}")
    except Exception as e:
        result = {"success": False, "error": str(e)}
        logging.error(f"[Full Backup] Backup failed: {e}")
    finally:
        _set_config_key('last_backup_result', json.dumps(result))
        _relaunch_app()

def check_for_pending_restore():
    try:
        conn = get_config_db_connection()
        row = conn.cursor().execute("SELECT value FROM config WHERE key = ?", ('pending_full_restore',)).fetchone()
        conn.close()
    except Exception as e:
        logging.error(f"[Full Restore] Could not read pending restore request: {e}")
        return
    if not row or not row['value']:
        return
    try:
        request = json.loads(row['value'])
        source_path = request.get("source")
        main_pid = request.get("pid")
    except Exception as e:
        logging.error(f"[Full Restore] Invalid restore request data: {e}")
        _clear_config_key('pending_full_restore')
        return
    logging.info(f"[Full Restore] Pending restore request found. Waiting for main app (PID {main_pid}) to close...")
    waited = 0
    while _is_main_app_running(main_pid) and waited < 60:
        time.sleep(1)
        waited += 1
    if _is_main_app_running(main_pid):
        logging.warning("[Full Restore] Main app did not close in time. Will retry on next cycle.")
        return
    temp_dir = None
    rollback_dir = None
    try:
        if not os.path.isfile(source_path):
            raise FileNotFoundError(f"Backup file not found: {source_path}")
        temp_dir = tempfile.mkdtemp(prefix="engplayer_restore_")
        with tarfile.open(source_path, "r:gz") as tar:
            if hasattr(tarfile, "data_filter"):
                tar.extractall(temp_dir, filter="data")
            else:
                tar.extractall(temp_dir)
        extracted_config = os.path.join(temp_dir, "config")
        if not os.path.isdir(extracted_config):
            raise ValueError("This does not look like a valid EngPlayer backup file (missing 'config' folder).")
        if not os.path.isfile(os.path.join(extracted_config, "config.db")):
            raise ValueError("The backup's 'config' folder is incomplete (config.db is missing); the archive is most likely truncated or corrupted.")
        cache_path = get_cache_path()
        extracted_cache = os.path.join(temp_dir, "cache")
        if os.path.isdir(APP_CONFIG_DIR):
            rollback_dir = f"{APP_CONFIG_DIR}.bak-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            os.rename(APP_CONFIG_DIR, rollback_dir)
            logging.info(f"[Full Restore] Current configuration moved aside to: {rollback_dir}")
        try:
            shutil.move(extracted_config, APP_CONFIG_DIR)
        except Exception:
            if rollback_dir and os.path.isdir(rollback_dir):
                if os.path.isdir(APP_CONFIG_DIR):
                    shutil.rmtree(APP_CONFIG_DIR, ignore_errors=True)
                os.rename(rollback_dir, APP_CONFIG_DIR)
                rollback_dir = None
                logging.warning("[Full Restore] Could not install the backup; the previous configuration has been put back.")
            raise
        if os.path.isdir(extracted_cache):
            try:
                if os.path.isdir(cache_path):
                    shutil.rmtree(cache_path)
                shutil.move(extracted_cache, cache_path)
            except Exception as cache_error:
                logging.warning(f"[Full Restore] Cache could not be restored, continuing without it: {cache_error}")
        _clear_config_key('pending_full_backup')
        _clear_config_key('pending_full_restore')
        if rollback_dir and os.path.isdir(rollback_dir):
            shutil.rmtree(rollback_dir, ignore_errors=True)
            rollback_dir = None
        result = {"success": True}
        logging.info("[Full Restore] Restore completed successfully.")
    except Exception as e:
        if rollback_dir and os.path.isdir(rollback_dir):
            if not os.path.isdir(APP_CONFIG_DIR):
                try:
                    os.rename(rollback_dir, APP_CONFIG_DIR)
                    logging.warning("[Full Restore] Restore failed; the previous configuration has been put back.")
                except Exception as rollback_error:
                    logging.error(f"[Full Restore] Could not put the previous configuration back: {rollback_error}. It is still available at: {rollback_dir}")
            else:
                logging.warning(f"[Full Restore] Restore failed after the new configuration was already in place. The previous one was kept at: {rollback_dir}")
        result = {"success": False, "error": str(e)}
        logging.error(f"[Full Restore] Restore failed: {e}")
    finally:
        if temp_dir and os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        _set_config_key('last_restore_result', json.dumps(result))
        _relaunch_app()

def _has_pending_request():
    try:
        conn = get_config_db_connection()
        row = conn.cursor().execute(
            "SELECT 1 FROM config WHERE key IN ('pending_full_backup', 'pending_full_restore') AND value != ''"
        ).fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False

def _reap_zombie_children():
    if platform_utils.IS_WINDOWS:
        return
    try:
        while True:
            pid, _ = os.waitpid(-1, os.WNOHANG)
            if pid == 0:
                break
    except ChildProcessError:
        pass
    except Exception as e:
        logging.debug(f"[Full Backup/Restore] Zombie reap check: {e}")

def main_loop():
    logging.info("Background Recording Service (Daemon) started.")
    try:
        while True:
            _reap_zombie_children()
            check_for_due_recordings()
            check_for_finished_recordings()
            try:
                check_for_pending_backup()
                check_for_pending_restore()
            except Exception as e:
                logging.error(f"[Full Backup/Restore] Unexpected error during check: {e}")
            if not _lock_is_still_ours():
                logging.info(
                    "The configuration directory was replaced underneath this daemon "
                    "(most likely by a Full Restore); a newer daemon now owns the lock. "
                    "Shutting this one down."
                )
                _stop_active_recordings()
                return
            logging.info("Next check in 60 seconds.")
            for _ in range(6):
                time.sleep(10)
                if _has_pending_request():
                    logging.info("[Full Backup/Restore] Pending request detected, checking now.")
                    break
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt detected. Stopping service.")
        for job_id, recorder in active_recordings.items():
            logging.info(f"Stopping recording with ID {job_id}...")
            recorder.stop()
        logging.info("All active recordings stopped. Exiting.")

if __name__ == "__main__":
    if not acquire_single_instance_lock():
        sys.exit(0)
    main_loop()
