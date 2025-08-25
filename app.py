from flask import Flask, render_template, request, jsonify, session, send_file
from flask_socketio import SocketIO, emit, join_room, leave_room
import json
import uuid
from datetime import datetime
import os
import qrcode
from io import BytesIO

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*")

# Load questions from JSON file
def load_questions():
    try:
        with open('questions.json', 'r') as f:
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

# Store active sessions in memory (simple)
active_sessions = {}

# Load questions
QUESTIONS = load_questions()

@app.route('/')
def index():
    """Main page to create a new session"""
    # Add a simple health check response for Render
    user_agent = request.headers.get('User-Agent', '')
    if 'Render' in user_agent:
        return jsonify({'status': 'healthy', 'message': 'Privilege Walk app is running'})
    return render_template('index.html')

@app.route('/health')
def health_check():
    """Health check endpoint for Render - optimized for speed"""
    try:
        # Super fast response - no database queries or heavy operations
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'sessions_count': len(active_sessions),
            'uptime': 'running'
        })
    except Exception as e:
        # Even if there's an error, return quickly
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/create_session', methods=['POST'])
def create_session():
    """Create a new session"""
    session_name = request.form.get('session_name', 'Privilege Walk')
    session_id = str(uuid.uuid4())[:8]
    
    active_sessions[session_id] = {
        'name': session_name,
        'users': {},
        'status': 'waiting',
        'current_question': 0,
        'created_at': datetime.now()
    }
    
    return jsonify({'session_id': session_id, 'redirect_url': f'/instructor/{session_id}'})

@app.route('/instructor/<session_id>')
def instructor_view(session_id):
    """Instructor view for managing a session"""
    if session_id not in active_sessions:
        return "Session not found", 404
    
    session_data = active_sessions[session_id]
    
    # Simple QR code URL for Render
    qr_url = f"https://privilage-walk.onrender.com/join/{session_id}"
    
    return render_template('instructor.html', 
                          session_id=session_id, 
                          session_name=session_data['name'],
                          qr_url=qr_url,
                          network_ip="Render")

@app.route('/qr/<session_id>')
def generate_qr_code(session_id):
    """Generate QR code for session joining"""
    if session_id not in active_sessions:
        return "Session not found", 404
    
    # Simple QR code URL for Render
    qr_url = f"https://privilage-walk.onrender.com/join/{session_id}"
    
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
def join_session_page(session_id):
    """Page for students to join a session"""
    if session_id not in active_sessions:
        return "Session not found", 404
    
    return render_template('student_join.html', session_id=session_id)

@app.route('/api/join_session', methods=['POST'])
def api_join_session():
    """API endpoint for students to join a session"""
    session_id = request.form.get('session_id')
    username = request.form.get('username')
    
    if not session_id or not username:
        return jsonify({'success': False, 'error': 'Missing session_id or username'}), 400
    
    if session_id not in active_sessions:
        return jsonify({'success': False, 'error': 'Session not found'}), 404
    
    if active_sessions[session_id]['status'] != 'waiting':
        return jsonify({'success': False, 'error': 'Session already started'}), 400
    
    # Add user to session
    active_sessions[session_id]['users'][username] = {
        'position': 0,
        'current_question': 0,
        'joined_at': datetime.now()
    }
    
    # Notify instructor view
    socketio.emit('user_joined', {
        'username': username,
        'user_count': len(active_sessions[session_id]['users'])
    }, room=f'instructor_{session_id}')
    
    return jsonify({'success': True, 'redirect_url': f'/student/{session_id}?username={username}'})

@app.route('/student/<session_id>')
def student_view(session_id):
    """Student view for answering questions"""
    username = request.args.get('username')
    
    if not username:
        return "Username required", 400
    
    if session_id not in active_sessions:
        return "Session not found", 404
    
    if username not in active_sessions[session_id]['users']:
        return "User not in session", 400
    
    return render_template('student.html', 
                          session_id=session_id, 
                          username=username,
                          questions=QUESTIONS)

