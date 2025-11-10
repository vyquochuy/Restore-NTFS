
import struct
import os
import sys
import shutil
from datetime import datetime

# --- CẤU HÌNH ---
VHD_FILE_PATH = r"D:\anToanVaPhucHoi\demo_2.safecopy.vhd"
BACKUP_SUFFIX = ".backup"
RECOVERY_PATH = r"D:\anToanVaPhucHoi\Recovered_Files"
# ----------------

SECTOR_SIZE = 512

class NTFSError:
    """Các loại lỗi NTFS"""
    PARTITION_ERROR = "partition_error"      # Mô tả sai về Phân vùng
    VOLUME_ERROR = "volume_error"            # Tham số sai của Volume
    CLUSTER_ERROR = "cluster_error"          # Bảng thư mục và bảng Cluster sai
    FILE_ERROR = "file_error"                # File/thư mục đã xóa
    VBR_CORRUPTED = "vbr_corrupted"          # VBR bị hỏng
    MFT_CORRUPTED = "mft_corrupted"          # MFT bị hỏng

def create_backup(file_path):
    """Tạo bản sao lưu VHD trước khi sửa"""
    backup_path = file_path + BACKUP_SUFFIX
    
    if os.path.exists(backup_path):
        print(f"Bản backup đã tồn tại: {backup_path}")
        response = input("Ghi đè backup cũ? (y/n): ")
        if response.lower() != 'y':
            print("Sử dụng backup hiện có.")
            return backup_path
    
    print(f"Đang tạo backup: {backup_path}")
    try:
        shutil.copy2(file_path, backup_path)
        print(f"Backup thành công!")
        return backup_path
    except Exception as e:
        print(f"Lỗi khi tạo backup: {e}")
        return None

def diagnose_ntfs(vhd_path):
    """
    Chẩn đoán các lỗi NTFS trong VHD
    Trả về: dict với các loại lỗi và thông tin chi tiết
    """
    errors = {}
    boot_info = {}
    
    try:
        with open(vhd_path, "rb") as f:
            # Đọc MBR (sector 0)
            f.seek(0)
            mbr_data = f.read(SECTOR_SIZE)
            
            if len(mbr_data) < SECTOR_SIZE:
                errors['critical'] = "File quá nhỏ hoặc bị hỏng nặng"
                return errors, boot_info
            
            # Kiểm tra MBR signature
            mbr_sig = struct.unpack("<H", mbr_data[510:512])[0]
            if mbr_sig != 0xAA55:
                errors['mbr_signature'] = f"MBR signature sai: 0x{mbr_sig:04X} (expected 0xAA55)"
            
            # Tìm phân vùng NTFS
            partition_offset = 0
            partition_found = False
            
            for i in range(4):
                entry_offset = 0x1BE + (i * 16)
                partition_type = mbr_data[entry_offset + 4]
                
                if partition_type == 0x07:  # NTFS
                    lba_start = struct.unpack('<I', mbr_data[entry_offset + 8:entry_offset + 12])[0]
                    partition_offset = lba_start * SECTOR_SIZE
                    partition_found = True
                    boot_info['partition_offset'] = partition_offset
                    break
            
            if not partition_found:
                # Thử đọc boot sector tại offset 0 (raw NTFS volume)
                partition_offset = 0
            
            # Đọc boot sector
            f.seek(partition_offset)
            boot_sector = f.read(SECTOR_SIZE)
            
            if len(boot_sector) < SECTOR_SIZE:
                errors[NTFSError.VBR_CORRUPTED] = "Không đọc được boot sector đầy đủ"
                return errors, boot_info
            
            # Phân tích boot sector
            oem_id = boot_sector[3:11].decode('ascii', errors='ignore').strip()
            bytes_per_sector = struct.unpack("<H", boot_sector[11:13])[0]
            sectors_per_cluster = boot_sector[13]
            total_sectors = struct.unpack("<Q", boot_sector[40:48])[0]
            mft_cluster = struct.unpack("<Q", boot_sector[48:56])[0]
            signature = struct.unpack("<H", boot_sector[510:512])[0]
            
            boot_info.update({
                'oem_id': oem_id,
                'bytes_per_sector': bytes_per_sector,
                'sectors_per_cluster': sectors_per_cluster,
                'total_sectors': total_sectors,
                'mft_cluster': mft_cluster,
                'signature': signature,
            })
            
            # Kiểm tra các lỗi
            
            # Nhóm 1: Mô tả sai về Phân vùng
            if oem_id != "NTFS" or total_sectors == 0:
                errors[NTFSError.PARTITION_ERROR] = {
                    'oem_id': oem_id,
                    'total_sectors': total_sectors,
                }
            
            # Nhóm 2: Tham số sai của Volume
            if bytes_per_sector not in [512, 1024, 2048, 4096] or sectors_per_cluster == 0:
                errors[NTFSError.VOLUME_ERROR] = {
                    'bytes_per_sector': bytes_per_sector,
                    'sectors_per_cluster': sectors_per_cluster,
                }
            
            # Nhóm 3: Bảng thư mục và bảng Cluster sai
            if mft_cluster == 0 or mft_cluster > total_sectors:
                errors[NTFSError.CLUSTER_ERROR] = {
                    'mft_cluster': mft_cluster,
                    'total_sectors': total_sectors,
                }
            
            # Nhóm 4: VBR signature
            if signature != 0xAA55:
                errors[NTFSError.FILE_ERROR] = f"Boot signature sai: 0x{signature:04X}"
    
    except Exception as e:
        errors['exception'] = str(e)
    
    return errors, boot_info

