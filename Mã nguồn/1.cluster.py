import struct
import re

# ==========================================
# HÀM HỖ TRỢ: TÍNH TOÁN OFFSET
# ==========================================
def get_mft_info(f, vhd_path):
    # 1. Tìm phân vùng NTFS
    partition_offset = 0
    found = False
    for i in range(5000):
        f.seek(i * 512)
        if f.read(512)[3:7] == b'NTFS':
            partition_offset = i * 512
            found = True
            break
    
    if not found:
        raise Exception("Không tìm thấy phân vùng NTFS!")

    # 2. Đọc Boot Sector
    f.seek(partition_offset)
    boot = f.read(512)
    bps = struct.unpack_from("<H", boot, 0x0B)[0]
    spc = struct.unpack_from("<B", boot, 0x0D)[0]
    mft_cl = struct.unpack_from("<Q", boot, 0x30)[0]
    
    mft_start = partition_offset + (bps * spc * mft_cl)
    return mft_start

# ==========================================
# CHỨC NĂNG 1: QUÉT (SCAN)
# ==========================================
def scan_mft(vhd_path):
    print(f"[*] Đang QUÉT file: {vhd_path}...")
    broken_records = [] # Danh sách chứa ID các record bị lỗi

    with open(vhd_path, "rb") as f:
        try:
            mft_offset = get_mft_info(f, vhd_path)
            print(f"[+] MFT Offset: {mft_offset}")
            print("-" * 50)
            
# Quét 200 record đầu tiên
            for i in range(200):
                target = mft_offset + (i * 1024)
                f.seek(target)
                rec = f.read(1024)
                sig = rec[0:4]

                # --- LOGIC MỚI: XỬ LÝ TRƯỜNG HỢP 00 00 00 00 ---
                if sig != b'FILE':
                    # Trường hợp 1: Header là 0000
                    if sig == b'\x00\x00\x00\x00':
                        # Kiểm tra xem toàn bộ record có phải là số 0 hết không?
                        # Nếu cả 1024 byte đều là 0 -> Record rỗng thật -> Bỏ qua
                        if rec == b'\x00' * 1024:
                            continue 
                        else:
                            # Header là 00 nhưng bên trong có dữ liệu -> BỊ XÓA HEADER!
                            print(f"[!!!] CẢNH BÁO CAO: Record {i} bị xóa trắng Header (0000) nhưng vẫn chứa dữ liệu!")
                            broken_records.append(i)
                            continue

                    # Trường hợp 2: Header bị sửa thành chữ khác (ví dụ BAD!)
                    print(f"[!!!] PHÁT HIỆN LỖI tại Record {i} (Signature: {sig})")
                    broken_records.append(i)
                    continue

        except Exception as e:
            print(f"Lỗi khi quét: {e}")

    return broken_records

# ==========================================
# CHỨC NĂNG 2: SỬA CHỮA (FIX)
# ==========================================
def fix_list_records(vhd_path, record_list):
    if not record_list:
        print("[INFO] Không có gì để sửa.")
        return

    print(f"\n[*] BẮT ĐẦU QUÁ TRÌNH PHỤC HỒI CHO {len(record_list)} RECORDS...")
    
    with open(vhd_path, "r+b") as f: # Mở chế độ Ghi
        mft_offset = get_mft_info(f, vhd_path)
        
        for idx in record_list:
            target = mft_offset + (idx * 1024)
            print(f" -> Đang xử lý Record {idx} tại offset {target}...", end="")
            
            # Ghi đè
            f.seek(target)
            f.write(b'FILE')
            print(" [XONG]")
            
    print("\n[THÀNH CÔNG] Đã phục hồi toàn bộ danh sách lỗi.")

# ==========================================
# MAIN - CHƯƠNG TRÌNH CHÍNH
# ==========================================
vhd_file = r"D:\HuyMai\Y4-HK1\ATPHDL\midTerm\cluster\demo_cluster.vhd" 

# BƯỚC 1: Tự động quét và lấy danh sách lỗi
found_errors = scan_mft(vhd_file)

if len(found_errors) > 0:
    print("-" * 50)
    print(f"TỔNG KẾT: Tìm thấy {len(found_errors)} record bị hỏng. Danh sách ID: {found_errors}")
    
    # BƯỚC 2: Hỏi người dùng
    ans = input(">>> Bạn có muốn TỰ ĐỘNG SỬA tất cả không? (y/n): ")
    
    if ans.lower() == 'y':
        fix_list_records(vhd_file, found_errors)
    else:
        print("Đã hủy thao tác sửa.")
else:
    print("[OK] Hệ thống MFT khỏe mạnh, không tìm thấy lỗi Signature.")