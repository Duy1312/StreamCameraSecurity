from flask import Flask, render_template, jsonify, request, redirect, url_for, g
from flask_socketio import SocketIO
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import cv2
import os
import time
import json
import threading
from datetime import datetime
import numpy as np
from PIL import Image
import base64
import io
import uuid
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor

from config import config, Config
from models import db, Camera, Detection, StreamSession, DetectionSchedule
from cache import cache_manager, CameraCache, StreamCache, DetectionCache
from services import (
    CameraService, StreamService, DetectionService, 
    async_face_detection_service, AsyncFaceDetectionService
)

# Import logging và middleware
from logger_config import setup_logging, request_logger, security_logger, performance_logger
from middleware import (
    RequestLoggingMiddleware, CompressionMiddleware, RateLimitMiddleware,
    CacheControlMiddleware, SecurityHeadersMiddleware,
    require_json, validate_pagination, log_api_call,
    create_paginated_response, create_api_response
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Load configuration
config_name = os.environ.get('FLASK_CONFIG', 'default')
app.config.from_object(config[config_name])

# Setup comprehensive logging system
logger = setup_logging(app)

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[app.config['RATELIMIT_DEFAULT']],
    storage_uri=app.config['RATELIMIT_STORAGE_URL']
)
limiter.init_app(app)

# Initialize middleware
request_logging = RequestLoggingMiddleware(app)
compression = CompressionMiddleware(app, min_size=1024)
rate_limit_middleware = RateLimitMiddleware(app)
cache_control = CacheControlMiddleware(app)
security_headers = SecurityHeadersMiddleware(app)

# Thư mục lưu trữ ảnh khi phát hiện khuôn mặt
UPLOAD_FOLDER = app.config['DETECTION_FOLDER']
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Global variables for backward compatibility
cameras = {}
active_streams = set()
face_detection_schedule = {}
face_detection_active = {}
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

# Utility functions for validation
def validate_request_data(data, required_fields):
    """Validate request data has required fields"""
    if not data:
        return False, "Dữ liệu request không hợp lệ"
    
    missing_fields = [field for field in required_fields if not data.get(field)]
    if missing_fields:
        return False, f"Thiếu các trường bắt buộc: {', '.join(missing_fields)}"
    
    return True, None

def sanitize_string(value, max_length=None):
    """Sanitize string input"""
    if not isinstance(value, str):
        return str(value)
    
    # Remove dangerous characters
    sanitized = value.strip()
    
    if max_length and len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    
    return sanitized

def validate_camera_id(camera_id):
    """Validate camera ID format"""
    if not camera_id:
        return False, "Camera ID không được để trống"
    
    if not isinstance(camera_id, str):
        return False, "Camera ID phải là chuỗi"
    
    if len(camera_id) > 50:
        return False, "Camera ID quá dài"
    
    return True, None

# Database initialization functions
def init_database():
    """Initialize database with sample data if needed"""
    try:
        with app.app_context():
            # Create tables
            db.create_all()
            
            # Check if we need to migrate from JSON
            json_file = app.config['CAMERAS_JSON_FILE']
            if os.path.exists(json_file) and Camera.query.count() == 0:
                logger.info("Migrating data from JSON to database...")
                migrate_from_json()
            
            # Create sample data if database is empty
            elif Camera.query.count() == 0:
                logger.info("Creating sample camera data...")
                create_sample_cameras()
                
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")

def migrate_from_json():
    """Migrate camera data from JSON file to database"""
    try:
        json_file = app.config['CAMERAS_JSON_FILE']
        with open(json_file, 'r', encoding='utf-8') as f:
            cameras_data = json.load(f)
        
        for camera_id, camera_data in cameras_data.items():
            camera = Camera.from_dict(camera_data)
            db.session.add(camera)
        
        db.session.commit()
        logger.info(f"Migrated {len(cameras_data)} cameras from JSON")
        
        # Backup JSON file
        backup_file = f"{json_file}.backup"
        os.rename(json_file, backup_file)
        logger.info(f"JSON file backed up as {backup_file}")
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error migrating from JSON: {e}")

