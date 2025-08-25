import os
import json
import uuid
import time
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, send_file, Response
from io import BytesIO
import qrcode

# Configure comprehensive logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# In-memory storage for active sessions (will be lost on worker restart, but that's OK)
active_sessions = {}

def log_session_state(session_id, action, details=""):
    """Log session state changes for debugging"""
    session_info = active_sessions.get(session_id, {})
    user_count = len(session_info.get('users', {}))
    logger.info(f"SESSION {action}: {session_id} | Users: {user_count} | {details}")

@app.route('/')
def index():
    """Main page for creating sessions"""
    # Check if this is a Render health check
    user_agent = request.headers.get('User-Agent', '')
    if 'Render' in user_agent:
        return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})
    
    return render_template('index.html')

@app.route('/create_session', methods=['POST'])
def create_session():
    """Create a new session"""
    session_id = str(uuid.uuid4())[:8]
    
    # Initialize session data
    active_sessions[session_id] = {
        'users': {},
        'status': 'waiting',
        'current_question': 0,
        'questions': load_questions(),
        'last_activity': datetime.now().isoformat()
    }
    
    log_session_state(session_id, "CREATED")
    return jsonify({'session_id': session_id})

@app.route('/instructor/<session_id>')
def instructor_view(session_id):
    """Instructor view for a session"""
    if session_id not in active_sessions:
        return "Session not found", 404
    
    log_session_state(session_id, "INSTRUCTOR_VIEW_ACCESSED")
    
    # Get actual network IP address that other computers can reach
    import socket
    try:
        # Create a socket to get the local IP address
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Connect to a remote address (doesn't actually send data)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except:
        # Fallback to hostname method
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
        except:
            local_ip = "127.0.0.1"
    
    return render_template('instructor.html', 
                         session_id=session_id,
                         session_name="Privilege Walk Session",
                         network_ip=local_ip)

@app.route('/join/<session_id>')
def student_join(session_id):
    """Student join page"""
    if session_id not in active_sessions:
        logger.error(f"Student join attempt for non-existent session: {session_id}")
        return "Session not found", 404
    
    log_session_state(session_id, "STUDENT_JOIN_PAGE_ACCESSED")
    return render_template('student_join.html', session_id=session_id)

@app.route('/student/<session_id>')
def student_view(session_id):
    """Student view for a session"""
    if session_id not in active_sessions:
        logger.error(f"Student view attempt for non-existent session: {session_id}")
        return "Session not found", 404
    
    username = request.args.get('username', 'Anonymous')
    
    # Add user to session
    if session_id in active_sessions:
        active_sessions[session_id]['users'][username] = {
            'joined_at': datetime.now().isoformat(),
            'answers': [],
            'position': 0
        }
        
        log_session_state(session_id, "STUDENT_JOINED", f"Username: {username}")
    
    return render_template('student.html', session_id=session_id, username=username)

@app.route('/qr/<session_id>')
def qr_code(session_id):
    """Generate QR code for session"""
    if session_id not in active_sessions:
        return "Session not found", 404
    
    # Get actual network IP address for local development
    import socket
    try:
        # Create a socket to get the local IP address
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Connect to a remote address (doesn't actually send data)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except:
        # Fallback to hostname method
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
        except:
            local_ip = "127.0.0.1"
    
    # Use local network IP for development, Render domain for production
    port = int(os.environ.get('PORT', 5001))
    if os.environ.get('RENDER', False):
        # Production on Render
        join_url = f'https://privilage-walk.onrender.com/join/{session_id}'
    else:
        # Local development
        join_url = f'http://{local_ip}:{port}/join/{session_id}'
    
    # Create QR code pointing to the correct URL
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(join_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to bytes
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return send_file(img_io, mimetype='image/png')

@app.route('/api/join_session', methods=['POST'])
def api_join_session():
    """API endpoint for joining a session"""
    data = request.get_json()
    session_id = data.get('session_id')
    username = data.get('username')
    
    if not session_id or not username:
        return jsonify({'error': 'Missing session_id or username'}), 400
    
    if session_id not in active_sessions:
        logger.error(f"API join attempt for non-existent session: {session_id}")
        return jsonify({'error': 'Session not found'}), 404
    
    # Add user to session
    active_sessions[session_id]['users'][username] = {
        'joined_at': datetime.now().isoformat(),
        'answers': [],
        'position': 0
    }
    
    log_session_state(session_id, "API_JOIN", f"Username: {username}")
    
    return jsonify({'success': True, 'session_id': session_id})

@app.route('/api/start_session', methods=['POST'])
def api_start_session():
    """Start the privilege walk session"""
    data = request.get_json()
    session_id = data.get('session_id')
    
    if not session_id or session_id not in active_sessions:
        return jsonify({'error': 'Invalid session'}), 400
    
    session_data = active_sessions[session_id]
    session_data['status'] = 'active'
    session_data['current_question'] = 0
    session_data['last_activity'] = datetime.now().isoformat()
    
    log_session_state(session_id, "STARTED")
    
    return jsonify({'success': True})

@app.route('/api/submit_answer', methods=['POST'])
def api_submit_answer():
    """Submit a student's answer"""
    data = request.get_json()
    session_id = data.get('session_id')
    username = data.get('username')
    answer = data.get('answer')
    
    if not all([session_id, username, answer]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    if session_id not in active_sessions:
        logger.error(f"Answer submission for non-existent session: {session_id}")
        return jsonify({'error': 'Session not found'}), 404
    
    session_data = active_sessions[session_id]
    
    if username not in session_data['users']:
        return jsonify({'error': 'User not in session'}), 400
    
    # Record answer
    user_data = session_data['users'][username]
    user_data['answers'].append(answer)
    
    # Update position based on answer
    if answer == 'agree':
        user_data['position'] += 1
    elif answer == 'disagree':
        user_data['position'] -= 1
    
    log_session_state(session_id, "ANSWER_SUBMITTED", f"User: {username}, Answer: {answer}, Position: {user_data['position']}")
    
    # Check if all users have answered
    all_answered = all(len(user['answers']) > session_data['current_question'] 
                       for user in session_data['users'].values())
    
    if all_answered:
        # Move to next question
        session_data['current_question'] += 1
        questions = session_data['questions']
        
        if session_data['current_question'] < len(questions):
            # Next question - just log it
            next_question = questions[session_data['current_question']]
            logger.info(f"Moving to next question: {session_id} | Q{session_data['current_question'] + 1}: {next_question}")
            
            # Reset answers for next question
            for user in session_data['users'].values():
                user['answers'] = user['answers'][:session_data['current_question']]
        else:
            # Session finished
            session_data['status'] = 'finished'
            final_positions = {username: user['position'] for username, user in session_data['users'].items()}
            
            log_session_state(session_id, "FINISHED", f"Final positions: {final_positions}")
    
    session_data['last_activity'] = datetime.now().isoformat()
    return jsonify({'success': True})

@app.route('/api/reset_session', methods=['POST'])
def api_reset_session():
    """Reset a session to start over"""
    data = request.get_json()
    session_id = data.get('session_id')
    
    if not session_id or session_id not in active_sessions:
        return jsonify({'error': 'Invalid session'}), 400
    
    # Reset session data
    session_data = active_sessions[session_id]
    session_data['status'] = 'waiting'
    session_data['current_question'] = 0
    
    # Reset user data
    for user in session_data['users'].values():
        user['answers'] = []
        user['position'] = 0
    
    session_data['last_activity'] = datetime.now().isoformat()
    
    log_session_state(session_id, "RESET")
    
    return jsonify({'success': True})

# Polling endpoints for real-time updates
@app.route('/api/session_status/<session_id>')
def session_status(session_id):
    """Get current session status for polling"""
    if session_id not in active_sessions:
        return jsonify({'error': 'Session not found'}), 404
    
    session_data = active_sessions[session_id]
    
    return jsonify({
        'status': session_data['status'],
        'users': list(session_data['users'].keys()),
        'user_count': len(session_data['users']),
        'current_question': session_data['current_question'],
        'total_questions': len(session_data['questions']),
        'last_activity': session_data['last_activity']
    })

@app.route('/api/question/<session_id>')
def get_question(session_id):
    """Get current question for a session"""
    if session_id not in active_sessions:
        return jsonify({'error': 'Session not found'}), 404
    
    session_data = active_sessions[session_id]
    
    if session_data['status'] != 'active':
        return jsonify({'error': 'Session not active'}), 400
    
    current_q = session_data['current_question']
    questions = session_data['questions']
    
    if current_q >= len(questions):
        return jsonify({'error': 'No more questions'}), 400
    
    return jsonify({
        'question': questions[current_q],
        'question_number': current_q + 1,
        'total_questions': len(questions)
    })

@app.route('/api/positions/<session_id>')
def get_positions(session_id):
    """Get current user positions for a session"""
    if session_id not in active_sessions:
        return jsonify({'error': 'Session not found'}), 404
    
    session_data = active_sessions[session_id]
    positions = {username: user['position'] for username, user in session_data['users'].items()}
    
    return jsonify({'positions': positions})

@app.route('/health')
def health_check():
    """Health check endpoint for Render"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'active_sessions': len(active_sessions),
        'total_users': sum(len(session.get('users', {})) for session in active_sessions.values())
    })

def load_questions():
    """Load questions from JSON file"""
    try:
        with open('questions.json', 'r') as f:
            questions = json.load(f)
            logger.info(f"Loaded {len(questions)} questions from questions.json")
            return [q['text'] for q in questions['questions']]
    except Exception as e:
        logger.error(f"Error loading questions: {str(e)}")
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    logger.info(f"Starting Flask app on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False) 