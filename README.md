# 🛠️ Công cụ Khôi phục VHD NTFS

Bộ công cụ để chẩn đoán và khôi phục file VHD NTFS bị lỗi, đặc biệt xử lý trường hợp **Bảng thư mục và bảng Cluster sai**.

## 📋 Các Scripts

### 1. `ntfs_recovery_main.py` - **SCRIPT CHÍNH** (Khuyến nghị)
Script tổng hợp tự động:
- ✅ Chẩn đoán tự động các loại lỗi NTFS
- ✅ Tạo backup VHD trước khi sửa
- ✅ Phục hồi VBR từ bản backup (nếu cần)
- ✅ Quét và khôi phục files từ MFT records
- ✅ Hỗ trợ MBR parsing, partition detection
- ✅ Xử lý cluster table bị hỏng

**Cách dùng:**
```powershell
# Sửa đường dẫn VHD trong file
python ntfs_recovery_main.py
```

### 2. `check_ntfs_boot.py` - Kiểm tra lỗi
Chẩn đoán các loại lỗi:
- Mô tả sai về Phân vùng (partition error)
- Tham số sai của Volume (volume error)
- **Bảng thư mục và bảng Cluster sai** (cluster error) ← Trường hợp này
- File/thư mục đã xóa (file error)

**Cách dùng:**
```powershell
python check_ntfs_boot.py
```

### 3. `ntfs_restore_vbr.py` - Phục hồi VBR
Phục hồi Volume Boot Record từ bản backup (ở cuối volume).

**Cách dùng:**
```powershell
python ntfs_restore_vbr.py
```

### 4. `restore_cluster.py` - Khôi phục files
Quét toàn bộ VHD để tìm MFT records và khôi phục files:
- ✅ Tự động phát hiện cluster size từ boot sector
- ✅ MBR parsing để tìm partition offset
- ✅ MFT record validation (giảm false positives)
- ✅ Hỗ trợ resident và non-resident data
- ✅ Data runs parsing cho files lớn
- ✅ Error handling cho cluster table bị hỏng
- ✅ File signatures (JPEG, PNG, PDF, ZIP, etc.)

**Cách dùng:**
```powershell
python restore_cluster.py
```

## 🚀 Hướng dẫn Khôi phục VHD bị lỗi "Bảng thư mục và bảng Cluster sai"

### ⚡ NHANH NHẤT: Chỉ cần files (không cần mount VHD)

```powershell
# Detach VHD (nếu đang attach)
# Chạy script trích xuất
python restore_cluster.py
# → Files được lưu vào Recovered_Files/
# → VHD gốc KHÔNG BỊ THAY ĐỔI
```

### 🔧 Phương án 1: Sửa VBR từ backup (VBR backup còn tốt)

```powershell
# Bước 1: Detach VHD khỏi Windows
# Bước 2: Sửa boot sector
python fix_vhd.py
# Bước 3: Attach lại VHD và thử mount
```

### 🛠️ Phương án 2: Tái tạo boot sector (VBR backup cũng hỏng)

```powershell
# Bước 1: Detach VHD
# Bước 2: Tái tạo boot sector hoàn toàn mới
python rebuild_boot_sector.py
# Bước 3: Attach lại VHD và chạy chkdsk
```

### 📋 Phương án 3: Tự động đầy đủ

```powershell
# Script tự động: chẩn đoán → sửa → khôi phục
python ntfs_recovery_main.py
```

## 📁 Kết quả

Files khôi phục được lưu vào:
```
D:\anToanVaPhucHoi\Recovered_Files\
```

Tên file: `<offset>_<tên_file_gốc>`
- VD: `524288_document.txt`
- Offset giúp xác định vị trí MFT record trong VHD

## ⚙️ Cấu hình

Sửa các biến sau trong mỗi script:

```python
# Đường dẫn VHD cần khôi phục
VHD_FILE_PATH = r"D:\anToanVaPhucHoi\demo_2.vhd"

# Thư mục lưu files khôi phục
RECOVERY_PATH = r"D:\anToanVaPhucHoi\Recovered_Files"
```

