import sys
import struct
import os

# --- THAY ĐỔI THÔNG SỐ NÀY ---
VHD_FILE_PATH = r"D:\anToanVaPhucHoi\demo_2.vhd"
# Đường dẫn thư mục để lưu các file khôi phục được
RECOVERY_PATH = r"D:\anToanVaPhucHoi\Recovered_Files"
# -------------------------------

# --- Các hằng số ---
ASSUMED_CLUSTER_SIZE = 4096
MFT_SIGNATURE = b'FILE'  # MFT entry signature is 'FILE'
MFT_RECORD_SIZE = 1024

# Mã các loại thuộc tính (Attribute Types)
ATTR_STANDARD_INFO = 0x10
ATTR_FILE_NAME = 0x30
ATTR_DATA = 0x80
ATTR_END = 0xFFFFFFFF

# Tạo thư mục khôi phục nếu chưa có
if not os.path.exists(RECOVERY_PATH):
    os.makedirs(RECOVERY_PATH)
    print(f"Đã tạo thư mục khôi phục: {RECOVERY_PATH}")

## Helper: Parse MBR to find NTFS partition offset
def parse_mbr(f):
    """Parse MBR and return first NTFS partition start offset (in bytes)"""
    f.seek(0)
    mbr = f.read(512)
    if len(mbr) < 512:
        return None
    
    # Check MBR signature
    if mbr[510:512] != b'\x55\xAA':
        return None
    
    # Partition table starts at 0x1BE
    for i in range(4):
        entry_offset = 0x1BE + (i * 16)
        partition_type = mbr[entry_offset + 4]
        
        # NTFS partition type is 0x07
        if partition_type == 0x07:
            lba_start = struct.unpack('<I', mbr[entry_offset + 8 : entry_offset + 12])[0]
            return lba_start * 512  # Convert sectors to bytes
    
    return None

## Helper: đọc boot sector để lấy kích thước cluster và vị trí MFT
def read_boot_sector(f, offset=0):
    f.seek(offset)
    boot = f.read(512)
    if len(boot) < 512:
        return None
    try:
        # Check for NTFS signature
        oem_id = boot[3:11]
        if b'NTFS' not in oem_id:
            return None
        
        bytes_per_sector = struct.unpack('<H', boot[11:13])[0]
        sectors_per_cluster = boot[13]
        
        # Validate reasonable values
        if bytes_per_sector not in [512, 1024, 2048, 4096] or sectors_per_cluster == 0:
            return None
        
        cluster_size = bytes_per_sector * sectors_per_cluster
        # MFT cluster (8 bytes at offset 48)
        mft_cluster = struct.unpack('<Q', boot[48:56])[0]
        
        return {
            'bytes_per_sector': bytes_per_sector,
            'sectors_per_cluster': sectors_per_cluster,
            'cluster_size': cluster_size,
            'mft_cluster': mft_cluster,
            'raw': boot,
        }
    except Exception:
        return None

def validate_mft_record(record_data):
    """Validate MFT record to reduce false positives"""
    try:
        if len(record_data) < MFT_RECORD_SIZE:
            return False
        
        # Check signature
        if not record_data.startswith(MFT_SIGNATURE):
            return False
        
        # Check flags at offset 0x16 (2 bytes)
        flags = struct.unpack('<H', record_data[0x16:0x18])[0]
        # Bit 0: in use, Bit 1: directory
        # Valid flags should be 0, 1, 2, or 3
        if flags > 3:
            return False
        
        # Check first attribute offset (should be reasonable)
        attr_offset = struct.unpack('<H', record_data[0x14:0x16])[0]
        if attr_offset < 0x30 or attr_offset >= MFT_RECORD_SIZE:
            return False
        
        return True
    except Exception:
        return False

def decode_filename(data):
    try:
        if len(data) < 0x42:
            return "[Tên Không Rõ]"
        filename_len = data[0x40]
        name_start = 0x42
        name_end = name_start + (filename_len * 2)
        if name_end > len(data):
            # dữ liệu thiếu, cắt vừa đủ
            name_end = len(data)
        filename = data[name_start:name_end].decode('utf-16-le', errors='ignore')
        return filename
    except Exception as e:
        return f"[Loi Decode Ten: {e}]"
    except Exception as e:
        return f"[Loi Decode Ten: {e}]"

