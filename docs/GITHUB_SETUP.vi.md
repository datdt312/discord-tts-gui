# Khởi tạo repository GitHub

Thông tin đã chuẩn bị cho dự án; repository trực tuyến chưa được tạo.

| Trường | Giá trị |
| --- | --- |
| Owner | `datdt312` |
| Repository name | `discord-tts-gui` |
| Description | Cross-platform Vietnamese AI text-to-speech for Discord on Linux, Windows and macOS, with Qt UI and offline voices. |
| Visibility | **Public** |
| Default branch | `main` |
| Phiên bản hiện tại | `1.3.0` |
| Topics | `discord`, `text-to-speech`, `vietnamese`, `linux`, `windows`, `macos`, `cross-platform`, `pyqt`, `offline-tts`, `vieneu` |
| README | Dùng `README.md` có sẵn |
| .gitignore | Dùng `.gitignore` có sẵn |
| License | Chưa chọn; không tự thêm giấy phép cho mã nguồn của chủ dự án |

Nếu tạo bằng trang GitHub, bỏ chọn tạo README, .gitignore và license tự động,
vì bộ mã nguồn đã có README và .gitignore. URL dự kiến sau khi tạo thành công:
`https://github.com/datdt312/discord-tts-gui`.

## Tạo và push từ bản Git đã chuẩn bị

Trong thư mục dự án gốc, bản mã nguồn đã commit nằm ở `dist/github-source`.
Thư mục này là bản sao độc lập; môi trường Python, cache, model tải về và các
gói `.deb` không nằm trong commit.

Đăng nhập lại nếu cần:

```bash
gh auth login --hostname github.com --web
```

Sau đó, từ thư mục dự án gốc:

```bash
cd dist/github-source
gh repo create datdt312/discord-tts-gui --public --source=. --remote=origin --description "Cross-platform Vietnamese AI text-to-speech for Discord on Linux, Windows and macOS, with Qt UI and offline voices." --push
gh repo view datdt312/discord-tts-gui --json nameWithOwner,url,visibility,defaultBranchRef
```

Nếu repository đã được tạo thủ công và vẫn trống, dùng:

```bash
git remote add origin https://github.com/datdt312/discord-tts-gui.git
git push -u origin main
```

Nếu repository đã có nội dung, xem lại lịch sử trước khi tích hợp; không dùng
force push. Các file `.deb` nên được đính kèm GitHub Release khi phát hành.
Việc tạo repository không tự xuất bản Release.

## Bản sao mang sang máy khác

`dist/discord-tts-gui-github.bundle` chứa commit khởi tạo và nhánh `main`:

```bash
git clone discord-tts-gui-github.bundle discord-tts-gui
cd discord-tts-gui
git remote remove origin
gh repo create datdt312/discord-tts-gui --public --source=. --remote=origin --description "Cross-platform Vietnamese AI text-to-speech for Discord on Linux, Windows and macOS, with Qt UI and offline voices." --push
```

Bundle dùng địa chỉ tác giả `datdt312@users.noreply.github.com`.
Đây là thông tin tác giả của commit, không phải thông tin đăng nhập.

## Build đa nền tảng

Sau khi push, mở Actions → Build native desktop packages → Run workflow.
Workflow tạo .deb Linux và ZIP native Windows/macOS (ARM64 + Intel) trong
Artifacts. Nó không tự đăng Release. Bộ nguồn hiện đã có launcher cho cả
Windows và macOS; binary native chỉ có sau khi CI build thành công.
