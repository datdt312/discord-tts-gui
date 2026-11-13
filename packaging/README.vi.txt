DISCORD TTS GUI — BẢN LINUX

Dành cho Ubuntu/Kubuntu 22.04 trở lên, Linux Mint 21 trở lên và các bản
Debian tương thích có Python 3.10 trở lên. Gói không chứa mã máy theo kiến
trúc CPU; thư viện hệ thống được trình cài đặt lấy đúng theo máy của bạn.
Chưa kiểm thử trực tiếp trên từng phiên bản Kubuntu/Mint.

CÀI BẰNG CHUỘT
1. Bấm đúp file discord-tts-gui_1.2.0_all.deb.
2. Chọn Install/Cài đặt và nhập mật khẩu quản trị khi hệ thống yêu cầu.
   Lần đầu cần Internet để tải các thành phần còn thiếu từ kho của hệ điều hành.
3. Mở menu ứng dụng, tìm “Discord TTS GUI (Linux)” và bấm mở.
   Bạn có thể ghim biểu tượng vào thanh tác vụ để mở lại nhanh.

Nếu bấm đúp không mở trình cài gói, chọn Open With/Mở bằng Discover trên
Kubuntu hoặc GDebi/Package Installer trên Linux Mint. Có thể cài bằng lệnh:
  sudo apt install ./discord-tts-gui_1.2.0_all.deb

SỬ DỤNG
1. Bấm “Create virtual mic”.
2. Trong Discord → User Settings → Voice & Video, chọn thiết bị đầu vào
   “Discord_TTS_Microphone”. Nếu chưa thấy, mở lại danh sách thiết bị.
3. VieNeu-TTS là mặc định. Lần đầu bấm Download để cài giọng offline.
   Chọn giọng, nhập nội dung, bấm Speak. Có thể chọn Microsoft Edge để dùng online.
4. Bấm Stop để dừng. Đóng app sẽ dừng phát và gỡ mic ảo do app tạo.

GIAO DIỆN MỚI
App dùng Qt: PyQt6 trên hệ mới, PyQt5 trên Ubuntu 22.04/Mint 21. Trình cài
lấy thư viện phù hợp từ kho hệ điều hành. Các nút Speak, Stop, Create virtual
mic luôn ở phía dưới; phần nội dung/cài đặt cuộn được khi cửa sổ nhỏ.
Mở “Audio & settings” để chọn loa, trộn mic, làm mới thiết bị hoặc sửa model.
Thông tin tiến trình tự ẩn khi tải/cài kết thúc. Tải thành công thì nút Download
cũng ẩn; nút Repair / download AI voices nằm trong Audio & settings.

Khi đang đọc, bấm Speak lại sẽ dừng lượt cũ và đọc nội dung hiện tại.
Đổi model hoặc giọng khi đang đọc cũng dừng lượt cũ rồi đọc lại text hiện tại.
Bấm liên tiếp chỉ giữ yêu cầu mới nhất; các lượt đọc không phát chồng nhau.
Stop huỷ cả lượt đang đọc và lượt chờ phát lại. Đổi model khi đang rảnh sẽ
không tự đọc. Model đã tải được giữ nguyên khi nâng cấp.

Trong ô nhập, Ctrl+A chọn toàn bộ. Ctrl+V thay thế phần đang bôi đen;
nếu không có vùng chọn thì chèn tại con trỏ. Ctrl+Z hoàn tác lần dán.

Bản này đã có phát trực tiếp từng phần âm thanh (streaming). Giọng online
cần Internet và gửi nội dung tới Microsoft. eSpeak NG là lựa chọn offline.

GIỌNG AI OFFLINE TỰ NHIÊN HƠN
Chọn “VieNeu-TTS v3 Turbo (offline AI)”, bấm “Download offline AI voices”.
Lần đầu cần Internet để cài runtime và tải model; nên dành vài GB dung lượng
trống. Không cần API key. Runtime được cài vào môi trường Python riêng trong
thư mục cá nhân, không cài vào Python hệ thống. Gói .deb nhỏ không chứa weights.