def parse_data_runs(data_runs_bytes):
    """
    Giải mã Data Runs (non-resident attribute) -> danh sách (length_in_clusters, lcn)
    """
    runs = []
    i = 0
    prev_lcn = 0
    length = len(data_runs_bytes)
    
    try:
        while i < length:
            header = data_runs_bytes[i]
            i += 1
            if header == 0:
                break
            length_size = header & 0x0F
            offset_size = (header >> 4) & 0x0F

            if length_size == 0 or length_size > 8:
                break

            if i + length_size > length:
                break

            run_length = int.from_bytes(data_runs_bytes[i:i+length_size], 'little')
            i += length_size

            if offset_size > 0:
                if i + offset_size > length:
                    break
                raw_offset = data_runs_bytes[i:i+offset_size]
                i += offset_size
                # signed little-endian
                lcn_offset = int.from_bytes(raw_offset, 'little', signed=True)
            else:
                lcn_offset = 0

            lcn = prev_lcn + lcn_offset
            runs.append((run_length, lcn))
            prev_lcn = lcn
    except Exception as e:
        print(f"  [Lỗi giải mã data runs: {e}]")
    
    return runs


# File signatures for carving
FILE_SIGNATURES = {
    b'\xFF\xD8\xFF': {'ext': 'jpg', 'name': 'JPEG'},
    b'\x89PNG\r\n\x1a\n': {'ext': 'png', 'name': 'PNG'},
    b'%PDF-': {'ext': 'pdf', 'name': 'PDF'},
    b'PK\x03\x04': {'ext': 'zip', 'name': 'ZIP/DOCX/XLSX'},
    b'GIF87a': {'ext': 'gif', 'name': 'GIF87a'},
    b'GIF89a': {'ext': 'gif', 'name': 'GIF89a'},
    b'BM': {'ext': 'bmp', 'name': 'BMP'},
    b'\x00\x00\x01\x00': {'ext': 'ico', 'name': 'ICO'},
}

def carve_file_by_signature(data, offset):
    """Try to identify and carve file from raw data by signature"""
    for sig, info in FILE_SIGNATURES.items():
        if data.startswith(sig):
            return info
    return None


