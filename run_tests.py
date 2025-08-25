#!/usr/bin/env python3
"""
Simple test runner for Privilege Walk application
Run with: python run_tests.py
"""

import sys
import os
import json
from datetime import datetime, timedelta

# Add the current directory to Python path to import app
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def run_basic_tests():
    """Run basic functionality tests without external dependencies"""
    print("🧪 Running Basic Privilege Walk Application Tests...")
    print("=" * 60)
    
    tests_passed = 0
    tests_failed = 0
    test_results = []
    
    # Test 1: App imports
    try:
        from app import app, active_sessions, load_questions, calculate_user_rankings
        print("✅ App imports successful")
        tests_passed += 1
        test_results.append(("App imports", "PASSED"))
    except Exception as e:
        print(f"❌ App imports failed: {e}")
        tests_failed += 1
        test_results.append(("App imports", f"FAILED: {e}"))
    
    # Test 2: Flask app creation
    try:
        assert app is not None
        assert hasattr(app, 'route')
        print("✅ Flask app creation successful")
        tests_passed += 1
        test_results.append(("Flask app creation", "PASSED"))
    except Exception as e:
        print(f"❌ Flask app creation failed: {e}")
        tests_failed += 1
        test_results.append(("Flask app creation", f"FAILED: {e}"))
    
    # Test 3: Questions loading
    try:
        questions = load_questions()
        assert len(questions) > 0
        assert isinstance(questions, list)
        print(f"✅ Questions loading successful ({len(questions)} questions)")
        tests_passed += 1
        test_results.append(("Questions loading", "PASSED"))
    except Exception as e:
        print(f"❌ Questions loading failed: {e}")
        tests_failed += 1
        test_results.append(("Questions loading", f"FAILED: {e}"))
    
    # Test 4: User rankings calculation
    try:
        sample_session = {
            'users': {
                'user1': {'position': 2, 'username': 'user1'},
                'user2': {'position': -1, 'username': 'user2'},
                'user3': {'position': 5, 'username': 'user3'}
            }
        }
        rankings = calculate_user_rankings(sample_session)
        assert len(rankings) == 3
        assert rankings['user3']['rank'] == 1  # Highest position
        assert rankings['user1']['rank'] == 2
        assert rankings['user2']['rank'] == 3  # Lowest position
        print("✅ User rankings calculation successful")
        tests_passed += 1
        test_results.append(("User rankings calculation", "PASSED"))
    except Exception as e:
        print(f"❌ User rankings calculation failed: {e}")
        tests_failed += 1
        test_results.append(("User rankings calculation", f"FAILED: {e}"))
    
    # Test 5: Session data structure
    try:
        from app import active_sessions
        assert isinstance(active_sessions, dict)
        print("✅ Session data structure valid")
        tests_passed += 1
        test_results.append(("Session data structure", "PASSED"))
    except Exception as e:
        print(f"❌ Session data structure failed: {e}")
        tests_failed += 1
        test_results.append(("Session data structure", f"FAILED: {e}"))
    
    # Test 6: Template files exist
    template_files = ['templates/index.html', 'templates/instructor.html', 'templates/student.html']
    for template in template_files:
        try:
            assert os.path.exists(template)
            print(f"✅ Template file exists: {template}")
            tests_passed += 1
            test_results.append((f"Template: {template}", "PASSED"))
        except Exception as e:
            print(f"❌ Template file missing: {template}")
            tests_failed += 1
            test_results.append((f"Template: {template}", f"FAILED: {e}"))
    
    # Test 7: Static files exist
    try:
        assert os.path.exists('app.py')
        assert os.path.exists('requirements.txt')
        print("✅ Core application files exist")
        tests_passed += 1
        test_results.append(("Core files", "PASSED"))
    except Exception as e:
        print(f"❌ Core files check failed: {e}")
        tests_failed += 1
        test_results.append(("Core files", f"FAILED: {e}"))
    
    # Test 8: Flask routes registration
    try:
        routes = [rule.rule for rule in app.url_map.iter_rules()]
        expected_routes = ['/', '/create_session', '/instructor/<session_id>', '/join/<session_id>']
        for route in expected_routes:
            if route == '/':
                assert '/' in routes
            else:
                route_base = route.split('<')[0]
                matching_routes = [r for r in routes if r.startswith(route_base)]
                assert len(matching_routes) > 0, f"Route {route} not found"
        print("✅ Flask routes registration successful")
        tests_passed += 1
        test_results.append(("Flask routes", "PASSED"))
    except Exception as e:
        print(f"❌ Flask routes check failed: {e}")
        tests_failed += 1
        test_results.append(("Flask routes", f"FAILED: {e}"))
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    for test_name, result in test_results:
        status = "✅" if "PASSED" in result else "❌"
        print(f"{status} {test_name}: {result}")
    
    print(f"\n🎯 Final Results: {tests_passed} passed, {tests_failed} failed")
    
    if tests_failed == 0:
        print("🎉 All tests passed! Application is ready for deployment.")
        return True
    else:
        print("⚠️  Some tests failed. Please fix issues before pushing to production.")
        return False

def run_advanced_tests():
    """Run more advanced tests if pytest is available"""
    try:
        import pytest
        print("\n🚀 Running advanced tests with pytest...")
        print("=" * 60)
        
        # Run pytest on the test file
        import subprocess
        result = subprocess.run([sys.executable, '-m', 'pytest', 'test_app.py', '-v'], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Advanced tests passed!")
            return True
        else:
            print("❌ Advanced tests failed:")
            print(result.stdout)
            print(result.stderr)
            return False
            
    except ImportError:
        print("ℹ️  pytest not available. Install with: pip install -r requirements-test.txt")
        return None

def main():
    """Main test runner"""
    print("🔍 Privilege Walk Application Test Suite")
    print("=" * 60)
    
    # Run basic tests
    basic_tests_passed = run_basic_tests()
    
    # Try to run advanced tests
    advanced_tests_result = run_advanced_tests()
    
    # Final recommendation
    print("\n" + "=" * 60)
    print("🎯 DEPLOYMENT RECOMMENDATION")
    print("=" * 60)
    
    if basic_tests_passed and (advanced_tests_result is None or advanced_tests_result):
        print("✅ READY FOR DEPLOYMENT")
        print("   All critical functionality tests passed.")
        print("   Application is stable and ready for production.")
    elif basic_tests_passed:
        print("⚠️  DEPLOYMENT WITH CAUTION")
        print("   Basic tests passed but advanced tests failed.")
        print("   Review advanced test failures before deploying.")
    else:
        print("❌ DO NOT DEPLOY")
        print("   Critical functionality tests failed.")
        print("   Fix all issues before pushing to production.")
    
    return basic_tests_passed

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
