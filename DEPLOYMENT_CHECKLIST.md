# 🚀 Quick Deployment Checklist

## ✅ Pre-Deployment
- [ ] Test application locally
- [ ] Ensure all files are committed
- [ ] Note your server's IP address

## 📤 Upload to Server
- [ ] Upload entire `Privilage_walk/` folder to server
- [ ] SSH into server
- [ ] Navigate to project directory

## 🔧 Server Setup
- [ ] Run `chmod +x deploy.sh`
- [ ] Run `./deploy.sh`
- [ ] Edit `config.json` - set your server IP
- [ ] Install PM2 if not already installed: `npm install -g pm2`

## 🚀 Start Application
- [ ] Run `pm2 start ecosystem.config.js`
- [ ] Run `pm2 save`
- [ ] Run `pm2 startup` (optional - auto-start on boot)

## ✅ Verify Deployment
- [ ] Check `pm2 status`
- [ ] Visit `http://YOUR_SERVER_IP:5001/`
- [ ] Test QR code with phone
- [ ] Check logs: `pm2 logs privilege-walk`

## 🔄 Daily Operations
- **Start**: `pm2 start privilege-walk`
- **Stop**: `pm2 stop privilege-walk`
- **Restart**: `pm2 restart privilege-walk`
- **Status**: `pm2 status`
- **Logs**: `pm2 logs privilege-walk`
- **Monitor**: `pm2 monit`

## 🚨 Emergency
- **Kill all**: `pm2 kill`
- **Restart all**: `pm2 start ecosystem.config.js`
- **Check port**: `sudo netstat -tlnp | grep :5001` 