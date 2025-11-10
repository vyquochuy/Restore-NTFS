#!/usr/bin/env python3
# ntfs_partition_rebuild.py
# Mục đích: scan image for NTFS boot sectors, parse them, propose MBR partition entries,
# optionally write a new MBR into a copy of the image.
# CẢNH BÁO: Luôn làm việc trên bản sao. Không ghi lên device thật nếu không chắc.

import argparse
import struct
import os
import json

SECTOR_SIZE = 512  # đọc theo sector 512 mặc định; nếu MBR khác sẽ detect

def read_sector(f, lba, sector_size=SECTOR_SIZE):
    f.seek(lba * sector_size)
    return f.read(sector_size)

def is_ntfs_boot_sector(sec):
    # offset 3, 8 bytes should be ASCII "NTFS    "
    if len(sec) < 11:
        return False
    return sec[3:11] == b'NTFS    '

def parse_ntfs_boot(sec):
    # parse fields we need: bytes_per_sector (0x0B,2), sectors_per_cluster (0x0D,1),
    # total_sectors (0x28,8), mft_lcn (0x30,8), mftmirr_lcn (0x38,8), clusters_per_mft_record (0x40,1 signed)
    if len(sec) < 512:
        raise ValueError("Boot sector too small")
    bps = struct.unpack_from("<H", sec, 0x0B)[0]
    spc = struct.unpack_from("<B", sec, 0x0D)[0]
    # total sectors (8 bytes) at 0x28
    total_sectors = struct.unpack_from("<Q", sec, 0x28)[0]
    mft_lcn = struct.unpack_from("<q", sec, 0x30)[0]  # signed 8 bytes (but usually positive)
    mftmirr_lcn = struct.unpack_from("<q", sec, 0x38)[0]
    clusters_per_file_record = struct.unpack_from("<b", sec, 0x40)[0]  # signed char; if negative, file record size = 2^(abs(val))
    info = {
        "bytes_per_sector": bps,
        "sectors_per_cluster": spc,
        "bytes_per_cluster": bps * spc,
        "total_sectors": total_sectors,
        "mft_lcn": mft_lcn,
        "mftmirr_lcn": mftmirr_lcn,
        "clusters_per_file_record": clusters_per_file_record
    }
    # compute MFT byte offset (relative to partition start)
    if mft_lcn >= 0:
        info["mft_byte_offset"] = mft_lcn * info["bytes_per_cluster"]
    else:
        info["mft_byte_offset"] = None
    return info

def scan_image_for_ntfs(image_path, max_sectors=None):
    candidates = []
    with open(image_path, "rb") as f:
        f.seek(0, os.SEEK_END)
        total_bytes = f.tell()
        total_sectors_image = total_bytes // SECTOR_SIZE
        max_scan = total_sectors_image if max_sectors is None else min(total_sectors_image, max_sectors)
        print(f"[+] Image size: {total_bytes} bytes, sectors: {total_sectors_image}. Scanning first {max_scan} sectors.")
        for lba in range(0, max_scan):
            sec = read_sector(f, lba)
            if is_ntfs_boot_sector(sec):
                try:
                    info = parse_ntfs_boot(sec)
                    info["boot_lba"] = lba
                    # sanity checks
                    if info["mft_byte_offset"] is not None:
                        # ensure mft lies within image:
                        if info["mft_byte_offset"] + 1024 < total_bytes:
                            info["sanity"] = "ok"
                        else:
                            info["sanity"] = "mft_out_of_range"
                    else:
                        info["sanity"] = "no_mft"
                    candidates.append(info)
                    print(f"[+] Found NTFS boot at LBA {lba}: {info}")
                except Exception as e:
                    print(f"[!] Failed parse at LBA {lba}: {e}")
    return candidates

