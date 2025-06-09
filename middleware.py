from flask import request, g, jsonify
from functools import wraps
import time
import gzip
import json
from io import BytesIO
from logger_config import request_logger, security_logger, performance_logger

class RequestLoggingMiddleware:
    """Middleware để log tất cả HTTP requests"""
    
    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize middleware với Flask app"""
        app.before_request(self.before_request)
        app.after_request(self.after_request)
        app.teardown_appcontext(self.teardown_request)
    
    def before_request(self):
        """Ghi nhận thời gian bắt đầu request"""
        g.start_time = time.time()
        g.request_id = f"{request.remote_addr}_{int(time.time() * 1000)}"
        
        # Log request start
        performance_logger.logger.debug(
            "Request started",
            extra={
                "request_id": g.request_id,
                "method": request.method,
                "url": request.url,
                "remote_addr": request.remote_addr,
                "user_agent": request.headers.get('User-Agent', 'Unknown')
            }
        )
    
    def after_request(self, response):
        """Log request completion và performance metrics"""
        if hasattr(g, 'start_time'):
            duration = time.time() - g.start_time
            
            # Log request completion
            request_logger.log_request(request, response, duration)
            
            # Log slow requests
            if duration > 1.0:  # Requests slower than 1 second
                performance_logger.logger.warning(
                    "Slow request detected",
                    extra={
                        "request_id": getattr(g, 'request_id', 'unknown'),
                        "method": request.method,
                        "url": request.url,
                        "duration_ms": round(duration * 1000, 2),
                        "status_code": response.status_code
                    }
                )
            
            # Add performance headers
            response.headers['X-Response-Time'] = f"{round(duration * 1000, 2)}ms"
            response.headers['X-Request-ID'] = getattr(g, 'request_id', 'unknown')
        
        return response
    
    def teardown_request(self, exception=None):
        """Cleanup sau request"""
        if exception:
            performance_logger.logger.error(
                "Request failed with exception",
                extra={
                    "request_id": getattr(g, 'request_id', 'unknown'),
                    "exception": str(exception),
                    "method": request.method,
                    "url": request.url
                },
                exc_info=True
            )

class CompressionMiddleware:
    """Middleware để compress API responses"""
    
    def __init__(self, app=None, min_size=1024):
        self.app = app
        self.min_size = min_size
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize compression middleware"""
        app.after_request(self.compress_response)
    
    def compress_response(self, response):
        """Compress response nếu client hỗ trợ gzip"""
        
        # Chỉ compress JSON responses
        if (response.content_type and 
            'application/json' in response.content_type and
            len(response.data) > self.min_size):
            
            # Kiểm tra client có hỗ trợ gzip không
            accept_encoding = request.headers.get('Accept-Encoding', '')
            if 'gzip' in accept_encoding.lower():
                
                # Compress response data
                gzip_buffer = BytesIO()
                with gzip.GzipFile(fileobj=gzip_buffer, mode='wb') as gzip_file:
                    gzip_file.write(response.data)
                
                compressed_data = gzip_buffer.getvalue()
                
                # Chỉ sử dụng compressed version nếu nhỏ hơn
                if len(compressed_data) < len(response.data):
                    response.data = compressed_data
                    response.headers['Content-Encoding'] = 'gzip'
                    response.headers['Content-Length'] = len(compressed_data)
                    
                    # Log compression ratio
                    ratio = len(compressed_data) / len(response.data) * 100
                    performance_logger.logger.debug(
                        f"Response compressed: {ratio:.1f}% of original size"
                    )
        
        return response

