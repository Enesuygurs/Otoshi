import json
import os
from typing import Any, Dict
from .utils.logger import logger

CONFIG_FILE = "otoshi_config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "record_hotkey": "f2",
    "play_hotkey": "f3",
    "playback_speed": 1.0,
    "macro_loop_count": 1,
    "ac_hotkey": "f4",
    "ac_interval_ms": 1000,
    "ac_button": "Left",
    "ac_type": "Single",
    "ac_click_times": 0,
    "ac_loc_type": "Current",
    "ac_loc_x": 0,
    "ac_loc_y": 0,
    "show_overlay": False,
    "close_to_tray": False
}

def load_config() -> Dict[str, Any]:
    """
    Loads the configuration from the JSON file. 
    If the file doesn't exist or is invalid, returns the default configuration.
    """
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                # Merge with defaults to ensure all keys exist and handle new updates
                return {**DEFAULT_CONFIG, **data}
        except (json.JSONDecodeError, IOError):
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()

def save_config(config_data: Dict[str, Any]) -> None:
    """
    Saves the provided configuration data to the JSON file.
    """
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config_data, f, indent=4)
    except IOError as e:
        logger.error(f"Failed to save configuration: {e}")
