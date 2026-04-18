import multiprocessing
import os

bind = os.getenv('BIND_ADDRESS', f"0.0.0.0:{os.getenv('PORT', '8000')}")
workers = 2
threads = 2
worker_class = 'sync'       # ← sync for WSGI/Django, never uvicorn
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50
timeout = 120
keepalive = 2
accesslog = '-'
errorlog = '-'
loglevel = 'info'
capture_output = True
enable_stdio_inheritance = True
reload = False
preload_app = True

def on_starting(server):
    pass

def on_reload(server):
    pass

def when_ready(server):
    pass

def pre_fork(server, worker):
    pass

def post_fork(server, worker):
    pass

def pre_exec(server):
    pass

def pre_request(worker, req):
    pass

def post_request(worker, req, environ, resp):
    pass

def child_exit(server, worker):
    pass

def worker_exit(server, worker):
    pass

def nworkers_changed(server, new_value, old_value):
    pass

def on_exit(server):
    pass