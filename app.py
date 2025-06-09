from flask import Flask, render_template, jsonify, request, redirect, url_for
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

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Load configuration
config_name = os.environ.get('FLASK_CONFIG', 'default')
app.config.from_object(config[config_name])

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
def get_cameras():
    """Get all cameras with caching"""
    try:
        cameras_dict = CameraService.get_all_cameras()
        return jsonify(cameras_dict)
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách camera: {e}")
        return jsonify({"error": "Lỗi hệ thống khi lấy danh sách camera"}), 500

@app.route('/api/active-streams')
@limiter.limit("100/minute")
def get_active_streams():
    """Get active streams with caching"""
    try:
        active_streams_list = StreamService.get_active_streams()
        return jsonify(active_streams_list)
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách stream: {e}")
        return jsonify({"error": "Lỗi hệ thống khi lấy danh sách stream"}), 500

@app.route('/api/start-stream', methods=['POST'])
@limiter.limit("30/minute")
def start_stream():
    """Start camera stream"""
    try:
        data = request.get_json()
        is_valid, error = validate_request_data(data, ['camera_id'])
        if not is_valid:
            return jsonify({"error": error}), 400
        
        camera_id = sanitize_string(data['camera_id'])
        is_valid, error = validate_camera_id(camera_id)
        if not is_valid:
            return jsonify({"error": error}), 400
        
        success, message = StreamService.start_camera_stream(camera_id)
        
        if success:
            return jsonify({"success": True, "message": message})
        else:
            return jsonify({"error": message}), 400
    
    except Exception as e:
        logger.error(f"Lỗi khi bắt đầu stream: {e}")
        return jsonify({"error": "Lỗi hệ thống khi bắt đầu stream"}), 500

@app.route('/api/stop-stream', methods=['POST'])
@limiter.limit("30/minute")
def stop_stream():
    """Stop camera stream"""
    try:
        data = request.get_json()
        is_valid, error = validate_request_data(data, ['camera_id'])
        if not is_valid:
            return jsonify({"error": error}), 400
        
        camera_id = sanitize_string(data['camera_id'])
        is_valid, error = validate_camera_id(camera_id)
        if not is_valid:
            return jsonify({"error": error}), 400
        
        success, message = StreamService.stop_camera_stream(camera_id)
        
        if success:
            return jsonify({"success": True, "message": message})
        else:
            return jsonify({"error": message}), 400
    
    except Exception as e:
        logger.error(f"Lỗi khi dừng stream: {e}")
        return jsonify({"error": "Lỗi hệ thống khi dừng stream"}), 500

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
def get_detection_results():
    """Get detection results with pagination"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', app.config['PAGINATION_PER_PAGE'], type=int)
        
        # Limit per_page to prevent abuse
        per_page = min(per_page, 100)
        
        results, total_count = DetectionService.get_detection_results(page, per_page)
        
        return jsonify({
            "results": results,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total_count,
                "pages": (total_count + per_page - 1) // per_page
            }
        })
    
    except Exception as e:
        logger.error(f"Lỗi khi lấy kết quả phát hiện: {e}")
        return jsonify({"error": "Lỗi hệ thống khi lấy kết quả phát hiện"}), 500

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

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint không tồn tại"}), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({"error": "Phương thức HTTP không được phép"}), 405

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Lỗi hệ thống: {error}")
    return jsonify({"error": "Lỗi hệ thống nội bộ"}), 500

# Khởi tạo dữ liệu
try:
    init_database()
    logger.info("Ứng dụng khởi tạo thành công")
except Exception as e:
    logger.error(f"Lỗi khởi tạo ứng dụng: {e}")

if __name__ == '__main__':
    try:
        logger.info("Khởi động server...")
        socketio.run(app, debug=app.config['DEBUG'], host='0.0.0.0', port=5000)
    except Exception as e:
        logger.error(f"Lỗi khởi động server: {e}") 