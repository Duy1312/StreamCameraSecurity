from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()

class Camera(db.Model):
    """Model cho camera"""
    __tablename__ = 'cameras'
    
    id = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    ip = db.Column(db.String(15), nullable=False, unique=True)
    location = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), default='offline')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    detections = db.relationship('Detection', backref='camera', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Camera {self.id}: {self.name}>'
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'ip': self.ip,
            'location': self.location,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    @staticmethod
    def from_dict(data):
        """Create camera from dictionary"""
        camera = Camera(
            id=data.get('id'),
            name=data.get('name'),
            ip=data.get('ip'),
            location=data.get('location'),
            status=data.get('status', 'offline')
        )
        return camera

class Detection(db.Model):
    """Model cho kết quả phát hiện khuôn mặt"""
    __tablename__ = 'detections'
    
    id = db.Column(db.Integer, primary_key=True)
    camera_id = db.Column(db.String(50), db.ForeignKey('cameras.id'), nullable=False)
    timestamp = db.Column(db.Integer, nullable=False)
    image_path = db.Column(db.String(255), nullable=False)
    faces_count = db.Column(db.Integer, default=0)
    test_mode = db.Column(db.Boolean, default=False)
    real_camera = db.Column(db.Boolean, default=False)
    schedule_id = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Indexes for better performance
    __table_args__ = (
        db.Index('idx_camera_timestamp', 'camera_id', 'timestamp'),
        db.Index('idx_timestamp', 'timestamp'),
        db.Index('idx_schedule', 'schedule_id'),
    )
    
    def __repr__(self):
        return f'<Detection {self.id}: {self.camera_id} at {self.timestamp}>'
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'camera_id': self.camera_id,
            'timestamp': self.timestamp,
            'image_path': self.image_path,
            'faces_count': self.faces_count,
            'test_mode': self.test_mode,
            'real_camera': self.real_camera,
            'schedule_id': self.schedule_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'camera_info': self.camera.to_dict() if self.camera else {}
        }

class StreamSession(db.Model):
    """Model cho tracking stream sessions"""
    __tablename__ = 'stream_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    camera_id = db.Column(db.String(50), db.ForeignKey('cameras.id'), nullable=False)
    session_id = db.Column(db.String(100), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='active')  # active, stopped, error
    
    def __repr__(self):
        return f'<StreamSession {self.id}: {self.camera_id}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'camera_id': self.camera_id,
            'session_id': self.session_id,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'status': self.status
        }

class DetectionSchedule(db.Model):
    """Model cho lịch trình phát hiện"""
    __tablename__ = 'detection_schedules'
    
    id = db.Column(db.String(100), primary_key=True)
    camera_ids = db.Column(db.Text, nullable=False)  # JSON string of camera IDs
    duration = db.Column(db.Integer, nullable=False)  # in minutes
    status = db.Column(db.String(20), default='active')  # active, completed, cancelled
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<DetectionSchedule {self.id}: {self.status}>'
    
    def get_camera_ids(self):
        """Get camera IDs as list"""
        try:
            return json.loads(self.camera_ids)
        except:
            return []
    
    def set_camera_ids(self, camera_list):
        """Set camera IDs from list"""
        self.camera_ids = json.dumps(camera_list)
    
    def to_dict(self):
        return {
            'id': self.id,
            'camera_ids': self.get_camera_ids(),
            'duration': self.duration,
            'status': self.status,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        } 