def create_sample_cameras():
    """Create sample camera data"""
    try:
        for i in range(1, 401):
            camera_id = f"cam_{i}"
            camera = Camera(
                id=camera_id,
                name=f"Camera {i}",
                ip=f"192.168.1.{(i % 254) + 1}",
                location=f"Khu vực {(i-1)//20 + 1}, Phòng {(i-1)%20 + 1}",
                status="offline"
            )
            db.session.add(camera)
        
        db.session.commit()
        logger.info("Created 400 sample cameras")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating sample cameras: {e}")

# Routes with improved error handling and performance
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/cameras')
@limiter.limit("200/minute")
@log_api_call
def get_cameras():
    """Get all cameras with caching và enhanced logging"""
    try:
        start_time = time.time()
        cameras_dict = CameraService.get_all_cameras()
        duration = time.time() - start_time
        
        # Log performance
        if duration > 0.5:
            performance_logger.log_slow_query(
                "SELECT cameras", duration, {"table": "cameras"}
            )
        
        logger.info(f"Retrieved {len(cameras_dict)} cameras in {duration:.3f}s")
        return create_api_response(cameras_dict, "Cameras retrieved successfully")
        
    except Exception as e:
        logger.error(f"Error retrieving cameras: {e}", exc_info=True)
        return create_api_response(
            status="error", 
            message="Lỗi hệ thống khi lấy danh sách camera",
            code=500
        )

@app.route('/api/active-streams')
@limiter.limit("100/minute")
@log_api_call
def get_active_streams():
    """Get active streams with caching và enhanced logging"""
    try:
        active_streams_list = StreamService.get_active_streams()
        logger.debug(f"Retrieved {len(active_streams_list)} active streams")
        return create_api_response(active_streams_list, "Active streams retrieved")
        
    except Exception as e:
        logger.error(f"Error retrieving active streams: {e}", exc_info=True)
        return create_api_response(
            status="error",
            message="Lỗi hệ thống khi lấy danh sách stream",
            code=500
        )

@app.route('/api/start-stream', methods=['POST'])
@limiter.limit("30/minute")
@require_json
@log_api_call
def start_stream():
    """Start camera stream với enhanced validation và logging"""
    try:
        data = request.get_json()
        is_valid, error = validate_request_data(data, ['camera_id'])
        if not is_valid:
            security_logger.log_validation_error(request.remote_addr, request.endpoint, error)
            return create_api_response(status="error", message=error, code=400)
        
        camera_id = sanitize_string(data['camera_id'])
        is_valid, error = validate_camera_id(camera_id)
        if not is_valid:
            security_logger.log_validation_error(request.remote_addr, request.endpoint, error)
            return create_api_response(status="error", message=error, code=400)
        
        success, message = StreamService.start_camera_stream(camera_id)
        
        if success:
            logger.info(f"Stream started successfully for camera {camera_id}")
            return create_api_response({"camera_id": camera_id}, message)
        else:
            logger.warning(f"Failed to start stream for camera {camera_id}: {message}")
            return create_api_response(status="error", message=message, code=400)
    
    except Exception as e:
        logger.error(f"Error starting stream: {e}", exc_info=True)
        return create_api_response(
            status="error",
            message="Lỗi hệ thống khi bắt đầu stream",
            code=500
        )

