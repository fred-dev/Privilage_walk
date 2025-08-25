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

# In-memory storage for active sessions
active_sessions = {}

def log_session_state(session_id, action, details=""):
    """Log session state changes for debugging"""
    session_info = active_sessions.get(session_id, {})
    user_count = len(session_info.get('users', {}))
    logger.info(f"SESSION {action}: {session_id} | Users: {user_count} | {details}")

def notify_sse_clients(session_id, event_type, data):
    """Notify all SSE clients in a session about an event"""
    if session_id in active_sessions:
        # Add event to pending events
        if 'pending_events' not in active_sessions[session_id]:
            active_sessions[session_id]['pending_events'] = []

        active_sessions[session_id]['pending_events'].append({
            'type': event_type,
            'data': data,
            'timestamp': datetime.now().isoformat()
        })
        
        logger.info(f"SSE Event queued: {session_id} | {event_type} | {data}")

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
        'pending_events': []
    }
    
    log_session_state(session_id, "CREATED")
    return jsonify({'session_id': session_id})

@app.route('/instructor/<session_id>')
def instructor_view(session_id):
    """Instructor view for a session"""
    if session_id not in active_sessions:
        return "Session not found", 404
    
    log_session_state(session_id, "INSTRUCTOR_VIEW_ACCESSED")
    return render_template('instructor.html', session_id=session_id)

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
        
        # Notify instructor about new user
        notify_sse_clients(session_id, 'user_joined', {'username': username})
    
    return render_template('student.html', session_id=session_id, username=username)

@app.route('/qr/<session_id>')
def qr_code(session_id):
    """Generate QR code for session"""
    if session_id not in active_sessions:
        return "Session not found", 404
    
    # Create QR code pointing to the Render domain
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(f'https://privilage-walk.onrender.com/join/{session_id}')
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
    
    # Notify all clients about new user
    notify_sse_clients(session_id, 'user_joined', {'username': username})
    
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
    
    log_session_state(session_id, "STARTED")
    
    # Get first question
    questions = session_data['questions']
    first_question = questions[0] if questions else "No questions available"
    
    # Notify all clients that session has started
    notify_sse_clients(session_id, 'session_started', {
        'question': first_question,
        'question_number': 1,
        'total_questions': len(questions)
    })
    
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
            # Next question
            next_question = questions[session_data['current_question']]
            notify_sse_clients(session_id, 'next_question', {
                'question': next_question,
                'question_number': session_data['current_question'] + 1,
                'total_questions': len(questions)
            })
            
            # Reset answers for next question
            for user in session_data['users'].values():
                user['answers'] = user['answers'][:session_data['current_question']]
        else:
            # Session finished
            session_data['status'] = 'finished'
            final_positions = {username: user['position'] for username, user in session_data['users'].items()}
            
            notify_sse_clients(session_id, 'session_finished', {
                'final_positions': final_positions
            })
            
            log_session_state(session_id, "FINISHED", f"Final positions: {final_positions}")
    
    # Send position update
    positions = {username: user['position'] for username, user in session_data['users'].items()}
    notify_sse_clients(session_id, 'position_update', {'positions': positions})
    
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
    
    # Clear pending events
    session_data['pending_events'] = []
    
    log_session_state(session_id, "RESET")
    
    # Notify all clients about reset
    notify_sse_clients(session_id, 'session_reset', {})
    
    return jsonify({'success': True})

@app.route('/stream/<session_id>')
def stream(session_id):
    """SSE stream endpoint for real-time updates"""
    if session_id not in active_sessions:
        logger.error(f"SSE stream attempt for non-existent session: {session_id}")
        return "Session not found", 404

    logger.info(f"SSE stream started for session: {session_id}")

    def generate():
        try:
            # Send initial connection message
            yield f"data: {json.dumps({'type': 'connected', 'session_id': session_id})}\n\n"
            logger.info(f"SSE connection established for session: {session_id}")

            # Keep track of last event sent
            last_event_index = 0

            # Keep connection alive and check for new events
            while True:
                try:
                    # Check for new events
                    if 'pending_events' in active_sessions[session_id]:
                        events = active_sessions[session_id]['pending_events']
                        while last_event_index < len(events):
                            event = events[last_event_index]
                            yield f"data: {json.dumps(event)}\n\n"
                            last_event_index += 1
                            logger.debug(f"SSE event sent: {session_id} | {event['type']}")

                    # Send keepalive every 15 seconds
                    yield f"data: {json.dumps({'type': 'keepalive', 'timestamp': datetime.now().isoformat()})}\n\n"
                    
                    # Simple sleep - Render will handle worker configuration
                    time.sleep(15)

                except GeneratorExit:
                    logger.info(f"SSE stream closed by client for session: {session_id}")
                    break
                except Exception as e:
                    logger.error(f"SSE stream error for session {session_id}: {str(e)}")
                    break

        except Exception as e:
            logger.error(f"SSE stream generation error for session {session_id}: {str(e)}")

    return Response(generate(), mimetype='text/event-stream')

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
            return questions
    except Exception as e:
        logger.error(f"Error loading questions: {str(e)}")
        return ["Sample question 1", "Sample question 2"]

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    logger.info(f"Starting Flask app on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False) 