class RateLimitMiddleware:
    """Enhanced rate limiting middleware"""
    
    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize rate limit middleware"""
        # Handle rate limit exceeded errors
        from flask_limiter.errors import RateLimitExceeded
        
        @app.errorhandler(RateLimitExceeded)
        def handle_rate_limit_exceeded(e):
            """Handle rate limit exceeded errors"""
            security_logger.log_rate_limit_exceeded(
                request.remote_addr,
                request.endpoint or request.path,
                str(e.limit)
            )
            
            return jsonify({
                "error": "Rate limit exceeded",
                "message": "Bạn đã vượt quá giới hạn số lượng request cho phép",
                "retry_after": getattr(e, 'retry_after', None)
            }), 429

class CacheControlMiddleware:
    """Middleware để thêm cache control headers"""
    
    def __init__(self, app=None):
        self.app = app
        self.cache_rules = {
            '/api/cameras': 300,  # Cache 5 minutes
            '/api/active-streams': 60,  # Cache 1 minute
            '/api/detection-results': 120,  # Cache 2 minutes
        }
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize cache control middleware"""
        app.after_request(self.add_cache_headers)
    
    def add_cache_headers(self, response):
        """Add appropriate cache headers"""
        
        # Chỉ cache GET requests
        if request.method == 'GET':
            endpoint = request.endpoint
            path = request.path
            
            # Tìm cache time cho endpoint này
            cache_time = None
            for rule, time_seconds in self.cache_rules.items():
                if path.startswith(rule):
                    cache_time = time_seconds
                    break
            
            if cache_time and response.status_code == 200:
                response.headers['Cache-Control'] = f'public, max-age={cache_time}'
                response.headers['Expires'] = time.strftime(
                    '%a, %d %b %Y %H:%M:%S GMT',
                    time.gmtime(time.time() + cache_time)
                )
            else:
                # No cache cho sensitive endpoints
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'
        
        return response

class SecurityHeadersMiddleware:
    """Middleware để thêm security headers"""
    
    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize security headers middleware"""
        app.after_request(self.add_security_headers)
    
    def add_security_headers(self, response):
        """Add security headers to all responses"""
        
        # Content Security Policy
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        )
        
        # Other security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        return response

# Decorators cho API optimization
def require_json(f):
    """Decorator yêu cầu request phải có Content-Type: application/json"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not request.is_json:
            security_logger.log_validation_error(
                request.remote_addr,
                request.endpoint,
                "Content-Type must be application/json"
            )
            return jsonify({"error": "Content-Type phải là application/json"}), 400
        return f(*args, **kwargs)
    return decorated_function

def validate_pagination(f):
    """Decorator để validate pagination parameters"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        # Validate pagination
        if page < 1:
            return jsonify({"error": "Page phải >= 1"}), 400
        
        if per_page < 1 or per_page > 100:
            return jsonify({"error": "Per_page phải từ 1-100"}), 400
        
        # Add to kwargs
        kwargs['page'] = page
        kwargs['per_page'] = per_page
        
        return f(*args, **kwargs)
    return decorated_function

def log_api_call(f):
    """Decorator để log API calls với details"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        start_time = time.time()
        
        try:
            result = f(*args, **kwargs)
            duration = time.time() - start_time
            
            # Log successful API call
            performance_logger.logger.info(
                f"API call: {request.endpoint}",
                extra={
                    "endpoint": request.endpoint,
                    "method": request.method,
                    "duration_ms": round(duration * 1000, 2),
                    "status": "success",
                    "args_count": len(args),
                    "kwargs_count": len(kwargs)
                }
            )
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            
            # Log failed API call
            performance_logger.logger.error(
                f"API call failed: {request.endpoint}",
                extra={
                    "endpoint": request.endpoint,
                    "method": request.method,
                    "duration_ms": round(duration * 1000, 2),
                    "status": "error",
                    "error": str(e)
                },
                exc_info=True
            )
            
            raise
    
    return decorated_function

# Response helpers
def create_paginated_response(items, page, per_page, total_count, endpoint=None):
    """Tạo standardized paginated response"""
    
    pages = (total_count + per_page - 1) // per_page
    
    response = {
        "data": items,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total_count,
            "pages": pages,
            "has_prev": page > 1,
            "has_next": page < pages
        }
    }
    
    # Add navigation links nếu có endpoint
    if endpoint:
        response["pagination"]["links"] = {
            "self": f"{endpoint}?page={page}&per_page={per_page}",
            "first": f"{endpoint}?page=1&per_page={per_page}",
            "last": f"{endpoint}?page={pages}&per_page={per_page}"
        }
        
        if page > 1:
            response["pagination"]["links"]["prev"] = f"{endpoint}?page={page-1}&per_page={per_page}"
        
        if page < pages:
            response["pagination"]["links"]["next"] = f"{endpoint}?page={page+1}&per_page={per_page}"
    
    return response

def create_api_response(data=None, message=None, status="success", code=200, **kwargs):
    """Tạo standardized API response format"""
    
    response = {
        "status": status,
        "timestamp": time.time(),
        "request_id": getattr(g, 'request_id', 'unknown')
    }
    
    if data is not None:
        response["data"] = data
    
    if message:
        response["message"] = message
    
    # Thêm extra fields
    response.update(kwargs)
    
    return jsonify(response), code 