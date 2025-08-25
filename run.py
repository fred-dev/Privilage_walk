#!/usr/bin/env python3
"""
Privilege Walk Application Startup Script
Uses UV environment for dependency management
"""

import sys
import os
import subprocess

def check_uv_environment():
    """Check if UV environment is properly set up"""
    venv_path = os.path.join(os.path.dirname(__file__), '.venv')
    if not os.path.exists(venv_path):
        print("❌ Error: UV environment not found")
        print("Please run 'uv sync' to create the environment")
        sys.exit(1)
    
    # Check if we're in the UV environment
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("✅ Running in virtual environment")
    else:
        print("⚠️  Not in virtual environment, activating UV environment...")
        # Try to activate the UV environment
        python_path = os.path.join(venv_path, 'bin', 'python')
        if os.name == 'nt':  # Windows
            python_path = os.path.join(venv_path, 'Scripts', 'python.exe')
        
        if os.path.exists(python_path):
            print(f"🔄 Restarting with UV environment: {python_path}")
            # Restart the script with the UV environment
            os.execv(python_path, [python_path] + sys.argv)
        else:
            print("❌ Could not find Python in UV environment")
            sys.exit(1)

def main():
    """Main startup function"""
    print("🚶‍♂️ Privilege Walk Application")
    print("=" * 40)
    
    # Check UV environment
    check_uv_environment()
    
    print("\n🚀 Starting the application...")
    print("📱 Open your browser to: http://localhost:5001")
    print("🔗 Students will connect via your computer's IP address")
    print("\n💡 Tips:")
    print("   - Make sure all devices are on the same network")
    print("   - Test the QR code with one student first")
    print("   - Press Ctrl+C to stop the server")
    print("\n" + "=" * 40)
    
    # Start the Flask application
    try:
        from app import app, socketio
        socketio.run(app, debug=True, host='0.0.0.0', port=5001)
    except KeyboardInterrupt:
        print("\n\n👋 Application stopped by user")
    except Exception as e:
        print(f"\n❌ Error starting application: {e}")
        print("Please check the error message above and try again")

if __name__ == "__main__":
    main() 