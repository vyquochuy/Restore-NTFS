import os
import struct
import string
import sys

# --- CẤU HÌNH CHUNG ---
# (Đã xóa biến DRIVE, sẽ hỏi người dùng khi chạy)
MFT_LIST_FILE = "mft_record_list.txt" # File tạm để lưu danh sách MFT record
OUTPUT_DIR = "recovered_files"    # Thư mục chứa file khôi phục
MAX_MFT_RECORDS_TO_SCAN = 50000   # Số lượng MFT record tối đa cần quét

# --- GIAI ĐOẠN 1: HÀM ĐỌC VÀ PHÂN TÍCH BOOT SECTOR ---

def read_disk_sector(drive_path, offset=0, size=512):
    """
    Đọc một lượng byte nhất định (mặc định là 1 sector) từ ổ đĩa tại offset.
    """
    try:
        with open(drive_path, "rb") as f:
            f.seek(offset)
            data = f.read(size)
        return data
    except PermissionError:
        print(f"[!] LỖI: Không có quyền truy cập {drive_path}.")
        print("    Vui lòng chạy script này với quyền Administrator.")
        return None
    except FileNotFoundError:
        print(f"[!] LỖI: Không tìm thấy ổ đĩa {drive_path}.")
        return None
    except Exception as e:
        print(f"[!] Lỗi không xác định khi đọc ổ đĩa tại offset {offset}: {e}")
        return None

def format_hex_view(data, bytes_per_line=16):
    """
    Định dạng dữ liệu byte sang dạng hex + ASCII.
    """
    lines = []
    for i in range(0, len(data), bytes_per_line):
        chunk = data[i:i + bytes_per_line]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{i:04x}  {hex_part:<47}  {ascii_part}")
    return "\n".join(lines)

def parse_boot_sector(bs):
    """
    Phân tích Boot Sector NTFS và trả về một dictionary thông tin.
    """
    info = {}
    try:
        info["OEM_ID"] = bs[3:11].decode("ascii", errors="ignore").strip()
        if info["OEM_ID"] != "NTFS":
            print(f"[!] Lỗi: Ổ đĩa không phải là NTFS (OEM ID: {info['OEM_ID']})")
            return None

        info["BytesPerSector"] = int.from_bytes(bs[11:13], "little")
        info["SectorsPerCluster"] = bs[13]
        info["BytesPerCluster"] = info["BytesPerSector"] * info["SectorsPerCluster"]

        info["MFT_LCN"] = int.from_bytes(bs[48:56], "little")
        info["MFTMirr_LCN"] = int.from_bytes(bs[56:64], "little")

        clusters_per_record = struct.unpack("b", bs[64:65])[0]
        if clusters_per_record > 0:
            info["BytesPerFileRecord"] = clusters_per_record * info["BytesPerCluster"]
        else:
            info["BytesPerFileRecord"] = 2 ** abs(clusters_per_record)

        info["ClustersPerFileRecord"] = clusters_per_record
        info["MFT_Offset"] = info["MFT_LCN"] * info["BytesPerCluster"]
        return info
    except Exception as e:
        print(f"[!] Lỗi khi phân tích boot sector: {e}")
        return None

# --- GIAI ĐOẠN 2: HÀM QUÉT MFT ---

def read_mft_records(drive_path, start_offset, record_size, max_records, output_file):
    """
    Đọc các MFT record, kiểm tra tính hợp lệ và ghi offset vào file.
    """
    valid_records = []
    print(f"[+] Đang đọc {max_records} record đầu tiên trong MFT tại offset {start_offset}...\n")
    
    with open(drive_path, "rb") as f:
        for i in range(max_records):
            record_offset = start_offset + i * record_size
            f.seek(record_offset)
            data = f.read(record_size)

            if len(data) < record_size:
                print(f"[!] Record {i}: Dữ liệu không đủ. Dừng quét.")
                break

            signature = data[0:4]
            if signature != b"FILE":
                continue # Bỏ qua, không cần in ra

            flags = struct.unpack("<H", data[22:24])[0]
            deleted = not (flags & 0x0001)

            # print(f"  [{i:04}]  Hợp lệ | {'ĐÃ XÓA' if deleted else 'TỒN TẠI'} | Offset: {record_offset}")
            valid_records.append(record_offset)

    with open(output_file, "w") as out_f:
        for offset in valid_records:
            out_f.write(f"{offset}\n")
            
    print(f"\n[+] Đã ghi {len(valid_records)} offset record hợp lệ vào '{output_file}'.")
    return valid_records

# --- GIAI ĐOẠN 3: HÀM PHÂN TÍCH MFT RECORD (TÊN VÀ DATA) ---

