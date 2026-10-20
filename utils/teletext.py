# utils/teletext.py

import unicodedata

_HAMMING_8_4 = (0x15, 0x02, 0x49, 0x5E, 0x64, 0x73, 0x38, 0x2F,
                0xD0, 0xC7, 0x8C, 0x9B, 0xA1, 0xB6, 0xFD, 0xEA)


def _build_unham():
    table = [None] * 256
    for byte in range(256):
        for value, code in enumerate(_HAMMING_8_4):
            if bin(code ^ byte).count("1") <= 1:
                table[byte] = value
                break
    return table


_UNHAM = _build_unham()
_REVERSE = bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))

_NATIONAL_POSITIONS = (0x23, 0x24, 0x40, 0x5B, 0x5C, 0x5D, 0x5E, 0x5F, 0x60, 0x7B, 0x7C, 0x7D, 0x7E)
_NATIONAL_SETS = {
    "english": "£$@←½→↑#―¼‖¾÷",
    "french": "éïàëêùî#èâôûç",
    "swedish": "#¤ÉÄÖÅÜ_éäöåü",
    "czech": "#ůčťžýířéáěúš",
    "german": "#$§ÄÖÜ^_°äöüß",
    "spanish": "ç$¡áéíóú¿üñèà",
    "italian": "£$é°ç→↑#ùàòèì",
    "romanian": "#¤ŢÂŞĂÎıţâşăî",
    "polish": "#ńĄƵŚŁćóężśłź",
    "turkish": "₺ğİŞÖÇÜĞışöçü",
    "serbian_croatian": "#ËČĆŽĐŠëčćžđš",
    "estonian": "#õŠÄÖŽÜÕšäöžü",
    "lettish_lithuanian": "#$ŠėęŽčūšąųžį",
    "danish": "#¤ÉÆØÅÜ_éæøåü",
}

_OPTION_SETS = {0: "english", 1: "french", 2: "swedish", 3: "czech",
                4: "german", 5: "spanish", 6: "italian", 7: "romanian"}

_LANGUAGE_SETS = {
    "dan": "danish", "da": "danish", "nor": "danish", "nob": "danish", "nno": "danish",
    "no": "danish", "nb": "danish", "nn": "danish",
    "pol": "polish", "pl": "polish",
    "tur": "turkish", "tr": "turkish",
    "rum": "romanian", "ron": "romanian", "ro": "romanian",
    "hrv": "serbian_croatian", "scr": "serbian_croatian", "srp": "serbian_croatian",
    "slv": "serbian_croatian", "bos": "serbian_croatian",
    "hr": "serbian_croatian", "sr": "serbian_croatian", "sl": "serbian_croatian", "bs": "serbian_croatian",
    "est": "estonian", "et": "estonian",
    "lav": "lettish_lithuanian", "lit": "lettish_lithuanian", "lv": "lettish_lithuanian", "lt": "lettish_lithuanian",
}

_G2_LATIN = (" ¡¢£$¥#§¤‘“«←↑→↓°±²³×µ¶·÷’”»¼½¾¿"
             " `´^~¯˘˙¨.˚¸_˝˛ˇ―¹®©™♪₠‰α   ⅛⅜⅝⅞"
             "ΩÆĐªĦ ĲĿŁØŒºÞŦŊŉĸæđðħıĳŀłøœßþŧŋ ")
_DIACRITICS = {1: "̀", 2: "́", 3: "̂", 4: "̃", 5: "̄", 6: "̆",
               7: "̇", 8: "̈", 10: "̊", 11: "̧", 13: "̋", 14: "̨",
               15: "̌"}

_CHARMAPS = {}


def _charmap(name):
    table = _CHARMAPS.get(name)
    if table is None:
        table = {code: chr(code) for code in range(0x20, 0x7F)}
        for position, char in zip(_NATIONAL_POSITIONS, _NATIONAL_SETS[name]):
            table[position] = char
        _CHARMAPS[name] = table
    return table


