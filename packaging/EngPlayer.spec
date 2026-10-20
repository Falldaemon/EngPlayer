# -*- mode: python ; coding: utf-8 -*-
# packaging/EngPlayer.spec
# Build from the project root:
#   python -m PyInstaller packaging/EngPlayer.spec --noconfirm --distpath packaging/dist --workpath packaging/build
# ENGPLAYER_CONSOLE=1 builds exes with a console window for debugging.

import os
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
MSYS = "C:/msys64/ucrt64"
CONSOLE = os.environ.get("ENGPLAYER_CONSOLE") == "1"
ICON = os.path.join(SPECPATH, "app_icon.ico")

hiddenimports = ["gi._gi_cairo", "cairo", "sqlite3"]
hiddenimports += collect_submodules("gi.overrides", filter=lambda name: "Gst" in name or "_gi_gst" in name)
datas = [
    (os.path.join(ROOT, "resources"), "resources"),
    (os.path.join(SPECPATH, "deno.exe"), "."),
    (os.path.join(ROOT, "LICENSE"), "."),
    (os.path.join(ROOT, "ADDITIONAL-TERMS.md"), "."),
    (os.path.join(ROOT, "THIRD-PARTY-NOTICES.md"), "."),
]
binaries = [
    (f"{MSYS}/bin/ffmpeg.exe", "."),
    (f"{MSYS}/bin/libsoup-3.0-0.dll", "."),
    (f"{MSYS}/libexec/gstreamer-1.0/gst-plugin-scanner.exe", "."),
]

for pkg in ("guessit", "rebulk", "babelfish", "yt_dlp_ejs"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
hiddenimports += collect_submodules("yt_dlp")

hooksconfig = {
    "gi": {
        "module-versions": {"Gtk": "4.0"},
        "icons": ["Adwaita", "hicolor"],
        "themes": [],
        "languages": ["tr", "de", "fr", "it", "es", "pt_BR"],
    },
}

common = dict(
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig=hooksconfig,
    runtime_hooks=[os.path.join(SPECPATH, "rthook.py")],
    excludes=["tkinter", "unittest", "pydoc_data"],
    noarchive=False,
)

a_main = Analysis([os.path.join(ROOT, "main.py")], **common)
a_daemon = Analysis([os.path.join(ROOT, "recorder_daemon.py")], **common)

pyz_main = PYZ(a_main.pure)
pyz_daemon = PYZ(a_daemon.pure)

exe_main = EXE(
    pyz_main, a_main.scripts, [],
    exclude_binaries=True,
    name="EngPlayer",
    console=CONSOLE,
    icon=ICON,
    upx=False,
)
exe_daemon = EXE(
    pyz_daemon, a_daemon.scripts, [],
    exclude_binaries=True,
    name="EngPlayerDaemon",
    console=CONSOLE,
    icon=ICON,
    upx=False,
)

coll = COLLECT(
    exe_main, a_main.binaries, a_main.datas,
    exe_daemon, a_daemon.binaries, a_daemon.datas,
    upx=False,
    name="EngPlayer",
)