@app.route('/api/stop-stream', methods=['POST'])
@limiter.limit("30/minute")
@require_json
@log_api_call
def stop_stream():
    """Stop camera stream với enhanced validation và logging"""
    try:
        data = request.get_json()
        is_valid, error = validate_request_data(data, ['camera_id'])
        if not is_valid:
            security_logger.log_validation_error(request.remote_addr, request.endpoint, error)
            return create_api_response(status="error", message=error, code=400)
        
        camera_id = sanitize_string(data['camera_id'])
        is_valid, error = validate_camera_id(camera_id)
        if not is_valid:
            security_logger.log_validation_error(request.remote_addr, request.endpoint, error)
            return create_api_response(status="error", message=error, code=400)
        
        success, message = StreamService.stop_camera_stream(camera_id)
        
        if success:
            logger.info(f"Stream stopped successfully for camera {camera_id}")
            return create_api_response({"camera_id": camera_id}, message)
        else:
            logger.warning(f"Failed to stop stream for camera {camera_id}: {message}")
            return create_api_response(status="error", message=message, code=400)
    
    except Exception as e:
        logger.error(f"Error stopping stream: {e}", exc_info=True)
        return create_api_response(
            status="error",
            message="Lỗi hệ thống khi dừng stream",
            code=500
        )

@app.route('/api/schedule-detection', methods=['POST'])
@limiter.limit("10/minute")
def schedule_detection():
    """Schedule face detection with async processing"""
    try:
        data = request.get_json()
        is_valid, error = validate_request_data(data, ['camera_ids'])
        if not is_valid:
            return jsonify({"error": error}), 400
        
        camera_ids = data.get('camera_ids', [])
        duration = data.get('duration', 60)
        
        # Validate camera_ids
        if not isinstance(camera_ids, list):
            return jsonify({"error": "camera_ids phải là danh sách"}), 400
        
        if len(camera_ids) == 0:
            return jsonify({"error": "Phải chọn ít nhất 1 camera"}), 400
        
        max_detection = app.config['MAX_CAMERAS_DETECTION']
        if len(camera_ids) > max_detection:
            return jsonify({"error": f"Không thể lên lịch quá {max_detection} camera cùng lúc"}), 400
        
        # Validate duration
        if not isinstance(duration, int) or duration < 1 or duration > 120:
            return jsonify({"error": "Thời gian phải từ 1-120 phút"}), 400
        
        # Validate all camera IDs exist
        cameras_dict = CameraService.get_all_cameras()
        invalid_cameras = [cid for cid in camera_ids if cid not in cameras_dict]
        if invalid_cameras:
            return jsonify({"error": f"Camera không tồn tại: {', '.join(invalid_cameras)}"}), 400
        
        schedule_id = f"schedule_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        
        # Create schedule record
        schedule = DetectionSchedule(
            id=schedule_id,
            duration=duration,
            status='active'
        )
        schedule.set_camera_ids(camera_ids)
        
        db.session.add(schedule)
        db.session.commit()
        
        logger.info(f"Lên lịch phát hiện {len(camera_ids)} camera trong {duration} phút")
        
        # Start async face detection
        threading.Thread(target=run_async_face_detection, args=(schedule_id, camera_ids, duration)).start()
        
        return jsonify({"schedule_id": schedule_id})
    
    except Exception as e:
        logger.error(f"Lỗi khi lên lịch phát hiện: {e}")
        return jsonify({"error": "Lỗi hệ thống khi lên lịch phát hiện"}), 500

@app.route('/api/detection-results')
@limiter.limit("100/minute")
@validate_pagination
@log_api_call
def get_detection_results(page=1, per_page=20):
    """Get detection results với enhanced pagination và logging"""
    try:
        start_time = time.time()
        results, total_count = DetectionService.get_detection_results(page, per_page)
        duration = time.time() - start_time
        
        # Log performance
        if duration > 0.5:
            performance_logger.log_slow_query(
                "SELECT detections with pagination", duration, 
                {"page": page, "per_page": per_page}
            )
        
        # Create paginated response
        response_data = create_paginated_response(
            results, page, per_page, total_count, "/api/detection-results"
        )
        
        logger.info(f"Retrieved {len(results)} detection results (page {page}) in {duration:.3f}s")
        return create_api_response(response_data, "Detection results retrieved")
        
    except Exception as e:
        logger.error(f"Error retrieving detection results: {e}", exc_info=True)
        return create_api_response(
            status="error",
            message="Lỗi hệ thống khi lấy kết quả phát hiện",
            code=500
        )

