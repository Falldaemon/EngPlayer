# ui/custom_visualizer.py

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
import cairo
import colorsys

class CustomVisualizer(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self.bands = 64
        self.min_db = -60.0 
        self.magnitudes = [self.min_db] * self.bands
        self.smoothed_mags = [0.0] * self.bands
        self.peaks = [0.0] * self.bands       
        self.set_draw_func(self.on_draw)
        self.set_visible(False) 
        self.set_can_target(False)

    def update_magnitudes(self, new_mags):
        if new_mags and len(new_mags) > 0:
            self.magnitudes = new_mags
            self.queue_draw()

    def reset(self):
        self.magnitudes = [self.min_db] * self.bands
        self.smoothed_mags = [0.0] * self.bands
        self.peaks = [0.0] * self.bands
        self.queue_draw()

    def on_draw(self, area, cr, width, height):       
        if not self.magnitudes or len(self.magnitudes) == 0:
            return                 
        bands = len(self.magnitudes)
        total_width = width * 0.95 
        center_x = width / 2        
        bar_width = (total_width / 2) / bands
        actual_width = max(2.0, bar_width * 0.85)      
        segment_height = max(2.0, height * 0.012)
        segment_gap = 1.0 
        step = segment_height + segment_gap       
        baseline_y = height * 0.70 
        max_bar_height = height * 0.55 
        max_ref_height = height * 0.20        
        for i, mag in enumerate(self.magnitudes):
            max_db_visual = -15.0 
            range_db = max_db_visual - self.min_db           
            normalized = (mag - self.min_db) / range_db
            normalized = normalized ** 2.0           
            normalized = max(0.01, min(1.0, normalized))
            if normalized > self.smoothed_mags[i]:
                self.smoothed_mags[i] = (self.smoothed_mags[i] * 0.10) + (normalized * 0.90)
            else:
                self.smoothed_mags[i] = (self.smoothed_mags[i] * 0.80) + (normalized * 0.20)              
            current_val = self.smoothed_mags[i]            
            if current_val >= self.peaks[i]:
                self.peaks[i] = current_val 
            else:
                self.peaks[i] -= 0.01 
                if self.peaks[i] < current_val:
                    self.peaks[i] = current_val           
            x_right = center_x + (i * bar_width)
            x_left = center_x - ((i + 1) * bar_width)            
            hue = 0.85 - (i / bands) * 0.85
            r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
            cr.set_source_rgb(r, g, b)
            y_current = baseline_y - segment_gap
            drawn_height = 0
            target_height = current_val * max_bar_height                      
            while drawn_height < target_height:
                cr.rectangle(x_right, y_current - segment_height, actual_width, segment_height)
                cr.rectangle(x_left, y_current - segment_height, actual_width, segment_height)
                cr.fill()
                y_current -= step
                drawn_height += step               
            peak_y = baseline_y - (self.peaks[i] * max_bar_height) - segment_gap
            cr.rectangle(x_right, peak_y - segment_height, actual_width, segment_height)
            cr.rectangle(x_left, peak_y - segment_height, actual_width, segment_height)
            cr.fill()
            pat = cairo.LinearGradient(0, baseline_y, 0, baseline_y + max_ref_height)
            pat.add_color_stop_rgba(0.0, r, g, b, 0.4) 
            pat.add_color_stop_rgba(1.0, r, g, b, 0.0) 
            cr.set_source(pat)          
            y_current = baseline_y + segment_gap
            drawn_height = 0
            target_ref = current_val * max_ref_height                   
            while drawn_height < target_ref:
                cr.rectangle(x_right, y_current, actual_width, segment_height)
                cr.rectangle(x_left, y_current, actual_width, segment_height)
                cr.fill()
                y_current += step
                drawn_height += step
