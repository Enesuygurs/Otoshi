import json

import pytest

from otoshi.config import Settings, int_parser, load_settings, parse_speed, save_settings


def test_defaults_when_missing(tmp_path):
    assert load_settings(tmp_path / "config.json", legacy=[]) == Settings()


def test_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    s = Settings(playback_speed=2.5, ac_button="right", show_overlay=True)
    assert save_settings(s, path)
    assert load_settings(path, legacy=[]) == s


def test_migrates_legacy_config(tmp_path):
    old = tmp_path / "otoshi_config.json"
    old.write_text(
        json.dumps(
            {
                "record_hotkey": "F6",
                "ac_hotkey": "f8",
                "ac_button": "Right",
                "ac_type": "Double",
                "ac_loc_type": "Current",
                "ac_loc_x": 10,
                "ac_loc_y": 20,
                "show_overlay": 1,
                "close_to_tray": 0,
                "playback_speed": 12.0,
                "macro_loop_count": 5,
            }
        )
    )
    new = tmp_path / "config.json"
    s = load_settings(new, legacy=[old])
    assert (s.record_hotkey, s.clicker_hotkey) == ("f6", "f8")
    assert (s.ac_button, s.ac_click_type, s.ac_location) == ("right", "double", "cursor")
    assert (s.ac_x, s.ac_y, s.show_overlay, s.close_to_tray) == (10, 20, True, False)
    assert new.exists()


def test_invalid_values_fall_back_or_clamp():
    s = Settings.from_dict(
        {
            "playback_speed": 0,
            "macro_loop_count": -4,
            "ac_interval_ms": "abc",
            "ac_button": "laser",
            "show_overlay": "yes",
            "overlay_position": "center",
            "record_hotkey": 5,
        }
    )
    assert s.playback_speed == 0.1
    assert s.macro_loop_count == 0
    assert s.ac_interval_ms == Settings().ac_interval_ms
    assert s.ac_button == "left"
    assert s.show_overlay is True
    assert s.overlay_position == "top-left"
    assert s.record_hotkey == "f2"


@pytest.mark.parametrize("content", ["{not json", "[1, 2, 3]"])
def test_corrupt_file_is_backed_up(tmp_path, content):
    path = tmp_path / "config.json"
    path.write_text(content)
    assert load_settings(path, legacy=[]) == Settings()
    if content.startswith("{"):
        assert (tmp_path / "config.json.bad").exists()


def test_parse_speed():
    assert parse_speed("2x") == 2.0
    assert parse_speed(" 1,5 X ") == 1.5
    for bad in ("0", "-1", "abc", "1000", "nan"):
        with pytest.raises(ValueError):
            parse_speed(bad)


def test_int_parser():
    parse = int_parser("Repeat", 0, 10)
    assert parse(" 7 ") == 7
    for bad in ("-1", "11", "1.5", ""):
        with pytest.raises(ValueError):
            parse(bad)
