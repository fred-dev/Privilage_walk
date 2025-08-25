from flask import Flask, render_template, request, jsonify, session, send_file
from flask_socketio import SocketIO, emit, join_room, leave_room
import json
import uuid
from datetime import datetime
import os
import qrcode
from io import BytesIO
import socket

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*")

# Load configuration
def load_config():
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        # Default config if file doesn't exist
        return {
            "server": {"host": "0.0.0.0", "port": 5001, "debug": True},
            "network": {"local_testing": True, "local_ip": "localhost", "server_domain": "localhost"},
            "questions_file": "questions.json"
        }

config = load_config()

# Load questions from JSON file
def load_questions():
    try:
        with open(config['questions_file'], 'r') as f:
            questions_data = json.load(f)
            return [q['text'] for q in questions_data['questions']]
    except FileNotFoundError:
        # Fallback questions if file doesn't exist
        return [
            "I have rarely been judged negatively or discriminated against because of my body size.",
            "My mental health is generally robust, and it has never seriously limited my opportunities.",
            "I am neurotypical, and my ways of thinking and learning are usually supported in school or work.",
            "My sexuality has never caused me to be excluded, harassed, or made invisible.",
            "I am able-bodied, and I do not face barriers to everyday activities, buildings, or services.",
            "I have access to post-secondary education and am likely to complete it.",
            "My skin colour has never caused me to be unfairly treated or stereotyped.",
            "I am a citizen or permanent resident and do not have to worry about losing my right to remain in this country.",
            "My gender identity is cisgender and has never been a barrier to being accepted or respected.",
            "English is my first or fluent language, and it has always been an advantage for me in education and society.",
            "I grew up in a family that was financially secure and could afford most of what we needed.",
            "I have always had secure housing and have never been at risk of homelessness."
        ]

# Store active sessions
active_sessions = {}

def save_sessions():
    """Save sessions to disk"""
    try:
        with open('sessions.json', 'w') as f:
            # Convert datetime objects to strings for JSON serialization
            sessions_to_save = {}
            for session_id, session_data in active_sessions.items():
                sessions_to_save[session_id] = session_data.copy()
                if 'created_at' in sessions_to_save[session_id]:
                    sessions_to_save[session_id]['created_at'] = sessions_to_save[session_id]['created_at'].isoformat()
                for username, user_data in sessions_to_save[session_id].get('users', {}).items():
                    if 'joined_at' in user_data:
                        user_data['joined_at'] = user_data['joined_at'].isoformat()
            json.dump(sessions_to_save, f, indent=2)
    except Exception as e:
        print(f"Error saving sessions: {e}")

def load_sessions():
    """Load sessions from disk"""
    try:
        with open('sessions.json', 'r') as f:
            sessions_data = json.load(f)
            for session_id, session_data in sessions_data.items():
                # Convert string dates back to datetime objects
                if 'created_at' in session_data:
                    session_data['created_at'] = datetime.fromisoformat(session_data['created_at'])
                for username, user_data in session_data.get('users', {}).items():
                    if 'joined_at' in user_data:
                        user_data['joined_at'] = datetime.fromisoformat(user_data['joined_at'])
            return sessions_data
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"Error loading sessions: {e}")
        return {}

# Load existing sessions on startup
active_sessions = load_sessions()

def get_network_ip():
    """Get the local network IP address"""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return None

# Load questions
QUESTIONS = load_questions()

@app.route('/health')
def health_check():
    """Health check endpoint for Render"""
    return jsonify({'status': 'healthy', 'sessions': len(active_sessions)})

@app.route('/')
def index():
    """Main page to create a new session"""
    return render_template('index.html')

@app.route('/create_session', methods=['POST'])
def create_session():
    """Create a new session"""
    session_name = request.form.get('session_name', 'Unnamed Session')
    session_id = str(uuid.uuid4())[:8]
    
    active_sessions[session_id] = {
        'name': session_name,
        'users': {},
        'status': 'waiting',  # waiting, active, finished
        'current_question': 0,
        'user_answers': {},
        'created_at': datetime.now()
    }
    
    # Save sessions to disk
    save_sessions()
    
    return jsonify({'session_id': session_id, 'redirect_url': f'/instructor/{session_id}'})

