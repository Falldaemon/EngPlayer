# ui/theme_manager.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1") 
from gi.repository import Gtk, Gdk, Adw
import logging

class ThemeManager:

    LIGHT_CSS = """
    @define-color window_bg_color #F4F5F7;
    @define-color window_fg_color #2e3436;
    @define-color view_bg_color #F4F5F7;
    @define-color view_fg_color #2e3436;
    @define-color headerbar_bg_color #F4F5F7;
    @define-color headerbar_fg_color #2e3436;
    @define-color popover_bg_color #F4F5F7;
    @define-color popover_fg_color #2e3436;
    @define-color card_bg_color #F4F5F7;
    @define-color card_fg_color #2e3436;    
    @define-color accent_color #3F9AAE;
    @define-color accent_bg_color #3F9AAE;
    @define-color accent_fg_color #ffffff;
    @define-color border_color alpha(#000000, 0.25);  
    @define-color border_pop_up_color rgba(0, 0, 0, 0.40); 
    @define-color nav_rail_bg transparent;
    @define-color nav_button_bg #F4F5F7;
    @define-color nav_button_border transparent;
    @define-color nav_button_hover_bg rgba(179, 179, 179, 0.80);
    @define-color nav_button_hover_box_shadow rgba(0, 0, 0, 0.50);   
    @define-color player_bg_color #F4F5F7;
    @define-color player_box_shadow #000000;
    @define-color player_controls_border_color rgba(0, 0, 0, 0.20);     
    @define-color epg_bg_color #F4F5F7;
    @define-color epg_box_shadow #000000; 
    @define-color epg_panel_border_color rgba(0, 0, 0, 0.20);        
    @define-color osd_btn_grad_top rgba(255, 255, 255, 0.70); 
    @define-color osd_btn_grad_bot rgba(0, 0, 0, 0.50);        
    @define-color osd_btn_shadow rgba(0, 0, 0, 0.40);         
    @define-color settings-popover_hover_box_shadow rgba(0, 0, 0, 0.40);     
    @define-color settings_popover_row_bg rgba(179, 179, 179, 0.80);
    @define-color settings_popover_row_hover_bg rgba(219, 219, 219, 0.75);     
    @define-color settings_popover_row_switch_bg #6E6E6E;
    @define-color settings_popover_row_switch_slider_bg #303030;
    @define-color settings_popover_row_switch_checked_bg #FFFFFF;
    @define-color settings_popover_row_switch_checked_slider_bg #303030;   
    @define-color box_fullscreen_controls_popover_grad_top alpha(#83858A, 0.95); 
    @define-color box_fullscreen_controls_popover_grad_bot alpha(#000000, 0.80); 
    @define-color fullscreen_border_color rgba(216, 222, 233, 0.60);       
    @define-color fullscreen_bg_top alpha(#83858A, 0.95); 
    @define-color fullscreen_bg_bot alpha(#000000, 0.80);   
    @define-color fullscreen_fg_color #E9E3DF;
    @define-color fullscreen_btn_grad_top rgba(255, 255, 255, 0.70);
    @define-color fullscreen_btn_grad_bot rgba(0, 0, 0, 0.10);   
    @define-color fullscreen_border_color rgba(216, 222, 233, 0.60);    
    @define-color fullscreen_ch_list_grad_top alpha(#83858A, 0.95);
    @define-color fullscreen_ch_list_grad_bot alpha(#000000, 0.75);  
    @define-color fullscreen_ch_border_color rgba(216, 222, 233, 0.60); 
    @define-color fullscreen_ch_list_row rgba(0, 0, 0, 0.30);
    @define-color fullscreen_ch_hover rgba(0, 0, 0, 0.30);
    @define-color fullscreen_ch_bg transparent;   
    @define-color fullscreen_ch_entry alpha(#000000, 0.25);
    @define-color fullscreen_ch_entry_border rgba(216, 222, 233, 0.60);
    @define-color fullscreen_ch_list_label #E9E3DF;
    @define-color fullscreen_ch_list_row_sel_label #E9E3DF;
    @define-color fullscreen_ch_list_row_label #E9E3DF;
    @define-color fullscreen_epg_bar_fill #3F9AAE;
    @define-color fullscreen_epg_bar_bg rgba(216, 222, 233, 0.40);
    @define-color fullscreen_ch_list_entry_text #E9E3DF;
    @define-color fullscreen_ch_list_entry_image #E9E3DF;
    @define-color fullscreen_ch_list_button #E9E3DF;
    @define-color fullscreen_slider_highlight #3F9AAE;
    @define-color fullscreen_slider_color #AB998F;
    @define-color fullscreen_slider_fill rgba(0, 0, 0, 0.5);
    @define-color splash_content_grad_top alpha(#83858A, 0.75); 
    @define-color splash_content_grad_bot alpha(#000000, 0.65);
    @define-color splash_content_border rgba(216, 222, 233, 0.60);
    @define-color splash-title #E9E3DF;
    @define-color splash-status #E9E3DF;
    @define-color splash_content_spinner #E9E3DF;
    @define-color flat-button #E9E3DF;
    """

    DARK_CSS = """
    @define-color window_bg_color #121212;
    @define-color window_fg_color #E9E3DF;
    @define-color view_bg_color #121212;
    @define-color view_fg_color #E9E3DF;
    @define-color headerbar_bg_color #121212;
    @define-color headerbar_fg_color #E9E3DF;
    @define-color popover_bg_color #121212;
    @define-color popover_fg_color #E9E3DF;
    @define-color card_bg_color #121212;
    @define-color card_fg_color #E9E3DF;
    @define-color accent_color rgba(216, 222, 233, 0.50);
    @define-color accent_bg_color rgba(216, 222, 233, 0.50);
    @define-color accent_fg_color #FFFFFF;    
    @define-color border_color rgba(216, 222, 233, 0.80); 
    @define-color border_pop_up_color rgba(216, 222, 233, 0.40); 
    @define-color nav_rail_bg transparent;
    @define-color nav_button_bg #121212; 
    @define-color nav_button_border transparent;
    @define-color nav_button_hover_bg rgba(216, 222, 233, 0.30);
    @define-color nav_button_hover_box_shadow transparent;   
    @define-color player_bg_color #121212;
    @define-color player_box_shadow rgba(216, 222, 233, 0.40);
    @define-color player_controls_border_color rgba(216, 222, 233, 0.20);     
    @define-color epg_bg_color #121212; 
    @define-color epg_box_shadow rgba(216, 222, 233, 0.40);
    @define-color epg_panel_border_color rgba(216, 222, 233, 0.20);       
    @define-color osd_btn_grad_top rgba(255, 255, 255, 0.60); 
    @define-color osd_btn_grad_bot rgba(255, 255, 255, 0.10); 
    @define-color osd_btn_shadow transparent;       
    @define-color settings-popover_hover_box_shadow transparent;     
    @define-color settings_popover_row_bg rgba(89, 89, 89, 0.95);
    @define-color settings_popover_row_hover_bg rgba(163, 163, 163, 0.65);    
    @define-color settings_popover_row_switch_bg rgba(216, 222, 233, 0.50);
    @define-color settings_popover_row_switch_slider_bg #363636;
    @define-color settings_popover_row_switch_checked_bg #FFFFFF;
    @define-color settings_popover_row_switch_checked_slider_bg #363636;   
    @define-color box_fullscreen_controls_popover_grad_top alpha(#121212, 0.55);  
    @define-color box_fullscreen_controls_popover_grad_bot alpha(#000000, 0.90); 
    @define-color fullscreen_border_color rgba(216, 222, 233, 0.60);      
    @define-color fullscreen_bg_top alpha(#121212, 0.55); 
    @define-color fullscreen_bg_bot alpha(#000000, 0.90);   
    @define-color fullscreen_fg_color #E9E3DF;
    @define-color fullscreen_btn_grad_top rgba(216, 222, 233, 0.30);
    @define-color fullscreen_btn_grad_bot rgba(0, 0, 0, 0.40);
    @define-color fullscreen_border_color rgba(216, 222, 233, 0.60);    
    @define-color fullscreen_ch_list_grad_top alpha(#121212, 0.55);
    @define-color fullscreen_ch_list_grad_bot alpha(#000000, 0.90);    
    @define-color fullscreen_ch_border_color rgba(216, 222, 233, 0.60); 
    @define-color fullscreen_ch_list_row rgba(216, 222, 233, 0.40);
    @define-color fullscreen_ch_hover rgba(216, 222, 233, 0.40);
    @define-color fullscreen_ch_bg transparent;   
    @define-color fullscreen_ch_entry alpha(#121212, 0.55);
    @define-color fullscreen_ch_entry_border rgba(216, 222, 233, 0.60);
    @define-color fullscreen_ch_list_label #E9E3DF;
    @define-color fullscreen_ch_list_row_sel_label #E9E3DF;
    @define-color fullscreen_ch_list_row_label #E9E3DF;
    @define-color fullscreen_epg_bar_fill rgba(216, 222, 233, 0.70);
    @define-color fullscreen_epg_bar_bg rgba(216, 222, 233, 0.40);
    @define-color fullscreen_ch_list_entry_text #E9E3DF;
    @define-color fullscreen_ch_list_entry_image #FFFFFF;
    @define-color fullscreen_ch_list_button #E9E3DF;
    @define-color fullscreen_slider_highlight #AB998F;
    @define-color fullscreen_slider_color #AB998F;
    @define-color fullscreen_slider_fill rgba(0, 0, 0, 0.5);   
    @define-color splash_content_grad_top alpha(#121212, 0.55);
    @define-color splash_content_grad_bot alpha(#000000, 0.65);
    @define-color splash_content_border rgba(216, 222, 233, 0.60);
    @define-color splash-title #E9E3DF;
    @define-color splash-status #E9E3DF;
    @define-color splash_content_spinner #E9E3DF;
    @define-color flat-button #E9E3DF;
    """

    NORD_CSS = """
    @define-color window_bg_color #2E3440;
    @define-color window_fg_color #D8DEE9;
    @define-color view_bg_color #2E3440;
    @define-color view_fg_color #ECEFF4;
    @define-color headerbar_bg_color #2E3440;
    @define-color headerbar_fg_color #D8DEE9;
    @define-color headerbar_backdrop_color #2E3440;
    @define-color popover_bg_color #2E3440;
    @define-color popover_fg_color #D8DEE9;
    @define-color card_bg_color rgba(59, 66, 82, 0.30);
    @define-color card_fg_color #D8DEE9;  
    @define-color accent_color rgba(216, 222, 233, 0.50);
    @define-color accent_bg_color rgba(216, 222, 233, 0.50);
    @define-color accent_fg_color #2E3440;    
    @define-color border_color rgba(216, 222, 233, 0.80);
    @define-color border_pop_up_color rgba(216, 222, 233, 0.80);     
    @define-color nav_rail_bg transparent;
    @define-color nav_button_bg #2E3440;
    @define-color nav_button_border transparent;
    @define-color nav_button_hover_bg rgba(216, 222, 233, 0.15);
    @define-color nav_button_hover_box_shadow #000000;  
    @define-color player_bg_color #2E3440;
    @define-color player_box_shadow #000000;
    @define-color player_controls_border_color rgba(216, 222, 233, 0.20);   
    @define-color epg_bg_color #2E3440;   
    @define-color epg_box_shadow #000000; 
    @define-color epg_panel_border_color rgba(216, 222, 233, 0.20);      
    @define-color osd_btn_grad_top rgba(255, 255, 255, 0.50); 
    @define-color osd_btn_grad_bot rgba(0, 0, 0, 0.30); 
    @define-color osd_btn_shadow #000000;  
    @define-color settings-popover_hover_box_shadow #000000;     
    @define-color settings_popover_row_bg rgba(98, 108, 128, 0.50);
    @define-color settings_popover_row_hover_bg rgba(139, 153, 181, 0.55);       
    @define-color settings_popover_row_switch_bg rgba(216, 222, 233, 0.50);
    @define-color settings_popover_row_switch_slider_bg #2E3440;
    @define-color settings_popover_row_switch_checked_bg #FFFFFF;
    @define-color settings_popover_row_switch_checked_slider_bg #2E3440;   
    @define-color box_fullscreen_controls_popover_grad_top alpha(#2E3440, 0.80); 
    @define-color box_fullscreen_controls_popover_grad_bot alpha(#000000, 0.70);
    @define-color fullscreen_border_color rgba(216, 222, 233, 0.80);     
    @define-color fullscreen_bg_top alpha(#2E3440, 0.80); 
    @define-color fullscreen_bg_bot alpha(#000000, 0.70);   
    @define-color fullscreen_fg_color #D8DEE9;   
    @define-color fullscreen_btn_grad_top rgba(255, 255, 255, 0.1);
    @define-color fullscreen_btn_grad_bot rgba(79, 83, 89, 0.99);
    @define-color fullscreen_border_color rgba(216, 222, 233, 0.80);    
    @define-color fullscreen_ch_list_grad_top alpha(#2E3440, 0.80);
    @define-color fullscreen_ch_list_grad_bot alpha(#000000, 0.85);
    @define-color fullscreen_ch_border_color rgba(216, 222, 233, 0.80);      
    @define-color fullscreen_ch_list_row_bg transparent;
    @define-color fullscreen_ch_list_row rgba(91, 95, 102, 0.60);
    @define-color fullscreen_ch_hover rgba(91, 95, 102, 0.60);   
    @define-color fullscreen_ch_bg alpha(#D8DEE9, 0.30);
    @define-color fullscreen_ch_entry rgba(3, 18, 48, 0.20);
    @define-color fullscreen_ch_entry_border alpha(#D8DEE9, 0.30);
    @define-color fullscreen_ch_list_label rgba(255, 255, 255, 0.90);
    @define-color fullscreen_ch_list_row_sel_label rgba(255, 255, 255, 0.90);
    @define-color fullscreen_ch_list_row_label rgba(255, 255, 255, 0.90);
    @define-color fullscreen_epg_bar_fill rgba(216, 222, 233, 0.70);
    @define-color fullscreen_epg_bar_bg rgba(129, 161, 193, 0.50);   
    @define-color fullscreen_ch_list_entry_text rgba(255, 255, 255, 0.85);
    @define-color fullscreen_ch_list_entry_image rgba(255, 255, 255, 0.85);
    @define-color fullscreen_ch_list_button rgba(255, 255, 255, 0.85);
    @define-color fullscreen_slider_highlight rgba(216, 222, 233, 0.70);
    @define-color fullscreen_slider_color rgba(216, 222, 233, 0.99);
    @define-color fullscreen_slider_fill rgba(216, 222, 233, 0.30);
    @define-color splash_content_grad_top alpha(#2E3440, 0.60);
    @define-color splash_content_grad_bot alpha(#000000, 0.75);
    @define-color splash_content_border rgba(216, 222, 233, 0.80); 
    @define-color splash-title #D8DEE9;
    @define-color splash-status #D8DEE9;
    @define-color splash_content_spinner #D8DEE9;
    @define-color flat-button #D8DEE9;
    @define-color profile_window_border #444754; 
    filechooser .view image,
    filechooser .sidebar image,
    .filechooser image {
        filter: sepia(100%) saturate(0.6) hue-rotate(-180deg);
        opacity: 0.9;
    }
    """

    NEBULA_CSS = """
    @define-color window_bg_color #39204F;
    @define-color window_fg_color #FFFFFF;
    @define-color view_bg_color #39204F;
    @define-color view_fg_color #FFFFFF;
    @define-color headerbar_bg_color #39204F;
    @define-color headerbar_fg_color #FFFFFF;
    @define-color popover_bg_color #39204F;
    @define-color popover_fg_color #FFFFFF;
    @define-color card_bg_color #39204F;
    @define-color card_fg_color #FFFFFF;      
    @define-color accent_color rgba(216, 222, 233, 0.60);
    @define-color accent_bg_color rgba(216, 222, 233, 0.60);
    @define-color accent_fg_color #39204F;     
    @define-color border_color #D4A9FC; 
    @define-color border_pop_up_color #D4A9FC;      
    @define-color nav_rail_bg transparent;
    @define-color nav_button_bg #58327A;
    @define-color nav_button_border #D4A9FC;
    @define-color nav_button_hover_bg #58327A;
    @define-color nav_button_hover_box_shadow #000000;     
    @define-color player_bg_color #39204F;
    @define-color player_box_shadow #000000;
    @define-color player_controls_border_color rgba(216, 222, 233, 0.20);     
    @define-color epg_bg_color #39204F;
    @define-color epg_box_shadow #000000;
    @define-color epg_panel_border_color rgba(216, 222, 233, 0.20);    
    @define-color osd_btn_grad_top rgba(140, 81, 194, 0.80); 
    @define-color osd_btn_grad_bot rgba(255, 255, 255, 0.10); 
    @define-color osd_btn_shadow #000000;      
    @define-color settings-popover_hover_box_shadow #000000;    
    @define-color settings_popover_row_bg rgba(129, 71, 181, 0.60);
    @define-color settings_popover_row_hover_bg rgba(196, 158, 230, 0.70);    
    @define-color settings_popover_row_switch_bg #9872BA;
    @define-color settings_popover_row_switch_slider_bg #FFFFFF;
    @define-color settings_popover_row_switch_checked_bg #FFFFFF;
    @define-color settings_popover_row_switch_checked_slider_bg #A94DFA;   
    @define-color box_fullscreen_controls_popover_grad_top alpha(#39204F, 0.60); 
    @define-color box_fullscreen_controls_popover_grad_bot alpha(#190A26, 0.80); 
    @define-color fullscreen_border_color #D4A9FC;          
    @define-color fullscreen_bg_top alpha(#39204F, 0.60); 
    @define-color fullscreen_bg_bot alpha(#190A26, 0.80);   
    @define-color fullscreen_fg_color rgba(255, 255, 255, 0.85);   
    @define-color fullscreen_btn_grad_top rgba(140, 81, 194, 0.80); 
    @define-color fullscreen_btn_grad_bot rgba(0, 0, 0, 0.10);
    @define-color fullscreen_border_color #D4A9FC;     
    @define-color fullscreen_ch_list_grad_top alpha(#27014A, 0.60); 
    @define-color fullscreen_ch_list_grad_bot alpha(#190A26, 0.80);
    @define-color fullscreen_ch_border_color #D4A9FC;    
    @define-color fullscreen_ch_list_row alpha(#D4A9FC, 0.60);
    @define-color fullscreen_ch_hover alpha(#D4A9FC, 0.60);
    @define-color fullscreen_ch_bg transparent;    
    @define-color fullscreen_ch_entry alpha(#39204F, 0.60);
    @define-color fullscreen_ch_entry_border #D4A9FC;
    @define-color fullscreen_ch_list_label rgba(255, 255, 255, 0.90);
    @define-color fullscreen_ch_list_row_sel_label rgba(255, 255, 255, 0.90);
    @define-color fullscreen_ch_list_row_label rgba(255, 255, 255, 0.90);   
    @define-color fullscreen_epg_bar_fill rgba(255, 255, 255, 0.90);   
    @define-color fullscreen_epg_bar_bg rgba(255, 255, 255, 0.40);
    @define-color fullscreen_ch_list_entry_text rgba(255, 255, 255, 0.85);
    @define-color fullscreen_ch_list_entry_image rgba(255, 255, 255, 0.85);
    @define-color fullscreen_ch_list_button rgba(255, 255, 255, 0.85);
    @define-color fullscreen_slider_highlight rgba(255, 255, 255, 0.50);
    @define-color fullscreen_slider_color rgba(255, 255, 255, 0.99);
    @define-color fullscreen_slider_fill rgba(255, 255, 255, 0.40);
    @define-color splash_content_grad_top alpha(#39204F, 0.60);
    @define-color splash_content_grad_bot alpha(#190A26, 0.80);
    @define-color splash_content_border #D4A9FC; 
    @define-color splash-title rgba(255, 255, 255, 0.85);
    @define-color splash-status rgba(255, 255, 255, 0.85);
    @define-color splash_content_spinner rgba(255, 255, 255, 0.85);
    @define-color flat-button #C6DDBD;
    @define-color profile_window_border #88AA88;
    filechooser .view image,
    filechooser .sidebar image,
    .filechooser image {
        filter: sepia(100%) saturate(0.6) hue-rotate(-180deg);
        opacity: 0.9;
    }
    """

    MIST_CSS = """
    @define-color window_bg_color #C6DDBD;
    @define-color window_fg_color #000000;
    @define-color view_bg_color #C6DDBD;
    @define-color view_fg_color #000000;
    @define-color headerbar_bg_color #C6DDBD;
    @define-color headerbar_fg_color #000000;
    @define-color popover_bg_color #C6DDBD;
    @define-color popover_fg_color #000000;
    @define-color card_bg_color #DDF6D2; 
    @define-color card_fg_color #000000;  
    @define-color accent_color #4F9032;
    @define-color accent_bg_color #4F9032;
    @define-color accent_fg_color #C6DDBD;   
    @define-color border_color rgba(0, 0, 0, 0.40);
    @define-color border_pop_up_color rgba(0, 0, 0, 0.40);  
    @define-color nav_rail_bg transparent;
    @define-color nav_button_bg #C6DDBD;
    @define-color nav_button_border transparent;
    @define-color nav_button_hover_bg #9AAC93;
    @define-color nav_button_hover_box_shadow #000000;   
    @define-color player_bg_color #C6DDBD;
    @define-color player_box_shadow #000000;
    @define-color player_controls_border_color rgba(255, 255, 255, 0.40);   
    @define-color epg_bg_color #C6DDBD;   
    @define-color epg_box_shadow #000000;
    @define-color epg_panel_border_color rgba(255, 255, 255, 0.40);  
    @define-color osd_btn_grad_top rgba(255, 255, 255, 0.50); 
    @define-color osd_btn_grad_bot rgba(0, 0, 0, 0.60); 
    @define-color osd_btn_shadow #000000;  
    @define-color settings-popover_hover_box_shadow #000000;     
    @define-color settings_popover_row_bg rgba(117, 130, 112, 0.50);
    @define-color settings_popover_row_hover_bg rgba(164, 179, 159, 0.55);     
    @define-color settings_popover_row_switch_bg #839C79;
    @define-color settings_popover_row_switch_slider_bg #4F9032;
    @define-color settings_popover_row_switch_checked_bg #FFFFFF;
    @define-color settings_popover_row_switch_checked_slider_bg #4F9032;   
    @define-color box_fullscreen_controls_popover_grad_top alpha(#9aac93, 0.90);
    @define-color box_fullscreen_controls_popover_grad_bot alpha(#42493F, 0.98);
    @define-color fullscreen_border_color #4BBD4B;      
    @define-color fullscreen_bg_top alpha(#9aac93, 0.90); 
    @define-color fullscreen_bg_bot alpha(#42493F, 0.98);
    @define-color fullscreen_fg_color rgba(255, 255, 255, 0.90);    
    @define-color fullscreen_btn_grad_top rgba(255, 255, 255, 0.40); 
    @define-color fullscreen_btn_grad_bot rgba(0, 0, 0, 0.1);
    @define-color fullscreen_border_color #4BBD4B;    
    @define-color fullscreen_ch_list_grad_top alpha(#9aac93, 0.90);
    @define-color fullscreen_ch_list_grad_bot alpha(#42493F, 0.98);
    @define-color fullscreen_ch_border_color #4BBD4B;  
    @define-color fullscreen_ch_list_row alpha(#42493F, 0.90);
    @define-color fullscreen_ch_hover alpha(#42493F, 0.70);
    @define-color fullscreen_ch_bg transparent;
    @define-color fullscreen_ch_entry alpha(#42493F, 0.50);
    @define-color fullscreen_ch_entry_border #88AA88;   
    @define-color fullscreen_ch_list_label rgba(255, 255, 255, 0.90);
    @define-color fullscreen_ch_list_row_sel_label rgba(255, 255, 255, 0.90);
    @define-color fullscreen_ch_list_row_label rgba(255, 255, 255, 0.90);   
    @define-color fullscreen_epg_bar_fill rgba(0, 0, 0, 0.90);
    @define-color fullscreen_epg_bar_bg rgba(255, 255, 255, 0.5);
    @define-color fullscreen_ch_list_entry_text rgba(255, 255, 255, 0.85);
    @define-color fullscreen_ch_list_entry_image rgba(255, 255, 255, 0.85);
    @define-color fullscreen_ch_list_button rgba(255, 255, 255, 0.85);
    @define-color fullscreen_slider_highlight #67B346;
    @define-color fullscreen_slider_color #67B346;
    @define-color fullscreen_slider_fill rgba(0, 0, 0, 0.5);
    @define-color splash_content_grad_top alpha(#9aac93, 0.80);
    @define-color splash_content_grad_bot alpha(#42493F, 0.95);
    @define-color splash_content_border #88AA88;
    @define-color splash-title rgba(255, 255, 255, 0.85);
    @define-color splash-status rgba(255, 255, 255, 0.85);
    @define-color splash_content_spinner rgba(255, 255, 255, 0.85);
    @define-color flat-button #C6DDBD;
    @define-color profile_window_border #88AA88;
    filechooser .view image,
    filechooser .sidebar image,
    .filechooser image {
        filter: sepia(100%) saturate(0.6) hue-rotate(-280deg);
        opacity: 0.9;
    }
    """

    DEEP_ABYSS_CSS = """
    @define-color window_bg_color #200263;
    @define-color window_fg_color #ffffff;
    @define-color view_bg_color transparent;
    @define-color view_fg_color #ffffff;
    @define-color headerbar_bg_color #200263;
    @define-color headerbar_fg_color #ffffff;
    @define-color popover_bg_color #200263;
    @define-color popover_fg_color #ffffff;
    @define-color card_bg_color #200263;
    @define-color card_fg_color #ffffff;    
    @define-color accent_color #9267F5;
    @define-color accent_bg_color #9267F5;
    @define-color accent_fg_color #FFFFFF;    
    @define-color border_color #9267F5;
    @define-color border_pop_up_color #9267F5;
    window {
        background-image: radial-gradient(
            circle at center, 
            #4A2B99 0%,  
            #200263 55%,  
            #0B0124 100%  
        );
    }   
    window.splash, 
    window.splash-window,
   .splash-window {
       background-color: transparent;
       background-image: none;	
       box-shadow: none;
    } 
    window.popup,
    window.dialog,
    window.messagedialog,
    popover,
    .scheduler-window,
    .equalizer-window,
    .media-info-dialog,
    .global-search-dialog,
    .stream-info-dialog {
        background-image: none;
    } 
    @define-color nav_rail_bg transparent;
    @define-color nav_button_bg transparent;
    @define-color nav_button_border #9267F5;
    @define-color nav_button_hover_bg rgba(60, 2, 233, 0.15);
    @define-color nav_button_hover_box_shadow #000000;   
    @define-color player_bg_color transparent; 
    @define-color player_box_shadow rgba(60, 42, 102, 0.95); 
    @define-color player_controls_border_color rgba(255, 255, 255, 0.20);    
    @define-color epg_bg_color transparent;   
    @define-color epg_box_shadow rgba(60, 42, 102, 0.90); 
    @define-color epg_panel_border_color rgba(255, 255, 255, 0.20);      
    @define-color osd_btn_grad_top rgba(128, 111, 166, 0.80); 
    @define-color osd_btn_grad_bot rgba(0, 0, 0, 0.40); 
    @define-color osd_btn_shadow #000000;     
    @define-color settings-popover_hover_box_shadow #000000;     
    @define-color settings_popover_row_bg rgba(108, 60, 214, 0.60);
    @define-color settings_popover_row_hover_bg rgba(134, 99, 212, 0.95);      
    @define-color settings_popover_row_switch_bg #7337FA;
    @define-color settings_popover_row_switch_slider_bg #FFFFFF;
    @define-color settings_popover_row_switch_checked_bg #FFFFFF;
    @define-color settings_popover_row_switch_checked_slider_bg #7337FA;   
    @define-color box_fullscreen_controls_popover_grad_top alpha(#200263, 0.60);
    @define-color box_fullscreen_controls_popover_grad_bot alpha(#09001F, 0.90);         
    @define-color fullscreen_bg_top alpha(#200263, 0.60); 
    @define-color fullscreen_bg_bot alpha(#09001F, 0.90);   
    @define-color fullscreen_fg_color #D8DEE9;   
    @define-color fullscreen_btn_grad_top rgba(128, 111, 166, 0.80);
    @define-color fullscreen_btn_grad_bot rgba(0, 0, 0, 0.40);    
    @define-color fullscreen_border_color #9267F5;  
    @define-color fullscreen_ch_list_grad_top alpha(#200263, 0.60);
    @define-color fullscreen_ch_list_grad_bot alpha(#09001F, 0.90);    
    @define-color fullscreen_ch_border_color #9267F5;  
    @define-color fullscreen_ch_list_row_bg transparent;   
    @define-color fullscreen_ch_list_row rgba(146, 103, 245, 0.40);
    @define-color fullscreen_ch_hover rgba(146, 103, 245, 0.40);      
    @define-color fullscreen_ch_bg transparent;   
    @define-color fullscreen_ch_entry rgba(3, 18, 48, 0.20);
    @define-color fullscreen_ch_entry_border alpha(#9267F5, 0.90);   
    @define-color fullscreen_ch_list_label #FFFFFF;
    @define-color fullscreen_ch_list_row_sel_label #FFFFFF;
    @define-color fullscreen_ch_list_row_label #FFFFFF;   
    @define-color fullscreen_epg_bar_fill rgba(216, 222, 233, 0.70);
    @define-color fullscreen_epg_bar_bg rgba(129, 161, 193, 0.50);      
    @define-color fullscreen_ch_list_entry_text #FFFFFF;
    @define-color fullscreen_ch_list_entry_image #FFFFFF;
    @define-color fullscreen_ch_list_button #FFFFFF;   
    @define-color fullscreen_slider_highlight #926DE8;
    @define-color fullscreen_slider_color #5C36B3;
    @define-color fullscreen_slider_fill rgba(255, 255, 255, 0.25);   
    @define-color splash_content_grad_top alpha(#200263, 0.60);
    @define-color splash_content_grad_bot alpha(#09001F, 0.90); 
    @define-color splash_content_border #9267F5; 
    @define-color splash-title #FFFFFF;
    @define-color splash-status #FFFFFF;
    @define-color splash_content_spinner #FFFFFF;
    @define-color flat-button #FFFFFF;
    @define-color profile_window_border #9267F5;
    filechooser .view image,
    filechooser .sidebar image,
    .filechooser image {
        filter: sepia(100%) saturate(1.5) hue-rotate(190deg);
        opacity: 0.9;
    }
    """

    LATTE_CSS = """
    @define-color window_bg_color #D6C0B3;
    @define-color window_fg_color #000000;
    @define-color view_bg_color #D6C0B3;
    @define-color view_fg_color #000000;
    @define-color headerbar_bg_color #D6C0B3;
    @define-color headerbar_fg_color #000000;
    @define-color popover_bg_color  #D6C0B3;
    @define-color popover_fg_color #000000;
    @define-color card_bg_color #D6C0B3;
    @define-color card_fg_color #000000;  
    @define-color accent_color #403935;
    @define-color accent_bg_color #403935;
    @define-color accent_fg_color #D6C0B3;
    @define-color border_color rgba(64, 57, 53, 0.70);
    @define-color border_pop_up_color rgba(64, 57, 53, 0.70);   
    @define-color nav_rail_bg transparent;
    @define-color nav_button_bg #D6C0B3; 
    @define-color nav_button_border transparent;
    @define-color nav_button_hover_bg #C0ACA1;
    @define-color nav_button_hover_box_shadow #393330;    
    @define-color player_bg_color #D6C0B3;
    @define-color player_box_shadow #000000;
    @define-color player_controls_border_color rgba(255, 255, 255, 0.20);   
    @define-color epg_bg_color #D6C0B3;   
    @define-color epg_box_shadow #000000;
    @define-color epg_panel_border_color rgba(255, 255, 255, 0.20);   
    @define-color osd_btn_grad_top rgba(255, 255, 255, 0.50); 
    @define-color osd_btn_grad_bot rgba(0, 0, 0, 0.60); 
    @define-color osd_btn_shadow #393330;   
    @define-color settings-popover_hover_box_shadow #393330;     
    @define-color settings_popover_row_bg rgba(148, 132, 123, 0.60);
    @define-color settings_popover_row_hover_bg rgba(240, 228, 221, 0.25);    
    @define-color settings_popover_row_switch_bg #877063;
    @define-color settings_popover_row_switch_slider_bg #B89A88;
    @define-color settings_popover_row_switch_checked_bg #FFFFFF;
    @define-color settings_popover_row_switch_checked_slider_bg #B89A88;   
    @define-color box_fullscreen_controls_popover_grad_top alpha(#D6C0B3, 0.95); 
    @define-color box_fullscreen_controls_popover_grad_bot alpha(#3E2723, 0.75);
    @define-color fullscreen_border_color rgba(117, 58, 22, 0.95);       
    @define-color fullscreen_bg_top alpha(#D6C0B3, 0.95); 
    @define-color fullscreen_bg_bot alpha(#3E2723, 0.75);
    @define-color fullscreen_fg_color rgba(255, 255, 255, 0.95);    
    @define-color fullscreen_btn_grad_top rgba(255, 255, 255, 0.40); 
    @define-color fullscreen_btn_grad_bot rgba(0, 0, 0, 0.1);   
    @define-color fullscreen_border_color rgba(117, 58, 22, 0.95);       
    @define-color fullscreen_ch_list_grad_top alpha(#D6C0B3, 0.95);
    @define-color fullscreen_ch_list_grad_bot alpha(#3E2723, 0.75);
    @define-color fullscreen_ch_border_color rgba(117, 58, 22, 0.95);   
    @define-color fullscreen_ch_list_row alpha(#3E2723, 0.50);
    @define-color fullscreen_ch_hover alpha(#3E2723, 0.50);
    @define-color fullscreen_ch_bg #AB998F;
    @define-color fullscreen_ch_entry alpha(#3E2723, 0.30);
    @define-color fullscreen_ch_entry_border #AB998F;
    @define-color fullscreen_ch_list_label rgba(255, 255, 255, 0.95);
    @define-color fullscreen_ch_list_row_sel_label rgba(255, 255, 255, 0.95);
    @define-color fullscreen_ch_list_row_label rgba(255, 255, 255, 0.95);
    @define-color fullscreen_epg_bar_fill #403935;
    @define-color fullscreen_epg_bar_bg rgba(255, 255, 255, 0.25);
    @define-color fullscreen_ch_list_entry_text rgba(255, 255, 255, 0.95);
    @define-color fullscreen_ch_list_entry_image rgba(255, 255, 255, 0.95);
    @define-color fullscreen_ch_list_button rgba(255, 255, 255, 0.95);
    @define-color fullscreen_slider_highlight #AB998F;
    @define-color fullscreen_slider_color #AB998F;
    @define-color fullscreen_slider_fill rgba(0, 0, 0, 0.5);
    @define-color splash_content_grad_top alpha(#D6C0B3, 0.90);
    @define-color splash_content_grad_bot alpha(#393330, 0.95);
    @define-color splash_content_border #AB998F;
    @define-color splash-title #FFFFFF;
    @define-color splash-status #FFFFFF;
    @define-color splash_content_spinner #FFFFFF;
    @define-color flat-button #AB998F;
    filechooser .view image,
    filechooser .sidebar image,
    .filechooser image {
        filter: sepia(100%) saturate(0.5) hue-rotate(-390deg);
        opacity: 0.9;
    }
    """

    NIGHT_OCEAN_CSS = """
    @define-color window_bg_color #215E61;
    @define-color window_fg_color #FFFFFF;
    @define-color view_bg_color transparent;
    @define-color view_fg_color #FFFFFF;
    @define-color headerbar_bg_color #215E61;
    @define-color headerbar_fg_color #FFFFFF;
    @define-color popover_bg_color #215E61;
    @define-color popover_fg_color #FFFFFF;
    
    @define-color card_bg_color #215E61;
    
    @define-color card_fg_color #FFFFFF;
    window {
        background-image: radial-gradient(
            circle at center, 
            #0C7779 0%,  
            #215E61 50%,  
            #013740 100% 
        );
    }   
    window.splash, 
    window.splash-window,
   .splash-window {
       background-color: transparent;
       background-image: none;	
       box-shadow: none;
    } 
    window.popup,
    window.dialog,
    window.messagedialog,
    popover,
    .scheduler-window,
    .equalizer-window,
    .media-info-dialog,
    .global-search-dialog,
    .stream-info-dialog {
        background-image: none;
    } 
    @define-color accent_color rgba(6, 180, 189, 0.50);
    @define-color accent_bg_color rgba(216, 222, 233, 0.20);
    
    @define-color accent_fg_color #FFFFFF;  
          
    @define-color border_color alpha(#71C5C9, 0.85);
    @define-color border_pop_up_color alpha(#71C5C9, 0.85);   
    @define-color nav_rail_bg transparent;
    @define-color nav_button_bg #0A5A5E;
    @define-color nav_button_border rgba(113, 197, 201, 0.90);
    @define-color nav_button_hover_bg transparent;
    @define-color nav_button_hover_box_shadow #000000;  
    @define-color player_bg_color transparent; 
    @define-color player_box_shadow #000000;
    @define-color player_controls_border_color rgba(255, 255, 255, 0.20);   
    @define-color epg_bg_color transparent;   
    @define-color epg_box_shadow #000000; 
    @define-color epg_panel_border_color rgba(255, 255, 255, 0.20);       
    @define-color osd_btn_grad_top rgba(44, 148, 153, 0.90); 
    @define-color osd_btn_grad_bot rgba(0, 0, 0, 0.60); 
    @define-color osd_btn_shadow #000000;     
    @define-color settings_popover_row_bg rgba(1, 55, 64, 0.50);
    @define-color settings_popover_row_hover_bg rgba(1, 55, 64, 0.80);    
    @define-color settings-popover_hover_box_shadow #000000;   
    @define-color settings_popover_row_switch_bg #4A878A;
    @define-color settings_popover_row_switch_slider_bg #174C4F;
    @define-color settings_popover_row_switch_checked_bg #FFFFFF;
    @define-color settings_popover_row_switch_checked_slider_bg #174C4F;   
    @define-color box_fullscreen_controls_popover_grad_top alpha(#215E61, 0.80);  
    @define-color box_fullscreen_controls_popover_grad_bot alpha(#003033, 0.95);
    @define-color fullscreen_border_color alpha(#10D4DE, 0.90);            
    @define-color fullscreen_bg_top alpha(#215E61, 0.80); 
    @define-color fullscreen_bg_bot alpha(#003033, 0.95);   
    @define-color fullscreen_fg_color alpha(#FFFFFF, 0.65);       
    @define-color fullscreen_btn_grad_top rgba(44, 148, 153, 0.90); 
    @define-color fullscreen_btn_grad_bot rgba(0, 0, 0, 0.40);    
    @define-color fullscreen_border_color alpha(#10D4DE, 0.90);    
    @define-color fullscreen_ch_list_grad_top alpha(#215E61, 0.80); 
    @define-color fullscreen_ch_list_grad_bot alpha(#003033, 0.95);    
    @define-color fullscreen_ch_border_color alpha(#10D4DE, 0.90); 
    @define-color fullscreen_ch_list_row_bg transparent;   
    @define-color fullscreen_ch_list_row rgba(0, 19, 20, 0.50);
    @define-color fullscreen_ch_hover rgba(0, 19, 20, 0.50); 
    @define-color fullscreen_ch_bg transparent;   
    @define-color fullscreen_ch_entry alpha(#215E61, 0.60); 
    @define-color fullscreen_ch_entry_border alpha(#10D4DE, 0.90);    
    @define-color fullscreen_ch_list_label alpha(#FFFFFF, 0.75); 
    @define-color fullscreen_ch_list_row_sel_label alpha(#FFFFFF, 0.75);
    @define-color fullscreen_ch_list_row_label alpha(#FFFFFF, 0.75);   
    @define-color fullscreen_epg_bar_fill rgba(216, 222, 233, 0.70);
    @define-color fullscreen_epg_bar_bg rgba(129, 161, 193, 0.50);      
    @define-color fullscreen_ch_list_entry_text alpha(#FFFFFF, 0.75);
    @define-color fullscreen_ch_list_entry_image alpha(#FFFFFF, 0.75);
    @define-color fullscreen_ch_list_button alpha(#FFFFFF, 0.75);    
    @define-color fullscreen_slider_highlight alpha(#10D4DE, 0.90);
    @define-color fullscreen_slider_color alpha(#10D4DE, 0.90);
    @define-color fullscreen_slider_fill rgba(255, 255, 255, 0.35);   
    @define-color splash_content_grad_top alpha(#215E61, 0.80);
    @define-color splash_content_grad_bot alpha(#003033, 0.95); 
    @define-color splash_content_border alpha(#10D4DE, 0.90);
    @define-color splash-title alpha(#FFFFFF, 0.75);
    @define-color splash-status alpha(#FFFFFF, 0.75);
    @define-color splash_content_spinner alpha(#FFFFFF, 0.95);
    @define-color flat-button alpha(#FFFFFF, 0.75);
    @define-color profile_window_border alpha(#10D4DE, 0.90);
    filechooser .view image,
    filechooser .sidebar image,
    .filechooser image {
        filter: sepia(100%) saturate(0.5) hue-rotate(150deg);
        opacity: 0.9;
    }
    """

    @classmethod
    def apply_theme(cls, theme_name):
        display = Gdk.Display.get_default()
        style_manager = Adw.StyleManager.get_default()
        if theme_name == "default":
            theme_name = "deep_abyss"
        if theme_name in ["mist", "latte", "force_light"]:
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)           
        elif theme_name in ["night_ocean", "nord", "nebula", "deep_abyss", "force_dark"]:
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)          
        else:
            style_manager.set_color_scheme(Adw.ColorScheme.DEFAULT)
        css_data = None
        if theme_name == "force_light":
            css_data = cls.LIGHT_CSS
        elif theme_name == "force_dark":
            css_data = cls.DARK_CSS
        elif theme_name == "nord":
            css_data = cls.NORD_CSS
        elif theme_name == "nebula":
            css_data = cls.NEBULA_CSS
        elif theme_name == "mist":
            css_data = cls.MIST_CSS
        elif theme_name == "deep_abyss":
            css_data = cls.DEEP_ABYSS_CSS
        elif theme_name == "latte":
            css_data = cls.LATTE_CSS
        elif theme_name == "night_ocean":
            css_data = cls.NIGHT_OCEAN_CSS 
        else:
            css_data = cls.DEFAULT_CSS
        if css_data:
            provider = Gtk.CssProvider()
            try:
                provider.load_from_data(css_data.encode())
                Gtk.StyleContext.add_provider_for_display(
                    display,
                    provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_USER
                )
            except Exception as e:
                logging.error(f"Failed to apply theme CSS: {e}")

    @staticmethod
    def get_icon_folder(theme_name):
        if not theme_name or theme_name == "default":
            theme_name = "deep_abyss"          
        if theme_name in ["force_light", "mist", "latte"]:
            return "light"
        else:
            return "dark"
