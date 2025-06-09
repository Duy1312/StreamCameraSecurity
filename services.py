import asyncio
import concurrent.futures
import logging
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import uuid
import cv2
import numpy as np
import os

from models import db, Camera, Detection, StreamSession, DetectionSchedule
from cache import CameraCache, StreamCache, DetectionCache, cache_manager
from config import Config

logger = logging.getLogger(__name__)

class CameraService:
    """Service layer cho Camera operations"""
    
    @staticmethod
    def get_all_cameras(use_cache=True) -> Dict:
        """Lấy tất cả camera với caching"""
        if use_cache:
            cached_cameras = CameraCache.get_all_cameras()
            if cached_cameras:
                logger.debug("Trả về cameras từ cache")
                return cached_cameras
        
        try:
            cameras = Camera.query.all()
            cameras_dict = {camera.id: camera.to_dict() for camera in cameras}
            
            if use_cache:
                CameraCache.set_all_cameras(cameras_dict, expire=Config.CACHE_CAMERAS_TIMEOUT)
            
            logger.info(f"Lấy {len(cameras_dict)} cameras từ database")
            return cameras_dict
        
        except Exception as e:
            logger.error(f"Lỗi khi lấy cameras: {e}")
            return {}
    
    @staticmethod
    def get_camera_by_id(camera_id: str, use_cache=True) -> Optional[Dict]:
        """Lấy camera theo ID với caching"""
        if use_cache:
            cached_camera = CameraCache.get_camera_detail(camera_id)
            if cached_camera:
                return cached_camera
        
        try:
            camera = Camera.query.get(camera_id)
            if camera:
                camera_dict = camera.to_dict()
                if use_cache:
                    CameraCache.set_camera_detail(camera_id, camera_dict)
                return camera_dict
            return None
        
        except Exception as e:
            logger.error(f"Lỗi khi lấy camera {camera_id}: {e}")
            return None
    
    @staticmethod
    def create_camera(camera_data: Dict) -> Tuple[bool, str, Optional[Dict]]:
        """Tạo camera mới"""
        try:
            # Check if IP already exists
            existing_camera = Camera.query.filter_by(ip=camera_data['ip']).first()
            if existing_camera:
                return False, "IP camera đã tồn tại", None
            
            # Generate new ID
            cameras_count = Camera.query.count()
            camera_id = f"cam_{cameras_count + 1}"
            
            camera = Camera(
                id=camera_id,
                name=camera_data['name'],
                ip=camera_data['ip'],
                location=camera_data['location'],
                status=camera_data.get('status', 'offline')
            )
            
            db.session.add(camera)
            db.session.commit()
            
            # Invalidate cache
            CameraCache.invalidate_all()
            
            logger.info(f"Tạo camera mới: {camera_id}")
            return True, "Camera đã được tạo thành công", camera.to_dict()
        
        except Exception as e:
            db.session.rollback()
            logger.error(f"Lỗi khi tạo camera: {e}")
            return False, f"Lỗi hệ thống: {str(e)}", None
    
    @staticmethod
    def update_camera(camera_id: str, update_data: Dict) -> Tuple[bool, str, Optional[Dict]]:
        """Cập nhật camera"""
        try:
            camera = Camera.query.get(camera_id)
            if not camera:
                return False, "Camera không tồn tại", None
            
            # Check IP conflict if IP is being updated
            if 'ip' in update_data and update_data['ip'] != camera.ip:
                existing_camera = Camera.query.filter_by(ip=update_data['ip']).first()
                if existing_camera:
                    return False, "IP camera đã tồn tại", None
            
            # Update fields
            for field in ['name', 'ip', 'location', 'status']:
                if field in update_data:
                    setattr(camera, field, update_data[field])
            
            camera.updated_at = datetime.utcnow()
            db.session.commit()
            
            # Invalidate cache
            CameraCache.invalidate_camera(camera_id)
            
            logger.info(f"Cập nhật camera: {camera_id}")
            return True, "Camera đã được cập nhật", camera.to_dict()
        
        except Exception as e:
            db.session.rollback()
            logger.error(f"Lỗi khi cập nhật camera {camera_id}: {e}")
            return False, f"Lỗi hệ thống: {str(e)}", None
    
    @staticmethod
    def delete_camera(camera_id: str) -> Tuple[bool, str]:
        """Xóa camera"""
        try:
            camera = Camera.query.get(camera_id)
            if not camera:
                return False, "Camera không tồn tại"
            
            # Stop any active streams
            StreamService.stop_camera_stream(camera_id)
            
            # Delete camera (cascade will delete related records)
            db.session.delete(camera)
            db.session.commit()
            
            # Invalidate cache
            CameraCache.invalidate_camera(camera_id)
            StreamCache.invalidate_streams()
            
            logger.info(f"Xóa camera: {camera_id}")
            return True, "Camera đã được xóa"
        
        except Exception as e:
            db.session.rollback()
            logger.error(f"Lỗi khi xóa camera {camera_id}: {e}")
            return False, f"Lỗi hệ thống: {str(e)}"

