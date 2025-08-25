#!/usr/bin/env python3
"""
Comprehensive tests for Privilege Walk application
Run with: python -m pytest test_app.py -v
"""

import pytest
import json
import tempfile
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import sys
import os

# Add the current directory to Python path to import app
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, active_sessions, load_questions, calculate_user_rankings, cleanup_old_sessions

@pytest.fixture
def client():
    """Create a test client for the Flask app"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def sample_session_data():
    """Sample session data for testing"""
    return {
        'session_id': 'test_session_123',
        'session_name': 'Test Session',
        'status': 'waiting',
        'current_question': 0,
        'questions': [
            "I have rarely been judged negatively or discriminated against because of my body size.",
            "My mental health is generally robust, and it has never seriously limited my opportunities.",
            "I am neurotypical, and my ways of thinking and learning are usually supported in school or work."
        ],
        'users': {
            'student1': {
                'username': 'student1',
                'position': 0,
                'answers': []
            },
            'student2': {
                'username': 'student2',
                'position': 0,
                'answers': []
            }
        },
        'created_at': datetime.now().isoformat(),
        'last_activity': datetime.now().isoformat()
    }

@pytest.fixture
def sample_questions():
    """Sample questions for testing"""
    return [
        "I have rarely been judged negatively or discriminated against because of my body size.",
        "My mental health is generally robust, and it has never seriously limited my opportunities.",
        "I am neurotypical, and my ways of thinking and learning are usually supported in school or work."
    ]

class TestAppInitialization:
    """Test app initialization and basic setup"""
    
    def test_app_creation(self):
        """Test that the Flask app is created correctly"""
        assert app is not None
        assert hasattr(app, 'route')
    
    def test_load_questions(self, sample_questions):
        """Test that questions can be loaded"""
        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = json.dumps({
                'questions': sample_questions
            })
            questions = load_questions()
            assert len(questions) == 3
            assert "body size" in questions[0]
    
    def test_load_questions_fallback(self):
        """Test that questions fallback to defaults if file not found"""
        with patch('builtins.open', side_effect=FileNotFoundError):
            questions = load_questions()
            assert len(questions) == 12  # Default questions
            assert "body size" in questions[0]

class TestSessionManagement:
    """Test session creation and management"""
    
    def test_create_session(self, client):
        """Test creating a new session"""
        response = client.post('/create_session', data={'session_name': 'Test Session'})
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'session_id' in data
        assert data['session_name'] == 'Test Session'
    
    def test_create_session_missing_name(self, client):
        """Test creating session without name"""
        response = client.post('/create_session', data={})
        assert response.status_code == 400
    
    def test_instructor_view(self, client, sample_session_data):
        """Test instructor view page loads"""
        # Add session to active_sessions
        active_sessions[sample_session_data['session_id']] = sample_session_data
        
        response = client.get(f'/instructor/{sample_session_data["session_id"]}')
        assert response.status_code == 200
        assert b'Privilege Walk Session' in response.data
    
    def test_instructor_view_invalid_session(self, client):
        """Test instructor view with invalid session ID"""
        response = client.get('/instructor/invalid_session')
        assert response.status_code == 404

class TestStudentJoin:
    """Test student joining functionality"""
    
    def test_student_join_page(self, client, sample_session_data):
        """Test student join page loads"""
        active_sessions[sample_session_data['session_id']] = sample_session_data
        
        response = client.get(f'/join/{sample_session_data["session_id"]}')
        assert response.status_code == 200
        assert b'Join Session' in response.data
    
    def test_student_join_invalid_session(self, client):
        """Test student join with invalid session"""
        response = client.get('/join/invalid_session')
        assert response.status_code == 404
    
    def test_student_join_post(self, client, sample_session_data):
        """Test student joining a session"""
        active_sessions[sample_session_data['session_id']] = sample_session_data
        
        response = client.post(f'/join/{sample_session_data["session_id"]}', 
                              data={'username': 'newstudent'})
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
        
        # Check user was added to session
        session = active_sessions[sample_session_data['session_id']]
        assert 'newstudent' in session['users']
    
    def test_student_join_duplicate_username(self, client, sample_session_data):
        """Test student join with duplicate username"""
        active_sessions[sample_session_data['session_id']] = sample_session_data
        
        response = client.post(f'/join/{sample_session_data["session_id"]}', 
                              data={'username': 'student1'})
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'already exists' in data['error']

class TestSessionControl:
    """Test session start/stop functionality"""
    
    def test_start_session(self, client, sample_session_data):
        """Test starting a session"""
        active_sessions[sample_session_data['session_id']] = sample_session_data
        
        response = client.post(f'/api/start_session/{sample_session_data["session_id"]}')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
        
        # Check session status changed
        session = active_sessions[sample_session_data['session_id']]
        assert session['status'] == 'active'
    
    def test_start_session_invalid(self, client):
        """Test starting invalid session"""
        response = client.post('/api/start_session/invalid_session')
        assert response.status_code == 404
    
    def test_stop_session(self, client, sample_session_data):
        """Test stopping a session"""
        sample_session_data['status'] = 'active'
        active_sessions[sample_session_data['session_id']] = sample_session_data
        
        response = client.post(f'/api/stop_session/{sample_session_data["session_id"]}')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
        
        # Check session status changed
        session = active_sessions[sample_session_data['session_id']]
        assert session['status'] == 'finished'

class TestAnswerSubmission:
    """Test student answer submission"""
    
    def test_submit_answer(self, client, sample_session_data):
        """Test student submitting an answer"""
        sample_session_data['status'] = 'active'
        active_sessions[sample_session_data['session_id']] = sample_session_data
        
        response = client.post(f'/api/submit_answer/{sample_session_data["session_id"]}',
                              json={'username': 'student1', 'answer': 'agree'})
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
        
        # Check answer was recorded
        session = active_sessions[sample_session_data['session_id']]
        user = session['users']['student1']
        assert len(user['answers']) == 1
        assert user['answers'][0] == 'agree'
        assert user['position'] == 1  # +1 for agree
    
    def test_submit_answer_disagree(self, client, sample_session_data):
        """Test student submitting disagree answer"""
        sample_session_data['status'] = 'active'
        active_sessions[sample_session_data['session_id']] = sample_session_data
        
        response = client.post(f'/api/submit_answer/{sample_session_data["session_id"]}',
                              json={'username': 'student1', 'answer': 'disagree'})
        assert response.status_code == 200
        
        # Check position decreased
        session = active_sessions[sample_session_data['session_id']]
        user = session['users']['student1']
        assert user['position'] == -1  # -1 for disagree
    
    def test_submit_answer_invalid_session(self, client):
        """Test submitting answer to invalid session"""
        response = client.post('/api/submit_answer/invalid_session',
                              json={'username': 'student1', 'answer': 'agree'})
        assert response.status_code == 404
    
    def test_submit_answer_invalid_user(self, client, sample_session_data):
        """Test submitting answer with invalid username"""
        sample_session_data['status'] = 'active'
        active_sessions[sample_session_data['session_id']] = sample_session_data
        
        response = client.post(f'/api/submit_answer/{sample_session_data["session_id"]}',
                              json={'username': 'invalid_user', 'answer': 'agree'})
        assert response.status_code == 400

class TestQuestionProgression:
    """Test question progression and advancement"""
    
    def test_automatic_question_progression(self, client, sample_session_data):
        """Test that questions automatically progress when all users answer"""
        sample_session_data['status'] = 'active'
        active_sessions[sample_session_data['session_id']] = sample_session_data
        
        # All users answer first question
        for username in sample_session_data['users']:
            response = client.post(f'/api/submit_answer/{sample_session_data["session_id"]}',
                                  json={'username': username, 'answer': 'agree'})
            assert response.status_code == 200
        
        # Check question progressed
        session = active_sessions[sample_session_data['session_id']]
        assert session['current_question'] == 1
    
    def test_manual_question_advancement(self, client, sample_session_data):
        """Test manual question advancement by instructor"""
        sample_session_data['status'] = 'active'
        # Make sure all users have answered current question
        for username in sample_session_data['users']:
            sample_session_data['users'][username]['answers'] = ['agree']
        active_sessions[sample_session_data['session_id']] = sample_session_data
        
        response = client.post(f'/api/advance_question/{sample_session_data["session_id"]}',
                              json={'session_id': sample_session_data['session_id']})
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
        
        # Check question advanced
        session = active_sessions[sample_session_data['session_id']]
        assert session['current_question'] == 1
    
    def test_advance_question_not_all_answered(self, client, sample_session_data):
        """Test that question can't advance if not all users answered"""
        sample_session_data['status'] = 'active'
        active_sessions[sample_session_data['session_id']] = sample_session_data
        
        response = client.post(f'/api/advance_question/{sample_session_data["session_id"]}',
                              json={'session_id': sample_session_data['session_id']})
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'Not all users have answered' in data['error']

