# Oai2Ollama-GUI

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.7%2B-blue)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)](https://github.com/Tonyhzk/oai2ollama-gui)

A desktop GUI application that bridges OpenAI-compatible APIs to Ollama-compatible APIs, enabling tools like GitHub Copilot to seamlessly use third-party AI platforms through a local Ollama-like interface.

## 📋 Table of Contents
- [Overview](#overview)
- [Features](#features)
- [Screenshots](#screenshots)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [API Endpoints](#api-endpoints)
- [Requirements](#requirements)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [Credits](#credits)
- [License](#license)

## 🎯 Overview

**Oai2Ollama-GUI** is a Python-based desktop application that acts as a bridge between OpenAI-compatible API services and applications expecting an Ollama API interface. This allows you to use third-party OpenAI-compatible services (like Azure OpenAI, local LLMs, or other providers) with tools that are designed to work with Ollama, such as GitHub Copilot and other development tools.

Unlike the original [oai2ollama](https://github.com/CNSeniorious000/oai2ollama) which is a Docker-based terminal application, this project provides a user-friendly graphical interface for easy configuration and management.

## ✨ Features

- **🖥️ Intuitive GUI**: User-friendly interface built with Tkinter and ttkbootstrap
- **🔄 API Translation**: Seamlessly converts between OpenAI and Ollama API formats
- **🌐 Multi-language Support**: Available in English and Chinese (easily extensible)
- **📝 Model Management**: 
  - Custom model list configuration
  - Model interception and filtering
  - Advanced JSON-based model editing
- **🎨 Theme Support**: Dark and light theme options
- **⚙️ Flexible Configuration**:
  - Customizable API endpoints
  - Configurable server host and port
  - API key management with secure display toggle
- **📊 Real-time Logging**: Monitor server activity with auto-scrolling logs
- **💾 Persistent Settings**: Automatically saves and loads configurations
- **🚀 Quick Start Wizard**: Guided setup for first-time users
- **🔧 Advanced Features**:
  - Capability tagging (tools, vision, embedding)
  - Extra model injection
  - Streaming response support

## 📸 Screenshots

*Note: Add screenshots of your application here*

```
[Main Interface Screenshot]
[Model Management Screenshot]
[Quick Setup Wizard Screenshot]
```

## 🚀 Installation

### Prerequisites

- Python 3.7 or higher
- pip package manager

### Step 1: Clone the Repository

```bash
git clone https://github.com/Tonyhzk/oai2ollama-gui.git
cd oai2ollama-gui
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

Or install packages individually:

```bash
pip install ttkbootstrap fastapi uvicorn httpx pydantic pillow pystray
```

### Step 3: Run the Application

```bash
python oai2ollama_gui.py
```

## 📖 Usage

### Quick Start

1. **Launch the application** by running the Python script
2. **Complete the Quick Setup Wizard** (appears on first run):
   - Select a preset configuration or choose custom
   - Enter your API key
   - Set the base URL for your OpenAI-compatible service
   - Configure listening address and port (optional)
3. **Click "Start"** to begin the server
4. **Configure your applications** (e.g., GitHub Copilot) to use:
   - Endpoint: `http://localhost:11434` (or your configured port)
   - Model: Any model from your configured list

### Configuration Options

#### Basic Settings
- **API Key**: Your OpenAI-compatible service API key
- **Base URL**: The endpoint of your OpenAI-compatible service
- **Listen Address**: Local address for the bridge server (default: localhost)
- **Port**: Local port for the bridge server (default: 11434)

#### Advanced Settings
- **Capabilities**: Comma-separated list (e.g., `tools, vision, embedding`)
- **Extra Models**: Additional model names to expose
- **Intercept Model List**: Enable to override the model list from the API

### Model Management

1. Click **"Settings"** next to "Intercept Model List"
2. In the Model Management window:
   - **Fetch models** from your configured API
   - **Add custom models** manually
   - **Enable/disable** specific models
   - **Search and filter** models
   - **Advanced editing** with JSON editor

## 🔌 API Endpoints

The bridge exposes the following Ollama-compatible endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Service status |
| `/api/tags` | GET | List available models (Ollama format) |
| `/api/show` | POST | Show model information |
| `/api/version` | GET | Ollama version info |
| `/v1/models` | GET | List models (OpenAI format) |
| `/v1/chat/completions` | POST | Chat completion endpoint |

## 📋 Requirements

- **Operating System**: Windows, macOS, or Linux
- **Python**: 3.7+
- **Required Python Packages**:
  - `ttkbootstrap`: Modern themed tkinter widgets
  - `fastapi`: Web framework for API
  - `uvicorn`: ASGI server
  - `httpx`: HTTP client with HTTP/2 support
  - `pydantic`: Data validation
  - `pillow`: Image processing for icons
  - `pystray`: System tray support (optional)

## 📁 Project Structure

```
oai2ollama-gui/
├── oai2ollama_gui.py          # Main application script
├── config.json                 # Configuration file (auto-generated)
├── locales/                    # Localization files
│   ├── en_US/
│   │   └── LC_MESSAGES/
│   │       ├── messages.mo
│   │       └── messages.po
│   └── zh_CN/
│       └── LC_MESSAGES/
│           ├── messages.mo
│           └── messages.po
├── icon.ico                    # Application icon (optional)
├── icon.png                    # Application icon alternative (optional)
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 🙏 Credits

- **Author**: [Tonyhzk](https://github.com/Tonyhzk)
- **Inspiration**: [oai2ollama](https://github.com/CNSeniorious000/oai2ollama) by CNSeniorious000
- **UI Framework**: [ttkbootstrap](https://github.com/israel-dryer/ttkbootstrap)

This project was inspired by the original [oai2ollama](https://github.com/CNSeniorious000/oai2ollama) Docker-based terminal application. We've transformed it into a desktop GUI application to make it more accessible and user-friendly for developers who prefer graphical interfaces.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🐛 Known Issues & Troubleshooting

### Common Issues

1. **Port Already in Use**: Change the port in settings if 11434 is occupied
2. **API Key Invalid**: Ensure your API key is correct and has proper permissions
3. **Connection Failed**: Verify the base URL and network connectivity

### Debug Tips

- Check the application logs for detailed error messages
- Enable "Show" for API key to verify it's entered correctly
- Test your API endpoint directly with curl or Postman
- Ensure firewall isn't blocking the local server

## 📮 Contact & Support

- **GitHub Issues**: [Report bugs or request features](https://github.com/Tonyhzk/oai2ollama-gui/issues)
- **Author**: Tonyhzk

## 🔄 Version History

- **v1.0.1** (Current)
  - Multi-language support (EN/CN)
  - Model interception and management
  - Advanced JSON editing
  - Quick setup wizard
  - Theme switching

---

**Note**: This application is not affiliated with OpenAI or Ollama. It's an independent tool designed to bridge compatibility between different API formats.