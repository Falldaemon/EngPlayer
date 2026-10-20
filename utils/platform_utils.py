# utils/platform_utils.py

import os
import sys
import logging
import re
import shutil
import subprocess

IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")
IS_FLATPAK = IS_LINUX and os.path.exists("/.flatpak-info")
IS_FROZEN = bool(getattr(sys, "frozen", False))

APP_MUTEX_NAME = "Local\\io.github.falldaemon.engplayer.app"
DAEMON_MUTEX_NAME = "Local\\io.github.falldaemon.engplayer.daemon"

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def setup_platform_environment():
    if not IS_WINDOWS:
        return
    _setup_windows_dirs()
    _setup_windows_language()
    _setup_windows_console_encoding()
    _setup_windows_proxy_resolver()
    _setup_windows_js_runtime()
    _setup_windows_rendering()
    if IS_FROZEN:
        _setup_frozen_gstreamer()

def _setup_windows_rendering():
    flags = os.environ.get("GDK_DEBUG", "")
    if "dcomp" not in flags.split(","):
        os.environ["GDK_DEBUG"] = f"{flags},dcomp" if flags else "dcomp"
    os.environ.setdefault("GSK_RENDERER", "cairo")

def _setup_frozen_gstreamer():
    scanner = os.path.join(sys._MEIPASS, "gst-plugin-scanner.exe")
    if os.path.isfile(scanner):
        os.environ["GST_PLUGIN_SCANNER"] = scanner
        os.environ["GST_REGISTRY_FORK"] = "yes"
    cache_dir = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "EngPlayer")
    try:
        os.makedirs(cache_dir, exist_ok=True)
    except OSError:
        pass
    os.environ["GST_REGISTRY"] = os.path.join(cache_dir, "gstreamer-registry.bin")
    os.environ["DENO_DIR"] = os.path.join(cache_dir, "deno")

def _setup_windows_dirs():
    appdata = os.environ.get("APPDATA")
    local_appdata = os.environ.get("LOCALAPPDATA")
    if appdata and not os.environ.get("XDG_CONFIG_HOME"):
        os.environ["XDG_CONFIG_HOME"] = appdata
    if local_appdata and not os.environ.get("XDG_CACHE_HOME"):
        os.environ["XDG_CACHE_HOME"] = local_appdata

def _setup_windows_language():
    if os.environ.get("LANGUAGE") or os.environ.get("LANG"):
        return
    try:
        import ctypes
        import locale
        lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        lang = locale.windows_locale.get(lcid)
        if lang:
            os.environ["LANGUAGE"] = lang
            os.environ["LANG"] = f"{lang}.UTF-8"
    except Exception:
        pass

def _setup_windows_console_encoding():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

def _setup_windows_proxy_resolver():
    if os.environ.get("GIO_USE_PROXY_RESOLVER"):
        return
    if any(os.environ.get(k) for k in ("http_proxy", "https_proxy", "HTTP_PROXY",
                                       "HTTPS_PROXY", "all_proxy", "ALL_PROXY")):
        return
    os.environ["GIO_USE_PROXY_RESOLVER"] = "dummy"

def _setup_windows_js_runtime():
    import glob
    import shutil
    if shutil.which("deno"):
        return
    candidates = []
    if IS_FROZEN:
        candidates.append(os.path.dirname(sys.executable))
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        winget = os.path.join(local_appdata, "Microsoft", "WinGet")
        candidates.append(os.path.join(winget, "Links"))
        candidates.extend(glob.glob(os.path.join(winget, "Packages", "DenoLand.Deno_*")))
    candidates.append(os.path.join(os.path.expanduser("~"), ".deno", "bin"))
    for directory in candidates:
        if os.path.isfile(os.path.join(directory, "deno.exe")):
            os.environ["PATH"] = directory + os.pathsep + os.environ.get("PATH", "")
            logging.info(f"JS runtime for yt-dlp: {directory}")
            return

def get_glibc():
    if not IS_LINUX:
        return None
    try:
        import ctypes
        import ctypes.util
        libc_path = ctypes.util.find_library("c") or "libc.so.6"
        return ctypes.CDLL(libc_path)
    except Exception as e:
        logging.info(f"glibc not accessible on this system: {e}")
        return None

_CREATE_NEW_PROCESS_GROUP = 0x00000200
_DETACHED_PROCESS = 0x00000008
_CREATE_NO_WINDOW = 0x08000000

