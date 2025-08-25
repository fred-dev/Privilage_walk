module.exports = {
  apps: [{
    name: 'privilege-walk',
    script: 'gunicorn',
    args: '--config gunicorn_config.py wsgi:app',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
    env: {
      NODE_ENV: 'production',
      PYTHONPATH: '.',
      FLASK_ENV: 'production'
    },
    env_production: {
      NODE_ENV: 'production',
      PYTHONPATH: '.',
      FLASK_ENV: 'production'
    },
    error_file: './logs/err.log',
    out_file: './logs/out.log',
    log_file: './logs/combined.log',
    time: true
  }]
}; 