## 🔍 Xử lý các trường hợp lỗi

### Trường hợp 1: Bảng thư mục và bảng Cluster sai
**Triệu chứng:**
- MFT cluster = 0 hoặc > total_sectors
- Không mount được VHD
- Windows báo "file system corrupted"

**Giải pháp:**
1. Phục hồi VBR từ backup → Cập nhật lại thông tin MFT
2. Quét toàn bộ disk tìm MFT records → Khôi phục files trực tiếp
3. Nếu data runs bị hỏng → Fallback sang file carving

**Script:** `ntfs_recovery_main.py` (tự động) hoặc `restore_cluster.py`

### Trường hợp 2: VBR bị hỏng
**Triệu chứng:**
- Boot signature != 0xAA55
- OEM ID != "NTFS"
- Bytes per sector/cluster không hợp lệ

**Giải pháp:**
1. Phục hồi VBR từ backup (ở cuối volume)

**Script:** `ntfs_restore_vbr.py`

### Trường hợp 3: MFT hoàn toàn bị hỏng
**Triệu chứng:**
- Không tìm thấy MFT records hợp lệ
- Tất cả MFT signatures đều invalid

**Giải pháp:**
1. File carving bằng signatures (JPEG, PNG, PDF, etc.)
2. Sử dụng công cụ chuyên dụng (PhotoRec, TestDisk)

**Script:** `restore_cluster.py` có hỗ trợ file carving cơ bản

## 🛡️ An toàn

- ✅ `ntfs_recovery_main.py` tự động tạo backup trước khi sửa
- ✅ Scripts chỉ **đọc** VHD (trừ `ntfs_restore_vbr.py` ghi VBR)
- ⚠️ Luôn detach VHD khỏi Disk Management trước khi chạy
- ⚠️ Chạy PowerShell/Command Prompt với quyền Administrator nếu cần

## 📊 Kết quả mong đợi

**Khi cluster table BỊ HỎNG:**
- Script vẫn có thể khôi phục files nhờ:
  - Quét toàn bộ disk tìm MFT signatures
  - Validation để lọc false positives
  - Đọc trực tiếp data từ clusters (nếu LCN hợp lệ)
  - Fallback sang carving (nếu data runs invalid)

**Tỷ lệ thành công:**
- Resident files (nhỏ): ~90-95%
- Non-resident files (lớn) với data runs hợp lệ: ~70-80%
- Files với cluster map bị hỏng: ~30-50% (tùy mức độ hỏng)

## 🔧 Xử lý lỗi thường gặp

### Lỗi: `PermissionError`
```
Giải pháp:
1. Detach VHD trong Disk Management
2. Chạy PowerShell với quyền Administrator
3. Đóng các ứng dụng đang mở VHD
```

### Lỗi: Không tìm thấy MFT records
```
Nguyên nhân: MFT table bị hỏng hoàn toàn
Giải pháp:
1. Kiểm tra partition offset (MBR vs raw NTFS)
2. Thử file carving (PhotoRec, TestDisk)
3. Liên hệ chuyên gia data recovery
```

### Lỗi: Files khôi phục bị hỏng/không mở được
```
Nguyên nhân: Data runs sai, cluster mapping corrupted
Giải pháp:
1. Resident files thường OK
2. Non-resident files có thể thiếu data
3. Thử carving bằng file signatures
```

## 📝 Log và Debug

Các scripts in thông tin chi tiết ra console:
- ✅ MFT records tìm thấy
- ✅ Validation results
- ✅ Files được khôi phục
- ⚠️ Errors và warnings
- 📊 Thống kê cuối cùng

## 🤝 Hỗ trợ

Nếu gặp vấn đề:
1. Kiểm tra log output từ scripts
2. Verify backup đã tạo
3. Thử chạy từng script riêng lẻ
4. Check partition offset và boot sector info

## 📚 Tài liệu tham khảo

- NTFS File System Structure
- MFT (Master File Table) Format
- Data Runs Encoding
- NTFS Boot Sector Layout