# --- MBR helpers ---
def make_mbr_with_partitions(partitions):
    """
    partitions: list of dicts with fields: 
      { 'bootable':0/1, 'type': int, 'start_lba': int, 'num_sectors': int }
    returns 512-byte MBR bytes
    """
    mbr = bytearray(512)
    # Lấy MBR Boot Code cũ (hoặc để trống)
    # Giả định MBR Code (0x00 - 0x1BD) được giữ nguyên hoặc để 0x00
    
    # Ghi các Partition Entry tại offset 446 (0x1BE)
    for i, p in enumerate(partitions[:4]):
        entry_offset = 446 + i * 16

        # Phân vùng đầu tiên thường là Active
        boot_flag = 0x80 if i == 0 else 0x00
        part_type = p.get("type", 0x07) # 0x07 là NTFS/HPFS
        start_lba = p["start_lba"]
        num_sectors = p["num_sectors"]
        
        # Xây dựng 16 bytes:
        ent = bytearray(16)
        
        # Byte 0: Boot Flag
        ent[0] = boot_flag
        
        # Byte 1-3: CHS Start (Sử dụng giá trị tương thích LBA)
        ent[1] = 0x01   # Head Start
        ent[2] = 0x01   # Sector Start (Phải là 1-63, ở đây chọn 1)
        ent[3] = 0x00   # Cylinder Start
        
        # Byte 4: Partition Type
        ent[4] = part_type
        
        # Byte 5-7: CHS End (Sử dụng giá trị lớn nhất cho LBA)
        ent[5] = 0xFE   # Head End (254)
        ent[6] = 0xFF   # Sector End (63)
        ent[7] = 0xFF   # Cylinder End (1023)
        
        # Byte 8-11: LBA Start (Little-Endian, 4 bytes)
        ent[8:12] = struct.pack("<I", start_lba & 0xFFFFFFFF)
        
        # Byte 12-15: Total Sectors (Little-Endian, 4 bytes)
        ent[12:16] = struct.pack("<I", num_sectors & 0xFFFFFFFF)
        
        mbr[entry_offset:entry_offset+16] = ent
        
    # MBR Signature (offset 510-511)
    mbr[510] = 0x55
    mbr[511] = 0xAA
    return bytes(mbr)

def apply_new_mbr(image_in, image_out, partitions):
    # copy input to output, write MBR at sector 0 replaced
    with open(image_in, "rb") as fi, open(image_out, "wb") as fo:
        # first sector replaced
        full = fi.read()
        if len(full) < 512:
            raise RuntimeError("image too small")
        new_mbr = make_mbr_with_partitions(partitions)
        fo.write(new_mbr)
        fo.write(full[512:])
    print(f"[+] Wrote new image to {image_out}")

def propose_partitions_from_candidates(candidates, image_total_sectors):
    proposals = []
    for c in candidates:
        start = c["boot_lba"]
        if c.get("total_sectors") and c["total_sectors"]>0:
            length = c["total_sectors"]
        else:
            # fallback: try to find next NTFS boot or end of disk
            length = image_total_sectors - start
        proposals.append({
            "start_lba": start,
            "num_sectors": length,
            "type": 0x07,
            "bootable": 0
        })
    return proposals

def main():
    ap = argparse.ArgumentParser(description="Scan image for NTFS boot sectors and propose partition table (MBR).")
    ap.add_argument("--image", required=True)
    ap.add_argument("--out", required=False, help="If provided and --apply, write new image with rebuilt MBR")
    ap.add_argument("--apply", action="store_true", help="Apply changes (write out new image). Must provide --out")
    ap.add_argument("--max-sectors", type=int, default=None, help="Max sectors to scan (for speed)")
    args = ap.parse_args()

    candidates = scan_image_for_ntfs(args.image, max_sectors=args.max_sectors)
    if not candidates:
        print("[!] No NTFS boot sectors found.")
        return

    # read image size
    with open(args.image,"rb") as f:
        f.seek(0, os.SEEK_END)
        total_bytes = f.tell()
    total_sectors = total_bytes // SECTOR_SIZE

    proposals = propose_partitions_from_candidates(candidates, total_sectors)
    out = {
        "image": args.image,
        "candidates": candidates,
        "proposals": proposals
    }
    print("[+] Proposals:")
    print(json.dumps(out, indent=2))

    # Save suggestions to file
    sugg_name = os.path.splitext(os.path.basename(args.image))[0] + ".suggestions.json"
    with open(sugg_name, "w") as sg:
        json.dump(out, sg, indent=2)
    print(f"[+] Suggestions saved to {sugg_name}")

    if args.apply:
        if not args.out:
            raise SystemExit("Provide --out when using --apply")
        # CHỈ LẤY PHÂN VÙNG ĐẦU TIÊN (LBA THẤP NHẤT) ĐỂ GHI VÀO MBR
        if proposals:
            apply_new_mbr(args.image, args.out, proposals[:1]) # Chỉ ghi proposals[0]
            print("[+] Done. New image written. Use kpartx/losetup to map partitions and test mount.")
        else:
            print("[!] Cannot apply: No valid partition proposals found.")
            
if __name__ == "__main__":
    main()
