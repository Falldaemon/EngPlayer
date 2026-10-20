# ui/genre_filter_bar.py

import logging
import re
from collections import Counter
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib, GObject
import gettext
_ = gettext.gettext

GENRE_ORDER = (
    "action", "adventure", "animation", "comedy", "crime", "documentary",
    "drama", "family", "fantasy", "science_fiction", "horror", "thriller",
    "mystery", "romance", "history", "war", "music", "western",
)

_ALIASES = {
    "action": ("action", "aksiyon", "acción", "accion", "azione", "ação", "acao", "أكشن", "اكشن", "حركة"),
    "adventure": ("adventure", "macera", "abenteuer", "aventure", "aventura", "avventura", "مغامرة"),
    "animation": ("animation", "animasyon", "animación", "animacion", "animazione", "animação", "animacao", "anime", "رسوم متحركة"),
    "comedy": ("comedy", "komedi", "komödie", "komodie", "comédie", "comedie", "comedia", "commedia", "comédia", "كوميديا", "كوميدي"),
    "crime": ("crime", "suç", "suc", "krimi", "crimen", "جريمة"),
    "documentary": ("documentary", "belgesel", "dokumentarfilm", "dokumentation", "documentaire", "documental", "documentario", "documentário", "وثائقي"),
    "drama": ("drama", "dram", "drame", "dramma", "دراما"),
    "family": ("family", "aile", "familie", "familial", "familia", "famiglia", "família", "kids", "çocuklar", "cocuklar", "çocuk", "cocuk", "enfants", "kinder", "niños", "ninos", "bambini", "infantil", "عائلي", "أطفال"),
    "fantasy": ("fantasy", "fantastik", "fantazi", "fantastique", "fantasía", "fantasia", "خيال"),
    "science_fiction": ("science fiction", "sci fi", "scifi", "bilim kurgu", "bilimkurgu", "science-fiction", "ciencia ficción", "ciencia ficcion", "fantascienza", "ficção científica", "ficcao cientifica", "خيال علمي"),
    "horror": ("horror", "korku", "horreur", "terror", "رعب"),
    "thriller": ("thriller", "gerilim", "suspense", "suspenso", "إثارة", "اثارة"),
    "mystery": ("mystery", "gizem", "mystère", "mystere", "misterio", "mistero", "mistério", "غموض"),
    "romance": ("romance", "romantik", "romantic", "liebesfilm", "romántico", "romantico", "رومانسي", "رومانسية"),
    "history": ("history", "tarih", "historie", "histoire", "historia", "storia", "história", "تاريخ", "تاريخي"),
    "war": ("war", "savaş", "savas", "kriegsfilm", "krieg", "guerre", "guerra", "bélica", "belica", "حرب"),
    "music": ("music", "müzik", "muzik", "musik", "musique", "música", "musica", "موسيقى"),
    "western": ("western", "vahşi batı", "vahsi bati", "faroeste", "ويسترن"),
}

_COMBINED = {
    "action & adventure": ("action", "adventure"),
    "aksiyon & macera": ("action", "adventure"),
    "sci fi & fantasy": ("science_fiction", "fantasy"),
    "bilim kurgu & fantazi": ("science_fiction", "fantasy"),
    "science fiction & fantastique": ("science_fiction", "fantasy"),
    "war & politics": ("war",),
    "savaş & politik": ("war",),
    "guerre & politique": ("war",),
}

_SPLIT_RE = re.compile(r"[,/|;]+")
_SPACE_RE = re.compile(r"[\s\-_.]+")


def _normalize(text):
    return _SPACE_RE.sub(" ", text.replace("İ", "i").lower()).strip()

_LOOKUP = {}
for _key, _names in _ALIASES.items():
    for _name in _names:
        _LOOKUP[_normalize(_name)] = (_key,)
for _name, _keys in _COMBINED.items():
    _LOOKUP[_normalize(_name)] = _keys
_cache = {}
_unknown_tokens = Counter()

def _keys_for_token(token):
    norm = _normalize(token)
    if not norm:
        return ()
    found = _LOOKUP.get(norm)
    if found:
        return found
    if "&" in norm or " and " in norm or " ve " in norm:
        keys = []
        for part in re.split(r"&| and | ve ", norm):
            keys.extend(_LOOKUP.get(part.strip(), ()))
        if keys:
            return tuple(keys)
    _unknown_tokens[norm] += 1
    return ()

def genre_keys_for(genre_text):
    if not genre_text or not isinstance(genre_text, str):
        return frozenset()
    cached = _cache.get(genre_text)
    if cached is not None:
        return cached
    keys = set()
    for token in _SPLIT_RE.split(genre_text):
        keys.update(_keys_for_token(token))
    result = frozenset(keys)
    if len(_cache) < 50000:
        _cache[genre_text] = result
    return result

def genre_label(key):
    labels = {
        "action": _("Action"),
        "adventure": _("Adventure"),
        "animation": _("Animation"),
        "comedy": _("Comedy"),
        "crime": _("Crime"),
        "documentary": _("Documentary"),
        "drama": _("Drama"),
        "family": _("Family"),
        "fantasy": _("Fantasy"),
        "science_fiction": _("Science Fiction"),
        "horror": _("Horror"),
        "thriller": _("Thriller"),
        "mystery": _("Mystery"),
        "romance": _("Romance"),
        "history": _("Historical"),
        "war": _("War"),
        "music": _("Music"),
        "western": _("Western"),
    }
    return labels.get(key, key)