def parse_mft_record(record_data, record_offset, fhandle=None, cluster_size=ASSUMED_CLUSTER_SIZE, partition_offset=0):
    """
    Phân tích một MFT Record (1024 bytes) để tìm tên file và dữ liệu.
    """
    print(f"\n--- Phân tích Record tại 0x{record_offset:X} ---")

    try:
        # 0x14 (byte 20): Offset đến thuộc tính đầu tiên
        attr_offset = struct.unpack('<H', record_data[0x14:0x16])[0]

        current_filename = None

        while attr_offset < MFT_RECORD_SIZE:
            # Đọc 4 byte đầu của thuộc tính
            attr_type = struct.unpack('<I', record_data[attr_offset : attr_offset + 4])[0]

            # 1. Kiểm tra xem có phải là kết thúc (0xFFFFFFFF)
            if attr_type == ATTR_END:
                break

            # 2. Đọc tổng chiều dài của thuộc tính này (để nhảy đến thuộc tính tiếp theo)
            attr_len = struct.unpack('<I', record_data[attr_offset + 4 : attr_offset + 8])[0]
            if attr_len <= 0 or attr_len + attr_offset > MFT_RECORD_SIZE:
                break # Thuộc tính bị hỏng, dừng lại

            # 3. Kiểm tra cờ Resident / Non-Resident
            resident_flag = struct.unpack('<B', record_data[attr_offset + 8 : attr_offset + 9])[0]

            # --- Xử lý thuộc tính ---

            if attr_type == ATTR_FILE_NAME:
                # 0x00 = Resident
                if resident_flag == 0x00:
                    # 0x10: Data size
                    data_len = struct.unpack('<I', record_data[attr_offset + 0x10 : attr_offset + 0x14])[0]
                    # 0x14: Data offset (tính từ đầu header thuộc tính)
                    data_offset = struct.unpack('<H', record_data[attr_offset + 0x14 : attr_offset + 0x16])[0]

                    # Lấy payload của thuộc tính $FILE_NAME
                    payload_start = attr_offset + data_offset
                    payload = record_data[payload_start : payload_start + data_len]

                    # Giải mã tên file
                    current_filename = decode_filename(payload)
                    print(f"  [TÌM THẤY TÊN FILE]: {current_filename}")

            elif attr_type == ATTR_DATA:
                if resident_flag == 0x00:
                    # DỮ LIỆU NỘI TRÚ (RESIDENT)
                    data_len = struct.unpack('<I', record_data[attr_offset + 0x10 : attr_offset + 0x14])[0]
                    data_offset = struct.unpack('<H', record_data[attr_offset + 0x14 : attr_offset + 0x16])[0]

                    payload_start = attr_offset + data_offset
                    file_data = record_data[payload_start : payload_start + data_len]

                    print(f"  [TÌM THẤY DỮ LIỆU NỘI TRÚ]: {data_len} bytes")

                    # Ghi file ra đĩa
                    if current_filename:
                        safe_filename = "".join(c for c in current_filename if c.isalnum() or c in ('.', '_'))
                        save_name = f"{record_offset}_{safe_filename}"
                    else:
                        save_name = f"{record_offset}_unknown_file.dat"

                    save_path = os.path.join(RECOVERY_PATH, save_name)
                    with open(save_path, 'wb') as f_out:
                        f_out.write(file_data)
                    print(f"  [ĐÃ LƯU]: {save_path}")

                else:
                    # NON-RESIDENT: parse data runs and read clusters from disk
                    if fhandle is None:
                        print("  [KHÔNG THỂ ĐỌC NON-RESIDENT]: file handle không được cung cấp")
                    else:
                        try:
                            # data run offset is at offset 0x20 in non-resident attribute header
                            data_run_rel = struct.unpack('<H', record_data[attr_offset + 0x20 : attr_offset + 0x22])[0]
                            data_run_start = attr_offset + data_run_rel
                            data_run_bytes = record_data[data_run_start : attr_offset + attr_len]
                            runs = parse_data_runs(data_run_bytes)

                            print(f"  [TÌM THẤY DỮ LIỆU NON-RESIDENT]: {len(runs)} run(s)")

                            if len(runs) == 0:
                                print("  [CẢNH BÁO]: Không giải mã được data runs - cluster table có thể bị hỏng")
                                # Try carving from current location as fallback
                                print("  [FALLBACK]: Thử carving dữ liệu từ vị trí hiện tại...")
                                
                            # Ghi file từ các cluster tìm được
                            if current_filename:
                                safe_filename = "".join(c for c in current_filename if c.isalnum() or c in ('.', '_'))
                                save_name = f"{record_offset}_{safe_filename}"
                            else:
                                save_name = f"{record_offset}_unknown_file.dat"

                            save_path = os.path.join(RECOVERY_PATH, save_name)
                            saved = False
                            
                            with open(save_path, 'wb') as f_out:
                                for run_len, lcn in runs:
                                    if lcn <= 0:
                                        # không biết LCN, skip
                                        print(f"    [Skip run: invalid LCN {lcn}]")
                                        continue
                                    try:
                                        byte_offset = partition_offset + (lcn * cluster_size)
                                        fhandle.seek(byte_offset)
                                        to_read = run_len * cluster_size
                                        chunk = fhandle.read(to_read)
                                        if chunk:
                                            f_out.write(chunk)
                                            saved = True
                                    except Exception as e:
                                        print(f"    [Lỗi đọc cluster {lcn}: {e}]")
                            
                            if saved:
                                print(f"  [ĐÃ LƯU NON-RESIDENT]: {save_path}")
                            else:
                                print(f"  [KHÔNG THỂ LƯU]: Không đọc được dữ liệu từ cluster")
                                # Remove empty file
                                if os.path.exists(save_path) and os.path.getsize(save_path) == 0:
                                    os.remove(save_path)
                        
                        except Exception as e:
                            print(f"  [Lỗi xử lý NON-RESIDENT: {e}]")

            # Nhảy đến thuộc tính tiếp theo
            attr_offset += attr_len

    except Exception as e:
        print(f"  [Lỗi khi phân tích record 0x{record_offset:X}]: {e}")

