import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Cấu hình cơ bản cho ứng dụng"""
    
    # Flask Configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-change-in-production'
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    # Database Configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///camera_security.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'connect_args': {'check_same_thread': False} if 'sqlite' in os.environ.get('DATABASE_URL', 'sqlite') else {}
    }
    
    # Redis Configuration
    REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
    REDIS_DB = int(os.environ.get('REDIS_DB', 0))
    REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD', None)
    
    # Application Settings
    MAX_CAMERAS_STREAM = int(os.environ.get('MAX_CAMERAS_STREAM', 20))
    MAX_CAMERAS_DETECTION = int(os.environ.get('MAX_CAMERAS_DETECTION', 20))
    DETECTION_FOLDER = os.environ.get('DETECTION_FOLDER', 'static/detections')
    CAMERAS_JSON_FILE = os.environ.get('CAMERAS_JSON_FILE', 'cameras.json')
    
    # Performance Settings
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))  # 16MB
    PAGINATION_PER_PAGE = int(os.environ.get('PAGINATION_PER_PAGE', 20))
    
    # Cache Settings
    CACHE_DEFAULT_TIMEOUT = int(os.environ.get('CACHE_DEFAULT_TIMEOUT', 300))  # 5 minutes
    CACHE_CAMERAS_TIMEOUT = int(os.environ.get('CACHE_CAMERAS_TIMEOUT', 300))
    CACHE_DETECTIONS_TIMEOUT = int(os.environ.get('CACHE_DETECTIONS_TIMEOUT', 120))
    CACHE_STREAMS_TIMEOUT = int(os.environ.get('CACHE_STREAMS_TIMEOUT', 60))
    
    # Rate Limiting
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL') or f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
    RATELIMIT_DEFAULT = os.environ.get('RATELIMIT_DEFAULT', "100/hour")
    RATELIMIT_HEADERS_ENABLED = True
    
    # Async Processing
    MAX_WORKERS = int(os.environ.get('MAX_WORKERS', 4))
    FACE_DETECTION_TIMEOUT = int(os.environ.get('FACE_DETECTION_TIMEOUT', 30))  # seconds
    
    # Security Settings
    ALLOWED_EXTENSIONS = set(os.environ.get('ALLOWED_EXTENSIONS', 'jpg,jpeg,png').split(','))
    MAX_FILE_SIZE = int(os.environ.get('MAX_FILE_SIZE', 10485760))  # 10MB
    
    # Validation Rules
    MAX_CAMERA_NAME_LENGTH = 100
    MAX_LOCATION_LENGTH = 200
    MAX_IP_LENGTH = 15
    
    @staticmethod
    def validate_ip(ip):
        """Validate IP address format"""
        import re
        pattern = r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
        return re.match(pattern, ip) is not None
    
    @staticmethod
    def validate_camera_data(data):
        """Validate camera data"""
        errors = []
        
        if not data.get('name') or len(data['name'].strip()) == 0:
            errors.append("Tên camera không được để trống")
        elif len(data['name']) > Config.MAX_CAMERA_NAME_LENGTH:
            errors.append(f"Tên camera không được vượt quá {Config.MAX_CAMERA_NAME_LENGTH} ký tự")
        
        if not data.get('ip'):
            errors.append("IP camera không được để trống")
        elif not Config.validate_ip(data['ip']):
            errors.append("Định dạng IP không hợp lệ")
        
        if not data.get('location') or len(data['location'].strip()) == 0:
            errors.append("Vị trí camera không được để trống")
        elif len(data['location']) > Config.MAX_LOCATION_LENGTH:
            errors.append(f"Vị trí không được vượt quá {Config.MAX_LOCATION_LENGTH} ký tự")
        
        return errors
    
    @staticmethod
    def init_app(app):
        """Initialize app with config"""
        pass

class DevelopmentConfig(Config):
    """Cấu hình cho môi trường development"""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DEV_DATABASE_URL') or 'sqlite:///camera_security_dev.db'
    
    # Disable caching in development
    CACHE_DEFAULT_TIMEOUT = 60
    CACHE_CAMERAS_TIMEOUT = 60
    CACHE_DETECTIONS_TIMEOUT = 30
    
    # More relaxed rate limiting for development
    RATELIMIT_DEFAULT = "1000/hour"

class ProductionConfig(Config):
    """Cấu hình cho môi trường production"""
    DEBUG = False
    
    # Production database URL (PostgreSQL recommended)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        os.environ.get('PROD_DATABASE_URL') or \
        'postgresql://user:password@localhost/camera_security_prod'
    
    # Optimized cache timeouts for production
    CACHE_DEFAULT_TIMEOUT = 600  # 10 minutes
    CACHE_CAMERAS_TIMEOUT = 600
    CACHE_DETECTIONS_TIMEOUT = 300
    CACHE_STREAMS_TIMEOUT = 120
    
    # Stricter rate limiting for production
    RATELIMIT_DEFAULT = "100/hour"
    
    # Production-specific SQLAlchemy settings
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_recycle': 120,
        'pool_pre_ping': True,
        'max_overflow': 20
    }
    
    @classmethod
    def init_app(cls, app):
        Config.init_app(app)
        
        # Log to syslog in production
        import logging
        from logging.handlers import SysLogHandler
        syslog_handler = SysLogHandler()
        syslog_handler.setLevel(logging.WARNING)
        app.logger.addHandler(syslog_handler)
        
        # Performance monitoring
        try:
            from flask import g, request
            import time
            
            @app.before_request
            def before_request():
                g.start_time = time.time()
            
            @app.after_request
            def after_request(response):
                try:
                    if hasattr(g, 'start_time'):
                        total_time = time.time() - g.start_time
                        if total_time > 1.0:  # Log slow requests
                            # Safely access request.url with proper error handling
                            try:
                                url = request.url
                                app.logger.warning(f"Slow request: {total_time:.2f}s for {url}")
                            except RuntimeError:
                                # If request context is not available, just log the timing
                                app.logger.warning(f"Slow request: {total_time:.2f}s")
                except Exception as e:
                    app.logger.error(f"Error in performance monitoring: {e}")
                return response
        except Exception as e:
            app.logger.error(f"Error setting up performance monitoring: {e}")

class TestingConfig(Config):
    """Cấu hình cho testing"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    
    # Disable caching for tests
    CACHE_DEFAULT_TIMEOUT = 0
    CACHE_CAMERAS_TIMEOUT = 0
    CACHE_DETECTIONS_TIMEOUT = 0
    
    # No rate limiting for tests
    RATELIMIT_ENABLED = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
} 