Model FP32 chính khoảng 475 MB, codec khoảng 91 MB, tổng khoảng 566 MB
chưa tính runtime và cache. Cả bộ cài và bản sao ONNX cục bộ có thể chiếm
khoảng 2–3 GB tuỳ phiên bản thư viện. Thanh tiến trình hiển thị % CỦA FILE
ĐANG TẢI cùng số MB/GB đã nhận trên tổng dung lượng và tên file. File đã có
trong cache sẽ được ghi rõ. Nếu chưa biết tổng dung lượng, app hiển thị số
byte đã tải và trạng thái đang chạy. Cài thư viện/nạp model/kiểm tra offline
có trạng thái riêng; file đạt 100% chưa có nghĩa toàn bộ bước cài đã xong.

Nếu bản 1.1.0 báo “External data path escapes model directory”, đóng app,
cài bản 1.2.0 rồi bấm Download/Repair lại. KHÔNG cần xoá cache hoặc tải lại toàn bộ.
Bản này đặt file ONNX và weights đi kèm thành các file thường cạnh nhau để
ONNX Runtime nạp được, thay vì theo liên kết sang các thư mục blob khác nhau.

Chờ báo sẵn sàng, chọn giọng trong danh sách rồi bấm Speak. App kiểm tra model
chạy được với chế độ offline trước khi đánh dấu sẵn sàng. Khi đọc, nội dung
được xử lý trên máy bằng CPU/ONNX fp32, âm thanh 48 kHz được phát từng phần.
Model giữ trong RAM giữa các câu; Stop hoặc đóng app giải phóng tiến trình.
Lần đọc đầu sau đó sẽ cần nạp lại model. eSpeak vẫn có sẵn nhưng giọng máy móc.

Model được lưu ở ~/.local/share/discord-tts-gui/neural/v3turbo-onnx-fp32
(hoặc trong XDG_DATA_HOME nếu đã cấu hình). Nâng cấp .deb không xoá model.
Nếu cài/tải chưa thành công, bấm lại nút Download để sửa; app không tự đổi sang
giọng khác. Bản 1.1.1 đã dùng SDK và cache model thật để kiểm tra nạp model,
khởi động offline, 25 giọng dựng sẵn và xuất WAV thành công sau khi sửa lỗi.
Chất lượng nghe và phát qua thiết bị thực tế vẫn cần nghe thử trên máy của bạn.

Thông báo online “3 attempts” là thử lại 3 lần cho MỘT câu bị lỗi, không phải
giới hạn đọc 3 câu. Microsoft không trả audio chưa đủ để kết luận bị rate-limit.
edge-tts không có chức năng tải model Hoài My/Nam Minh để chạy offline.

NÂNG CẤP TỪ BẢN CŨ
Đóng các cửa sổ app cũ trước khi cài. Nếu trước đây dùng install.sh, biểu
tượng “Discord TTS GUI” cũ có thể vẫn xuất hiện; hãy mở đúng biểu tượng
“Discord TTS GUI (Linux)”. Gói không ghi đè hay xoá dữ liệu trong thư mục
cá nhân của bạn. Những lần nâng cấp bằng .deb sau sẽ thay thế cùng gói này.

CHẨN ĐOÁN
  discord-tts-gui --check
  discord-tts-gui
Lỗi khởi động được ghi vào ~/.local/state/discord-tts-gui/startup.log
(hoặc thư mục XDG_STATE_HOME nếu được cấu hình).
Giao diện Qt cần phiên X11/XWayland hoặc Wayland trên desktop.
Âm thanh cần PipeWire với tương thích PulseAudio hoặc PulseAudio.

GỠ CÀI ĐẶT
Tìm “discord-tts-gui” trong trình quản lý gói để Remove/Gỡ, hoặc chạy:
  sudo apt remove discord-tts-gui

Gói .deb này dùng cho họ Ubuntu/Debian; không cài trực tiếp trên Fedora,
Arch, openSUSE. Các hệ đó có thể dùng mã nguồn với các phụ thuộc tương đương.
