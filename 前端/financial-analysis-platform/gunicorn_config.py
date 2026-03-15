# Gunicorn配置文件

# 绑定地址和端口
bind = "0.0.0.0:8000"

# 工作进程数
workers = 4

# 工作模式
worker_class = "sync"

# 超时时间
timeout = 120

# 日志配置
accesslog = "./logs/access.log"
errorlog = "./logs/error.log"
loglevel = "info"

# 进程名称
proc_name = "financial_analysis"

# 最大请求数
max_requests = 1000
max_requests_jitter = 50