@app.route('/instructor/<session_id>')
def instructor_view(session_id):
    """Instructor view with QR code and controls"""
    if session_id not in active_sessions:
        return "Session not found", 404
    
    session_data = active_sessions[session_id]
    
    # Get the IP address for the QR code based on config
    if config['network']['local_testing']:
        # Use configured local IP for testing
        host_ip = config['network']['local_ip']
        qr_url = f"http://{host_ip}:{config['server']['port']}/join/{session_id}"
    else:
        # Use server domain for production
        host_ip = config['network']['server_domain']
        qr_url = f"https://{host_ip}/join/{session_id}"
    
    # Get network IP for display
    network_ip = get_network_ip()
    
    return render_template('instructor.html', 
                         session_id=session_id, 
                         session_name=session_data['name'],
                         qr_url=qr_url,
                         network_ip=network_ip)

@app.route('/qr/<session_id>')
def generate_qr_code(session_id):
    """Generate QR code for a session"""
    if session_id not in active_sessions:
        return "Session not found", 404
    
    # Get the IP address for the QR code based on config
    if config['network']['local_testing']:
        # Use configured local IP for testing
        host_ip = config['network']['local_ip']
        qr_url = f"http://{host_ip}:{config['server']['port']}/join/{session_id}"
    else:
        # Use server domain for production
        host_ip = config['network']['server_domain']
        qr_url = f"https://{host_ip}/join/{session_id}"
    
    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_url)
    qr.make(fit=True)
    
    # Create QR code image
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to bytes
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return send_file(img_io, mimetype='image/png')

@app.route('/join/<session_id>')
def join_session(session_id):
    """Student join page"""
    if session_id not in active_sessions:
        return "Session not found", 404
    
    return render_template('student_join.html', session_id=session_id)

@app.route('/student/<session_id>')
def student_view(session_id):
    """Student question answering interface"""
    if session_id not in active_sessions:
        return "Session not found", 404
    
    username = request.args.get('username')
    if not username:
        return "Username required", 400
    
    session_data = active_sessions[session_id]
    if username not in session_data['users']:
        return "User not found in session", 400
    
    return render_template('student.html', 
                         session_id=session_id, 
                         username=username,
                         questions=QUESTIONS)

@app.route('/api/join_session', methods=['POST'])
def api_join_session():
    """API endpoint for students to join a session"""
    data = request.get_json()
    session_id = data.get('session_id')
    username = data.get('username')
    
    if session_id not in active_sessions:
        return jsonify({'error': 'Session not found'}), 404
    
    if not username or username.strip() == '':
        return jsonify({'error': 'Username is required'}), 400
    
    # Check if username is already taken in this session
    if username in active_sessions[session_id]['users']:
        return jsonify({'error': 'Username already taken'}), 400
    
    # Add user to session
    active_sessions[session_id]['users'][username] = {
        'joined_at': datetime.now(),
        'position': 0,  # Starting position
        'answers': []
    }
    
    # Save sessions to disk
    save_sessions()
    
    # Notify instructor view
    socketio.emit('user_joined', {
        'username': username,
        'user_count': len(active_sessions[session_id]['users'])
    }, room=f'instructor_{session_id}')
    
    return jsonify({'success': True, 'redirect_url': f'/student/{session_id}?username={username}'})

@app.route('/api/start_session', methods=['POST'])
def api_start_session():
    """Start the privilege walk questions"""
    data = request.get_json()
    session_id = data.get('session_id')
    
    print(f"🚀 START SESSION REQUEST: {session_id}")
    
    if session_id not in active_sessions:
        print(f"❌ Session {session_id} not found")
        return jsonify({'error': 'Session not found'}), 404
    
    session_data = active_sessions[session_id]
    print(f"📊 Session data: {session_data}")
    
    if len(session_data['users']) == 0:
        print(f"❌ No users in session {session_id}")
        return jsonify({'error': 'No users in session'}), 400
    
    session_data['status'] = 'active'
    session_data['current_question'] = 0
    session_data['user_answers'] = {username: [] for username in session_data['users']}
    
    # Save sessions to disk
    save_sessions()
    
    print(f"✅ Session {session_id} started with {len(session_data['users'])} users")
    
    # Notify all students
    print(f"📤 Emitting session_started to session_{session_id}")
    socketio.emit('session_started', {
        'question': QUESTIONS[0],
        'question_number': 1,
        'total_questions': len(QUESTIONS)
    }, room=f'session_{session_id}')
    
    # Also notify the instructor
    print(f"📤 Emitting session_started to instructor_{session_id}")
    socketio.emit('session_started', {
        'question': QUESTIONS[0],
        'question_number': 1,
        'total_questions': len(QUESTIONS)
    }, room=f'instructor_{session_id}')
    
    print(f"✅ Session start complete for {session_id}")
    return jsonify({'success': True})