def print_diagnosis(errors, boot_info):
    """In kết quả chẩn đoán"""
    print("\n" + "="*60)
    print(" KẾT QUẢ CHẨN ĐOÁN VHD NTFS")
    print("="*60)
    
    if boot_info:
        print("\n Thông tin Boot Sector:")
        print(f"  OEM ID: {boot_info.get('oem_id', 'N/A')}")
        print(f"  Bytes/Sector: {boot_info.get('bytes_per_sector', 'N/A')}")
        print(f"  Sectors/Cluster: {boot_info.get('sectors_per_cluster', 'N/A')}")
        print(f"  Total Sectors: {boot_info.get('total_sectors', 'N/A')}")
        print(f"  MFT Cluster: {boot_info.get('mft_cluster', 'N/A')}")
        print(f"  Boot Signature: 0x{boot_info.get('signature', 0):04X}")
        if 'partition_offset' in boot_info:
            print(f"  Partition Offset: 0x{boot_info['partition_offset']:X}")
    
    if not errors:
        print("\nKhông phát hiện lỗi - Volume NTFS hợp lệ!")
        return
    
    print("\nPHÁT HIỆN CÁC LỖI SAU:")
    
    error_messages = {
        NTFSError.PARTITION_ERROR: "Mô tả sai về Phân vùng - OEM ID hoặc kích thước không hợp lệ",
        NTFSError.VOLUME_ERROR: "Tham số sai của Volume - Bytes/sector hoặc sectors/cluster không đúng",
        NTFSError.CLUSTER_ERROR: "Bảng thư mục và bảng Cluster sai - Vị trí MFT bất thường",
        NTFSError.FILE_ERROR: "Boot signature sai - VBR có thể bị ghi đè",
        'mbr_signature': "MBR signature không hợp lệ",
    }
    
    for error_type, msg in error_messages.items():
        if error_type in errors:
            print(f"\n  {msg}")
            if isinstance(errors[error_type], dict):
                for k, v in errors[error_type].items():
                    print(f"    - {k}: {v}")
            elif isinstance(errors[error_type], str):
                print(f"    - {errors[error_type]}")
    
    if 'critical' in errors:
        print(f"\n  LỖI NGHIÊM TRỌNG: {errors['critical']}")
    
    if 'exception' in errors:
        print(f"\n  Exception: {errors['exception']}")

