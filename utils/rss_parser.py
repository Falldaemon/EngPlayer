import urllib.request
import xml.etree.ElementTree as ET
import logging
import ssl
from core.config import VERSION 

def parse_podcast_feed(rss_url):
    """
    Downloads the given RSS URL and parses the Podcast title, image, and episodes.
    Returns a dictionary (dict).
    """
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(rss_url, headers={'User-Agent': f'EngPlayer/{VERSION}'})       
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            xml_data = response.read()
        root = ET.fromstring(xml_data)
        channel = root.find("channel")       
        if channel is None:
            logging.error("Invalid RSS feed: No channel tag found.")
            return None
        podcast_data = {
            "title": channel.findtext("title"),
            "description": channel.findtext("description"),
            "image": None,
            "episodes": []
        }
        image_tag = channel.find("image")
        if image_tag is not None:
            podcast_data["image"] = image_tag.findtext("url")
        if not podcast_data["image"]:
            pass 
        for item in channel.findall("item"):
            episode = {
                "title": item.findtext("title"),
                "link": item.findtext("link"),
                "audio_url": None,
                "pub_date": item.findtext("pubDate")
            }
            enclosure = item.find("enclosure")
            if enclosure is not None:
                episode["audio_url"] = enclosure.get("url")
            if not episode["audio_url"] and episode["link"] and episode["link"].endswith(".mp3"):
                episode["audio_url"] = episode["link"]
            if episode["audio_url"]:
                podcast_data["episodes"].append(episode)
        return podcast_data
    except Exception as e:
        logging.error(f"Error parsing RSS feed ({rss_url}): {e}")
        return None