class TestRankingsAndScoring:
    """Test user rankings and scoring system"""
    
    def test_calculate_user_rankings(self, sample_session_data):
        """Test user ranking calculation"""
        # Set different positions for users
        sample_session_data['users']['student1']['position'] = 2
        sample_session_data['users']['student2']['position'] = -1
        
        rankings = calculate_user_rankings(sample_session_data)
        
        assert 'student1' in rankings
        assert 'student2' in rankings
        assert rankings['student1']['rank'] == 1  # Highest score
        assert rankings['student2']['rank'] == 2  # Lower score
        assert rankings['student1']['position'] == 2
        assert rankings['student2']['position'] == -1
    
    def test_get_rankings_api(self, client, sample_session_data):
        """Test rankings API endpoint"""
        sample_session_data['status'] = 'active'
        active_sessions[sample_session_data['session_id']] = sample_session_data
        
        response = client.get(f'/api/rankings/{sample_session_data["session_id"]}')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'rankings' in data
        assert 'current_question' in data
        assert 'total_questions' in data

class TestUserAnswers:
    """Test user answer tracking"""
    
    def test_get_user_answers(self, client, sample_session_data):
        """Test getting user answer status"""
        sample_session_data['status'] = 'active'
        # Add some answers
        sample_session_data['users']['student1']['answers'] = ['agree']
        active_sessions[sample_session_data['session_id']] = sample_session_data
        
        response = client.get(f'/api/user_answers/{sample_session_data["session_id"]}')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'user_answers' in data
        assert 'student1' in data['user_answers']
        assert data['user_answers']['student1']['answered'] == True
        assert data['user_answers']['student2']['answered'] == False

