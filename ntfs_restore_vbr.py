import struct
import sys

# -------------------------------
VHD_FILE_PATH = r"D:\anToanVaPhucHoi\demo_2.vhd"
# -------------------------------

SECTOR_SIZE = 512

# Vị trí các trường trong MBR
# Bảng phân vùng (Partition Table) bắt đầu từ byte 446 (0x1BE)
PARTITION_TABLE_OFFSET = 0x1BE
# Mỗi partition entry dài 16 bytes
PARTITION_ENTRY_SIZE = 16

# Chúng ta chỉ quan tâm đến Partition 1
PARTITION_1_OFFSET = PARTITION_TABLE_OFFSET

# Offset (tương đối so với đầu partition entry)
# 0x08: 4 bytes, Little-Endian, LBA Start (sector bắt đầu của phân vùng)
LBA_START_OFFSET_IN_ENTRY = 0x08
# 0x0C: 4 bytes, Little-Endian, Total Sectors (tổng số sector trong phân vùng)
TOTAL_SECTORS_OFFSET_IN_ENTRY = 0x0C

def recover_vbr_from_backup(file_path):
    """
    Phục hồi toàn bộ Volume Boot Record (VBR) bằng cách 
    sao chép từ VBR backup (ở cuối volume) đè lên VBR chính (ở đầu volume).
    """
    try:
        with open(file_path, 'rb+') as f:
            print(f"Đang mở file: {file_path}")

            # 1. Đọc MBR (Sector 0)
            f.seek(0)
            mbr_data = f.read(SECTOR_SIZE)
            
            if len(mbr_data) < SECTOR_SIZE:
                print("LỖI: Không thể đọc MBR. File quá nhỏ hoặc bị hỏng nặng.")
                return

            # 2. Phân tích MBR để tìm thông tin Partition 1
            # Vị trí tuyệt đối của các trường trong MBR
            lba_start_addr = PARTITION_1_OFFSET + LBA_START_OFFSET_IN_ENTRY
            total_sectors_addr = PARTITION_1_OFFSET + TOTAL_SECTORS_OFFSET_IN_ENTRY

            # Dùng 'struct.unpack' để chuyển 4 bytes (little-endian '<I') thành số
            lba_start = struct.unpack('<I', mbr_data[lba_start_addr : lba_start_addr + 4])[0]
            total_sectors = struct.unpack('<I', mbr_data[total_sectors_addr : total_sectors_addr + 4])[0]

            if lba_start == 0 or total_sectors == 0:
                print("LỖI: Không tìm thấy thông tin phân vùng hợp lệ trong MBR.")
                print(f"LBA Start đọc được: {lba_start}, Total Sectors đọc được: {total_sectors}")
                return

            print("--- Thông tin phân vùng (đọc từ MBR) ---")
            print(f"  Phân vùng bắt đầu tại Sector (LBA): {lba_start}")
            print(f"  Tổng số Sector của phân vùng: {total_sectors}")

            # 3. Tính toán vị trí (Offset) bằng byte
            
            # VBR chính (bị hỏng) nằm ở sector đầu tiên của phân vùng
            main_vbr_offset = lba_start * SECTOR_SIZE
            
            # VBR sao lưu nằm ở sector CUỐI CÙNG của phân vùng
            backup_vbr_offset = (lba_start + total_sectors - 1) * SECTOR_SIZE
            
            print("--- Vị trí (Offset) bằng byte ---")
            print(f"  VBR chính (hỏng):   {main_vbr_offset} (0x{main_vbr_offset:X})")
            print(f"  VBR sao lưu (tốt): {backup_vbr_offset} (0x{backup_vbr_offset:X})")

            # 4. Đọc VBR sao lưu (Known-Good)
            print(f"\nĐang đọc 512 bytes từ VBR sao lưu tại 0x{backup_vbr_offset:X}...")
            f.seek(backup_vbr_offset)
            backup_vbr_data = f.read(SECTOR_SIZE)
            
            if len(backup_vbr_data) != SECTOR_SIZE:
                print("LỖI: Không thể đọc đủ 512 bytes từ VBR sao lưu!")
                return
            
            # Kiểm tra nhanh xem nó có phải VBR hợp lệ không (chữ ký 0x55AA ở cuối)
            if backup_vbr_data[510:512] == b'\x55\xAA':
                print("  Đã đọc VBR sao lưu. (Chữ ký 0x55AA hợp lệ)")
            else:
                print("  CẢNH BÁO: VBR sao lưu không có chữ ký 0x55AA. Có thể nó cũng bị hỏng.")
                # Chúng ta vẫn tiếp tục, vì nó có thể tốt hơn cái VBR chính

            # 5. Ghi đè VBR chính (hỏng) bằng VBR sao lưu
            print(f"Đang ghi đè 512 bytes lên VBR chính tại 0x{main_vbr_offset:X}...")
            f.seek(main_vbr_offset)
            f.write(backup_vbr_data)
            
            print("\n✅ Phục hồi hoàn tất! Toàn bộ 512 bytes của VBR đã được khôi phục.")

    except FileNotFoundError:
        print(f"LỖI: Không tìm thấy file tại '{file_path}'")
    except PermissionError:
        print("LỖI: Không có quyền truy cập file!")
        print(">> Hãy chắc chắn rằng bạn đã 'Detach VHD' khỏi Disk Management! <<")
        print("Và hãy thử chạy script với quyền Administrator.")
    except Exception as e:
        print(f"Đã xảy ra lỗi không mong muốn: {e}")

# --- Chạy hàm chính ---
if __name__ == "__main__":
    recover_vbr_from_backup(VHD_FILE_PATH)