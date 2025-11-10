import struct

def check_ntfs_boot(vhd_path):
    with open(vhd_path, "rb") as f:
        boot_sector = f.read(512)

    if len(boot_sector) < 512:
        print("❌ Boot sector không đủ 512 bytes — có thể file bị hỏng.")
        return

    # Đọc một số trường chính
    oem_id = boot_sector[3:11].decode('ascii', errors='ignore').strip()
    bytes_per_sector = struct.unpack("<H", boot_sector[11:13])[0]
    sectors_per_cluster = boot_sector[13]
    total_sectors = struct.unpack("<Q", boot_sector[40:48])[0]
    mft_cluster = struct.unpack("<Q", boot_sector[48:56])[0]
    signature = struct.unpack("<H", boot_sector[510:512])[0]

    # Gom lỗi kỹ thuật vào các nhóm mô phỏng
    partition_error = False
    volume_error = False
    cluster_error = False
    file_error = False

    # ---- Kiểm tra các trường ----
    # Nhóm 1: Mô tả sai về Phân vùng
    if oem_id != "NTFS" or total_sectors == 0:
        partition_error = True

    # Nhóm 2: Tham số sai của Volume (Bytes/sector, cluster,...)
    if bytes_per_sector not in [512, 1024, 2048, 4096] or sectors_per_cluster == 0:
        volume_error = True

    # Nhóm 3: Bảng thư mục và bảng Cluster sai (VD: MFT offset bất thường)
    if mft_cluster == 0 or mft_cluster > total_sectors:
        cluster_error = True

    # Nhóm 4: File/thư mục đã xóa (giả lập — ta chỉ kiểm tra signature)
    if signature != 0xAA55:
        file_error = True

    # ---- In kết quả ----
    if not any([partition_error, volume_error, cluster_error, file_error]):
        print("✅ Volume NTFS hợp lệ, không phát hiện lỗi.")
    else:
        print("❌ Phát hiện lỗi trong Volume NTFS:")
        if partition_error:
            print("   - Mô tả sai về Phân vùng (partition): Thông tin nhận dạng hoặc kích thước không hợp lệ.")
        if volume_error:
            print("   - Tham số sai của Volume: Bytes per sector hoặc sectors per cluster không đúng.")
        if cluster_error:
            print("   - Bảng thư mục và bảng Cluster sai: Vị trí bảng MFT bất thường hoặc bị hỏng.")
        if file_error:
            print("   - File/thư mục đã xóa: Boot signature hoặc bảng tệp có thể đã bị ghi đè.")

# --- Ví dụ ---
check_ntfs_boot("D:\\anToanVaPhucHoi\\demo_2.vhd")