class TestSessionPersistence:
    """Test session persistence and cleanup"""
    
    def test_session_cleanup(self):
        """Test cleanup of old sessions"""
        # Create old session
        old_session = {
            'session_id': 'old_session',
            'last_activity': (datetime.now() - timedelta(hours=25)).isoformat(),
            'users': {},
            'questions': ['test'],
            'current_question': 0,
            'status': 'finished'
        }
        active_sessions['old_session'] = old_session
        
        # Create recent session
        recent_session = {
            'session_id': 'recent_session',
            'last_activity': datetime.now().isoformat(),
            'users': {},
            'questions': ['test'],
            'current_question': 0,
            'status': 'active'
        }
        active_sessions['recent_session'] = recent_session
        
        initial_count = len(active_sessions)
        cleanup_old_sessions()
        
        # Old session should be removed, recent kept
        assert 'old_session' not in active_sessions
        assert 'recent_session' in active_sessions
        assert len(active_sessions) == initial_count - 1

class TestHealthAndUtilities:
    """Test health check and utility endpoints"""
    
    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get('/health')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'status' in data
        assert data['status'] == 'healthy'
        assert 'active_sessions' in data
    
    def test_cleanup_endpoint(self, client):
        """Test manual cleanup endpoint"""
        response = client.get('/cleanup')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'status' in data

class TestErrorHandling:
    """Test error handling and edge cases"""
    
    def test_invalid_json_submission(self, client, sample_session_data):
        """Test handling of invalid JSON in answer submission"""
        sample_session_data['status'] = 'active'
        active_sessions[sample_session_data['session_id']] = sample_session_data
        
        response = client.post(f'/api/submit_answer/{sample_session_data["session_id"]}',
                              data='invalid json',
                              content_type='application/json')
        assert response.status_code == 400
    
    def test_missing_fields_in_answer(self, client, sample_session_data):
        """Test handling of missing fields in answer submission"""
        sample_session_data['status'] = 'active'
        active_sessions[sample_session_data['session_id']] = sample_session_data
        
        response = client.post(f'/api/submit_answer/{sample_session_data["session_id"]}',
                              json={'username': 'student1'})  # Missing answer
        assert response.status_code == 400

def run_tests():
    """Run all tests and report results"""
    print("🧪 Running Privilege Walk Application Tests...")
    print("=" * 50)
    
    # Import pytest and run tests
    try:
        import pytest
        pytest.main([__file__, '-v', '--tb=short'])
    except ImportError:
        print("❌ pytest not installed. Install with: pip install pytest")
        print("Running basic tests...")
        
        # Basic test runner
        test_functions = [func for func in globals().values() 
                         if callable(func) and func.__name__.startswith('test_')]
        
        passed = 0
        failed = 0
        
        for test_func in test_functions:
            try:
                test_func()
                print(f"✅ {test_func.__name__}")
                passed += 1
            except Exception as e:
                print(f"❌ {test_func.__name__}: {str(e)}")
                failed += 1
        
        print(f"\n📊 Test Results: {passed} passed, {failed} failed")
        
        if failed == 0:
            print("🎉 All tests passed!")
        else:
            print("⚠️  Some tests failed. Please fix issues before pushing.")

if __name__ == '__main__':
    run_tests()