@app.route('/api/cameras', methods=['POST'])
@limiter.limit("10/minute")
def add_camera():
    """Add new camera"""
    try:
        data = request.get_json()
        is_valid, error = validate_request_data(data, ['name', 'ip', 'location'])
        if not is_valid:
            return jsonify({"error": error}), 400
        
        # Validate camera data using Config
        validation_errors = Config.validate_camera_data(data)
        if validation_errors:
            return jsonify({"error": validation_errors[0]}), 400
        
        # Sanitize input data
        camera_data = {
            "name": sanitize_string(data['name'], Config.MAX_CAMERA_NAME_LENGTH),
            "ip": sanitize_string(data['ip'], Config.MAX_IP_LENGTH),
            "location": sanitize_string(data['location'], Config.MAX_LOCATION_LENGTH),
            "status": data.get('status', 'offline')
        }
        
        success, message, camera_dict = CameraService.create_camera(camera_data)
        
        if success:
            return jsonify({"success": True, "camera": camera_dict, "message": message})
        else:
            return jsonify({"error": message}), 400
    
    except Exception as e:
        logger.error(f"Lỗi khi thêm camera: {e}")
        return jsonify({"error": "Lỗi hệ thống khi thêm camera"}), 500

@app.route('/api/cameras/<camera_id>', methods=['PUT'])
@limiter.limit("20/minute")
def update_camera(camera_id):
    """Update camera"""
    try:
        camera_id = sanitize_string(camera_id)
        is_valid, error = validate_camera_id(camera_id)
        if not is_valid:
            return jsonify({"error": error}), 400
        
        data = request.get_json()
        if not data:
            return jsonify({"error": "Dữ liệu cập nhật không hợp lệ"}), 400
        
        # Validate if provided
        if any(field in data for field in ['name', 'ip', 'location']):
            validation_errors = Config.validate_camera_data(data)
            if validation_errors:
                return jsonify({"error": validation_errors[0]}), 400
        
        # Sanitize data
        update_data = {}
        for field in ['name', 'ip', 'location', 'status']:
            if field in data:
                if field in ['name', 'ip', 'location']:
                    max_length = getattr(Config, f'MAX_{field.upper()}_LENGTH', None)
                    update_data[field] = sanitize_string(data[field], max_length)
                else:
                    update_data[field] = data[field]
        
        success, message, camera_dict = CameraService.update_camera(camera_id, update_data)
        
        if success:
            return jsonify({"success": True, "camera": camera_dict, "message": message})
        else:
            return jsonify({"error": message}), 400 if "không tồn tại" in message else 409
    
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật camera: {e}")
        return jsonify({"error": "Lỗi hệ thống khi cập nhật camera"}), 500

@app.route('/api/cameras/<camera_id>', methods=['DELETE'])
@limiter.limit("10/minute")
def delete_camera(camera_id):
    """Delete camera"""
    try:
        camera_id = sanitize_string(camera_id)
        is_valid, error = validate_camera_id(camera_id)
        if not is_valid:
            return jsonify({"error": error}), 400
        
        success, message = CameraService.delete_camera(camera_id)
        
        if success:
            return jsonify({"success": True, "message": message})
        else:
            return jsonify({"error": message}), 404 if "không tồn tại" in message else 500
    
    except Exception as e:
        logger.error(f"Lỗi khi xóa camera: {e}")
        return jsonify({"error": "Lỗi hệ thống khi xóa camera"}), 500

# Async face detection runner
def run_async_face_detection(schedule_id, camera_ids, duration):
    """Run async face detection in a separate thread"""
    try:
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the async detection
        loop.run_until_complete(async_face_detection_loop(schedule_id, camera_ids, duration))
        
    except Exception as e:
        logger.error(f"Lỗi trong run_async_face_detection: {e}")
    finally:
        loop.close()