class StreamService:
    """Service layer cho Stream operations"""
    
    active_streams = set()  # In-memory active streams tracking
    
    @staticmethod
    def get_active_streams(use_cache=True) -> List[str]:
        """Lấy danh sách stream đang hoạt động"""
        if use_cache:
            cached_streams = StreamCache.get_active_streams()
            if cached_streams is not None:
                return cached_streams
        
        # Return from in-memory tracking
        streams_list = list(StreamService.active_streams)
        
        if use_cache:
            StreamCache.set_active_streams(streams_list)
        
        return streams_list
    
    @staticmethod
    def start_camera_stream(camera_id: str) -> Tuple[bool, str]:
        """Bắt đầu stream camera"""
        try:
            # Check camera exists
            camera = Camera.query.get(camera_id)
            if not camera:
                return False, "Camera không tồn tại"
            
            # Check stream limit
            if len(StreamService.active_streams) >= Config.MAX_CAMERAS_STREAM and camera_id not in StreamService.active_streams:
                return False, f"Không thể stream quá {Config.MAX_CAMERAS_STREAM} camera cùng lúc"
            
            # Add to active streams
            StreamService.active_streams.add(camera_id)
            
            # Create stream session record
            session = StreamSession(
                camera_id=camera_id,
                session_id=str(uuid.uuid4()),
                status='active'
            )
            db.session.add(session)
            db.session.commit()
            
            # Invalidate cache
            StreamCache.invalidate_streams()
            
            logger.info(f"Bắt đầu stream camera {camera_id}")
            return True, "Stream đã được bắt đầu"
        
        except Exception as e:
            db.session.rollback()
            logger.error(f"Lỗi khi bắt đầu stream {camera_id}: {e}")
            return False, f"Lỗi hệ thống: {str(e)}"
    
    @staticmethod
    def stop_camera_stream(camera_id: str) -> Tuple[bool, str]:
        """Dừng stream camera"""
        try:
            # Remove from active streams
            StreamService.active_streams.discard(camera_id)
            
            # Update stream session records
            active_sessions = StreamSession.query.filter_by(
                camera_id=camera_id,
                status='active'
            ).all()
            
            for session in active_sessions:
                session.ended_at = datetime.utcnow()
                session.status = 'stopped'
            
            if active_sessions:
                db.session.commit()
            
            # Invalidate cache
            StreamCache.invalidate_streams()
            
            logger.info(f"Dừng stream camera {camera_id}")
            return True, "Stream đã được dừng"
        
        except Exception as e:
            db.session.rollback()
            logger.error(f"Lỗi khi dừng stream {camera_id}: {e}")
            return False, f"Lỗi hệ thống: {str(e)}"
    
    @staticmethod
    def stop_all_streams() -> Tuple[bool, str]:
        """Dừng tất cả streams"""
        try:
            camera_ids = list(StreamService.active_streams)
            for camera_id in camera_ids:
                StreamService.stop_camera_stream(camera_id)
            
            logger.info(f"Dừng tất cả {len(camera_ids)} streams")
            return True, f"Đã dừng {len(camera_ids)} streams"
        
        except Exception as e:
            logger.error(f"Lỗi khi dừng tất cả streams: {e}")
            return False, f"Lỗi hệ thống: {str(e)}"

class DetectionService:
    """Service layer cho Face Detection operations"""
    
    @staticmethod
    def get_detection_results(page=1, per_page=None, use_cache=True) -> Tuple[List[Dict], int]:
        """Lấy kết quả phát hiện với pagination"""
        if per_page is None:
            per_page = Config.PAGINATION_PER_PAGE
        
        # Try cache first
        if use_cache:
            cached_results = DetectionCache.get_detection_results(page)
            cached_count = DetectionCache.get_detection_count()
            if cached_results is not None and cached_count is not None:
                return cached_results, cached_count
        
        try:
            # Get paginated results
            query = Detection.query.order_by(Detection.timestamp.desc())
            pagination = query.paginate(
                page=page,
                per_page=per_page,
                error_out=False
            )
            
            results = [detection.to_dict() for detection in pagination.items]
            total_count = pagination.total
            
            # Cache results
            if use_cache:
                DetectionCache.set_detection_results(page, results)
                DetectionCache.set_detection_count(total_count)
            
            logger.debug(f"Lấy {len(results)} detection results (page {page})")
            return results, total_count
        
        except Exception as e:
            logger.error(f"Lỗi khi lấy detection results: {e}")
            return [], 0
    
    @staticmethod
    def save_detection_result(camera_id: str, timestamp: int, image_path: str, 
                            faces_count: int = 0, test_mode: bool = False, 
                            real_camera: bool = False, schedule_id: str = None) -> bool:
        """Lưu kết quả phát hiện"""
        try:
            detection = Detection(
                camera_id=camera_id,
                timestamp=timestamp,
                image_path=image_path,
                faces_count=faces_count,
                test_mode=test_mode,
                real_camera=real_camera,
                schedule_id=schedule_id
            )
            
            db.session.add(detection)
            db.session.commit()
            
            # Invalidate cache
            DetectionCache.invalidate_detection_results()
            
            logger.info(f"Lưu detection result cho camera {camera_id}")
            return True
        
        except Exception as e:
            db.session.rollback()
            logger.error(f"Lỗi khi lưu detection result: {e}")
            return False