def parse_file_name_attribute(record):
    """
    Trích xuất tên file từ thuộc tính 0x30 ($FILE_NAME).
    """
    try:
        attr_offset = struct.unpack("<H", record[20:22])[0]
        
        while attr_offset + 4 <= len(record):
            attr_type = struct.unpack("<I", record[attr_offset:attr_offset+4])[0]
            if attr_type == 0xFFFFFFFF: # End of attributes
                break
            attr_len = struct.unpack("<I", record[attr_offset+4:attr_offset+8])[0]
            if attr_len == 0:
                break 

            if attr_type == 0x30:  # FILE_NAME attribute
                content_offset = struct.unpack("<H", record[attr_offset+0x14:attr_offset+0x16])[0]
                content = record[attr_offset + content_offset : attr_offset + attr_len]
                name_len = content[0x40]
                name_bytes = content[0x42 : 0x42 + name_len*2]
                return name_bytes.decode("utf-16le", errors="ignore")
            
            attr_offset += attr_len
    except Exception as e:
        print(f"[!] Lỗi khi parse_file_name_attribute: {e}")
    
    return "<không có tên>"

def parse_data_attribute(record):
    """
    Trích xuất danh sách cluster (data runs) từ thuộc tính 0x80 ($DATA).
    Trả về danh sách các tuple (LCN, ClusterCount).
    """
    try:
        attr_offset = struct.unpack("<H", record[20:22])[0]
        
        while attr_offset + 4 <= len(record):
            attr_type = struct.unpack("<I", record[attr_offset:attr_offset+4])[0]
            if attr_type == 0xFFFFFFFF: # End
                break
            attr_len = struct.unpack("<I", record[attr_offset+4:attr_offset+8])[0]
            if attr_len == 0:
                break

            if attr_type == 0x80:  # $DATA attribute
                non_resident_flag = record[attr_offset+8]
                if non_resident_flag == 0:
                    return None 

                runlist_offset = struct.unpack("<H", record[attr_offset+0x20:attr_offset+0x22])[0]
                runlist_end = struct.unpack("<H", record[attr_offset+0x18:attr_offset+0x1A])[0] # Kích thước phân bổ
                
                clusters = []
                current_lcn = 0
                p = attr_offset + runlist_offset
                
                while p < attr_offset + runlist_end:
                    header_byte = record[p]
                    if header_byte == 0x00:
                        break
                    p += 1
                    
                    len_bytes = header_byte & 0x0F
                    offset_bytes = (header_byte >> 4) & 0x0F
                    
                    if p + len_bytes + offset_bytes > len(record):
                        return None

                    run_length_bytes = record[p : p + len_bytes]
                    run_length = int.from_bytes(run_length_bytes + b'\x00' * (8 - len_bytes), 'little')
                    p += len_bytes
                    
                    run_offset_bytes = record[p : p + offset_bytes]
                    p += offset_bytes
                    
                    if run_offset_bytes:
                        # Xử lý số âm (two's complement)
                        if run_offset_bytes[-1] & 0x80:
                            run_offset_bytes += b'\xFF' * (8 - offset_bytes)
                        else:
                            run_offset_bytes += b'\x00' * (8 - offset_bytes)
                        run_offset = int.from_bytes(run_offset_bytes, 'little', signed=True)
                    else:
                        run_offset = 0
                    
                    current_lcn += run_offset 
                    
                    if run_length > 0:
                        clusters.append((current_lcn, run_length))
                        
                return clusters

            attr_offset += attr_len
    except Exception as e:
        print(f"[!] Lỗi khi parse_data_attribute: {e}")
    
    return None # Không tìm thấy $DATA hoặc data là resident

# --- GIAI ĐOẠN 4: HÀM KHÔI PHỤC FILE TỪ CLUSTER ---

def read_clusters(drive_path, clusters, bytes_per_cluster):
    """
    Đọc dữ liệu từ một danh sách các cluster (LCN, count).
    """
    data = b""
    try:
        with open(drive_path, "rb") as f:
            for lcn, count in clusters:
                try:
                    f.seek(lcn * bytes_per_cluster)
                    data += f.read(count * bytes_per_cluster)
                except Exception as e:
                    print(f"  [!] Lỗi khi đọc cluster (LCN: {lcn}, Count: {count}): {e}")
        return data
    except Exception as e:
        print(f"[!] Lỗi nghiêm trọng khi mở ổ đĩa để đọc cluster: {e}")
        return b""