async def async_face_detection_loop(schedule_id, camera_ids, duration):
    """Async face detection loop"""
    try:
        end_time = time.time() + (duration * 60)
        detection_service = AsyncFaceDetectionService()
        
        logger.info(f"Bắt đầu async face detection cho {len(camera_ids)} camera")
        
        while time.time() < end_time:
            # Check if schedule is still active
            schedule = DetectionSchedule.query.get(schedule_id)
            if not schedule or schedule.status != 'active':
                break
            
            # Process multiple cameras in parallel
            results = await detection_service.process_multiple_cameras_async(camera_ids, schedule_id)
            
            # Send WebSocket notifications for successful detections
            for result in results:
                if result:
                    detection_data = {
                        "camera_id": result["camera_id"],
                        "timestamp": result["timestamp"],
                        "image_path": result["image_path"],
                        "faces_count": result["faces_count"],
                        "schedule_id": result["schedule_id"],
                        "camera_info": CameraService.get_camera_by_id(result["camera_id"]) or {}
                    }
                    socketio.emit('face_detected', detection_data)
                    logger.info(f"Async phát hiện {result['faces_count']} khuôn mặt camera {result['camera_id']}")
            
            # Wait before next iteration
            await asyncio.sleep(2)
        
        # Mark schedule as completed
        schedule = DetectionSchedule.query.get(schedule_id)
        if schedule:
            schedule.status = 'completed'
            schedule.end_time = datetime.utcnow()
            db.session.commit()
        
        logger.info(f"Hoàn thành async face detection cho schedule {schedule_id}")
        
    except Exception as e:
        logger.error(f"Lỗi trong async_face_detection_loop: {e}")
        # Mark schedule as error
        try:
            schedule = DetectionSchedule.query.get(schedule_id)
            if schedule:
                schedule.status = 'error'
                db.session.commit()
        except:
            pass

# Keep existing test endpoints for backward compatibility
@app.route('/api/test-face-detection', methods=['POST'])
@limiter.limit("20/minute")
def test_face_detection():
    """API để test phát hiện khuôn mặt ngay lập tức"""
    try:
        data = request.get_json()
        is_valid, error = validate_request_data(data, ['camera_id'])
        if not is_valid:
            return jsonify({"error": error}), 400
        
        camera_id = sanitize_string(data['camera_id'])
        is_valid, error = validate_camera_id(camera_id)
        if not is_valid:
            return jsonify({"error": error}), 400
        
        camera = CameraService.get_camera_by_id(camera_id)
        if not camera:
            return jsonify({"error": "Camera không tồn tại"}), 404
        
        frame = simulate_camera_frame_with_face(camera_id)
        
        # Chuyển đổi sang thang độ xám
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Phát hiện khuôn mặt
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)
        
        # Vẽ hình chữ nhật xung quanh khuôn mặt
        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)
        
        # Lưu ảnh
        timestamp = int(time.time())
        filename = f"{camera_id}_{timestamp}_test.jpg"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        cv2.imwrite(filepath, frame)
        
        # Save to database
        image_path = f"/static/detections/{filename}"
        DetectionService.save_detection_result(
            camera_id=camera_id,
            timestamp=timestamp,
            image_path=image_path,
            faces_count=len(faces),
            test_mode=True
        )
        
        # Gửi thông báo qua WebSocket
        detection_data = {
            "camera_id": camera_id,
            "timestamp": timestamp,
            "image_path": image_path,
            "camera_info": camera,
            "test_mode": True,
            "faces_count": len(faces)
        }
        socketio.emit('face_detected', detection_data)
        
        logger.info(f"Test phát hiện khuôn mặt thành công cho camera {camera_id}")
        return jsonify({
            "success": True,
            "message": "Test phát hiện khuôn mặt thành công",
            "detection": detection_data
        })
    
    except Exception as e:
        logger.error(f"Lỗi khi test phát hiện khuôn mặt: {e}")
        return jsonify({"error": "Lỗi hệ thống khi test phát hiện khuôn mặt"}), 500

