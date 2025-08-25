# 🚀 Quick Start Guide

## Prerequisites
- **UV** (Python package manager) - [Install here](https://docs.astral.sh/uv/getting-started/installation/)
- **Python 3.11+** (UV will handle this automatically)

## 🎯 One-Command Setup

### Mac/Linux
```bash
./setup.sh
```

### Windows
```cmd
setup.bat
```

## 🚀 Running the Application

### Mac/Linux
```bash
./run.sh
```

### Windows
```cmd
run.bat
```

### Manual (any platform)
```bash
uv run python run.py
```

## 📱 What Happens Next

1. **Open your browser** to `http://localhost:5001`
2. **Create a session** with a name like "Sociology 101 - Section A"
3. **Share the QR code** with your students
4. **Students scan and join** with nicknames
5. **Press "Start"** when ready
6. **Watch real-time updates** as students answer questions

## 🔧 Troubleshooting

- **UV not found**: Run the setup script or install UV first
- **Port already in use**: Change port in `app.py` or stop other services
- **Students can't connect**: Ensure all devices are on the same network

## 📁 Project Structure
```
Privilege_walk/
├── .venv/              # UV virtual environment
├── templates/          # HTML templates
├── app.py             # Main Flask application
├── run.py             # Python startup script
├── run.sh/.bat        # Platform-specific runners
├── setup.sh/.bat      # Setup scripts
└── pyproject.toml     # UV project configuration
```

## 💡 Pro Tips

- Test with one student first
- Use descriptive session names
- Each class gets its own session
- Sessions are isolated and won't interfere

---

**Need help?** Check the main `README.md` for detailed documentation! 