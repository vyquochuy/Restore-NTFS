import struct

def check_ntfs_boot_sector(vhd_path):
    with open(vhd_path, "rb") as f:
        boot_sector = f.read(512)

    # Kiểm tra độ dài
    if len(boot_sector) < 512:
        print("Boot sector không đủ 512 bytes — có thể file bị hỏng.")
        return

    # Đọc các trường
    oem_id = boot_sector[3:11].decode('ascii', errors='ignore')
    bytes_per_sector = struct.unpack("<H", boot_sector[11:13])[0]
    sectors_per_cluster = boot_sector[13]
    total_sectors = struct.unpack("<Q", boot_sector[40:48])[0]
    signature = struct.unpack("<H", boot_sector[510:512])[0]

    # Kiểm tra điều kiện hợp lệ
    errors = []
    if oem_id.strip() != "NTFS":
        errors.append(f"OEM ID sai (found '{oem_id.strip()}')")
    if bytes_per_sector not in [512, 1024, 2048, 4096]:
        errors.append(f"Sai Bytes per sector ({bytes_per_sector})")
    if sectors_per_cluster == 0:
        errors.append("Sectors per cluster = 0 (invalid)")
    if total_sectors == 0:
        errors.append("Total sectors = 0 (invalid)")
    if signature != 0xAA55:
        errors.append(f"Sai boot signature (0x{signature:04X} != 0xAA55)")

    # In kết quả
    if not errors:
        print("Boot sector NTFS hợp lệ.")
        print(f"OEM ID: {oem_id.strip()}, {bytes_per_sector} bytes/sector, {sectors_per_cluster} sectors/cluster")
    else:
        print("Phát hiện lỗi trong boot sector:")
        for e in errors:
            print("   -", e)

# Ví dụ sử dụng
check_ntfs_boot_sector("D:\\anToanVaPhucHoi\\USB200MB.vhd")
