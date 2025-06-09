import logging
import logging.handlers
import os
import json
from datetime import datetime
from typing import Dict, Any

class JSONFormatter(logging.Formatter):
    """Custom JSON formatter cho structured logging"""
    
    def format(self, record):
        """Format log record thành JSON"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Thêm exception info nếu có
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Thêm extra fields nếu có
        for key, value in record.__dict__.items():
            if key not in ('name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
                          'module', 'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
                          'thread', 'threadName', 'processName', 'process', 'exc_info', 'exc_text',
                          'stack_info', 'getMessage'):
                log_entry[key] = value
        
        return json.dumps(log_entry, ensure_ascii=False)

class RequestLogger:
    """Logger riêng cho HTTP requests"""
    
    def __init__(self):
        self.logger = logging.getLogger('requests')
    
    def log_request(self, request, response, duration: float):
        """Log HTTP request/response"""
        self.logger.info(
            "HTTP Request",
            extra={
                "method": request.method,
                "url": request.url,
                "remote_addr": request.remote_addr,
                "user_agent": request.headers.get('User-Agent'),
                "status_code": response.status_code,
                "duration_ms": round(duration * 1000, 2),
                "content_length": response.content_length or 0
            }
        )

class SecurityLogger:
    """Logger riêng cho security events"""
    
    def __init__(self):
        self.logger = logging.getLogger('security')
    
    def log_rate_limit_exceeded(self, remote_addr: str, endpoint: str, limit: str):
        """Log rate limit violations"""
        self.logger.warning(
            "Rate limit exceeded",
            extra={
                "remote_addr": remote_addr,
                "endpoint": endpoint,
                "limit": limit,
                "event_type": "rate_limit_exceeded"
            }
        )
    
    def log_validation_error(self, remote_addr: str, endpoint: str, error: str):
        """Log input validation errors"""
        self.logger.warning(
            "Input validation error",
            extra={
                "remote_addr": remote_addr,
                "endpoint": endpoint,
                "error": error,
                "event_type": "validation_error"
            }
        )
    
    def log_authentication_failure(self, remote_addr: str, reason: str):
        """Log authentication failures"""
        self.logger.error(
            "Authentication failure",
            extra={
                "remote_addr": remote_addr,
                "reason": reason,
                "event_type": "auth_failure"
            }
        )

class PerformanceLogger:
    """Logger riêng cho performance monitoring"""
    
    def __init__(self):
        self.logger = logging.getLogger('performance')
    
    def log_slow_query(self, query: str, duration: float, params: Dict = None):
        """Log slow database queries"""
        self.logger.warning(
            "Slow database query",
            extra={
                "query": query[:200],  # Truncate long queries
                "duration_ms": round(duration * 1000, 2),
                "params": params,
                "event_type": "slow_query"
            }
        )
    
    def log_cache_miss(self, cache_key: str, operation: str):
        """Log cache misses"""
        self.logger.info(
            "Cache miss",
            extra={
                "cache_key": cache_key,
                "operation": operation,
                "event_type": "cache_miss"
            }
        )
    
    def log_memory_usage(self, memory_mb: float, process_name: str):
        """Log high memory usage"""
        self.logger.warning(
            "High memory usage",
            extra={
                "memory_mb": memory_mb,
                "process_name": process_name,
                "event_type": "high_memory"
            }
        )

def setup_logging(app):
    """Setup comprehensive logging system"""
    
    # Tạo thư mục logs
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler với colored output
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler với JSON format
    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, 'app.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(file_handler)
    
    # Error file handler
    error_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, 'error.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(error_handler)
    
    # Separate loggers cho different components
    loggers_config = {
        'requests': {
            'level': logging.INFO,
            'file': 'requests.log',
            'max_bytes': 50*1024*1024,  # 50MB
            'backup_count': 10
        },
        'security': {
            'level': logging.WARNING,
            'file': 'security.log',
            'max_bytes': 20*1024*1024,  # 20MB
            'backup_count': 10
        },
        'performance': {
            'level': logging.INFO,
            'file': 'performance.log',
            'max_bytes': 30*1024*1024,  # 30MB
            'backup_count': 5
        },
        'face_detection': {
            'level': logging.INFO,
            'file': 'face_detection.log',
            'max_bytes': 20*1024*1024,  # 20MB
            'backup_count': 5
        },
        'database': {
            'level': logging.WARNING,
            'file': 'database.log',
            'max_bytes': 30*1024*1024,  # 30MB
            'backup_count': 5
        }
    }
    
    # Setup specialized loggers
    for logger_name, config in loggers_config.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(config['level'])
        logger.propagate = False  # Không propagate lên root logger
        
        # File handler cho logger này
        handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, config['file']),
            maxBytes=config['max_bytes'],
            backupCount=config['backup_count'],
            encoding='utf-8'
        )
        handler.setLevel(config['level'])
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
    
    # Disable werkzeug logging in production
    if not app.config.get('DEBUG', False):
        logging.getLogger('werkzeug').setLevel(logging.WARNING)
    
    app.logger.info("Logging system initialized successfully")
    return root_logger

# Global logger instances
request_logger = RequestLogger()
security_logger = SecurityLogger()
performance_logger = PerformanceLogger()

# Utility functions
def log_function_call(func_name: str, args: tuple = None, kwargs: dict = None, duration: float = None):
    """Log function calls for debugging"""
    logger = logging.getLogger('function_calls')
    logger.debug(
        f"Function call: {func_name}",
        extra={
            "function": func_name,
            "args_count": len(args) if args else 0,
            "kwargs_count": len(kwargs) if kwargs else 0,
            "duration_ms": round(duration * 1000, 2) if duration else None
        }
    )

def log_database_operation(operation: str, table: str, affected_rows: int = None, duration: float = None):
    """Log database operations"""
    logger = logging.getLogger('database')
    logger.info(
        f"Database operation: {operation}",
        extra={
            "operation": operation,
            "table": table,
            "affected_rows": affected_rows,
            "duration_ms": round(duration * 1000, 2) if duration else None
        }
    ) 