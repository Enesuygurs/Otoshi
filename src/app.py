import customtkinter as ctk
import keyboard
import time
import threading
import pystray
from PIL import Image, ImageDraw
import ctypes
from tkinter import filedialog, messagebox
from .config import load_config, save_config
from .logic import MacroEngine, AutoClickerEngine
from .utils.logger import logger

# Theme Configuration
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

# Windows API Constants for click-through windows
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

# UI Mappings (Identity mappings for consistency or future i18n)
BUTTON_MAP = {"Left": "Left", "Right": "Right", "Middle": "Middle"}
BUTTON_MAP_INV = {v: k for k, v in BUTTON_MAP.items()}

CLICK_TYPE_MAP = {"Single": "Single", "Double": "Double"}
CLICK_TYPE_MAP_INV = {v: k for k, v in CLICK_TYPE_MAP.items()}

LOC_TYPE_MAP = {"Current": "Current", "Fixed": "Fixed"}
LOC_TYPE_MAP_INV = {v: k for k, v in LOC_TYPE_MAP.items()}

class StatusOverlay(ctk.CTkToplevel):
    """
    A small, non-intrusive overlay window that displays the current application status.
    Designed to be always-on-top and click-through.
    """
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Otoshi Overlay")
        self.geometry("120x32+20+20")  # Top-left corner position
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.85)
        self.attributes("-toolwindow", True)  # Hide from taskbar
        
        self.configure(fg_color="#09090B")
        
        self.label = ctk.CTkLabel(
            self, 
            text="● READY", 
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), 
            text_color="#F59E0B"
        )
        self.label.pack(expand=True, fill="both")
        
        self.make_click_through()

    def make_click_through(self):
        """Makes the window ignore all mouse events on Windows."""
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT)
        except Exception:
            pass

    def update_status(self, text, color):
        """Updates the status text and its color in the overlay."""
        self.label.configure(text=f"● {text.upper()}", text_color=color)