@app.route('/api/start_session', methods=['POST'])
def api_start_session():
    """Start the privilege walk session"""
    session_id = request.form.get('session_id')
    
    if not session_id or session_id not in active_sessions:
        return jsonify({'success': False, 'error': 'Invalid session'}), 400
    
    session_data = active_sessions[session_id]
    
    if len(session_data['users']) == 0:
        return jsonify({'success': False, 'error': 'No users in session'}), 400
    
    session_data['status'] = 'active'
    session_data['current_question'] = 0
    
    print(f"✅ Session {session_id} started with {len(session_data['users'])} users")
    
    # Notify all clients
    socketio.emit('session_started', {
        'question': QUESTIONS[0],
        'question_number': 1,
        'total_questions': len(QUESTIONS)
    }, room=f'session_{session_id}')
    
    # Also notify the instructor
    socketio.emit('session_started', {
        'question': QUESTIONS[0],
        'question_number': 1,
        'total_questions': len(QUESTIONS)
    }, room=f'instructor_{session_id}')
    
    return jsonify({'success': True})

@app.route('/api/submit_answer', methods=['POST'])
def api_submit_answer():
    """Submit a student's answer to a question"""
    session_id = request.form.get('session_id')
    username = request.form.get('username')
    answer = request.form.get('answer')  # 'agree' or 'disagree'
    
    if not all([session_id, username, answer]):
        return jsonify({'success': False, 'error': 'Missing parameters'}), 400
    
    if session_id not in active_sessions:
        return jsonify({'success': False, 'error': 'Session not found'}), 404
    
    session_data = active_sessions[session_id]
    
    if username not in session_data['users']:
        return jsonify({'success': False, 'error': 'User not in session'}), 400
    
    if session_data['status'] != 'active':
        return jsonify({'success': False, 'error': 'Session not active'}), 400
    
    user_data = session_data['users'][username]
    current_q = session_data['current_question']
    
    if user_data['current_question'] != current_q:
        return jsonify({'success': False, 'error': 'Question already answered'}), 400
    
    # Update user's position based on answer
    if answer == 'agree':
        user_data['position'] += 1
    elif answer == 'disagree':
        user_data['position'] -= 1
    
    user_data['current_question'] = current_q + 1
    
    # Check if all users have answered this question
    all_answered = all(user['current_question'] > current_q for user in session_data['users'].values())
    
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
            next_q = session_data['current_question']
            socketio.emit('next_question', {
                'question': QUESTIONS[next_q],
                'question_number': next_q + 1,
                'total_questions': len(QUESTIONS)
            }, room=f'session_{session_id}')
            
            # Also notify the instructor
            socketio.emit('next_question', {
                'question': QUESTIONS[next_q],
                'question_number': next_q + 1,
                'total_questions': len(QUESTIONS)
            }, room=f'instructor_{session_id}')
    
    # Update positions for all clients
    positions = {username: user_data['position'] for username, user_data in session_data['users'].items()}
    socketio.emit('position_update', {'positions': positions}, room=f'session_{session_id}')
    socketio.emit('position_update', {'positions': positions}, room=f'instructor_{session_id}')
    
    return jsonify({'success': True, 'all_answered': all_answered})

@app.route('/api/reset_session', methods=['POST'])
def api_reset_session():
    """Reset a session to allow new students to join"""
    session_id = request.form.get('session_id')
    
    if not session_id or session_id not in active_sessions:
        return jsonify({'success': False, 'error': 'Invalid session'}), 400
    
    # Reset session
    active_sessions[session_id]['status'] = 'waiting'
    active_sessions[session_id]['current_question'] = 0
    active_sessions[session_id]['users'] = {}
    
    # Notify all clients
    socketio.emit('session_reset', {}, room=f'session_{session_id}')
    socketio.emit('session_reset', {}, room=f'instructor_{session_id}')
    
    return jsonify({'success': True})

# WebSocket events
@socketio.on('join_instructor')
def on_join_instructor(data):
    """Instructor joins the instructor room"""
    session_id = data.get('session_id')
    if session_id:
        join_room(f'instructor_{session_id}')
        print(f"👨‍🏫 Instructor joined session {session_id}")

@socketio.on('join_student')
def on_join_student(data):
    """Student joins the student room"""
    session_id = data.get('session_id')
    if session_id:
        join_room(f'session_{session_id}')
        print(f"👤 Student joined session {session_id}")

@socketio.on('disconnect')
def on_disconnect():
    """Handle client disconnect"""
    print("Client disconnected")

if __name__ == '__main__':
    # Simple port binding for Render
    port = int(os.environ.get('PORT', 5001))
    socketio.run(app, 
                debug=False, 
                host='0.0.0.0', 
                port=port) 