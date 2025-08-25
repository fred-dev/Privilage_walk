# 🚶‍♂️ Privilege Walk Interactive Site

An interactive web application for conducting privilege walk activities in educational settings. Students scan a QR code to join, answer questions, and see their positions update in real-time on a shared display.

## ✨ Features

- **Session Management**: Create unique sessions with custom names to avoid interference between different classes
- **QR Code Generation**: Automatic QR code generation for easy student access
- **Real-time Updates**: Live position updates using WebSocket connections
- **Mobile-Friendly**: Students can participate using their phones
- **Progress Tracking**: Visual progress indicators and question management
- **Final Results**: Ranked final positions displayed at the end

## 🚀 Quick Start

### Prerequisites

- Python 3.7 or higher
- pip (Python package installer)

### Installation

1. **Clone or download the project files**

2. **Set up UV environment (recommended)**
   ```bash
   # On Mac/Linux
   ./setup.sh
   
   # On Windows
   setup.bat
   ```
   
   Or manually:
   ```bash
   uv sync
   ```

3. **Run the application**
   ```bash
   # On Mac/Linux
   ./run.sh
   
   # On Windows
   run.bat
   
   # Or directly with UV
   uv run python run.py
   ```

4. **Open your browser**
   - Navigate to `http://localhost:5001`
   - Create a new session with a custom name

## 📱 How It Works

### 1. Instructor Setup
- Go to the main page and create a new session
- Give your session a meaningful name (e.g., "Sociology 101 - Section A")
- You'll get a unique session ID and QR code

### 2. Student Participation
- Students scan the QR code with their phones
- They enter a nickname (can be fake/alias)
- Students see a "Please wait" message until you start

### 3. Running the Activity
- Watch the student count increase as they join
- Press "Start Privilege Walk" when ready
- Students will see questions appear on their screens
- Each student answers with Agree/Disagree
- Positions update in real-time on the main display

### 4. Question Flow
- Questions advance only when ALL students have answered
- Students move up (agree) or down (disagree) based on their answers
- Movement is calculated so full agreement = top, full disagreement = bottom

### 5. Final Results
- When all questions are answered, final positions are displayed
- Students see a "Thank you" message
- Results are ranked from highest to lowest position

## 🔧 Technical Details

### Configuration
The application uses `config.json` for easy configuration:

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 5001,
    "debug": true
  },
  "network": {
    "local_testing": true,
    "local_ip": "192.168.1.9",
    "server_domain": "yourdomain.com"
  },
  "questions_file": "questions.json"
}
```

- **Local Testing**: Set `local_testing: true` and update `local_ip` with your computer's IP
- **Production**: Set `local_testing: false` and update `server_domain` with your domain
- **Questions**: Modify `questions.json` to customize the privilege walk statements

### Architecture
- **Backend**: Python Flask with Flask-SocketIO
- **Frontend**: HTML/CSS/JavaScript with Socket.IO client
- **Real-time Communication**: WebSocket connections for live updates
- **Session Isolation**: Unique session IDs prevent cross-interference
- **Dependency Management**: UV for fast, reliable Python package management

### File Structure
```
Privilege_walk/
├── app.py                 # Main Flask application
├── config.json            # Configuration file (IP addresses, ports, etc.)
├── questions.json         # Privilege walk questions
├── pyproject.toml         # UV project configuration
├── README.md              # This file
└── templates/             # HTML templates
    ├── index.html         # Session creation page
    ├── instructor.html    # Instructor view with QR code
    ├── student_join.html  # Student username entry
    └── student.html       # Student question interface
```

### Questions Included
The system includes 12 privilege walk statements covering various aspects of privilege:
- Body size and appearance
- Mental health
- Neurodiversity
- Sexuality and gender identity
- Physical ability
- Education access
- Race and skin color
- Citizenship status
- Language fluency
- Financial security
- Housing stability

## 🌐 Network Setup

### For Local Use
- Run on `localhost:5001`
- Students connect via your computer's IP address
- Ensure all devices are on the same network

### For Production/Classroom Use
- Deploy to a web server or cloud platform
- Use HTTPS for secure connections
- Consider using a service like Heroku, Railway, or DigitalOcean

### Network Requirements
- All devices must be on the same network
- Port 5001 must be accessible
- WebSocket connections must be allowed

## 🎯 Best Practices

### Session Management
- Use descriptive session names
- Each class/group should have a unique session
- Sessions are automatically cleaned up when the server restarts

### Student Experience
- Encourage students to use memorable nicknames
- Ensure good network connectivity
- Have students test the QR code before starting

### Technical Considerations
- Test with a small group first
- Monitor network performance
- Have a backup plan if technology fails

## 🐛 Troubleshooting

### Common Issues

**Students can't join:**
- Check network connectivity
- Verify the session ID is correct
- Ensure the server is running

**QR code not working:**
- Verify the URL is accessible from student devices
- Check if students are on the same network
- Try accessing the URL directly in a browser

**Real-time updates not working:**
- Check browser console for WebSocket errors
- Verify firewall settings allow WebSocket connections
- Restart the server if needed

**Questions not advancing:**
- Ensure all students have answered
- Check browser console for errors
- Verify all students are still connected

### Debug Mode
The application runs in debug mode by default. Check the terminal for error messages and connection logs.

## 🔒 Privacy & Security

- Student nicknames are not stored permanently
- Session data is only kept in memory
- No personal information is collected
- Sessions are isolated by unique IDs

## 🆔 User Tracking & Session Management

### How Users Are Tracked
- **Username**: Students choose any nickname (can be fake/alias)
- **Session ID**: Each class gets a unique session identifier
- **No Persistent ID**: Same person could use different usernames in different sessions
- **Network IP**: Students connect via your computer's network IP address

### Session Options After Completion
1. **Reset Session**: Keep same students, start fresh questions
2. **New Session**: Generate new QR code and session ID
3. **Back to Setup**: Return to student join view

### For Multiple Rounds
- **Same Class, Different Questions**: Use "Reset Session" - students keep usernames
- **Different Class**: Use "New Session" - fresh start with new QR code
- **Tracking Individuals**: Currently not supported - would require persistent IDs or IP tracking

## 📝 Customization

### Adding/Modifying Questions
Edit the `QUESTIONS` list in `app.py`:
```python
QUESTIONS = [
    "Your custom question here?",
    "Another question?",
    # ... more questions
]
```

### Styling Changes
Modify the CSS in the HTML template files to change colors, fonts, and layout.

### Question Logic
The movement calculation can be adjusted in the `submit_answer` function in `app.py`.

## 🤝 Contributing

Feel free to modify and improve this application for your specific needs. Consider:
- Adding more question categories
- Implementing data export features
- Adding analytics and reporting
- Improving the mobile interface

## 🚀 Potential Improvements

### User Tracking
- **Persistent IDs**: Generate unique IDs for students to track across sessions
- **IP Tracking**: Track student IP addresses for identification
- **Account System**: Simple login system for returning students

### Session Management
- **Question Banks**: Multiple sets of questions for different topics
- **Results History**: Save and compare results across sessions
- **Student Progress**: Track individual student progress over time

### Features
- **Timer**: Add countdown for question answering
- **Anonymous Mode**: Hide usernames during the walk
- **Export Results**: Download results as CSV/PDF
- **Custom Scoring**: Adjustable scoring for different privilege dimensions

## 📄 License

This project is open source and available for educational use. Please respect the educational context and use responsibly.

---

**Happy teaching!** 🎓

For questions or support, check the troubleshooting section or review the code comments for technical details. 