@app.route('/api/reset_session', methods=['POST'])
def api_reset_session():
    """Reset a session for new questions"""
    data = request.get_json()
    session_id = data.get('session_id')
    
    if session_id not in active_sessions:
        return jsonify({'error': 'Session not found'}), 404
    
    session_data = active_sessions[session_id]
    
    # Reset session state but keep users
    session_data['status'] = 'waiting'
    session_data['current_question'] = 0
    session_data['user_answers'] = {}
    
    # Reset user positions
    for username in session_data['users']:
        session_data['users'][username]['position'] = 0
        session_data['users'][username]['answers'] = []
    
    # Save sessions to disk
    save_sessions()
    
    return jsonify({'success': True})

@app.route('/api/submit_answer', methods=['POST'])
def api_submit_answer():
    """Submit a student's answer to a question"""
    data = request.get_json()
    session_id = data.get('session_id')
    username = data.get('username')
    answer = data.get('answer')  # True for agree, False for disagree
    
    if session_id not in active_sessions:
        return jsonify({'error': 'Session not found'}), 404
    
    session_data = active_sessions[session_id]
    if username not in session_data['users']:
        return jsonify({'error': 'User not found'}), 400
    
    if session_data['status'] != 'active':
        return jsonify({'error': 'Session not active'}), 400
    
    current_q = session_data['current_question']
    
    # Store answer
    if username not in session_data['user_answers']:
        session_data['user_answers'][username] = []
    
    session_data['user_answers'][username].append(answer)
    
    # Calculate new position
    move_amount = 100 / len(QUESTIONS)  # Total screen height divided by number of questions
    if answer:  # Agree - move up
        session_data['users'][username]['position'] += move_amount
    else:  # Disagree - move down
        session_data['users'][username]['position'] -= move_amount
    
    # Check if all users have answered
    all_answered = all(len(answers) > current_q for answers in session_data['user_answers'].values())
    
    if all_answered:
        # Move to next question
        session_data['current_question'] += 1
        
        if session_data['current_question'] >= len(QUESTIONS):
            # All questions answered
            session_data['status'] = 'finished'
            socketio.emit('session_finished', {
                'final_positions': {username: user_data['position'] 
                                  for username, user_data in session_data['users'].items()}
            }, room=f'session_{session_id}')
            
            # Also notify the instructor
            socketio.emit('session_finished', {
                'final_positions': {username: user_data['position'] 
                                  for username, user_data in session_data['users'].items()}
            }, room=f'instructor_{session_id}')
        else:
            # Next question
            socketio.emit('next_question', {
                'question': QUESTIONS[session_data['current_question']],
                'question_number': session_data['current_question'] + 1,
                'total_questions': len(QUESTIONS)
            }, room=f'session_{session_id}')
            
            # Also notify the instructor
            socketio.emit('next_question', {
                'question': QUESTIONS[session_data['current_question']],
                'question_number': session_data['current_question'] + 1,
                'total_questions': len(QUESTIONS)
            }, room=f'instructor_{session_id}')
    
    # Update positions for all clients
    socketio.emit('position_update', {
        'positions': {username: user_data['position'] 
                     for username, user_data in session_data['users'].items()}
    }, room=f'session_{session_id}')
    
    # Also update the instructor
    socketio.emit('position_update', {
        'positions': {username: user_data['position'] 
                     for username, user_data in session_data['users'].items()}
    }, room=f'instructor_{session_id}')
    
    # Save sessions to disk
    save_sessions()
    
    return jsonify({'success': True, 'all_answered': all_answered})

# WebSocket events
@socketio.on('join_instructor')
def on_join_instructor(data):
    session_id = data['session_id']
    join_room(f'instructor_{session_id}')

@socketio.on('join_student')
def on_join_student(data):
    session_id = data['session_id']
    join_room(f'session_{session_id}')

@socketio.on('disconnect')
def on_disconnect():
    # Handle disconnection if needed
    pass

@socketio.on('session_reset')
def on_session_reset(data):
    # Notify all students in the session that it has been reset
    session_id = data.get('session_id')
    if session_id and session_id in active_sessions:
        socketio.emit('session_reset', room=f'session_{session_id}')

if __name__ == '__main__':
    # Use PORT environment variable for Render, fallback to config
    port = int(os.environ.get('PORT', config['server']['port']))
    socketio.run(app, 
                debug=config['server']['debug'], 
                host=config['server']['host'], 
                port=port) 