# Gunicorn settings, picked up automatically by `gunicorn app:app`.
#
# All live classroom state is held in memory in a single process, so there
# must be exactly ONE worker process. Concurrency comes from threads instead,
# which is plenty for short polling requests from several classes at once.
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
workers = 1
worker_class = 'gthread'
threads = int(os.environ.get('GUNICORN_THREADS', '32'))
timeout = 60
graceful_timeout = 20
keepalive = 30
accesslog = None  # polling would flood the logs; app logs state changes instead
