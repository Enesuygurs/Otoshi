<p align="center">
  <img src="otoshi/assets/icon.png" width="112" alt="Otoshi icon">
</p>

<h1 align="center">Otoshi</h1>

<p align="center">Macro recorder and auto clicker for Windows, built with Python and Qt (PySide6).</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT license">
  <img src="https://img.shields.io/badge/python-3.9%2B-blue.svg" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/platform-Windows-lightgrey.svg" alt="Windows">
</p>

## Features

- **Macro recorder**: captures mouse moves, clicks, scrolling and keyboard input with precise timing, then replays it any number of times (or until stopped) at 0.1x to 100x speed.
- **Auto clicker**: left, right or middle button, single or double clicks, a fixed interval, an optional click limit, at the cursor or at a fixed position chosen with an on-screen picker.
- **Global hotkeys**: registered with the Win32 `RegisterHotKey` API, so they work in the background and even while an administrator window has focus. Any combination can be assigned (e.g. `Ctrl+Shift+F5`). A registered hotkey is reserved for Otoshi while it runs.
- **Safe playback**: stopping a macro releases every key and mouse button it was holding, and the hotkeys themselves never end up inside a recording.
- **Macro files** (`.otm`): plain JSON. Files from Otoshi 1.x are still opened, through a restricted loader that cannot run code.
- **Countdown before playback**: 0 to 60 seconds to switch to the target window; the overlay shows the countdown and the play hotkey cancels it.
- **10 languages**: English, Türkçe, Deutsch, Español, Français, Italiano, Português, Русский, 日本語 and 简体中文. The Windows display language is picked on first start and can be changed live under Settings.
- **Status overlay and tray icon**: a small click-through indicator in any screen corner and a tray icon whose colour follows the current mode.

## Getting started

Requirements: Windows 10/11 and Python 3.9+ (3.11 or newer recommended).

```powershell
git clone https://github.com/Enesuygurs/Otoshi.git
cd Otoshi
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py          # or: python -m otoshi
```

> [!NOTE]
> Windows does not deliver input from elevated (administrator) windows to normal programs. To record or control such windows, run Otoshi as administrator too.

## Usage

| Action | Default hotkey |
| :--- | :---: |
| Start / stop recording | **F2** |
| Start / stop playback | **F3** |
| Start / stop the auto clicker | **F4** |

- Hotkeys can be changed under **Settings**: click one, then press the new combination (Esc cancels).
- Settings are saved automatically to `%APPDATA%\Otoshi\config.json`; logs go to `%APPDATA%\Otoshi\logs`. The **Data folder** button opens that directory. A 1.x `otoshi_config.json` in the working directory is imported on first start.
- Only one Otoshi instance can run at a time, because two instances would both react to every hotkey.

## Building a standalone executable

```powershell
pip install pyinstaller
pyinstaller Otoshi.spec        # -> dist\Otoshi\Otoshi.exe (one-folder build, keep the folder together)
```

## Development

```powershell
pip install -e .[dev]
pytest                         # unit tests (no real mouse/keyboard input is generated)
ruff check . ; ruff format .
python tools/build_icons.py    # regenerate otoshi/assets/icon.ico and icon.png
```

All icons, including the application icon, the tray state icons and the UI glyphs, are drawn in code in [`otoshi/icons.py`](otoshi/icons.py), so they stay sharp at every size and are easy to tweak.

### Project structure

```text
Otoshi/
├── main.py              # launcher (also used by PyInstaller)
├── Otoshi.spec          # PyInstaller build definition
├── otoshi/
│   ├── app.py           # main window, state machine, UI wiring
│   ├── macro.py         # recording, playback, .otm file format
│   ├── clicker.py       # auto clicker engine
│   ├── hotkeys.py       # global hotkeys (RegisterHotKey) and combination capture
│   ├── i18n.py          # translations; strings live in locales/*.json
│   ├── config.py        # typed settings, validation, migration
│   ├── overlay.py       # status overlay and location picker
│   ├── widgets.py       # styled Qt components (toggle, cards, rows)
│   ├── icons.py         # procedural icon artwork
│   ├── theme.py         # colours, fonts, spacing
│   ├── timing.py        # precise interruptible waits
│   ├── winutil.py       # Windows helpers (DPI, mutex, click-through)
│   ├── paths.py, logger.py
│   ├── locales/         # en, tr, de, es, fr, it, pt, ru, ja, zh
│   └── assets/          # generated icon.ico / icon.png
├── tests/               # pytest suite
└── tools/build_icons.py
```

### Macro file format

```json
{
  "format": "otoshi-macro", "version": 2, "loop_count": 1, "speed": 1.0,
  "events": [
    {"t": 0.42, "type": "move", "x": 10, "y": 20},
    {"t": 0.50, "type": "click", "x": 10, "y": 20, "button": "left", "pressed": true},
    {"t": 0.70, "type": "key", "key": {"vk": 65, "char": "a"}, "pressed": true}
  ]
}
```

`t` is the number of seconds since the recording started.

## License

MIT. See [LICENSE](LICENSE).
