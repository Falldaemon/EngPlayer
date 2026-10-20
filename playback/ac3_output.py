# playback/ac3_output.py

import os
import struct
import logging
import database
from gi.repository import Gst, GObject

CONFIG_KEY = "dolby_digital_output"
SINK_NAME = "ac3_output"
VOLUME_NAME = "ac3_volume"
_BURST_BYTES = 6144
_PCM_CAPS = "audio/x-raw, format=S16LE, layout=interleaved, rate=48000, channels=2, channel-mask=(bitmask)0x3"
_INPUT_CAPS = ("audio/x-raw,format=F32LE,layout=interleaved,channels=6,channel-mask=(bitmask)0x3f; "
               "audio/x-raw,format=F32LE,layout=interleaved,channels=2,channel-mask=(bitmask)0x3")
_ENCODE_CHAIN = ("audioresample ! audio/x-raw,rate=48000 ! audioconvert ! "
                 "avenc_ac3 bitrate=640000 ! ac3parse")
_payloader_registered = None


def is_enabled():
    return database.get_config_value(CONFIG_KEY) == '1'


def _iec61937_burst(frame):
    if len(frame) < 6 or frame[0] != 0x0B or frame[1] != 0x77:
        return None
    bsmod = frame[5] & 0x07
    if len(frame) % 2:
        frame += b"\x00"
    swapped = bytearray(len(frame))
    swapped[0::2] = frame[1::2]
    swapped[1::2] = frame[0::2]
    header = struct.pack("<HHHH", 0xF872, 0x4E1F, 0x01 | (bsmod << 8), len(frame) * 8)
    burst = header + bytes(swapped)
    if len(burst) > _BURST_BYTES:
        return None
    return burst + bytes(_BURST_BYTES - len(burst))


def _register_payloader():
    global _payloader_registered
    if _payloader_registered is not None:
        return _payloader_registered
    try:
        class Iec61937Pay(Gst.Element):
            __gtype_name__ = "EngIec61937Pay"
            __gstmetadata__ = ("IEC 61937 AC-3 payloader", "Filter/Audio",
                               "Wraps AC-3 frames into IEC 61937 bursts", "EngPlayer")
            __gsttemplates__ = (
                Gst.PadTemplate.new("sink", Gst.PadDirection.SINK, Gst.PadPresence.ALWAYS,
                                    Gst.Caps.from_string("audio/x-ac3, framed=(boolean)true")),
                Gst.PadTemplate.new("src", Gst.PadDirection.SRC, Gst.PadPresence.ALWAYS,
                                    Gst.Caps.from_string(_PCM_CAPS)),
            )

            def __init__(self):
                super().__init__()
                self.sinkpad = Gst.Pad.new_from_template(self.get_pad_template("sink"), "sink")
                self.sinkpad.set_chain_function_full(self._chain, None)
                self.sinkpad.set_event_function_full(self._event, None)
                self.add_pad(self.sinkpad)
                self.srcpad = Gst.Pad.new_from_template(self.get_pad_template("src"), "src")
                self.add_pad(self.srcpad)

            def _event(self, pad, parent, event):
                if event.type == Gst.EventType.CAPS:
                    return self.srcpad.push_event(Gst.Event.new_caps(Gst.Caps.from_string(_PCM_CAPS)))
                return self.srcpad.push_event(event)

            def _chain(self, pad, parent, buf):
                ok, info = buf.map(Gst.MapFlags.READ)
                if not ok:
                    return Gst.FlowReturn.ERROR
                frame = bytes(info.data)
                buf.unmap(info)
                burst = _iec61937_burst(frame)
                if burst is None:
                    return Gst.FlowReturn.OK
                out = Gst.Buffer.new_wrapped(burst)
                out.pts = buf.pts
                out.dts = buf.dts
                out.duration = buf.duration
                if buf.has_flags(Gst.BufferFlags.DISCONT):
                    out.set_flags(Gst.BufferFlags.DISCONT)
                return self.srcpad.push(out)

        GObject.type_register(Iec61937Pay)
        _payloader_registered = Gst.Element.register(None, "engiec61937pay", Gst.Rank.NONE, Iec61937Pay)
    except Exception as e:
        logging.error(f"AC-3 output: could not register the IEC 61937 payloader: {e}")
        _payloader_registered = False
    return _payloader_registered