class TeletextSubtitleDecoder:

    def __init__(self, language=None):
        self.language = language
        self._collecting = {}
        self._last_text = {}

    def _charset(self, national):
        name = _LANGUAGE_SETS.get((self.language or "").lower())
        if name is None:
            name = _OPTION_SETS.get(national, "english")
        return _charmap(name)

    def feed(self, payload, pts=None):
        events = []
        if not payload or payload[0] < 0x10 or payload[0] > 0x1F:
            return events
        pos = 1
        while pos + 2 <= len(payload):
            unit_id, length = payload[pos], payload[pos + 1]
            unit = payload[pos + 2:pos + 2 + length]
            pos += 2 + length
            if unit_id not in (0x02, 0x03) or length != 0x2C or len(unit) < 44:
                continue
            packet = unit[2:44].translate(_REVERSE)
            first, second = _UNHAM[packet[0]], _UNHAM[packet[1]]
            if first is None or second is None:
                continue
            magazine = first & 7 or 8
            row = (first >> 3) | (second << 1)
            if row == 0:
                self._header(packet, magazine, pts, events)
            elif magazine in self._collecting:
                if 1 <= row <= 23:
                    self._collecting[magazine][2][row] = packet[2:42]
                elif row == 26:
                    self._enhance(packet, self._collecting[magazine][3])
        return events

    def _header(self, packet, magazine, pts, events):
        fields = [_UNHAM[b] for b in packet[2:10]]
        if None in fields:
            return
        units, tens = fields[0], fields[1]
        control_c11_c14 = fields[7]
        serial = bool(control_c11_c14 & 1)
        for collecting in list(self._collecting):
            if serial or collecting == magazine:
                self._finish(collecting, events, pts)
        if units > 9 or tens > 9 or not fields[5] & 8:
            return
        page = magazine * 100 + tens * 10 + units
        national = (control_c11_c14 >> 1) & 7
        self._collecting[magazine] = (page, national, {}, {})

    def _finish(self, magazine, events, pts):
        page, national, rows, enhancements = self._collecting.pop(magazine)
        charset = self._charset(national)
        lines = [text for text in (self._row_text(rows[row], charset, enhancements.get(row, {}))
                                   for row in sorted(rows)) if text]
        result = "\n".join(lines)
        if page not in self._last_text and not any(char.isalpha() for char in result):
            return
        if result != self._last_text.get(page):
            self._last_text[page] = result
            events.append((page, pts, result))

    @staticmethod
    def _row_text(data, charset, overrides):
        chars, boxed, any_box = [], False, False
        for column, byte in enumerate(data):
            code = byte & 0x7F
            if code == 0x0B:
                boxed = True
                any_box = True
                chars.append(" ")
            elif code == 0x0A:
                boxed = False
                chars.append(" ")
            elif code < 0x20:
                chars.append(" ")
            else:
                char = overrides.get(column) or charset.get(code, " ")
                chars.append(char if (boxed or not any_box) else " ")
        return " ".join("".join(chars).split())

    @staticmethod
    def _enhance(packet, enhancements):
        active_row = None
        for pos in range(3, 42, 3):
            b0, b1, b2 = packet[pos], packet[pos + 1], packet[pos + 2]
            value = ((b0 >> 2) & 1) | ((b0 >> 4) & 7) << 1 | (b1 & 0x7F) << 4 | (b2 & 0x7F) << 11
            address, mode, data = value & 0x3F, (value >> 6) & 0x1F, value >> 11
            if address >= 40:
                if mode >= 0x11:
                    break
                if mode in (0x01, 0x04):
                    active_row = address - 40 or 24
                continue
            if active_row is None or data < 0x20:
                continue
            if mode == 0x0F:
                char = _G2_LATIN[data - 0x20]
            elif mode >= 0x11:
                char = unicodedata.normalize("NFC", chr(data) + _DIACRITICS.get(mode - 0x10, ""))
            else:
                continue
            enhancements.setdefault(active_row, {})[address] = char
