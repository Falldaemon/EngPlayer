#!/usr/bin/env bash
# packaging/build.sh - run from the MSYS2 UCRT64 terminal:
#   bash packaging/build.sh            (release build)
#   bash packaging/build.sh --console  (build with a console window for debugging)
set -e
cd "$(dirname "$0")/.."

taskkill //F //IM EngPlayerDaemon.exe //T >/dev/null 2>&1 || true
taskkill //F //IM EngPlayer.exe //T >/dev/null 2>&1 || true
sleep 1
rm -rf packaging/dist packaging/build

for po in resources/locale/*/LC_MESSAGES/engplayer.po; do
    msgfmt -c "$po" -o "${po%.po}.mo" || { echo "msgfmt failed: $po"; exit 1; }
done
echo "Translations compiled."

if [ "$1" = "--console" ]; then
    export ENGPLAYER_CONSOLE=1
fi
python -m PyInstaller packaging/EngPlayer.spec --noconfirm \
    --distpath packaging/dist --workpath packaging/build > packaging/build.log 2>&1 \
    || { echo "PyInstaller failed, see packaging/build.log"; tail -20 packaging/build.log; exit 1; }
echo "PyInstaller: OK ($(ls packaging/dist/EngPlayer/_internal | wc -l) items in _internal)"

if [ "$1" = "--console" ]; then
    echo "Console build ready: packaging/dist/EngPlayer/EngPlayer.exe (no installer made)"
    exit 0
fi

ISCC=""
for p in "/c/Program Files (x86)/Inno Setup 6/ISCC.exe" "/c/Program Files/Inno Setup 6/ISCC.exe" "$LOCALAPPDATA/Programs/Inno Setup 6/ISCC.exe"; do
    [ -f "$p" ] && ISCC="$p" && break
done
if [ -z "$ISCC" ]; then
    echo "ISCC.exe not found. Compile packaging/EngPlayer.iss from the Inno Setup window."
    exit 0
fi
"$ISCC" //Q packaging/EngPlayer.iss
ls -lh packaging/Output/