def recover_vbr(file_path, boot_info):
    """
    Phục hồi VBR từ bản sao lưu (ở cuối volume)
    """
    print("\n" + "="*60)
    print("BƯỚC 1: PHỤC HỒI VBR TỪ BACKUP")
    print("="*60)
    
    try:
        partition_offset = boot_info.get('partition_offset', 0)
        
        with open(file_path, 'rb+') as f:
            # Đọc MBR để lấy thông tin phân vùng
            f.seek(0)
            mbr_data = f.read(SECTOR_SIZE)
            
            lba_start_addr = 0x1BE + 0x08
            total_sectors_addr = 0x1BE + 0x0C
            
            lba_start = struct.unpack('<I', mbr_data[lba_start_addr:lba_start_addr + 4])[0]
            total_sectors = struct.unpack('<I', mbr_data[total_sectors_addr:total_sectors_addr + 4])[0]
            
            if lba_start == 0 or total_sectors == 0:
                print("Không tìm thấy thông tin phân vùng hợp lệ trong MBR")
                print("   Không thể phục hồi VBR tự động")
                return False
            
            main_vbr_offset = lba_start * SECTOR_SIZE
            backup_vbr_offset = (lba_start + total_sectors - 1) * SECTOR_SIZE
            
            print(f"  Partition LBA: {lba_start}")
            print(f"  Total Sectors: {total_sectors}")
            print(f"  VBR chính: 0x{main_vbr_offset:X}")
            print(f"  VBR backup: 0x{backup_vbr_offset:X}")
            
            # Đọc VBR backup
            f.seek(backup_vbr_offset)
            backup_vbr = f.read(SECTOR_SIZE)
            
            if len(backup_vbr) != SECTOR_SIZE:
                print("Không đọc được VBR backup")
                return False
            
            # Kiểm tra VBR backup
            if backup_vbr[510:512] == b'\x55\xAA':
                print("VBR backup hợp lệ (signature 0x55AA)")
            else:
                print("VBR backup không có signature hợp lệ - có thể cũng bị hỏng")
                response = input("Tiếp tục phục hồi? (y/n): ")
                if response.lower() != 'y':
                    return False
            
            # Ghi đè VBR chính
            print(f"  Đang ghi đè VBR chính...")
            f.seek(main_vbr_offset)
            f.write(backup_vbr)
            f.flush()
            
            print("Phục hồi VBR thành công!")
            return True
            
    except Exception as e:
        print(f"Lỗi khi phục hồi VBR: {e}")
        return False

