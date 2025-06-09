# Hệ thống Camera An ninh

Hệ thống quản lý và stream camera an ninh với khả năng phát hiện khuôn mặt người sử dụng OpenCV.

## Tính năng

- Stream tối đa 400 camera
- Hiển thị 20 camera cùng lúc
- Lên lịch phát hiện khuôn mặt cho 20 camera trong 1 giờ
- Lưu ảnh khi phát hiện khuôn mặt
- Hiển thị thông tin chi tiết về camera: IP, vị trí
- Thông báo khi phát hiện khuôn mặt
- Giao diện người dùng thân thiện

## Yêu cầu hệ thống

- Python 3.6+
- OpenCV
- Flask
- Các thư viện Python khác (xem file requirements.txt)

## Cài đặt

1. Clone repository:

```
git clone [url-repository]
cd StreamCameraSecurity
```

2. Cài đặt các thư viện phụ thuộc:

```
pip install -r requirements.txt
```

3. Tạo thư mục lưu trữ ảnh:

```
mkdir -p static/images
mkdir -p static/detections
```

4. Thêm ảnh mẫu cho camera:
   Thêm một ảnh có tên `camera-placeholder.jpg` vào thư mục `static/images/`

## Chạy ứng dụng

```
python app.py
```

Sau đó mở trình duyệt và truy cập: http://localhost:5000

## Cấu hình

### Thêm camera thực

Để kết nối với camera IP thực, bạn cần sửa hàm `simulate_camera_frame` trong file `app.py`:

```python
def get_camera_frame(camera_id):
    camera_info = cameras.get(camera_id, {})
    ip = camera_info.get('ip', '')

    # Kết nối với camera IP (ví dụ với OpenCV)
    cap = cv2.VideoCapture(f"rtsp://{ip}/stream")
    ret, frame = cap.read()
    cap.release()

    if not ret:
        # Trả về frame mặc định nếu không kết nối được
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(frame, "Không thể kết nối", (20, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

    # Thêm thông tin camera
    cv2.putText(frame, camera_info.get("name", ""), (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    cv2.putText(frame, f"IP: {ip}", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.putText(frame, f"Location: {camera_info.get('location', '')}", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    return frame
```

Sau đó thay `simulate_camera_frame` bằng `get_camera_frame` trong hàm `run_face_detection`.

### Cấu hình camera

Thông tin camera được lưu trong file `cameras.json`. Bạn có thể chỉnh sửa file này để thêm camera thực của mình.

## Dành cho nhà phát triển

### Cấu trúc dự án

- `app.py`: Mã nguồn chính của ứng dụng Flask
- `templates/`: Chứa các template HTML
- `static/`: Chứa CSS, JavaScript, và tài nguyên tĩnh
- `static/detections/`: Nơi lưu trữ ảnh khi phát hiện khuôn mặt
- `cameras.json`: Cấu hình camera

### Mở rộng

1. **Thêm xác thực người dùng**: Bảo mật hệ thống với đăng nhập và phân quyền
2. **Thêm chức năng ghi lại video**: Lưu lại video khi phát hiện khuôn mặt
3. **Tích hợp nhận dạng khuôn mặt**: Nhận dạng danh tính của người được phát hiện

## Giấy phép

[MIT License](LICENSE)
