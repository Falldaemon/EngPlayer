import gi
gi.require_version("Adw", "1")
from gi.repository import Adw

def get_icon_theme_folder():
    """
    Checks the current Adwaita style manager to see if the dark theme is active
    and returns the corresponding folder name ('dark' or 'light').
    """
    style_manager = Adw.StyleManager.get_default()
    if style_manager.get_dark():
        return "dark"
    else:
        return "light"