def _windows_default_device_accepts_ac3():
    import ctypes
    import uuid
    from ctypes import wintypes, POINTER, byref, c_void_p, c_long, c_ushort, c_uint

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    class WAVEFORMATEX(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("wFormatTag", c_ushort), ("nChannels", c_ushort), ("nSamplesPerSec", c_uint),
                    ("nAvgBytesPerSec", c_uint), ("nBlockAlign", c_ushort),
                    ("wBitsPerSample", c_ushort), ("cbSize", c_ushort)]

    class WAVEFORMATEXTENSIBLE(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("Format", WAVEFORMATEX), ("wValidBitsPerSample", c_ushort),
                    ("dwChannelMask", c_uint), ("SubFormat", GUID)]

    def guid(text):
        value = GUID()
        ctypes.memmove(byref(value), uuid.UUID(text).bytes_le, 16)
        return value

    def call(obj, index, argtypes, *args):
        vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
        return ctypes.WINFUNCTYPE(c_long, c_void_p, *argtypes)(vtbl[index])(obj, *args)

    CLSCTX_ALL = 23
    AUDCLNT_E_UNSUPPORTED_FORMAT = 0x88890008
    ole32 = ctypes.windll.ole32
    ole32.CoInitializeEx.restype = c_long
    ole32.CoCreateInstance.restype = c_long
    init_hr = ole32.CoInitializeEx(None, 2)
    enumerator = c_void_p()
    device = c_void_p()
    try:
        if ole32.CoCreateInstance(byref(guid("BCDE0395-E52F-467C-8E3D-C4579291692E")), None, CLSCTX_ALL,
                                  byref(guid("A95664D2-9614-4F35-A746-DE8DB63617E6")), byref(enumerator)) != 0:
            return None
        if call(enumerator, 4, [ctypes.c_int, ctypes.c_int, POINTER(c_void_p)], 0, 0, byref(device)) != 0:
            return None
        iid_audio_client = guid("1CB9AD4C-DBFA-4C32-B178-C2F568A703B2")
        formats = (
            WAVEFORMATEX(0x0092, 2, 48000, 192000, 4, 16, 0),
            WAVEFORMATEXTENSIBLE(WAVEFORMATEX(0xFFFE, 2, 48000, 192000, 4, 16, 22), 16, 3,
                                 guid("00000092-0000-0010-8000-00AA00389B71")),
        )
        unknown = False
        for fmt in formats:
            client = c_void_p()
            if call(device, 3, [POINTER(GUID), wintypes.DWORD, c_void_p, POINTER(c_void_p)],
                    byref(iid_audio_client), CLSCTX_ALL, None, byref(client)) != 0:
                unknown = True
                continue
            hr = call(client, 7, [ctypes.c_int, c_void_p, c_void_p],
                      1, ctypes.cast(byref(fmt), c_void_p), None) & 0xFFFFFFFF
            call(client, 2, [])
            if hr == 0:
                return True
            if hr != AUDCLNT_E_UNSUPPORTED_FORMAT:
                unknown = True
        return None if unknown else False
    except Exception as e:
        logging.debug(f"AC-3 output: WASAPI format check failed: {e}")
        return None
    finally:
        for obj in (device, enumerator):
            if obj:
                call(obj, 2, [])
        if init_hr in (0, 1):
            ole32.CoUninitialize()


def _sink_accepts(factory_name, caps_string, **props):
    probe = Gst.ElementFactory.make(factory_name, None)
    if probe is None:
        return False
    try:
        for key, value in props.items():
            probe.set_property(key, value)
        if probe.set_state(Gst.State.READY) == Gst.StateChangeReturn.FAILURE:
            return False
        caps = probe.get_static_pad("sink").query_caps(None)
        return caps.can_intersect(Gst.Caps.from_string(caps_string))
    finally:
        probe.set_state(Gst.State.NULL)


def create_sink():
    for name in ("avenc_ac3", "ac3parse"):
        if Gst.ElementFactory.find(name) is None:
            logging.warning(f"AC-3 output: GStreamer element '{name}' not found.")
            return None
    if os.name == 'nt':
        if not _register_payloader():
            return None
        if _windows_default_device_accepts_ac3() is False:
            logging.warning("AC-3 output: the current audio device does not accept a Dolby Digital bitstream.")
            return None
        if not _sink_accepts("wasapi2sink", _PCM_CAPS, exclusive=True):
            logging.warning("AC-3 output: the current audio device does not accept 48 kHz stereo in exclusive mode.")
            return None
        tail = ("queue max-size-time=200000000 max-size-buffers=0 max-size-bytes=0 ! "
                "engiec61937pay ! wasapi2sink exclusive=true")
    else:
        if not _sink_accepts("pulsesink", "audio/x-ac3, framed=(boolean)true"):
            logging.warning("AC-3 output: the current audio device does not accept Dolby Digital (passthrough not enabled).")
            return None
        tail = "pulsesink"
    tempo = "scaletempo ! " if Gst.ElementFactory.find("scaletempo") else ""
    try:
        sink = Gst.parse_bin_from_description(
            f'capsfilter caps="{_INPUT_CAPS}" ! volume name={VOLUME_NAME} ! {tempo}{_ENCODE_CHAIN} ! {tail}', True)
    except Exception as e:
        logging.error(f"AC-3 output: could not build the audio sink: {e}")
        return None
    sink.set_name(SINK_NAME)
    return sink


def is_ac3_error(message, error_text):
    obj = message.src if isinstance(message.src, Gst.Object) else None
    while obj is not None:
        if obj.get_name() == SINK_NAME:
            return True
        obj = obj.get_parent()
    err, _debug = message.parse_error()
    missing_plugin = err.matches(Gst.CoreError.quark(), Gst.CoreError.MISSING_PLUGIN)
    return "not-negotiated" in error_text or missing_plugin
