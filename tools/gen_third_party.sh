#!/usr/bin/env bash
set -u
BUNDLE="${1:?usage: gen_third_party.sh <bundle _internal folder> [--sources]}"
WITH_SOURCES="${2:-}"
OUT="THIRD-PARTY-LIBRARIES.md"
PREFIX="mingw-w64-ucrt-x86_64-"

declare -A seen
{
  echo "# Bundled libraries (Windows build)"
  echo
  echo "Generated on $(date -u +%Y-%m-%d) from the MSYS2 package database."
  echo
  echo "| Package | Version | License | Files |"
  echo "|---|---|---|---|"
} > "$OUT"

mkdir -p licenses
tmp=$(mktemp)
find "$BUNDLE" -iname "*.dll" -o -iname "*.exe" -o -iname "*.pyd" | while read -r f; do
  name=$(basename "$f")
  owner=$(pacman -Qqo "/ucrt64/bin/$name" 2>/dev/null || pacman -Qqo "$(find /ucrt64/lib -iname "$name" 2>/dev/null | head -1)" 2>/dev/null)
  echo "${owner:-UNKNOWN}|$name"
done | sort > "$tmp"

for pkg in $(cut -d'|' -f1 "$tmp" | sort -u); do
  files=$(grep "^$pkg|" "$tmp" | cut -d'|' -f2 | tr '\n' ' ')
  if [ "$pkg" = "UNKNOWN" ]; then
    echo "| (not from MSYS2 — check manually) | | | $files |" >> "$OUT"
    continue
  fi
  ver=$(pacman -Qi "$pkg" | sed -n 's/^Version *: //p')
  lic=$(pacman -Qi "$pkg" | sed -n 's/^Licenses *: //p')
  echo "| ${pkg#$PREFIX} | $ver | $lic | $files |" >> "$OUT"
  pacman -Qlq "$pkg" | grep -iE "/share/licenses/" | grep -v "/$" | while read -r lf; do
    dst="licenses/${pkg#$PREFIX}"; mkdir -p "$dst"; cp -f "$lf" "$dst/" 2>/dev/null
  done
  if [ "$WITH_SOURCES" = "--sources" ]; then
    base="mingw-w64-${pkg#$PREFIX}"
    mkdir -p sources
    curl -sfL -o "sources/$base-$ver.src.tar.zst" \
      "https://repo.msys2.org/mingw/sources/$base-$ver.src.tar.zst" \
      || echo "  [!] source not found for $pkg $ver (check its pkgbase)"
  fi
done
rm -f "$tmp"
echo "Done: $OUT, licenses/ $( [ "$WITH_SOURCES" = "--sources" ] && echo ', sources/')"