def main_recovery_scan(file_path):
    """
    Hàm chính: Quét VHD, tìm MFT record và gọi hàm phân tích.
    """
    print("---  Bắt đầu Quá trình Quét và Khôi phục ---")
    print(f"File VHD: {file_path}")
    print(f"Lưu vào: {RECOVERY_PATH}")
    
    found_count = 0
    valid_count = 0

    try:
        with open(file_path, 'rb') as f:
            partition_offset = 0
            
            # Try to read boot sector at offset 0
            boot = read_boot_sector(f, 0)
            
            if not boot:
                # Boot sector at 0 failed, try parsing MBR
                print(" Boot sector tại offset 0 không hợp lệ, thử phân tích MBR...")
                partition_offset = parse_mbr(f)
                
                if partition_offset:
                    print(f" Tìm thấy phân vùng NTFS tại offset: 0x{partition_offset:X} ({partition_offset} bytes)")
                    boot = read_boot_sector(f, partition_offset)
                else:
                    print(" Không tìm thấy phân vùng NTFS trong MBR")
            
            if boot:
                cluster_size = boot['cluster_size']
                mft_hint = boot['mft_cluster'] * cluster_size
                print(f"Detected cluster_size={cluster_size}, MFT cluster hint={boot['mft_cluster']} (offset {mft_hint})")
            else:
                cluster_size = ASSUMED_CLUSTER_SIZE
                mft_hint = None
                print(f" CẢNH BÁO: Không đọc được boot sector hợp lệ")
                print(f"   Sử dụng cluster size mặc định: {cluster_size}")
                print(f"   Bảng thư mục (MFT) và bảng Cluster có thể BỊ HỎNG")
                print(f"   Sẽ quét toàn bộ file để tìm MFT records...")

            # Tìm mọi vị trí có chữ ký MFT 'FILE' trong file bằng cách đọc theo chunk
            signature = MFT_SIGNATURE
            chunk_size = 4 * 1024 * 1024
            overlap = len(signature) - 1
            file_offset = 0
            prev = b''
            total_searched = 0

            f.seek(0)
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                buffer = prev + chunk
                idx = 0
                while True:
                    pos = buffer.find(signature, idx)
                    if pos == -1:
                        break
                    abs_offset = file_offset - len(prev) + pos
                    # Try to read MFT record
                    f.seek(abs_offset)
                    rec = f.read(MFT_RECORD_SIZE)
                    if len(rec) == MFT_RECORD_SIZE:
                        found_count += 1
                        
                        # Validate MFT record
                        if validate_mft_record(rec):
                            valid_count += 1
                            print(f"\n✅ MFT record hợp lệ tại 0x{abs_offset:X} (#{valid_count}/{found_count})")
                            parse_mft_record(rec, abs_offset, fhandle=f, cluster_size=cluster_size, partition_offset=partition_offset)
                        else:
                            # False positive - just signature match but not valid MFT
                            if found_count % 10 == 0:
                                print(f"\nTìm thấy chữ ký 'FILE' nhưng không phải MFT hợp lệ tại 0x{abs_offset:X}")
                    idx = pos + 1

                # prepare next loop
                total_searched += len(chunk)
                file_offset += len(chunk)
                prev = buffer[-overlap:]

                if total_searched % (chunk_size * 4) == 0:
                    print(f"  Đã quét ~{total_searched // (1024*1024)} MB...", end='\r')

    except FileNotFoundError:
        print(f"LỖI: Không tìm thấy file {file_path}")
        return
    except Exception as e:
        print(f"Lỗi: {e}")
        import traceback
        traceback.print_exc()

    print("\n\n--- ✅ Quét hoàn tất ---")
    print(f"Tổng cộng tìm thấy {found_count} chữ ký 'FILE'")
    print(f"Trong đó {valid_count} MFT record hợp lệ")
    print(f"Các file đã được lưu vào: {RECOVERY_PATH}")
    
    if valid_count == 0 and found_count > 0:
        print("\nCẢNH BÁO: Không tìm thấy MFT record hợp lệ nào!")
        print("   Bảng thư mục (MFT) có thể bị hỏng hoàn toàn.")
        print("   Khuyến nghị: Sử dụng công cụ file carving để khôi phục dữ liệu.")

# --- Chạy chương trình ---
if __name__ == "__main__":
    if not os.path.exists(VHD_FILE_PATH):
        print(f"LỖI KHỞI ĐỘNG: Không tìm thấy file VHD tại:")
        print(f"{VHD_FILE_PATH}")
        print("Vui lòng sửa biến 'VHD_FILE_PATH' ở đầu script.")
    else:
        main_recovery_scan(VHD_FILE_PATH)