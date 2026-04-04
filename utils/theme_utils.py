import database

def is_dark_theme():
    theme_name = database.get_config_value('app_theme')
    if not theme_name or theme_name == "default":
        theme_name = "deep_abyss"
    if theme_name in ["force_light", "mist", "latte"]:
        return False
    return True

def get_icon_theme_folder():
    theme_name = database.get_config_value('app_theme')
    if not theme_name or theme_name == "default":
        theme_name = "deep_abyss"
    if theme_name in ["force_light", "mist", "latte"]:
        return "light"
    return "dark"
