from flask import Flask, render_template, jsonify, request, redirect, url_for
from flask_socketio import SocketIO
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

app = Flask(__name__)
app.config['SECRET_KEY'] = 'streamcamerasecurity'
socketio = SocketIO(app)

# Thư mục lưu trữ ảnh khi phát hiện khuôn mặt
UPLOAD_FOLDER = 'static/detections'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Danh sách camera
cameras = {}
active_streams = set()
face_detection_schedule = {}
face_detection_active = {}
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

# Đọc danh sách camera từ file JSON hoặc tạo mới
def load_cameras():
    global cameras
    try:
        with open('cameras.json', 'r') as f:
            cameras = json.load(f)
    except FileNotFoundError:
        # Tạo dữ liệu mẫu cho 400 camera
        cameras = {}
        for i in range(1, 401):
            camera_id = f"cam_{i}"
            cameras[camera_id] = {
                "id": camera_id,
                "name": f"Camera {i}",
                "ip": f"192.168.1.{i % 255}",
                "location": f"Khu vực {(i-1)//20 + 1}, Phòng {(i-1)%20 + 1}",
                "status": "offline"
            }
        save_cameras()
    return cameras

def save_cameras():
    with open('cameras.json', 'w') as f:
        json.dump(cameras, f)

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/cameras')
def get_cameras():
    return jsonify(cameras)

@app.route('/api/active-streams')
def get_active_streams():
    return jsonify(list(active_streams))

@app.route('/api/start-stream', methods=['POST'])
def start_stream():
    camera_id = request.json.get('camera_id')
    if len(active_streams) >= 20 and camera_id not in active_streams:
        return jsonify({"error": "Không thể stream quá 20 camera cùng lúc"}), 400
    
    if camera_id not in active_streams:
        active_streams.add(camera_id)
    
    return jsonify({"success": True})

@app.route('/api/stop-stream', methods=['POST'])
def stop_stream():
    camera_id = request.json.get('camera_id')
    if camera_id in active_streams:
        active_streams.remove(camera_id)
    
    return jsonify({"success": True})

@app.route('/api/schedule-detection', methods=['POST'])
def schedule_detection():
    camera_ids = request.json.get('camera_ids', [])
    duration = request.json.get('duration', 60) # thời gian tính bằng phút
    
    if len(camera_ids) > 20:
        return jsonify({"error": "Không thể lên lịch quá 20 camera cùng lúc"}), 400
    
    schedule_id = f"schedule_{int(time.time())}"
    face_detection_schedule[schedule_id] = {
        "camera_ids": camera_ids,
        "start_time": datetime.now().isoformat(),
        "duration": duration,
        "status": "active"
    }
    
    # Bắt đầu thread phát hiện khuôn mặt
    threading.Thread(target=run_face_detection, args=(schedule_id, camera_ids, duration)).start()
    
    return jsonify({"schedule_id": schedule_id})

@app.route('/api/detection-results')
def get_detection_results():
    results = []
    for root, dirs, files in os.walk(UPLOAD_FOLDER):
        for file in files:
            if file.endswith('.jpg'):
                camera_id = file.split('_')[0]
                timestamp = file.split('_')[1].replace('.jpg', '')
                
                results.append({
                    "camera_id": camera_id,
                    "timestamp": timestamp,
                    "image_path": f"/static/detections/{file}",
                    "camera_info": cameras.get(camera_id, {})
                })
    
    return jsonify(results)

@app.route('/api/cameras', methods=['POST'])
def add_camera():
    data = request.json
    camera_id = f"cam_{len(cameras) + 1}"
    
    # Validate required fields
    required_fields = ['name', 'ip', 'location']
    for field in required_fields:
        if not data.get(field):
            return jsonify({"error": f"Thiếu trường {field}"}), 400
    
    cameras[camera_id] = {
        "id": camera_id,
        "name": data['name'],
        "ip": data['ip'],
        "location": data['location'],
        "status": data.get('status', 'offline')
    }
    
    save_cameras()
    return jsonify({"success": True, "camera": cameras[camera_id]})

@app.route('/api/cameras/<camera_id>', methods=['PUT'])
def update_camera(camera_id):
    if camera_id not in cameras:
        return jsonify({"error": "Camera không tồn tại"}), 404
    
    data = request.json
    
    # Update camera data
    if 'name' in data:
        cameras[camera_id]['name'] = data['name']
    if 'ip' in data:
        cameras[camera_id]['ip'] = data['ip']
    if 'location' in data:
        cameras[camera_id]['location'] = data['location']
    if 'status' in data:
        cameras[camera_id]['status'] = data['status']
    
    save_cameras()
    return jsonify({"success": True, "camera": cameras[camera_id]})

@app.route('/api/cameras/<camera_id>', methods=['DELETE'])
def delete_camera(camera_id):
    if camera_id not in cameras:
        return jsonify({"error": "Camera không tồn tại"}), 404
    
    # Remove from active streams if streaming
    if camera_id in active_streams:
        active_streams.remove(camera_id)
    
    # Delete camera
    del cameras[camera_id]
    save_cameras()
    
    return jsonify({"success": True})

# Xử lý phát hiện khuôn mặt
def run_face_detection(schedule_id, camera_ids, duration):
    face_detection_active[schedule_id] = True
    end_time = time.time() + (duration * 60)
    
    while time.time() < end_time and face_detection_active.get(schedule_id, False):
        for camera_id in camera_ids:
            # Mô phỏng lấy khung hình từ camera
            # Trong thực tế, bạn sẽ kết nối với camera IP và lấy frame
            frame = simulate_camera_frame(camera_id)
            
            # Chuyển đổi sang thang độ xám
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Phát hiện khuôn mặt
            faces = face_cascade.detectMultiScale(gray, 1.3, 5)
            
            # Nếu phát hiện khuôn mặt, lưu ảnh
            if len(faces) > 0:
                # Vẽ hình chữ nhật xung quanh khuôn mặt
                for (x, y, w, h) in faces:
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)
                
                # Lưu ảnh
                timestamp = int(time.time())
                filename = f"{camera_id}_{timestamp}.jpg"
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                cv2.imwrite(filepath, frame)
                
                # Gửi thông báo qua WebSocket
                detection_data = {
                    "camera_id": camera_id,
                    "timestamp": timestamp,
                    "image_path": f"/static/detections/{filename}",
                    "camera_info": cameras.get(camera_id, {})
                }
                socketio.emit('face_detected', detection_data)
                
        time.sleep(1)  # Kiểm tra mỗi giây
    
    # Kết thúc lịch trình
    if schedule_id in face_detection_active:
        del face_detection_active[schedule_id]
    
    if schedule_id in face_detection_schedule:
        face_detection_schedule[schedule_id]["status"] = "completed"

def simulate_camera_frame(camera_id):
    # Trong thực tế, bạn sẽ kết nối với camera IP và lấy frame thực
    # Đây chỉ là mô phỏng để demo
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    
    # Đôi khi thêm khuôn mặt để demo
    if np.random.random() < 0.1:  # 10% cơ hội có khuôn mặt
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

# Khởi tạo dữ liệu
load_cameras()

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0') 