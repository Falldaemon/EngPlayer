import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw
import database
import gettext

_ = gettext.gettext

class VideoSettingsWindow(Gtk.Window):
    def __init__(self, player):
        super().__init__()
        self.set_title(_("Video Settings"))
        self.set_default_size(400, 450)
        self.set_resizable(True)
        self.set_decorated(True)        
        self.player = player
        self.add_css_class("video-settings-window")
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(20)
        main_box.set_margin_bottom(20)
        main_box.set_margin_start(20)
        main_box.set_margin_end(20)
        self.set_child(main_box)
        
        def create_slider_row(label_text, min_val, max_val, default_val, config_key, property_name):
            row_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)         
            label = Gtk.Label(label=label_text, xalign=0)
            label.add_css_class("heading")
            row_box.append(label)           
            val_str = database.get_config_value(config_key)
            current_val = float(val_str) if val_str is not None else default_val            
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, min_val, max_val, 0.05)
            scale.set_value(current_val)
            scale.set_hexpand(True)
            scale.connect("value-changed", self._on_value_changed, config_key, property_name)            
            row_box.append(scale)
            return row_box, scale
        box_contrast, self.scale_contrast = create_slider_row(
            _("Contrast"), 0.0, 2.0, 1.0, "video_contrast", "contrast"
        )
        main_box.append(box_contrast)
        
        box_brightness, self.scale_brightness = create_slider_row(
            _("Brightness"), -1.0, 1.0, 0.0, "video_brightness", "brightness"
        )
        main_box.append(box_brightness)
        
        box_saturation, self.scale_saturation = create_slider_row(
            _("Saturation"), 0.0, 2.0, 1.0, "video_saturation", "saturation"
        )
        main_box.append(box_saturation)
        
        box_hue, self.scale_hue = create_slider_row(
            _("Hue"), -1.0, 1.0, 0.0, "video_hue", "hue"
        )
        main_box.append(box_hue)       
        main_box.append(Gtk.Box(vexpand=True))
        reset_button = Gtk.Button(label=_("Reset to Defaults"))
        reset_button.add_css_class("destructive-action")
        reset_button.connect("clicked", self._on_reset_clicked)
        main_box.append(reset_button)

    def _on_value_changed(self, scale, config_key, property_name):
        value = scale.get_value()
        database.set_config_value(config_key, str(value))
        if hasattr(self.player, 'set_video_correction'):
            self.player.set_video_correction(property_name, value)

    def _on_reset_clicked(self, button):
        self.scale_contrast.set_value(1.0)
        self.scale_brightness.set_value(0.0)
        self.scale_saturation.set_value(1.0)
        self.scale_hue.set_value(0.0)
