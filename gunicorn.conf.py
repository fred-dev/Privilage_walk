# Gunicorn configuration for Render deployment
# Using non-blocking workers to handle SSE streams properly

# Server socket
bind = "0.0.0.0:10000"
backlog = 2048

# Worker processes - CRITICAL: Use non-blocking workers for SSE
workers = 1  # Single worker for free tier
worker_class = "gevent"  # Non-blocking worker that can handle multiple connections
worker_connections = 1000

# Timeout settings - keep default 30s since we're using non-blocking workers
timeout = 30
graceful_timeout = 30

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Process naming
proc_name = "privilege-walk"

# Preload app for better performance
preload_app = True

# Worker lifecycle
max_requests = 1000
max_requests_jitter = 50
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
