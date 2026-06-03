# Otoshi - Professional Macro & Auto Clicker

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)
![Aesthetic](https://img.shields.io/badge/ui-customtkinter-orange.svg)

Otoshi is a high-performance macro recording and auto-clicking utility built with Python and CustomTkinter. Designed with a focus on precision and aesthetics, it features an industrial-grade dark UI and robust automation capabilities.

## ✨ Key Features

- **🔴 High-Precision Macro Recording**: Capture mouse movements, clicks, and keyboard inputs with millisecond accuracy.
- **⚡ Advanced Auto Clicker**: Fully customizable clicking engine supporting specific locations, intervals, and click types (Single/Double).
- **🎨 Premium Dark UI**: Minimalist industrial design with smooth transitions and iOS-style navigation.
- **⌨️ Customizable Hotkeys**: Register global hotkeys to control actions even when the app is in the background.
- **💾 Macro Serialization**: Export and import your workflows as `.otm` files for future use.
- **🚀 Playback Speed Control**: Fine-tune the playback speed from 0.5x to 20.0x.
- **📥 System Tray Integration**: Minimize to tray for an unobtrusive background experience with status notifications.

## 🛠️ Getting Started

### Prerequisites

- Python 3.8 or higher.
- Administrator privileges (recommended for global hotkey hooks).

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/enesuygurs/otoshi.git
   cd otoshi
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## 📖 Usage

Launch the application with:
```bash
python main.py
```

### Default Hotkeys

| Action | Hotkey |
| :--- | :--- |
| Start/Stop Recording | **F2** |
| Start/Stop Playback | **F3** |
| Toggle Auto Clicker | **F4** |

> [!TIP]
> You can customize these hotkeys and other behaviors in the **Settings** tab.

## 📂 Project Structure

```text
otoshi/
├── main.py            # Entry point
├── pyproject.toml     # Packaging & Metadata
├── src/               # Application logic
│   ├── app.py         # GUI & UI Logic
│   ├── logic.py       # Core Engines
│   ├── config.py      # Configuration Management
│   └── utils/         # Utilities (Logging, etc.)
├── README.md          # Documentation
└── LICENSE            # MIT License
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

1. Fork the Project.
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`).
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`).
4. Push to the Branch (`git push origin feature/AmazingFeature`).
5. Open a Pull Request.

## 📜 License

Distributed under the MIT License. See [LICENSE](LICENSE) for more information.