# Third-Party Software & Licenses

EngPlayer is licensed under the GNU General Public License v3 or later
(see [LICENSE](LICENSE)). The official builds also contain the third-party
components listed below. Each component remains under its own license and
copyright; their license texts are included with the Windows build in the
`licenses/` folder.

## Corresponding source

The Windows build is produced from MSYS2 (UCRT64) packages. The complete
source code of every bundled native component, in the exact version that was
shipped, is published with each release on the EngPlayer GitHub releases
page:

https://github.com/Falldaemon/EngPlayer/releases

The same source packages are also available from the MSYS2 project:
https://repo.msys2.org/mingw/sources/

On Linux (Flatpak), GTK, GStreamer, FFmpeg and the other system libraries are
provided by the GNOME Flatpak runtime and are not part of the EngPlayer
package. The Flatpak build additionally bundles gst-python (GStreamer Python
bindings), because it is not part of the GNOME runtime. Its source code is
available from https://gstreamer.freedesktop.org/src/gst-python/

## Python packages

| Package | License |
|---|---|
| requests | Apache-2.0 |
| yt-dlp | Unlicense |
| mutagen | GPL-2.0-or-later |
| guessit | LGPL-3.0-or-later |
| rebulk | MIT |
| babelfish | BSD-3-Clause |
| python-dateutil | Apache-2.0 OR BSD-3-Clause |
| protobuf | BSD-3-Clause |
| RapidFuzz | MIT |
| Levenshtein | GPL-2.0-or-later |
| thefuzz | MIT |
| deep-translator | MIT |
| PyGObject | LGPL-2.1-or-later |
| gst-python | LGPL-2.1-or-later |
| Python runtime (Windows build) | PSF-2.0 |

## Main native components (Windows build)

| Component | License |
|---|---|
| GTK 4 | LGPL-2.1-or-later |
| libadwaita | LGPL-2.1-or-later |
| GLib / GObject / GIO | LGPL-2.1-or-later |
| GStreamer and plugins (base, good, bad) | LGPL-2.1-or-later |
| gst-libav | LGPL-2.1-or-later |
| FFmpeg (libavcodec, libavformat, libavutil, libavfilter, libswscale, libswresample) | GPL-3.0-or-later (this build) |
| x264, x265, Xvid, vid.stab | GPL-2.0-or-later |
| cairo | LGPL-2.1-only OR MPL-1.1 |
| Pango | LGPL-2.1-or-later |
| HarfBuzz | MIT |
| gdk-pixbuf | LGPL-2.1-or-later |
| librsvg | LGPL-2.1-or-later |
| libsoup | LGPL-2.1-or-later |
| SQLite | Public domain |
| OpenSSL | Apache-2.0 |
| dav1d, libaom | BSD-2-Clause |
| libvpx, libwebp, Opus, libogg, libvorbis | BSD-3-Clause |
| libass | ISC |
| zlib | Zlib |

The complete list of every bundled library, with its exact version and
license, is in [THIRD-PARTY-LIBRARIES.md](THIRD-PARTY-LIBRARIES.md)
(generated automatically for each Windows build).

## Artwork

- Icon by Paul Mackenzie (whatspauldoing.com), licensed under CC BY-SA 4.0.

## Services

- This product uses the TMDb API but is not endorsed or certified by TMDb.
  (https://www.themoviedb.org/)
