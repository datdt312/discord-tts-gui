# Chuẩn bị Git remote

Bộ nguồn không tự kết nối GitHub, đăng nhập hoặc push. Bạn chọn URL remote và
thực hiện các lệnh bên dưới trong Terminal tại thư mục dự án.

## Thông tin repository

| Trường | Giá trị đề xuất |
| --- | --- |
| Name | `discord-tts-gui` |
| Description | Cross-platform Vietnamese AI text-to-speech for Discord on Linux, Windows and macOS, with Qt UI and offline voices. |
| Visibility | Public, theo lựa chọn của chủ dự án |
| Default branch | `main` |
| License | Chưa chọn; không tự thêm giấy phép |
| README / .gitignore | Dùng các file có sẵn trong bộ nguồn |

Nếu tạo repository trống trên GitHub, bỏ chọn tạo README, .gitignore và license
tự động để tránh phát sinh lịch sử riêng trước lần push đầu.

## Kiểm tra trước khi commit

Dùng Python trong môi trường phát triển đã thiết lập:

```bash
python tools/check_repo.py
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -t . -v
```

Chi tiết cho PowerShell và các kiểm thử phụ thuộc hệ điều hành nằm trong
[hướng dẫn kiểm thử](testing.md). Model, cache, môi trường Python, file cài
và dữ liệu cá nhân được loại khỏi bộ nguồn xuất bằng [exporter](../tools/export_source.py).

## Nếu dùng bộ nguồn ZIP mới

Giải nén vào thư mục mới, rồi chạy:

```bash
git init -b main
git add .
git diff --cached --check
git status --short
git commit -m "chore: prepare project and engineering harness"
git remote add origin <REMOTE_URL>
git push -u origin main
```

Thay `<REMOTE_URL>` bằng URL HTTPS hoặc SSH của repository bạn đã tạo.
Không ghi token vào URL hoặc commit thông tin đăng nhập.

## Nếu dùng bản Git đã chuẩn bị

Bản bàn giao Git ở `dist/github-source` đã có nhánh `main` và lịch sử commit.
Từ thư mục dự án gốc:

```bash
cd dist/github-source
git status --short
git remote -v
git remote add origin <REMOTE_URL>
git push -u origin main
```

Nếu đã có `origin`, kiểm tra URL hiện tại trước; chỉ dùng `git remote set-url
origin <REMOTE_URL>` khi bạn muốn thay URL đó. Nếu remote có commit riêng,
fetch và tích hợp lịch sử trước khi push; không force push để bỏ qua xung đột.

Trong môi trường agent hiện tại, `.git` của thư mục làm việc bị khóa ghi; bản
Git độc lập ở `dist/github-source` tránh đụng vào metadata được môi trường bảo vệ.
Đây không phải yêu cầu khi clone/giải nén dự án trên máy khác.

## Bundle và build

Có thể mang bản Git sang máy khác bằng `dist/discord-tts-gui-github.bundle`:

```bash
git clone discord-tts-gui-github.bundle discord-tts-gui
cd discord-tts-gui
git remote remove origin
git remote add origin <REMOTE_URL>
git push -u origin main
```

Sau khi push, workflow **Repository checks** kiểm tra source/docs và test.
Workflow **Build native desktop packages** chạy thủ công hoặc khi push tag
`v*`, tạo artifacts Linux/Windows/macOS; không tự đăng GitHub Release.
Xem [quy trình phát hành](releasing.md) trước khi gắn tag hoặc phân phối binary.
