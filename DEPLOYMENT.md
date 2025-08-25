# 🚀 Production Deployment Guide

## 📋 Prerequisites

- Server with Python 3.8+ installed
- PM2 installed (`npm install -g pm2`)
- Access to server via SSH
- Port 5001 available (or change in config)

## 🔧 Server Setup Steps

### 1. Upload Code
```bash
# Upload your project folder to the server
scp -r Privilage_walk/ user@your-server:/path/to/apps/
```

### 2. SSH into Server
```bash
ssh user@your-server
cd /path/to/apps/Privilage_walk
```

### 3. Run Deployment Script
```bash
chmod +x deploy.sh
./deploy.sh
```

### 4. Edit Configuration
```bash
nano config.json
# Change "YOUR_SERVER_IP_HERE" to your actual server IP
```

### 5. Start with PM2
```bash
pm2 start ecosystem.config.js
pm2 save
pm2 startup
```

## 📊 PM2 Management Commands

```bash
# Check status
pm2 status

# View logs
pm2 logs privilege-walk

# Restart app
pm2 restart privilege-walk

# Stop app
pm2 stop privilege-walk

# Delete app
pm2 delete privilege-walk

# Save PM2 configuration
pm2 save

# Set PM2 to start on boot
pm2 startup
```

## 🌐 Access Your App

- **Instructor View**: `http://YOUR_SERVER_IP:5001/`
- **Students**: Scan QR code from instructor view

## 🔒 Security Considerations

- **Firewall**: Ensure port 5001 is open
- **HTTPS**: Consider adding SSL certificate
- **Domain**: You can point a domain to your server IP

## 🚨 Troubleshooting

### Port Already in Use
```bash
# Check what's using port 5001
sudo netstat -tlnp | grep :5001

# Kill process if needed
sudo kill -9 <PID>
```

### PM2 Issues
```bash
# Reset PM2
pm2 kill
pm2 start ecosystem.config.js
```

### Python Dependencies
```bash
# Reinstall dependencies
pip3 install -r requirements.txt --force-reinstall
```

## 📁 File Structure After Deployment

```
Privilage_walk/
├── app.py                 # Main Flask app
├── config.json            # Server configuration
├── questions.json         # Privilege walk questions
├── gunicorn_config.py     # Gunicorn settings
├── wsgi.py               # WSGI entry point
├── ecosystem.config.js    # PM2 configuration
├── requirements.txt       # Python dependencies
├── logs/                 # Application logs
└── templates/            # HTML templates
```

## 🔄 Updates

To update your application:

1. Upload new code
2. Restart with PM2: `pm2 restart privilege-walk`
3. Check logs: `pm2 logs privilege-walk`

## 💡 Tips

- **Monitoring**: Use `pm2 monit` for real-time monitoring
- **Logs**: Check logs in `./logs/` directory
- **Backup**: Keep backup of your config.json
- **Testing**: Test locally before deploying 