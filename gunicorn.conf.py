# Gunicorn configuration file for Render deployment
# This prevents worker timeouts and improves stability

# Server socket
bind = "0.0.0.0:10000"
backlog = 2048

# Worker processes
workers = 1  # Single worker for free tier to avoid session conflicts
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50

# Timeout settings - critical for SSE streams
timeout = 120  # Increase from default 30s
keepalive = 2
graceful_timeout = 30

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "privilege-walk"

# Preload app for better performance
preload_app = True

# Worker lifecycle
worker_tmp_dir = "/dev/shm"  # Use RAM for temp files
worker_exit_on_app_exit = False

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

def when_ready(server):
    """Log when server is ready"""
    server.log.info("Server is ready. Spawning workers")

def worker_int(worker):
    """Log worker interruption"""
    worker.log.info("worker received INT or QUIT signal")

def pre_fork(server, worker):
    """Log before forking worker"""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def post_fork(server, worker):
    """Log after forking worker"""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def post_worker_init(worker):
    """Log after worker initialization"""
    worker.log.info("Worker initialized (pid: %s)", worker.pid)

def worker_abort(worker):
    """Log worker abort"""
    worker.log.info("Worker aborted (pid: %s)", worker.pid)
