#!/bin/bash

# Privilege Walk Deployment Script
# Run this on your server after uploading the code

echo "🚀 Deploying Privilege Walk Application..."

# Create logs directory
mkdir -p logs

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip3 install -r requirements.txt

# Install Gunicorn if not already installed
echo "🔧 Installing Gunicorn..."
pip3 install gunicorn

# Create production config
echo "⚙️  Creating production configuration..."
cat > config.json << EOF
{
  "server": {
    "host": "0.0.0.0",
    "port": 5001,
    "debug": false
  },
  "network": {
    "local_testing": false,
    "local_ip": "192.168.1.9",
    "server_domain": "YOUR_SERVER_IP_HERE"
  },
  "questions_file": "questions.json"
}
EOF

echo "✅ Please edit config.json and set your server IP address!"
echo "🌐 Then run: pm2 start ecosystem.config.js"
echo "📊 Monitor with: pm2 status"
echo "🔄 Restart with: pm2 restart privilege-walk"
echo "⏹️  Stop with: pm2 stop privilege-walk" 