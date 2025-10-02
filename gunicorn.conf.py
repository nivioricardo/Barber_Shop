# Configurações do Gunicorn
import multiprocessing

# Número de workers (ajuste conforme necessário)
workers = multiprocessing.cpu_count() * 2 + 1

# Endereço e porta
bind = "0.0.0.0:10000"

# Timeout (aumente se necessário)
timeout = 120

# Logs
accesslog = "-"
errorlog = "-"

# Configurações de performance
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 100