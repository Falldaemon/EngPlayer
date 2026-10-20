# utils/catchup_filter.py

_NO_ARCHIVE_VALUES = ("", "0", "false", "none")


def has_catchup(channel):
    value = str(channel.get("tv_archive", "") or "").strip().lower()
    return value not in _NO_ARCHIVE_VALUES


def catchup_bouquets(bouquets_data):
    if not bouquets_data:
        return set()
    return {name for name, channels in bouquets_data.items()
            if any(has_catchup(channel) for channel in channels)}


def catchup_channels(channels):
    return [channel for channel in channels if has_catchup(channel)]