import sys
import os

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class OtoshiApp(ctk.CTk):
    """
    The main application class for Otoshi. 
    Handles the GUI, configuration synchronization, and orchestration of engines.
    """
    def __init__(self):
        super().__init__()

        self.title("Otoshi")
        
        # Set window icon
        try:
            icon_path = get_resource_path("icon.ico")
            self.iconbitmap(icon_path)
            self.wm_iconbitmap(icon_path)
        except Exception as e:
            logger.error(f"Failed to load icon: {e}")
        self.geometry("420x540")
        self.resizable(False, False)
        self.configure(fg_color="#09090B") # Industrial Deep Dark
        
        try:
            self.attributes("-alpha", 0.98)
        except Exception:
            pass
            
        self.macro_engine = MacroEngine()
        self.ac_engine = AutoClickerEngine()
        
        # Initialize configuration
        self.config = load_config()
        self.apply_config_to_vars()
        
        self.setup_hotkeys()
        self.setup_ui()
        
        # Deferred initialization for background components to improve startup snappiness
        self.after(200, self.setup_background_components)
        logger.info("Otoshi application initialized.")

    def setup_background_components(self):
        """Initializes components that don't need to be immediate, improving initial UI response."""
        # Initialize Overlay
        self.overlay = StatusOverlay(self)
        if not self.show_overlay_cfg:
            self.overlay.withdraw()
            
        # System Tray & Events
        self.protocol("WM_DELETE_WINDOW", self.on_close_event)
        self.bind("<Unmap>", self.on_minimize)
        self.create_tray_icon()

    def apply_config_to_vars(self):
        """Syncs the loaded config dictionary to local application variables."""
        self.record_hotkey = self.config.get("record_hotkey", "f2")
        self.play_hotkey = self.config.get("play_hotkey", "f3")
        self.macro_engine.playback_speed = self.config.get("playback_speed", 1.0)
        self.macro_loop_count = self.config.get("macro_loop_count", 1)
        
        self.ac_hotkey = self.config.get("ac_hotkey", "f4")
        self.ac_interval_ms = self.config.get("ac_interval_ms", 1000)
        
        # Use logical defaults and mappings
        self.ac_button = self.config.get("ac_button", "Left")
        self.ac_type = self.config.get("ac_type", "Single")
        self.ac_click_times = self.config.get("ac_click_times", 0)
        self.ac_loc_type = self.config.get("ac_loc_type", "Current")
        
        self.ac_loc_x = self.config.get("ac_loc_x", 0)
        self.ac_loc_y = self.config.get("ac_loc_y", 0)
        self.show_overlay_cfg = self.config.get("show_overlay", True)
        self.close_to_tray_cfg = self.config.get("close_to_tray", True)

    def update_config_from_vars(self):
        """Syncs local variables back to the config dictionary and persists it."""
        self.config.update({
            "record_hotkey": self.record_hotkey,
            "play_hotkey": self.play_hotkey,
            "playback_speed": self.macro_engine.playback_speed,
            "macro_loop_count": self.macro_loop_count,
            "ac_hotkey": self.ac_hotkey,
            "ac_interval_ms": self.ac_interval_ms,
            "ac_button": self.ac_button,
            "ac_type": self.ac_type,
            "ac_click_times": self.ac_click_times,
            "ac_loc_type": self.ac_loc_type,
            "ac_loc_x": self.ac_loc_x,
            "ac_loc_y": self.ac_loc_y,
            "show_overlay": self.show_overlay_cfg,
            "close_to_tray": self.close_to_tray_cfg
        })
        save_config(self.config)

    def setup_hotkeys(self):
        """Registers global hotkeys using the keyboard module."""
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        keyboard.add_hotkey(self.record_hotkey, self.toggle_recording)
        keyboard.add_hotkey(self.play_hotkey, self.toggle_playing)
        keyboard.add_hotkey(self.ac_hotkey, self.toggle_auto_clicker)

    def setup_ui(self):
        """Main UI assembly."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # 1. Header Section
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=30, pady=(15, 10))
        self.header_frame.grid_columnconfigure(1, weight=1)
        
        self.title_label = ctk.CTkLabel(
            self.header_frame, text="OTOSHI", 
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold")
        )
        self.title_label.grid(row=0, column=0, sticky="w")
        
        self.status_pill = ctk.CTkFrame(self.header_frame, corner_radius=0, fg_color="transparent")
        self.status_pill.grid(row=0, column=1, sticky="e")
        
        self.status_dot = ctk.CTkLabel(
            self.status_pill, text="●", text_color="#F59E0B", 
            font=ctk.CTkFont(family="Segoe UI", size=12)
        )
        self.status_dot.pack(side="left", padx=(10, 4), pady=2)
        
        self.status_label = ctk.CTkLabel(
            self.status_pill, text="READY", 
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), 
            text_color="#F59E0B"
        )
        self.status_label.pack(side="left", padx=(0, 10), pady=2)

        # 2. Navigation
        self.nav_frame = ctk.CTkFrame(self, fg_color="#09090B", corner_radius=0, height=45)
        self.nav_frame.grid(row=1, column=0, sticky="ew", padx=30, pady=(0, 20))
        self.nav_frame.grid_propagate(False)
        
        self.seg_nav = ctk.CTkSegmentedButton(
            self.nav_frame, values=["Macro", "Auto Clicker", "Settings"],
            command=self.on_nav_change,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            height=38, corner_radius=0,
            fg_color="#09090B",
            selected_color="#18181B",
            selected_hover_color="#27272A",
            unselected_color="#09090B",
            unselected_hover_color="#18181B",
            text_color="#A1A1AA"
        )
        self.seg_nav.pack(fill="both", expand=True, padx=4, pady=4)
        self.seg_nav.set("Macro")

        # 3. Content Area
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.grid(row=2, column=0, sticky="nsew", padx=30, pady=(0, 25))
        self.container.grid_columnconfigure(0, weight=1)
        self.container.grid_rowconfigure(0, weight=1)

        self.frames = {}
        for name in ["Macro", "Auto Clicker", "Settings"]:
            f = ctk.CTkFrame(self.container, fg_color="#18181B", corner_radius=0)
            self.frames[name] = f
            f.grid(row=0, column=0, sticky="nsew")
            
        self.setup_macro_ui()
        self.setup_clicker_ui()
        self.setup_settings_ui()
        
        self.show_frame("Macro")

    def show_frame(self, name):
        """Raises the selected frame to the top."""
        frame = self.frames[name]
        frame.tkraise()

    def on_nav_change(self, value):
        """Handles tab switching."""
        self.show_frame(value)

    def setup_macro_ui(self):
        """Assembles the Macro tab UI."""
        f = self.frames["Macro"]
        f.grid_columnconfigure(0, weight=1)
        
        action_frame = ctk.CTkFrame(f, fg_color="transparent")
        action_frame.pack(fill="x", padx=20, pady=(20, 15))

        self.record_btn = ctk.CTkButton(
            action_frame, text=f"RECORD ({self.record_hotkey.upper()})", command=self.toggle_recording,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            height=42, corner_radius=0, fg_color="#E11D48", text_color="white", hover_color="#BE123C"
        )
        self.record_btn.pack(fill="x", pady=(0, 10))

        self.play_btn = ctk.CTkButton(
            action_frame, text=f"PLAY ({self.play_hotkey.upper()})", command=self.toggle_playing,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            height=42, corner_radius=0, fg_color="#059669", text_color="white", 
            hover_color="#047857", state="disabled"
        )
        self.play_btn.pack(fill="x")

        controls_panel = ctk.CTkFrame(f, fg_color="#18181B", corner_radius=0)
        controls_panel.pack(fill="x", padx=20, pady=(0, 20))

        btn_row = ctk.CTkFrame(controls_panel, fg_color="transparent")
        btn_row.pack(fill="x", padx=15, pady=(15, 10))
        btn_row.grid_columnconfigure((0, 1), weight=1)

        self.btn_save = ctk.CTkButton(
            btn_row, text="SAVE", command=self.save_macro_to_file,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            height=32, corner_radius=0, fg_color="#27272A", hover_color="#3F3F46"
        )
        self.btn_save.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.btn_load = ctk.CTkButton(
            btn_row, text="LOAD", command=self.load_macro_from_file,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            height=32, corner_radius=0, fg_color="#27272A", hover_color="#3F3F46"
        )
        self.btn_load.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        loop_row = ctk.CTkFrame(controls_panel, fg_color="transparent")
        loop_row.pack(fill="x", padx=15, pady=(0, 15))
        
        ctk.CTkLabel(
            loop_row, text="REPEAT COUNT (0=∞):", 
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), 
            text_color="#A1A1AA"
        ).pack(side="left")
        
        self.loop_entry = ctk.CTkEntry(
            loop_row, width=80, height=28, 
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), 
            corner_radius=0, border_width=0
        )
        self.loop_entry.insert(0, str(self.macro_loop_count))
        self.loop_entry.pack(side="right")

    def setup_clicker_ui(self):
        """Assembles the Auto Clicker tab UI."""
        f = self.frames["Auto Clicker"]
        container = ctk.CTkFrame(f, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=5, pady=15)

        def add_row(label, widget_type, values=None):
            row = ctk.CTkFrame(container, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=8)
            ctk.CTkLabel(
                row, text=label, 
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), 
                text_color="#E1E1E6"
            ).pack(side="left")
            if widget_type == "entry":
                w = ctk.CTkEntry(
                    row, width=110, height=28, 
                    font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), 
                    corner_radius=0, border_width=0
                )
            else:
                w = ctk.CTkOptionMenu(
                    row, values=values, width=110, height=28, 
                    font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                    fg_color="#27272A", button_color="#3F3F46", corner_radius=0
                )
            w.pack(side="right")
            return w

        self.ac_interval_entry = add_row("Interval (ms):", "entry")
        self.ac_interval_entry.insert(0, str(self.ac_interval_ms))

        self.ac_button_opt = add_row("Mouse Button:", "option", ["Left", "Right", "Middle"])
        self.ac_button_opt.set(BUTTON_MAP_INV.get(self.ac_button, "Left"))

        self.ac_type_opt = add_row("Click Type:", "option", ["Single", "Double"])
        self.ac_type_opt.set(CLICK_TYPE_MAP_INV.get(self.ac_type, "Single"))

        self.ac_times_entry = add_row("Repeat (0=∞):", "entry")
        self.ac_times_entry.insert(0, str(self.ac_click_times))

        self.ac_loc_opt = add_row("Location:", "option", ["Current", "Fixed"])
        self.ac_loc_opt.set(LOC_TYPE_MAP_INV.get(self.ac_loc_type, "Current"))
        self.ac_loc_opt.configure(command=self.on_ac_loc_change)

        self.ac_coord_frame = ctk.CTkFrame(container, fg_color="transparent")
        self.ac_x_entry = ctk.CTkEntry(
            self.ac_coord_frame, width=45, height=24, 
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), 
            corner_radius=0, border_width=0
        )
        self.ac_x_entry.insert(0, str(self.ac_loc_x))
        self.ac_x_entry.pack(side="left", padx=2)
        
        self.ac_y_entry = ctk.CTkEntry(
            self.ac_coord_frame, width=45, height=24, 
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), 
            corner_radius=0, border_width=0
        )
        self.ac_y_entry.insert(0, str(self.ac_loc_y))
        self.ac_y_entry.pack(side="left", padx=2)
        
        self.ac_picker_btn = ctk.CTkButton(
            self.ac_coord_frame, text="⌖", width=28, height=24, 
            corner_radius=0, fg_color="#3B82F6", command=self.pick_ac_location
        )
        self.ac_picker_btn.pack(side="left", padx=2)
        
        if self.ac_loc_type == "Fixed":
            self.ac_coord_frame.pack(fill="x", padx=10, pady=2)

        self.ac_toggle_btn = ctk.CTkButton(
            f, text=f"START ({self.ac_hotkey.upper()})", command=self.toggle_auto_clicker,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            height=42, corner_radius=0, fg_color="#4F46E5", text_color="white", hover_color="#4338CA"
        )
        self.ac_toggle_btn.pack(fill="x", padx=20, pady=20)

    def setup_settings_ui(self):
        """Assembles the Settings tab UI."""
        f = self.frames["Settings"]
        container = ctk.CTkFrame(f, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=5, pady=15)

        def add_hk_row(label, target):
            row = ctk.CTkFrame(container, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=8)
            ctk.CTkLabel(
                row, text=label, 
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), 
                text_color="#E1E1E6"
            ).pack(side="left")
            val = getattr(self, f"{target}_hotkey").upper()
            btn = ctk.CTkButton(
                row, text=val, width=100, height=28, 
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                fg_color="#27272A", border_width=0, border_color="#3F3F46", 
                corner_radius=0, command=lambda: self.wait_for_hotkey(target)
            )
            btn.pack(side="right")
            return btn

        self.rec_btn_hk = add_hk_row("Record Hotkey:", "record")
        self.play_btn_hk = add_hk_row("Play Hotkey:", "play")
        self.ac_btn_hk = add_hk_row("Clicker Hotkey:", "ac")

        row_speed = ctk.CTkFrame(container, fg_color="transparent")
        row_speed.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(
            row_speed, text="Playback Speed:", 
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), 
            text_color="#E1E1E6"
        ).pack(side="left")
        self.speed_option = ctk.CTkComboBox(
            row_speed, values=["0.5x", "1.0x", "1.5x", "2.0x", "3.0x", "4.0x", "5.0x", "10.0x", "20.0x"], 
            width=100, height=28, font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="#27272A", button_color="#3F3F46", corner_radius=0
        )
        self.speed_option.set(f"{self.macro_engine.playback_speed}x")
        self.speed_option.pack(side="right")

        row_ov = ctk.CTkFrame(container, fg_color="transparent")
        row_ov.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(
            row_ov, text="On-Screen Overlay:", 
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), 
            text_color="#E1E1E6"
        ).pack(side="left")
        self.ov_switch = ctk.CTkSwitch(row_ov, text="", width=45, progress_color="#2563EB")
        if self.show_overlay_cfg: self.ov_switch.select()
        self.ov_switch.pack(side="right")

        row_ct = ctk.CTkFrame(container, fg_color="transparent")
        row_ct.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(
            row_ct, text="Minimize to Tray on Close:", 
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), 
            text_color="#E1E1E6"
        ).pack(side="left")
        self.ct_switch = ctk.CTkSwitch(row_ct, text="", width=45, progress_color="#2563EB")
        if self.close_to_tray_cfg: self.ct_switch.select()
        self.ct_switch.pack(side="right")

        self.save_cfg_btn = ctk.CTkButton(
            f, text="SAVE SETTINGS", command=self.apply_new_settings,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            height=42, corner_radius=0, fg_color="#2563EB", hover_color="#1D4ED8"
        )
        self.save_cfg_btn.pack(fill="x", padx=20, pady=20)

    def apply_new_settings(self):
        """Validates and applies changes from the Settings tab."""
        new_rec = self.rec_btn_hk.cget("text").strip().lower()
        new_play = self.play_btn_hk.cget("text").strip().lower()
        new_ac = self.ac_btn_hk.cget("text").strip().lower()
        
        if "..." in [new_rec, new_play, new_ac]: return
        if len(set([new_rec, new_play, new_ac])) < 3:
            messagebox.showwarning("Invalid", "Hotkeys cannot be the same!")
            return
            
        self.record_hotkey, self.play_hotkey, self.ac_hotkey = new_rec, new_play, new_ac
        self.show_overlay_cfg = self.ov_switch.get()
        self.close_to_tray_cfg = self.ct_switch.get()
        
        if self.show_overlay_cfg: self.overlay.deiconify()
        else: self.overlay.withdraw()

        try:
            self.macro_engine.playback_speed = float(self.speed_option.get().replace("x", ""))
            self.macro_loop_count = int(self.loop_entry.get())
        except Exception: 
            pass

        self.update_config_from_vars()
        self.setup_hotkeys()
        
        # Sync UI labels
        self.record_btn.configure(text=f"RECORD ({self.record_hotkey.upper()})")
        self.play_btn.configure(text=f"PLAY ({self.play_hotkey.upper()})")
        self.ac_toggle_btn.configure(text=f"START ({self.ac_hotkey.upper()})")
        messagebox.showinfo("Success", "Settings updated!")

    def wait_for_hotkey(self, target):
        """Enters listening mode to capture a new hotkey for the specified target."""
        btns = {"record": self.rec_btn_hk, "play": self.play_btn_hk, "ac": self.ac_btn_hk}
        btn = btns[target]
        btn.configure(text="...")
        def on_key_press(e):
            key = e.keysym.lower()
            btn.configure(text=key.upper())
            self.unbind("<Key>")
        self.bind("<Key>", on_key_press)
        self.focus_set()

    def is_busy(self):
        """Checks if any operation is currently active and returns its name if so."""
        if self.macro_engine.is_recording:
            return "RECORDING"
        if self.macro_engine.is_playing:
            return "PLAYBACK"
        if self.ac_engine.is_running:
            return "CLICKER"
        return None

    def update_status(self, text, color):
        """Updates status indicators in both main window and overlay."""
        self.status_label.configure(text=text.upper(), text_color=color)
        self.status_dot.configure(text_color=color)
        if hasattr(self, 'overlay'):
            self.overlay.update_status(text, color)

    def toggle_recording(self):
        """Starts or stops the macro recording session."""
        self.after(0, self._do_toggle_recording)

    def _do_toggle_recording(self):
        if not self.macro_engine.is_recording:
            if self.is_busy():
                return

            if self.macro_engine.start_recording(self.on_move, self.on_click, self.on_scroll, self.on_press, self.on_release):
                logger.info("Started macro recording.")
                self.update_status("RECORDING", "#EF4444")
                self.play_btn.configure(state="disabled")
                self.record_btn.configure(text="STOP RECORDING", fg_color="#27272A", text_color="white")
        else:
            self.macro_engine.stop_recording()
            logger.info(f"Stopped macro recording. Events captured: {len(self.macro_engine.events)}")
            self.update_status("READY", "#F59E0B")
            self.play_btn.configure(state="normal", fg_color="#059669", text_color="white")
            self.record_btn.configure(text=f"RECORD ({self.record_hotkey.upper()})", fg_color="#E11D48", text_color="white")

    def toggle_playing(self):
        """Starts or stops macro playback."""
        self.after(0, self._do_toggle_playing)

    def _do_toggle_playing(self):
        if not self.macro_engine.is_playing:
            if self.is_busy():
                return

            if not self.macro_engine.events:
                self.update_status("NO MACRO", "#EF4444")
                self.after(2000, lambda: self.update_status("READY", "#F59E0B"))
                return
                
            try:
                self.macro_loop_count = int(self.loop_entry.get())
                self.update_config_from_vars()
            except Exception: 
                pass
            
            self.update_status("RUNNING", "#10B981")
            self.record_btn.configure(state="disabled")
            self.play_btn.configure(text="STOP PLAYBACK", fg_color="#27272A", text_color="white")
            self.macro_engine.play_macro(self.macro_loop_count, self.finish_playing)
        else:
            self.macro_engine.stop_playback()
            self.finish_playing()

    def finish_playing(self):
        """Callback triggered when macro playback ends."""
        self.update_status("READY", "#F59E0B")
        self.record_btn.configure(state="normal")
        self.play_btn.configure(text=f"PLAY ({self.play_hotkey.upper()})", fg_color="#059669", text_color="white")

    # Event recording callbacks
    def on_move(self, x, y): 
        self.macro_engine.events.append({'time': time.time() - self.macro_engine.start_time, 'type': 'move', 'pos': (x, y)})
    
    def on_click(self, x, y, button, pressed): 
        self.macro_engine.events.append({'time': time.time() - self.macro_engine.start_time, 'type': 'click', 'pos': (x, y), 'button': button, 'pressed': pressed})
    
    def on_scroll(self, x, y, dx, dy): 
        self.macro_engine.events.append({'time': time.time() - self.macro_engine.start_time, 'type': 'scroll', 'pos': (x, y), 'dx': dx, 'dy': dy})
    
    def on_press(self, key):
        k = str(key).replace("'", "").replace("Key.", "").lower()
        if k not in [self.record_hotkey.lower(), self.play_hotkey.lower(), self.ac_hotkey.lower()]: 
            self.macro_engine.events.append({'time': time.time() - self.macro_engine.start_time, 'type': 'keypress', 'key': key})
    
    def on_release(self, key):
        k = str(key).replace("'", "").replace("Key.", "").lower()
        if k not in [self.record_hotkey.lower(), self.play_hotkey.lower(), self.ac_hotkey.lower()]: 
            self.macro_engine.events.append({'time': time.time() - self.macro_engine.start_time, 'type': 'keyrelease', 'key': key})

    def toggle_auto_clicker(self): 
        self.after(0, self._do_toggle_auto_clicker)

    def _do_toggle_auto_clicker(self):
        """Toggles the auto-clicker state based on current UI parameters."""
        if not self.ac_engine.is_running:
            if self.is_busy():
                return

            try:
                # Sync UI values to internal English constants
                self.ac_interval_ms = int(self.ac_interval_entry.get())
                self.ac_button = BUTTON_MAP.get(self.ac_button_opt.get(), "Left")
                self.ac_type = CLICK_TYPE_MAP.get(self.ac_type_opt.get(), "Single")
                self.ac_click_times = int(self.ac_times_entry.get())
                self.ac_loc_type = LOC_TYPE_MAP.get(self.ac_loc_opt.get(), "Current")
                
                if self.ac_loc_type == "Fixed": 
                    self.ac_loc_x = int(self.ac_x_entry.get())
                    self.ac_loc_y = int(self.ac_y_entry.get())
                
                self.update_config_from_vars()
            except Exception as e: 
                logger.error(f"Invalid clicker settings: {e}")
                messagebox.showerror("Error", "Invalid values!")
                return
                
            self.ac_engine.start(
                self.ac_interval_ms, self.ac_button, self.ac_type, 
                self.ac_click_times, self.ac_loc_type, self.ac_loc_x, self.ac_loc_y, 
                self.toggle_auto_clicker
            )
            self.ac_toggle_btn.configure(text="STOP", fg_color="#27272A", text_color="white")
            self.update_status("CLICKER ACTIVE", "#8B5CF6")
        else:
            self.ac_engine.stop()
            self.ac_toggle_btn.configure(text=f"START ({self.ac_hotkey.upper()})", fg_color="#4F46E5", text_color="white")
            self.update_status("READY", "#F59E0B")

    def on_ac_loc_change(self, value):
        """Toggles visibility of coordinate entries based on location mode."""
        if LOC_TYPE_MAP.get(value) == "Fixed": 
            self.ac_coord_frame.pack(fill="x", padx=10, pady=2)
        else: 
            self.ac_coord_frame.pack_forget()

    def pick_ac_location(self):
        """Allows user to pick screen coordinates by pressing Space."""
        messagebox.showinfo("Location Picker", "Move mouse to target position and press Space.")
        def wait_space(e):
            if e.keysym == 'space':
                x, y = self.winfo_pointerx(), self.winfo_pointery()
                self.ac_x_entry.delete(0, 'end')
                self.ac_x_entry.insert(0, str(x))
                self.ac_y_entry.delete(0, 'end')
                self.ac_y_entry.insert(0, str(y))
                self.unbind("<Key>")
        self.bind("<Key>", wait_space)
        self.focus_set()

    def save_macro_to_file(self):
        """Opens a file dialog to save recorded macro events."""
        if not self.macro_engine.events: 
            messagebox.showwarning("Warning", "No macro to save.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".otm", filetypes=[("Otoshi Macro", "*.otm")])
        if path: 
            self.macro_engine.save_to_file(path)
            messagebox.showinfo("Success", "Macro saved.")

    def load_macro_from_file(self):
        """Opens a file dialog to load a previously saved macro."""
        path = filedialog.askopenfilename(filetypes=[("Otoshi Macro", "*.otm")])
        if path:
            count = self.macro_engine.load_from_file(path)
            self.update_status(f"LOADED ({count})", "#3B82F6")
            self.play_btn.configure(state="normal", fg_color="#059669", text_color="white")

    # System Tray & Background Execution
    def create_tray_icon(self):
        """Initializes the system tray icon using pystray."""
        # Create a simple icon image
        image = Image.new('RGBA', (64, 64), color=(0, 0, 0, 0))
        d = ImageDraw.Draw(image)
        d.ellipse([10, 10, 54, 54], fill=(225, 29, 72))  # Rose-colored brand circle
        
        menu = pystray.Menu(
            pystray.MenuItem("Show", self.show_window, default=True),
            pystray.MenuItem("Exit", self.quit_app)
        )
        self.icon = pystray.Icon("Otoshi", image, "Otoshi", menu)
        threading.Thread(target=self.icon.run, daemon=True).start()

    def hide_window(self):
        """Hides the main window to the system tray."""
        self.withdraw()
        if hasattr(self, 'overlay') and self.show_overlay_cfg:
            self.overlay.deiconify()
            self.overlay.lift()
        if hasattr(self, 'icon'):
            self.icon.notify("Otoshi is running in the background.", "Information")

    def on_close_event(self):
        """Handles the window close event based on configuration."""
        if self.close_to_tray_cfg:
            self.hide_window()
        else:
            self.quit_app()

    def on_minimize(self, event):
        """Automatically hides to tray on minimization."""
        if self.state() == 'iconic':
            self.hide_window()

    def show_window(self):
        """Restores the window from the tray."""
        self.deiconify()
        if self.show_overlay_cfg:
            self.overlay.deiconify()
        self.lift()
        self.focus_force()

    def quit_app(self):
        """Safely terminates the application."""
        if hasattr(self, 'icon'):
            self.icon.stop()
        self.quit()
        import os
        os._exit(0)