def simulate_camera_frame(camera_id):
    # Trong thực tế, bạn sẽ kết nối với camera IP và lấy frame thực
    # Đây chỉ là mô phỏng để demo
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    
    # Tăng tỷ lệ phát hiện cho demo
    if np.random.random() < 0.3:  # 30% cơ hội có khuôn mặt (tăng từ 10%)
        # Vẽ một hình tròn đại diện cho khuôn mặt
        cv2.circle(frame, (320, 240), 100, (0, 0, 255), -1)
        cv2.circle(frame, (280, 200), 20, (255, 255, 255), -1)  # Mắt trái
        cv2.circle(frame, (360, 200), 20, (255, 255, 255), -1)  # Mắt phải
        cv2.ellipse(frame, (320, 280), (60, 30), 0, 0, 180, (255, 255, 255), -1)  # Miệng
    
    # Thêm thông tin camera
    camera_info = cameras.get(camera_id, {"name": f"Camera {camera_id}", "ip": "Unknown", "location": "Unknown"})
    cv2.putText(frame, camera_info["name"], (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    cv2.putText(frame, f"IP: {camera_info['ip']}", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.putText(frame, f"Location: {camera_info['location']}", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    
    return frame

def simulate_camera_frame_with_face(camera_id):
    """Tạo frame giả luôn có khuôn mặt để test"""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    
    # Luôn thêm khuôn mặt để test
    # Vẽ một hình tròn đại diện cho khuôn mặt
    cv2.circle(frame, (320, 240), 100, (0, 0, 255), -1)
    cv2.circle(frame, (280, 200), 20, (255, 255, 255), -1)  # Mắt trái
    cv2.circle(frame, (360, 200), 20, (255, 255, 255), -1)  # Mắt phải
    cv2.ellipse(frame, (320, 280), (60, 30), 0, 0, 180, (255, 255, 255), -1)  # Miệng
    
    # Thêm text "TEST FACE"
    cv2.putText(frame, "TEST FACE", (250, 350), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    
    # Thêm thông tin camera
    camera_info = cameras.get(camera_id, {"name": f"Camera {camera_id}", "ip": "Unknown", "location": "Unknown"})
    cv2.putText(frame, camera_info["name"], (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    cv2.putText(frame, f"IP: {camera_info['ip']}", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.putText(frame, f"Location: {camera_info['location']}", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    
    return frame

# Health check và monitoring endpoints
@app.route('/api/health')
def health_check():
    """Health check endpoint cho monitoring"""
    try:
        health_status = {
            "status": "healthy",
            "timestamp": time.time(),
            "version": "2.0.0",
            "uptime": time.time() - app.start_time if hasattr(app, 'start_time') else 0,
            "components": {}
        }
        
        # Check database
        try:
            from sqlalchemy import text
            db.session.execute(text('SELECT 1'))
            health_status["components"]["database"] = "healthy"
        except Exception as e:
            health_status["components"]["database"] = f"unhealthy: {str(e)}"
            health_status["status"] = "degraded"
        
        # Check Redis cache
        try:
            cache_manager.redis_client.ping()
            health_status["components"]["redis"] = "healthy"
        except Exception as e:
            health_status["components"]["redis"] = f"unavailable: {str(e)}"
        
        # Check active streams
        try:
            active_streams = StreamService.get_active_streams(use_cache=False)
            health_status["components"]["streams"] = {
                "status": "healthy",
                "active_count": len(active_streams)
            }
        except Exception as e:
            health_status["components"]["streams"] = f"unhealthy: {str(e)}"
        
        status_code = 200 if health_status["status"] == "healthy" else 503
        return jsonify(health_status), status_code
        
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": time.time()
        }), 503

@app.route('/api/metrics')
@limiter.limit("10/minute")
def get_metrics():
    """API metrics endpoint cho monitoring tools"""
    try:
        metrics = {
            "timestamp": time.time(),
            "application": {
                "name": "StreamCameraSecurity",
                "version": "2.0.0",
                "uptime": time.time() - app.start_time if hasattr(app, 'start_time') else 0
            },
            "database": {},
            "cache": {},
            "streams": {},
            "detection": {}
        }
        
        # Database metrics
        try:
            cameras_count = Camera.query.count()
            detections_count = Detection.query.count()
            sessions_count = StreamSession.query.count()
            
            metrics["database"] = {
                "cameras_total": cameras_count,
                "detections_total": detections_count,
                "stream_sessions_total": sessions_count,
                "status": "connected"
            }
        except Exception as e:
            metrics["database"] = {"status": "error", "error": str(e)}
        
        # Cache metrics
        try:
            if cache_manager.is_available:
                # Get some cache stats (simplified)
                metrics["cache"] = {
                    "status": "available",
                    "type": "redis"
                }
            else:
                metrics["cache"] = {"status": "unavailable"}
        except Exception as e:
            metrics["cache"] = {"status": "error", "error": str(e)}
        
        # Stream metrics
        try:
            active_streams = StreamService.get_active_streams(use_cache=False)
            metrics["streams"] = {
                "active_count": len(active_streams),
                "active_streams": active_streams,
                "max_concurrent": app.config['MAX_CAMERAS_STREAM']
            }
        except Exception as e:
            metrics["streams"] = {"status": "error", "error": str(e)}
        
        # Detection metrics (last 24h)
        try:
            from datetime import timedelta
            yesterday = datetime.utcnow() - timedelta(days=1)
            recent_detections = Detection.query.filter(
                Detection.created_at >= yesterday
            ).count()
            
            metrics["detection"] = {
                "recent_24h": recent_detections,
                "max_concurrent": app.config['MAX_CAMERAS_DETECTION']
            }
        except Exception as e:
            metrics["detection"] = {"status": "error", "error": str(e)}
        
        return jsonify(metrics)
        
    except Exception as e:
        logger.error(f"Error retrieving metrics: {e}", exc_info=True)
        return create_api_response(
            status="error",
            message="Lỗi khi lấy metrics",
            code=500
        )

# Error handlers với enhanced logging
@app.errorhandler(404)
def not_found(error):
    security_logger.logger.warning(
        "404 Not Found",
        extra={
            "url": request.url,
            "method": request.method,
            "remote_addr": request.remote_addr,
            "user_agent": request.headers.get('User-Agent')
        }
    )
    return create_api_response(
        status="error",
        message="Endpoint không tồn tại",
        code=404
    )

@app.errorhandler(405)
def method_not_allowed(error):
    security_logger.logger.warning(
        "405 Method Not Allowed",
        extra={
            "url": request.url,
            "method": request.method,
            "remote_addr": request.remote_addr
        }
    )
    return create_api_response(
        status="error",
        message="Phương thức HTTP không được phép",
        code=405
    )

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}", exc_info=True)
    return create_api_response(
        status="error",
        message="Lỗi hệ thống nội bộ",
        code=500
    )

# Khởi tạo dữ liệu và start time tracking
app.start_time = time.time()

try:
    init_database()
    logger.info("✅ Ứng dụng khởi tạo thành công")
    logger.info(f"📊 Logging system: {len(logger.handlers)} handlers configured")
    logger.info(f"🗄️  Database: {app.config['SQLALCHEMY_DATABASE_URI']}")
    logger.info(f"🔄 Cache: {'Redis available' if cache_manager.is_available else 'Redis unavailable'}")
    logger.info(f"📈 Middleware: Request logging, compression, rate limiting enabled")
except Exception as e:
    logger.error(f"❌ Lỗi khởi tạo ứng dụng: {e}", exc_info=True)

if __name__ == '__main__':
    try:
        logger.info("Khởi động server...")
        socketio.run(app, debug=app.config['DEBUG'], host='0.0.0.0', port=5000)
    except Exception as e:
        logger.error(f"Lỗi khởi động server: {e}") 