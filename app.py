import os
import json
import uuid
import time
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, send_file, Response
from io import BytesIO
import qrcode
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure comprehensive logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# In-memory storage for active sessions (will be lost on worker restart, but that's OK)
active_sessions = {}

def save_sessions_to_file():
    """Save sessions to file for persistence across redeploys"""
    try:
        with open('sessions.json', 'w') as f:
            json.dump(active_sessions, f, default=str)
        logger.info(f"Saved {len(active_sessions)} sessions to file")
    except Exception as e:
        logger.error(f"Error saving sessions: {str(e)}")

def load_sessions_from_file():
    """Load sessions from file on startup"""
    try:
        with open('sessions.json', 'r') as f:
            sessions = json.load(f)
            
        # Validate and clean session data
        valid_sessions = {}
        for session_id, session_data in sessions.items():
            try:
                # Basic validation
                if not isinstance(session_data, dict):
                    logger.warning(f"Skipping invalid session {session_id}: not a dict")
                    continue
                    
                if 'users' not in session_data or 'status' not in session_data:
                    logger.warning(f"Skipping invalid session {session_id}: missing required fields")
                    continue
                
                # Convert string timestamps back to datetime objects
                if 'last_activity' in session_data:
                    try:
                        if isinstance(session_data['last_activity'], str):
                            session_data['last_activity'] = datetime.fromisoformat(session_data['last_activity'])
                    except Exception as e:
                        logger.warning(f"Invalid timestamp for session {session_id}: {e}")
                        session_data['last_activity'] = datetime.now()
                
                valid_sessions[session_id] = session_data
                
            except Exception as e:
                logger.error(f"Error processing session {session_id}: {e}")
                continue
        
        active_sessions.update(valid_sessions)
        logger.info(f"Loaded {len(valid_sessions)} valid sessions from file")
        
        # Save cleaned sessions back to file
        if valid_sessions != sessions:
            save_sessions_to_file()
            logger.info("Cleaned sessions saved back to file")
            
    except FileNotFoundError:
        logger.info("No existing sessions file found")
    except json.JSONDecodeError as e:
        logger.error(f"Corrupted sessions file: {e}")
        # Try to backup and remove corrupted file
        try:
            import shutil
            shutil.copy('sessions.json', 'sessions.json.backup')
            os.remove('sessions.json')
            logger.info("Corrupted sessions file backed up and removed")
        except Exception as backup_error:
            logger.error(f"Failed to backup corrupted file: {backup_error}")
    except Exception as e:
        logger.error(f"Error loading sessions: {str(e)}")

def cleanup_old_sessions():
    """Remove sessions older than 24 hours"""
    try:
        cutoff_time = datetime.now().timestamp() - (24 * 60 * 60)  # 24 hours ago
        sessions_to_remove = []
        
        for session_id, session_data in active_sessions.items():
            if 'last_activity' in session_data:
                if isinstance(session_data['last_activity'], datetime):
                    last_activity_timestamp = session_data['last_activity'].timestamp()
                else:
                    last_activity_timestamp = datetime.fromisoformat(session_data['last_activity']).timestamp()
                
                if last_activity_timestamp < cutoff_time:
                    sessions_to_remove.append(session_id)
        
        for session_id in sessions_to_remove:
            del active_sessions[session_id]
            logger.info(f"Cleaned up old session: {session_id}")
        
        if sessions_to_remove:
            save_sessions_to_file()
            
    except Exception as e:
        logger.error(f"Error cleaning up sessions: {str(e)}")