class GenreFilterBar(Gtk.Box):
    __gsignals__ = {
        "genre-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=4, **kwargs)
        self.set_margin_start(12)
        self.set_margin_end(12)
        self.add_css_class("genre-filter-bar")
        self.row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.scroller = Gtk.ScrolledWindow(propagate_natural_height=True, hexpand=True)
        self.scroller.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.NEVER)
        self.scroller.set_child(self.row)
        self.left_button = self._make_arrow("go-previous-symbolic", -1)
        self.right_button = self._make_arrow("go-next-symbolic", 1)
        self.append(self.left_button)
        self.append(self.scroller)
        self.append(self.right_button)
        wheel = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.BOTH_AXES)
        wheel.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        wheel.connect("scroll", self._on_wheel)
        self.scroller.add_controller(wheel)
        adjustment = self.scroller.get_hadjustment()
        self._arrows_pending = False
        adjustment.connect("changed", self._queue_update_arrows)
        adjustment.connect("value-changed", self._queue_update_arrows)
        self.selected_key = ""
        self._buttons = {}
        self._updating = False
        self.set_visible(False)

    def get_selected_key(self):
        return self.selected_key

    def clear(self):
        self._rebuild([], "")
        self.set_visible(False)

    def update(self, media_list, media_type, keep_selection=False):
        previous = self.selected_key if keep_selection else ""
        if media_type not in ("vod", "series") or not media_list:
            self.selected_key = ""
            self.clear()
            return
        counts = Counter()
        with_genre = 0
        for item in media_list:
            genre_text = item.get("genre") if isinstance(item, dict) else None
            keys = genre_keys_for(genre_text)
            if keys:
                with_genre += 1
                counts.update(keys)
        total = len(media_list)
        if not counts:
            logging.info(f"[Genres] No genre data in this {media_type} list ({total} items). Filter bar hidden.")
            self.selected_key = ""
            self.clear()
            return
        ordered = sorted(counts, key=lambda key: (-counts[key], GENRE_ORDER.index(key)))
        self.selected_key = previous if previous in counts else ""
        self._rebuild(ordered, self.selected_key, counts)
        self.set_visible(True)
        logging.info(
            f"[Genres] {with_genre}/{total} {media_type} items have genre data; "
            f"{len(ordered)} genres shown. Selected: '{self.selected_key or 'all'}'."
        )
        if _unknown_tokens:
            logging.debug(f"[Genres] Unmapped genre names so far: {_unknown_tokens.most_common(15)}")

    def _rebuild(self, ordered_keys, selected_key, counts=None):
        self._updating = True
        try:
            while (child := self.row.get_first_child()) is not None:
                self.row.remove(child)
            self.scroller.get_hadjustment().set_value(0)
            self._buttons = {}
            if not ordered_keys:
                return
            all_button = self._make_button("", _("All"), None)
            for key in ordered_keys:
                self._make_button(key, genre_label(key), counts.get(key) if counts else None, group=all_button)
            self._buttons.get(selected_key, all_button).set_active(True)
        finally:
            self._updating = False

    def _make_button(self, key, label, count, group=None):
        button = Gtk.ToggleButton(label=label)
        button.add_css_class("genre-chip")
        button.set_focus_on_click(False)
        if count is not None:
            button.set_tooltip_text(_("{} titles").format(count))
        if group is not None:
            button.set_group(group)
        button.connect("toggled", self._on_toggled, key)
        self.row.append(button)
        self._buttons[key] = button
        return button

    def _make_arrow(self, icon_name, direction):
        button = Gtk.Button(icon_name=icon_name, valign=Gtk.Align.CENTER)
        button.add_css_class("flat")
        button.add_css_class("genre-scroll-button")
        button.set_focus_on_click(False)
        button.set_visible(False)
        button.connect("clicked", self._on_arrow_clicked, direction)
        return button

    def _scroll_by(self, delta):
        adjustment = self.scroller.get_hadjustment()
        upper = max(0.0, adjustment.get_upper() - adjustment.get_page_size())
        adjustment.set_value(min(upper, max(0.0, adjustment.get_value() + delta)))

    def _on_arrow_clicked(self, button, direction):
        page = self.scroller.get_hadjustment().get_page_size()
        self._scroll_by(direction * max(120.0, page * 0.8))

    def _queue_update_arrows(self, *args):
        if not self._arrows_pending:
            self._arrows_pending = True
            GLib.idle_add(self._update_arrows)

    def _update_arrows(self, *args):
        self._arrows_pending = False
        adjustment = self.scroller.get_hadjustment()
        overflow = adjustment.get_upper() - adjustment.get_page_size() > 1
        self.left_button.set_visible(overflow)
        self.right_button.set_visible(overflow)
        if overflow:
            value = adjustment.get_value()
            self.left_button.set_sensitive(value > 1)
            self.right_button.set_sensitive(value < adjustment.get_upper() - adjustment.get_page_size() - 1)

    def _on_wheel(self, controller, dx, dy):
        adjustment = self.scroller.get_hadjustment()
        if adjustment.get_upper() - adjustment.get_page_size() <= 0:
            return False
        step = 60 if controller.get_unit() == Gdk.ScrollUnit.WHEEL else 1
        delta = dx if abs(dx) > abs(dy) else dy
        self._scroll_by(delta * step)
        return True

    def _on_toggled(self, button, key):
        if self._updating or not button.get_active():
            return
        if key == self.selected_key:
            return
        self.selected_key = key
        logging.debug(f"[Genres] Genre filter changed to '{key or 'all'}'.")
        self.emit("genre-changed", key)