def main():
    drive_path = r"\\.\D:" 
    
    print(f"*** Bắt đầu quá trình phân tích và khôi phục ổ đĩa: {drive_path} ***\n")
    
    # --- GIAI ĐOẠN 1: PHÂN TÍCH BOOT SECTOR ---
    print("[+] --- GIAI ĐOẠN 1: PHÂN TÍCH BOOT SECTOR ---")
    sector_data = read_disk_sector(drive_path, 0, 512)
    if sector_data is None:
        sys.exit(1)

    print("\n[+] --- Thông tin Boot Sector ---")
    
    print(f"\n*** Bắt đầu quá trình phân tích và khôi phục ổ đĩa: {drive_path} ***\n")
    
    # GIAI ĐOẠN 1: PHÂN TÍCH BOOT SECTOR
    print("[+] --- GIAI ĐOẠN 1: PHÂN TÍCH BOOT SECTOR ---")
    sector_data = read_disk_sector(drive_path, 0, 512)
    if sector_data is None:
        sys.exit(1) 

    print("\n[+] --- Thông tin Boot Sector ---")
    ntfs_info = parse_boot_sector(sector_data)
    
    if ntfs_info is None:
        print("[!] Dừng lại do không phân tích được Boot Sector.")
        sys.exit(1)

    print(f"  OEM_ID               : {ntfs_info['OEM_ID']}")
    print(f"  BytesPerCluster      : {ntfs_info['BytesPerCluster']}")
    print(f"  BytesPerFileRecord   : {ntfs_info['BytesPerFileRecord']}")
    print(f"  MFT_Offset           : {ntfs_info['MFT_Offset']}")

    # --- GIAI ĐOẠN 2: QUÉT MFT ---
    print("\n[+] --- GIAI ĐOẠN 2: QUÉT MFT ---")
    valid_record_offsets = read_mft_records(
        drive_path, 
        ntfs_info['MFT_Offset'], 
        ntfs_info['BytesPerFileRecord'],
        MAX_MFT_RECORDS_TO_SCAN,
        MFT_LIST_FILE
    )

    if not valid_record_offsets:
        print("[!] Không tìm thấy MFT record hợp lệ. Dừng lại.")
        sys.exit(1)

    # --- GIAI ĐOẠN 3: PHÂN TÍCH TÊN FILE VÀ DATA CLUSTERS ---
    print("\n[+] --- GIAI ĐOẠN 3: TÌM FILE ĐÃ XÓA VÀ CLUSTER DATA ---")
    print(f"  (Đọc {len(valid_record_offsets)} record từ file '{MFT_LIST_FILE}'...)\n")
    
    found_deleted_files = []
    
    for offset in valid_record_offsets:
        record = read_disk_sector(drive_path, offset, ntfs_info['BytesPerFileRecord'])
        if record is None or record[0:4] != b"FILE":
            continue
        
        flags = struct.unpack("<H", record[22:24])[0]
        deleted = not (flags & 0x0001)
        name = parse_file_name_attribute(record)
        
        # CHỈ TÌM FILE BỊ XÓA VÀ CÓ TÊN
        if deleted and name != "<không có tên>":
            print(f"  [ĐÃ XÓA] Tìm thấy: {name} (tại MFT offset {offset})")
            
            clusters = parse_data_attribute(record)
            
            if clusters:
                print(f"    -> Tìm thấy data runs: {clusters}")
                found_deleted_files.append({"name": name, "clusters": clusters, "offset": offset})
            #else:
                #print(f"    -> Không tìm thấy data runs (có thể file quá nhỏ hoặc bị ghi đè).")

    # GIAI ĐOẠN 4: KHÔI PHỤC FILE (TỰ ĐỘNG) ---
    print("\n[+] --- GIAI ĐOẠN 4: KHÔI PHỤC FILE TỰ ĐỘNG ---")
    
    if not found_deleted_files:
        print("[!] Không tìm thấy file nào đã xóa (còn data run) để khôi phục.")
        print("\n[+] === HOÀN THÀNH ===")
        sys.exit(0)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"[+] Tạo thư mục khôi phục tại: {os.path.abspath(OUTPUT_DIR)}")
    
    # Chạy vòng lặp trên danh sách TỰ ĐỘNG tìm được
    for file_info in found_deleted_files:
        file_name = file_info["name"]
        clusters = file_info["clusters"]
        offset = file_info["offset"] # Dùng để tránh trùng tên
        
        # Làm sạch tên file để tránh lỗi
        safe_name = "".join(c for c in file_name if c.isalnum() or c in (' ', '.', '_', '-')).strip()
        if not safe_name:
            safe_name = f"recovered_file_offset_{offset}.dat" # Tên dự phòng

        #print(f"[+] Đang khôi phục {safe_name}...")
        
        content = read_clusters(drive_path, clusters, ntfs_info['BytesPerCluster'])
        
        if content:
            output_path = os.path.join(OUTPUT_DIR, safe_name)
            
            # Xử lý nếu trùng tên file
            if os.path.exists(output_path):
                base, ext = os.path.splitext(safe_name)
                output_path = os.path.join(OUTPUT_DIR, f"{base}_(offset_{offset}){ext}")
            
            try:
                with open(output_path, "wb") as out_file:
                    out_file.write(content)
                print(f"   {safe_name} đã được khôi phục thành công.")
            except Exception as e:
                print(f"   Lỗi khi GHI file {safe_name}: {e}")
        else:
            print(f"   Lỗi khi ĐỌC cluster cho file {safe_name}. (Nội dung trống)")

    print("\n[+] === HOÀN THÀNH TẤT CẢ CÁC GIAI ĐOẠN ===")

if __name__ == "__main__":
    main()
    