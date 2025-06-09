# Hệ thống Camera An ninh - StreamCameraSecurity

Hệ thống giám sát và phát hiện khuôn mặt cho hệ thống camera an ninh với giao diện web hiện đại.

## Tính năng chính

- ✅ Quản lý tối đa 400 camera
- ✅ Stream đồng thời tối đa 20 camera
- ✅ Phát hiện khuôn mặt tự động
- ✅ Lên lịch phát hiện cho nhiều camera
- ✅ Test camera thật qua webcam
- ✅ Giao diện web responsive
- ✅ Thông báo real-time qua WebSocket
- ✅ Lưu trữ và quản lý kết quả phát hiện

## Cài đặt và Chạy

### Yêu cầu hệ thống

- Python 3.8+
- Camera (tùy chọn cho tính năng test camera thật)

### 1. Cài đặt dependencies

```bash
pip install -r requirements.txt
```

### 2. Cấu hình bảo mật (QUAN TRỌNG)

```bash
# Sao chép file cấu hình mẫu
cp example.env .env

# Chỉnh sửa file .env
# Thay đổi SECRET_KEY thành một chuỗi bí mật phức tạp
# Điều chỉnh các cài đặt khác theo nhu cầu
```

**Cài đặt bảo mật quan trọng:**

- `SECRET_KEY`: Thay đổi thành chuỗi bí mật phức tạp (tối thiểu 32 ký tự)
- `FLASK_ENV`: Đặt `production` cho môi trường sản xuất
- `MAX_FILE_SIZE`: Giới hạn kích thước file upload (mặc định 10MB)

### 3. Chạy ứng dụng

```bash
python app.py
```

Ứng dụng sẽ chạy tại: http://localhost:5000

## Cấu trúc dự án

```
StreamCameraSecurity/
├── app.py                 # Ứng dụng Flask chính
├── config.py             # Cấu hình và validation
├── requirements.txt      # Dependencies
├── example.env          # File cấu hình mẫu
├── .env                 # File cấu hình thực (tạo từ example.env)
├── cameras.json         # Dữ liệu camera (tự động tạo)
├── templates/
│   └── index.html       # Giao diện web
├── static/
│   ├── css/            # Stylesheets
│   ├── js/             # JavaScript
│   ├── fonts/          # Fonts
│   └── detections/     # Ảnh phát hiện khuôn mặt
└── README.md
```

## Sử dụng

### 1. Quản lý Camera

- **Xem danh sách**: Tất cả camera được hiển thị với trạng thái
- **Thêm camera**: Nhập tên, IP và vị trí
- **Sửa camera**: Cập nhật thông tin camera
- **Xóa camera**: Xóa camera khỏi hệ thống

### 2. Stream Camera

- Chọn camera từ danh sách
- Click "Bắt đầu Stream"
- Tối đa 20 camera cùng lúc
- Click "Dừng Stream" để ngừng

### 3. Phát hiện Khuôn mặt

#### Chế độ thủ công

- Sử dụng camera đang stream
- Đặt thời gian phát hiện (1-120 phút)
- Bắt đầu phát hiện

#### Chế độ tự động

- Tự động check 20 camera/chu kỳ
- Tiến trình từ camera 1 đến 400
- Đặt thời gian cho mỗi chu kỳ

### 4. Test Camera Thật

- Truy cập tab "📷 Test Camera Thật"
- Cho phép trình duyệt truy cập camera
- Click "Chụp và phát hiện khuôn mặt"

## API Endpoints

### Camera Management

- `GET /api/cameras` - Lấy danh sách camera
- `POST /api/cameras` - Thêm camera mới
- `PUT /api/cameras/<id>` - Cập nhật camera
- `DELETE /api/cameras/<id>` - Xóa camera

### Streaming

- `GET /api/active-streams` - Lấy danh sách stream đang hoạt động
- `POST /api/start-stream` - Bắt đầu stream camera
- `POST /api/stop-stream` - Dừng stream camera

### Face Detection

- `POST /api/schedule-detection` - Lên lịch phát hiện
- `GET /api/detection-results` - Lấy kết quả phát hiện
- `POST /api/test-face-detection` - Test phát hiện (camera giả)
- `POST /api/test-real-camera` - Test camera thật

## Tính năng Bảo mật

- ✅ Validation đầu vào đầy đủ
- ✅ Sanitization dữ liệu
- ✅ Rate limiting cho upload
- ✅ Error handling an toàn
- ✅ Logging hệ thống
- ✅ Cấu hình môi trường riêng biệt
- ✅ Kiểm tra định dạng IP
- ✅ Giới hạn kích thước file

## Monitoring và Logs

Ứng dụng ghi log các hoạt động quan trọng:

- Khởi tạo hệ thống
- Thêm/sửa/xóa camera
- Bắt đầu/dừng stream
- Phát hiện khuôn mặt
- Lỗi hệ thống

## Môi trường Production

Để triển khai production:

1. **Cấu hình bảo mật**:

```bash
# Trong file .env
FLASK_ENV=production
FLASK_DEBUG=False
SECRET_KEY=very_long_and_complex_secret_key_here
```

2. **Sử dụng WSGI server**:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 "app:app"
```

3. **Reverse proxy** (Nginx recommended)
4. **SSL/HTTPS** cho bảo mật
5. **Backup định kỳ** cho cameras.json

## Troubleshooting

### Lỗi thường gặp

1. **Camera không stream được**

   - Kiểm tra IP camera có đúng không
   - Đảm bảo không vượt quá 20 camera đồng thời

2. **Không phát hiện được khuôn mặt**

   - Kiểm tra camera có hoạt động không
   - Đảm bảo có đủ ánh sáng
   - Thử tính năng test trước

3. **Lỗi kết nối**

   - Kiểm tra port 5000 có bị chặn không
   - Đảm bảo firewall cho phép kết nối

4. **Lỗi cấu hình**
   - Kiểm tra file .env có tồn tại không
   - Đảm bảo SECRET_KEY đã được đặt

## Đóng góp

Chào mừng mọi đóng góp để cải thiện dự án!

## Giấy phép

Dự án này được phát hành dưới giấy phép MIT.