def detached_popen_kwargs():
    if IS_WINDOWS:
        return {
            "creationflags": _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP,
            "close_fds": True,
        }
    return {"start_new_session": True}

def hidden_popen_kwargs():
    if IS_WINDOWS:
        return {"creationflags": _CREATE_NO_WINDOW}
    return {}

def get_daemon_command():
    if IS_FLATPAK:
        return ["/app/bin/engplayer-daemon"]
    if IS_WINDOWS and IS_FROZEN:
        return [os.path.join(os.path.dirname(sys.executable), "EngPlayerDaemon.exe")]
    return [sys.executable, os.path.join(_BASE_DIR, "recorder_daemon.py")]

def get_app_command():
    if IS_FLATPAK:
        return ["/app/bin/engplayer"]
    if IS_WINDOWS and IS_FROZEN:
        return [os.path.join(os.path.dirname(sys.executable), "EngPlayer.exe")]
    return [sys.executable, os.path.join(_BASE_DIR, "main.py")]

def start_daemon():
    try:
        subprocess.Popen(get_daemon_command(),
                         stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         **detached_popen_kwargs())
        logging.info("Background daemon start command issued.")
    except Exception as e:
        logging.warning(f"Failed to start daemon: {e}")

def launch_app():
    command = get_app_command()
    if IS_LINUX and not IS_FLATPAK and os.environ.get("INVOCATION_ID") and shutil.which("systemd-run"):
        command = ["systemd-run", "--user", "--scope", "--quiet"] + command
    subprocess.Popen(command,
                     stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL,
                     **detached_popen_kwargs())

def restart_current_process():
    if IS_WINDOWS:
        if IS_FROZEN:
            subprocess.Popen(get_app_command() + sys.argv[1:], **detached_popen_kwargs())
        else:
            subprocess.Popen([sys.executable] + sys.argv, **detached_popen_kwargs())
        os._exit(0)
    os.execv(sys.executable, [sys.executable] + sys.argv)

def stop_ffmpeg_gracefully(process):
    if IS_WINDOWS:
        if process.stdin:
            try:
                process.stdin.write("q")
                process.stdin.flush()
                process.stdin.close()
                return
            except Exception as e:
                logging.warning(f"Could not send 'q' to ffmpeg stdin: {e}")
        process.terminate()
        return
    import signal
    process.send_signal(signal.SIGINT)

def ffmpeg_popen_kwargs():
    if IS_WINDOWS:
        kwargs = hidden_popen_kwargs()
        kwargs["stdin"] = subprocess.PIPE
        return kwargs
    return {}

def is_pid_alive_windows(pid):
    import ctypes
    from ctypes import wintypes
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)

_held_mutex_handles = []

def _kernel32():
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = wintypes.HANDLE
    k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    k32.OpenMutexW.restype = wintypes.HANDLE
    k32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    return k32

def acquire_named_mutex(name, exclusive):
    import ctypes
    ERROR_ALREADY_EXISTS = 183
    k32 = _kernel32()
    handle = k32.CreateMutexW(None, False, name)
    if not handle:
        logging.warning(f"CreateMutexW failed for {name} (error {ctypes.get_last_error()}).")
        return True
    if exclusive and ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        k32.CloseHandle(handle)
        return False
    _held_mutex_handles.append(handle)
    return True

def named_mutex_exists(name):
    SYNCHRONIZE = 0x00100000
    k32 = _kernel32()
    handle = k32.OpenMutexW(SYNCHRONIZE, False, name)
    if not handle:
        return False
    k32.CloseHandle(handle)
    return True

_sleep_inhibit_count = 0

def set_windows_sleep_inhibited(inhibited):
    global _sleep_inhibit_count
    if not IS_WINDOWS:
        return
    import ctypes
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ES_DISPLAY_REQUIRED = 0x00000002
    if inhibited:
        _sleep_inhibit_count += 1
    else:
        _sleep_inhibit_count = max(0, _sleep_inhibit_count - 1)
    flags = ES_CONTINUOUS
    if _sleep_inhibit_count > 0:
        flags |= ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(flags))
    except Exception as e:
        logging.warning(f"SetThreadExecutionState failed: {e}")

_EMOJI_RE = re.compile("(.)\ufe0f")


def display_text(text):
    if not IS_WINDOWS:
        return text
    return _EMOJI_RE.sub(lambda m: f'<span font_family="Segoe UI Emoji">{m.group(1)}</span>', text)     
