import redis
import json
import logging
from typing import Any, Optional, List, Dict
from functools import wraps
import time

logger = logging.getLogger(__name__)

class CacheManager:
    """Quản lý Redis cache"""
    
    def __init__(self, host='localhost', port=6379, db=0, decode_responses=True):
        try:
            self.redis_client = redis.Redis(
                host=host, 
                port=port, 
                db=db, 
                decode_responses=decode_responses,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # Test connection
            self.redis_client.ping()
            self.is_available = True
            logger.info("Redis cache kết nối thành công")
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"Không thể kết nối Redis: {e}. Chạy không có cache.")
            self.redis_client = None
            self.is_available = False
    
    def get(self, key: str) -> Optional[Any]:
        """Lấy dữ liệu từ cache"""
        if not self.is_available:
            return None
        
        try:
            data = self.redis_client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Lỗi khi lấy cache {key}: {e}")
            return None
    
    def set(self, key: str, value: Any, expire: int = 300) -> bool:
        """Lưu dữ liệu vào cache"""
        if not self.is_available:
            return False
        
        try:
            serialized = json.dumps(value, default=str)
            return self.redis_client.setex(key, expire, serialized)
        except Exception as e:
            logger.error(f"Lỗi khi lưu cache {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Xóa cache"""
        if not self.is_available:
            return False
        
        try:
            return bool(self.redis_client.delete(key))
        except Exception as e:
            logger.error(f"Lỗi khi xóa cache {key}: {e}")
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        """Xóa nhiều cache theo pattern"""
        if not self.is_available:
            return 0
        
        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                return self.redis_client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Lỗi khi xóa cache pattern {pattern}: {e}")
            return 0
    
    def exists(self, key: str) -> bool:
        """Kiểm tra cache có tồn tại không"""
        if not self.is_available:
            return False
        
        try:
            return bool(self.redis_client.exists(key))
        except Exception as e:
            logger.error(f"Lỗi khi kiểm tra cache {key}: {e}")
            return False
    
    def expire(self, key: str, expire: int) -> bool:
        """Đặt thời gian hết hạn cho cache"""
        if not self.is_available:
            return False
        
        try:
            return bool(self.redis_client.expire(key, expire))
        except Exception as e:
            logger.error(f"Lỗi khi đặt expire cache {key}: {e}")
            return False
    
    def flush_all(self) -> bool:
        """Xóa tất cả cache"""
        if not self.is_available:
            return False
        
        try:
            return self.redis_client.flushdb()
        except Exception as e:
            logger.error(f"Lỗi khi flush cache: {e}")
            return False

# Cache keys constants
class CacheKeys:
    CAMERAS_ALL = "cameras:all"
    CAMERA_DETAIL = "camera:detail:{}"
    ACTIVE_STREAMS = "streams:active"
    DETECTION_RESULTS = "detections:results:page:{}"
    DETECTION_COUNT = "detections:count"
    CAMERA_STATS = "camera:stats:{}"
    SCHEDULE_ACTIVE = "schedules:active"

# Cache decorators
def cached(expire: int = 300, key_func=None):
    """Decorator để cache kết quả function"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"func:{func.__name__}:{hash(str(args) + str(kwargs))}"
            
            # Try to get from cache
            cached_result = cache_manager.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Save to cache
            cache_manager.set(cache_key, result, expire)
            return result
        
        return wrapper
    return decorator

def cache_invalidate(pattern: str):
    """Decorator để xóa cache sau khi thực hiện function"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            cache_manager.delete_pattern(pattern)
            return result
        return wrapper
    return decorator

# Khởi tạo cache manager global
cache_manager = CacheManager()

# Utility functions for specific caching needs
class CameraCache:
    """Cache utilities cho camera"""
    
    @staticmethod
    def get_all_cameras():
        """Lấy danh sách tất cả camera từ cache"""
        return cache_manager.get(CacheKeys.CAMERAS_ALL)
    
    @staticmethod
    def set_all_cameras(cameras: Dict, expire: int = 300):
        """Lưu danh sách camera vào cache"""
        return cache_manager.set(CacheKeys.CAMERAS_ALL, cameras, expire)
    
    @staticmethod
    def get_camera_detail(camera_id: str):
        """Lấy chi tiết camera từ cache"""
        key = CacheKeys.CAMERA_DETAIL.format(camera_id)
        return cache_manager.get(key)
    
    @staticmethod
    def set_camera_detail(camera_id: str, camera_data: Dict, expire: int = 600):
        """Lưu chi tiết camera vào cache"""
        key = CacheKeys.CAMERA_DETAIL.format(camera_id)
        return cache_manager.set(key, camera_data, expire)
    
    @staticmethod
    def invalidate_camera(camera_id: str):
        """Xóa cache của camera"""
        # Xóa cache chi tiết
        detail_key = CacheKeys.CAMERA_DETAIL.format(camera_id)
        cache_manager.delete(detail_key)
        
        # Xóa cache danh sách tất cả
        cache_manager.delete(CacheKeys.CAMERAS_ALL)
        
        # Xóa cache stats
        stats_key = CacheKeys.CAMERA_STATS.format(camera_id)
        cache_manager.delete(stats_key)
    
    @staticmethod
    def invalidate_all():
        """Xóa tất cả cache của camera"""
        cache_manager.delete_pattern("camera:*")
        cache_manager.delete(CacheKeys.CAMERAS_ALL)

class StreamCache:
    """Cache utilities cho streaming"""
    
    @staticmethod
    def get_active_streams():
        """Lấy danh sách stream đang hoạt động"""
        return cache_manager.get(CacheKeys.ACTIVE_STREAMS)
    
    @staticmethod
    def set_active_streams(streams: List, expire: int = 60):
        """Lưu danh sách stream đang hoạt động"""
        return cache_manager.set(CacheKeys.ACTIVE_STREAMS, streams, expire)
    
    @staticmethod
    def invalidate_streams():
        """Xóa cache streams"""
        cache_manager.delete(CacheKeys.ACTIVE_STREAMS)

class DetectionCache:
    """Cache utilities cho detection results"""
    
    @staticmethod
    def get_detection_results(page: int = 1):
        """Lấy kết quả phát hiện theo trang"""
        key = CacheKeys.DETECTION_RESULTS.format(page)
        return cache_manager.get(key)
    
    @staticmethod
    def set_detection_results(page: int, results: List, expire: int = 120):
        """Lưu kết quả phát hiện theo trang"""
        key = CacheKeys.DETECTION_RESULTS.format(page)
        return cache_manager.set(key, results, expire)
    
    @staticmethod
    def invalidate_detection_results():
        """Xóa cache kết quả phát hiện"""
        cache_manager.delete_pattern("detections:results:*")
        cache_manager.delete(CacheKeys.DETECTION_COUNT)
    
    @staticmethod
    def get_detection_count():
        """Lấy tổng số detection từ cache"""
        return cache_manager.get(CacheKeys.DETECTION_COUNT)
    
    @staticmethod
    def set_detection_count(count: int, expire: int = 300):
        """Lưu tổng số detection vào cache"""
        return cache_manager.set(CacheKeys.DETECTION_COUNT, count, expire) 