def recover_files(file_path):
    """
    Khôi phục file bằng cách quét MFT records
    """
    print("\n" + "="*60)
    print("BƯỚC 2: KHÔI PHỤC FILES TỪ MFT RECORDS")
    print("="*60)
    
    # Import và chạy restore_cluster.py
    try:
        # Thêm đường dẫn hiện tại vào sys.path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        
        # Import module restore_cluster
        import restore_cluster
        
        # Cập nhật cấu hình
        restore_cluster.VHD_FILE_PATH = file_path
        restore_cluster.RECOVERY_PATH = RECOVERY_PATH
        
        # Tạo thư mục khôi phục
        if not os.path.exists(RECOVERY_PATH):
            os.makedirs(RECOVERY_PATH)
        
        # Chạy quá trình khôi phục
        restore_cluster.main_recovery_scan(file_path)
        
        print("\nQuá trình khôi phục file hoàn tất!")
        return True
        
    except Exception as e:
        print(f"Lỗi khi khôi phục files: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Hàm chính"""
    print("="*60)
    print("CÔNG CỤ KHÔI PHỤC VHD NTFS")
    print("="*60)
    print(f"File VHD: {VHD_FILE_PATH}")
    print(f"Thư mục khôi phục: {RECOVERY_PATH}")
    print(f"Thời gian: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Kiểm tra file tồn tại
    if not os.path.exists(VHD_FILE_PATH):
        print(f"\nLỖI: Không tìm thấy file VHD tại: {VHD_FILE_PATH}")
        print("Vui lòng kiểm tra đường dẫn và thử lại.")
        return
    
    # Bước 1: Chẩn đoán
    print("\nBước 1: Chẩn đoán VHD...")
    errors, boot_info = diagnose_ntfs(VHD_FILE_PATH)
    print_diagnosis(errors, boot_info)
    
    # Nếu không có lỗi hoặc chỉ có lỗi nhẹ
    if not errors:
        print("\nVolume hợp lệ - Không cần sửa chữa")
        response = input("\nVẫn muốn thử khôi phục files? (y/n): ")
        if response.lower() == 'y':
            recover_files(VHD_FILE_PATH)
        return
    
    # Xác định chiến lược khôi phục
    print("\n" + "="*60)
    print("CHIẾN LƯỢC KHÔI PHỤC")
    print("="*60)
    
    needs_vbr_recovery = False
    needs_file_recovery = False
    
    if NTFSError.CLUSTER_ERROR in errors:
        print("🔸 Phát hiện lỗi: Bảng thư mục và bảng Cluster sai")
        print("   → Sẽ thử phục hồi VBR từ backup")
        print("   → Sau đó quét toàn bộ disk để tìm MFT records")
        needs_vbr_recovery = True
        needs_file_recovery = True
    
    elif NTFSError.FILE_ERROR in errors or NTFSError.VBR_CORRUPTED in errors:
        print("🔸 Phát hiện lỗi VBR/Boot signature")
        print("   → Sẽ thử phục hồi VBR từ backup")
        needs_vbr_recovery = True
        needs_file_recovery = True
    
    elif NTFSError.PARTITION_ERROR in errors or NTFSError.VOLUME_ERROR in errors:
        print("🔸 Phát hiện lỗi partition/volume parameters")
        print("   → Sẽ thử phục hồi VBR từ backup")
        needs_vbr_recovery = True
        needs_file_recovery = True
    
    else:
        print("🔸 Phát hiện lỗi khác")
        print("   → Sẽ thử khôi phục files trực tiếp")
        needs_file_recovery = True
    
    # Xác nhận với người dùng
    print("\nCẢNH BÁO: Quá trình khôi phục sẽ thay đổi file VHD gốc!")
    response = input("Tiếp tục? (y/n): ")
    if response.lower() != 'y':
        print("Đã hủy.")
        return
    
    # Tạo backup
    backup_path = create_backup(VHD_FILE_PATH)
    if not backup_path:
        print("Không thể tạo backup - dừng quá trình khôi phục")
        return
    
    # Thực hiện khôi phục
    success = True
    
    if needs_vbr_recovery:
        vbr_ok = recover_vbr(VHD_FILE_PATH, boot_info)
        if not vbr_ok:
            print("\nPhục hồi VBR thất bại - tiếp tục với file recovery")
    
    if needs_file_recovery:
        files_ok = recover_files(VHD_FILE_PATH)
        if not files_ok:
            success = False
    
    # Tổng kết
    print("\n" + "="*60)
    print("TỔNG KẾT")
    print("="*60)
    
    if success:
        print("Quá trình khôi phục hoàn tất!")
        print(f"Files đã khôi phục: {RECOVERY_PATH}")
        print(f"Bản backup VHD gốc: {backup_path}")
    else:
        print("Quá trình khôi phục gặp một số vấn đề")
        print(f"Bản backup VHD gốc: {backup_path}")
        print("Vui lòng kiểm tra thư mục khôi phục và log để biết thêm chi tiết")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nĐã hủy bởi người dùng")
    except Exception as e:
        print(f"\nLỗi không mong muốn: {e}")
        import traceback
        traceback.print_exc()