def log_session_state(session_id, action, details=""):
    """Log session state changes for debugging"""
    session_info = active_sessions.get(session_id, {})
    user_count = len(session_info.get('users', {}))
    logger.info(f"SESSION {action}: {session_id} | Users: {user_count} | {details}")
    
    # Save sessions to file after each state change
    save_sessions_to_file()

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
    
    # Get the same network IP that the QR code uses
    base_url = None
    is_local_testing = os.environ.get('LOCAL_TESTING', 'false').lower() == 'true'
    
    if is_local_testing:
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            base_url = f'http://{local_ip}:5001'
        except Exception as e:
            logger.warning(f"Could not detect local IP, falling back to localhost: {e}")
            base_url = 'http://127.0.0.1:5001'
    else:
        base_url = 'https://privilage-walk.onrender.com'
    
    return render_template('instructor.html', 
                         session_id=session_id,
                         session_name="Privilege Walk Session",
                         base_url=base_url)

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
    
    # Check if we're in local testing mode
    is_local_testing = os.environ.get('LOCAL_TESTING', 'false').lower() == 'true'
    
    if is_local_testing:
        # Detect local network IP address for development
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            base_url = f'http://{local_ip}:5001'
            logger.info(f"Local testing mode - using network IP: {base_url}")
        except Exception as e:
            logger.warning(f"Could not detect local IP, falling back to localhost: {e}")
            base_url = 'http://localhost:5001'
    else:
        # Production mode - use fixed Render URL
        base_url = 'https://privilage-walk.onrender.com'
        logger.info("Production mode - using Render URL")
    
    join_url = f'{base_url}/join/{session_id}'
    
    # Create QR code pointing to the correct URL
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(join_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
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
def submit_answer():
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
    
    # Update accumulated position based on answer
    if answer == 'agree':
        user_data['position'] += 1
    elif answer == 'disagree':
        user_data['position'] -= 1
    
    log_session_state(session_id, "ANSWER_SUBMITTED", f"User: {username}, Answer: {answer}, Accumulated Position: {user_data['position']}")
    
    # Check if all users have answered the current question
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

@app.route('/api/user_answers/<session_id>')
def get_user_answers(session_id):
    """Get current user answer status for the current question"""
    if session_id not in active_sessions:
        return jsonify({'error': 'Session not found'}), 404
    
    session_data = active_sessions[session_id]
    current_q = session_data['current_question']
    
    user_answers = {}
    for username, user_data in session_data['users'].items():
        # User has answered if they have more answers than current question
        has_answered = len(user_data.get('answers', [])) > current_q
        user_answers[username] = {
            'answered': has_answered,
            'answer_count': len(user_data.get('answers', [])),
            'current_question': current_q
        }
    
    return jsonify({
        'user_answers': user_answers,
        'current_question': current_q,
        'total_questions': len(session_data['questions'])
    })

@app.route('/api/advance_question/<session_id>', methods=['POST'])
def advance_question(session_id):
    """Manually advance to the next question (instructor control)"""
    if session_id not in active_sessions:
        return jsonify({'error': 'Session not found'}), 404
    
    session_data = active_sessions[session_id]
    
    if session_data['status'] != 'active':
        return jsonify({'error': 'Session is not active'}), 400
    
    current_q = session_data['current_question']
    questions = session_data['questions']
    
    # Check if we can advance
    if current_q >= len(questions) - 1:
        return jsonify({'error': 'Already at the last question'}), 400
    
    # Check if all users have answered the current question
    all_answered = True
    for username, user_data in session_data['users'].items():
        if len(user_data.get('answers', [])) <= current_q:
            all_answered = False
            break
    
    if not all_answered:
        return jsonify({'error': 'Not all users have answered the current question'}), 400
    
    # Advance to next question
    session_data['current_question'] = current_q + 1
    session_data['last_activity'] = datetime.now().isoformat()
    
    log_session_state(session_id, "QUESTION_ADVANCED", f"Q{current_q + 1} -> Q{current_q + 2}")
    
    return jsonify({
        'success': True,
        'new_question': current_q + 2,
        'total_questions': len(questions)
    })

@app.route('/api/rankings/<session_id>')
def get_rankings(session_id):
    """Get current user rankings for a session"""
    if session_id not in active_sessions:
        return jsonify({'error': 'Session not found'}), 404
    
    session_data = active_sessions[session_id]
    
    if session_data['status'] != 'active':
        return jsonify({'error': 'Session is not active'}), 400
    
    rankings = calculate_user_rankings(session_data)
    
    return jsonify({
        'rankings': rankings,
        'current_question': session_data['current_question'],
        'total_questions': len(session_data['questions'])
    })

@app.route('/health')
def health_check():
    """Health check endpoint for Render"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'active_sessions': len(active_sessions),
        'total_users': sum(len(session.get('users', {})) for session in active_sessions.values())
    })

@app.route('/cleanup')
def cleanup_endpoint():
    """Endpoint to manually trigger session cleanup"""
    try:
        cleanup_old_sessions()
        return jsonify({
            'status': 'success',
            'message': 'Session cleanup completed',
            'active_sessions': len(active_sessions),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

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

def calculate_user_rankings(session_data):
    """Calculate user rankings based on accumulated scores (highest score = rank 1)"""
    users = session_data['users']
    if not users:
        return {}
    
    # Sort users by position (highest first for rank 1)
    sorted_users = sorted(users.items(), key=lambda x: x[1]['position'], reverse=True)
    
    rankings = {}
    for rank, (username, user_data) in enumerate(sorted_users, 1):
        rankings[username] = {
            'rank': rank,
            'position': user_data['position'],
            'total_users': len(users)
        }
    
    return rankings

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    logger.info(f"Starting Flask app on port {port}")
    cleanup_old_sessions()  # Clean up old sessions first
    load_sessions_from_file() # Load sessions from file on startup
    app.run(host='0.0.0.0', port=port, debug=False) 