class AsyncFaceDetectionService:
    """Service cho async face detection processing"""
    
    def __init__(self, max_workers=None):
        if max_workers is None:
            max_workers = Config.MAX_WORKERS
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    
    async def process_camera_frame_async(self, camera_id: str, schedule_id: str = None) -> Optional[Dict]:
        """Xử lý frame camera async"""
        loop = asyncio.get_event_loop()
        
        try:
            # Run face detection in thread pool
            result = await loop.run_in_executor(
                self.executor,
                self._process_single_camera,
                camera_id,
                schedule_id
            )
            return result
        
        except Exception as e:
            logger.error(f"Lỗi async face detection cho camera {camera_id}: {e}")
            return None
    
    def _process_single_camera(self, camera_id: str, schedule_id: str = None) -> Optional[Dict]:
        """Xử lý một camera (chạy trong thread pool)"""
        try:
            # Simulate camera frame (replace with real camera connection)
            frame = self._simulate_camera_frame(camera_id)
            if frame is None:
                return None
            
            # Convert to grayscale
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Detect faces
            faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
            
            if len(faces) > 0:
                # Draw rectangles around faces
                for (x, y, w, h) in faces:
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)
                
                # Save image
                timestamp = int(time.time())
                filename = f"{camera_id}_{timestamp}.jpg"
                if schedule_id:
                    filename = f"{camera_id}_{timestamp}_{schedule_id}.jpg"
                
                filepath = os.path.join(Config.DETECTION_FOLDER, filename)
                cv2.imwrite(filepath, frame)
                
                # Save to database
                image_path = f"/static/detections/{filename}"
                DetectionService.save_detection_result(
                    camera_id=camera_id,
                    timestamp=timestamp,
                    image_path=image_path,
                    faces_count=len(faces),
                    test_mode=False,
                    real_camera=False,
                    schedule_id=schedule_id
                )
                
                return {
                    "camera_id": camera_id,
                    "timestamp": timestamp,
                    "image_path": image_path,
                    "faces_count": len(faces),
                    "schedule_id": schedule_id
                }
            
            return None
        
        except Exception as e:
            logger.error(f"Lỗi khi xử lý camera {camera_id}: {e}")
            return None
    
    def _simulate_camera_frame(self, camera_id: str):
        """Simulate camera frame (replace with real camera connection)"""
        try:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            
            # 30% chance of having a face for demo
            if np.random.random() < 0.3:
                # Draw a circle representing a face
                cv2.circle(frame, (320, 240), 100, (0, 0, 255), -1)
                cv2.circle(frame, (280, 200), 20, (255, 255, 255), -1)  # Left eye
                cv2.circle(frame, (360, 200), 20, (255, 255, 255), -1)  # Right eye
                cv2.ellipse(frame, (320, 280), (60, 30), 0, 0, 180, (255, 255, 255), -1)  # Mouth
            
            # Add camera info
            camera = CameraService.get_camera_by_id(camera_id)
            if camera:
                cv2.putText(frame, camera["name"], (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                cv2.putText(frame, f"IP: {camera['ip']}", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                cv2.putText(frame, f"Location: {camera['location']}", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            return frame
        
        except Exception as e:
            logger.error(f"Lỗi khi simulate camera frame {camera_id}: {e}")
            return None
    
    async def process_multiple_cameras_async(self, camera_ids: List[str], schedule_id: str = None) -> List[Dict]:
        """Xử lý nhiều camera async"""
        tasks = []
        for camera_id in camera_ids:
            task = self.process_camera_frame_async(camera_id, schedule_id)
            tasks.append(task)
        
        try:
            # Wait for all tasks with timeout
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=Config.FACE_DETECTION_TIMEOUT
            )
            
            # Filter successful results
            successful_results = []
            for result in results:
                if isinstance(result, dict):
                    successful_results.append(result)
                elif isinstance(result, Exception):
                    logger.error(f"Task failed: {result}")
            
            return successful_results
        
        except asyncio.TimeoutError:
            logger.warning(f"Face detection timeout for {len(camera_ids)} cameras")
            return []
        except Exception as e:
            logger.error(f"Lỗi khi xử lý multiple cameras: {e}")
            return []
    
    def cleanup(self):
        """Cleanup executor"""
        self.executor.shutdown(wait=True)

# Global async face detection service instance
async_face_detection_service = AsyncFaceDetectionService() 