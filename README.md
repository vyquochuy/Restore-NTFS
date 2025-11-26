# Lab Phuc hoi Du lieu va Forensics tren he thong tap tin NTFS

## Gioi thieu
Du an nay la mot bo cong cu Python thuc hien viec phan tich va phuc hoi du lieu tren he thong tap tin NTFS o muc do thap (low-level). Bo cong cu mo phong quy trinh xu ly su co tu lop vat ly den lop ung dung, bao gom: khoi phuc bang phan vung (MBR), sua chua Boot Sector (VBR), sua chua Master File Table (MFT) va khoi phuc tap tin da xoa.

Du an duoc thiet ke cho muc dich hoc tap, nghien cuu ve cau truc NTFS va Digital Forensics.

## Cau truc Du an

Du an bao gom 4 script Python chinh, tuong ung voi 4 giai doan khoi phuc:

1. **1.partition.py**
   - Chuc nang: Quet toan bo file anh dia (image file) de tim cac dau hieu cua NTFS Boot Sector.
   - Muc dich: De xuat va tai tao lai bang phan vung MBR neu no bi hong hoac bi xoa.

2. **2.rescovery_vbr.py**
   - Chuc nang: Khoi phuc Volume Boot Record (VBR) chinh bi hong.
   - Co che: Doc thong tin tu MBR de xac dinh vi tri phan vung, sau do sao chep VBR du phong (nam o sector cuoi cung cua phan vung) de ghi de len VBR chinh.

3. **3.cluster.py**
   - Chuc nang: Quet va sua chua cac ban ghi (Record) trong Master File Table (MFT).
   - Co che: Kiem tra chu ky "FILE" cua tung MFT Record. Neu phat hien record bi loi (header bi xoa hoac hong), script se hoi nguoi dung de tu dong sua chua.

4. **4.recovery_file.py**
   - Chuc nang: Khoi phuc cac tap tin da bi xoa vinh vien khoi he thong.
   - Co che: Doc MFT, phan tich thuoc tinh $FILE_NAME va $DATA, trich xuat du lieu tu cac cluster tuong ung va luu ra file.

## Yeu cau He thong

- **Ngon ngu:** Python 3.6 tro len.
- **Quyen han:** Can chay voi quyen **Administrator** (Windows) hoac **Root** (Linux) de co the truy cap truc tiep vao o dia vat ly hoac ghi du lieu len file VHD dang duoc gan (mount).

## Huong dan Su dung

Luu y: Can chinh sua duong dan file `.vhd` hoac ten o dia (vi du: `\\.\D:`) trong code truoc khi chay neu cau hinh may cua ban khac voi mac dinh.

### Buoc 1: Khoi phuc Bang phan vung (Partition Table)
Su dung script `1.partition.py` de quet va tao lai MBR.

Cu phap:
python 1.partition.py --image <duong_dan_file_vhd> --apply --out <ten_file_output>

Vi du:
python 1.partition.py --image demo.vhd --apply --out fixed_mbr.vhd

### Buoc 2: Khoi phuc VBR (Volume Boot Record)
Sau khi co bang phan vung, su dung script `2.rescovery_vbr.py` de sua chua boot sector neu bi hong.

- Mo file `2.rescovery_vbr.py`.
- Kiem tra bien `VHD_FILE_PATH` de dam bao tro dung toi file VHD can sua.
- Chay lenh:
python 2.rescovery_vbr.py

### Buoc 3: Sua chua MFT (Master File Table)
Su dung script `3.cluster.py` de quet cac loi logic trong MFT.

- Mo file `3.cluster.py`.
- Kiem tra duong dan file tai bien `vhd_file`.
- Chay lenh:
python 3.cluster.py

Chuong trinh se quet va thong bao so luong record bi loi. Nhap 'y' de tien hanh sua chua.

### Buoc 4: Khoi phuc Tap tin (File Recovery)
Su dung script `4.recovery_file.py` de trich xuat du lieu.

- Luu y: Can Mount file VHD ra mot o dia that tren Windows (vi du o dia D:).
- Mo file `4.recovery_file.py`, sua bien `drive_path` thanh ky tu o dia tuong ung (vi du: `r"\\.\D:"`).
- Chay lenh:
python 4.recovery_file.py

Ket qua: Cac file khoi phuc duoc se nam trong thu muc `recovered_files`.

## Canh bao va Mien tru trach nhiem

1. **Sao luu du lieu:** Luon lam viec tren mot ban sao (copy) cua file anh dia hoac o dia. Viec ghi truc tiep len o dia goc co the gay mat du lieu vinh vien.
2. **Quyen truy cap:** Viec truy cap truc tiep vao o dia vat ly (`\\.\PhysicalDrive`) doi hoi quyen Admin cao nhat va rat nhay cam.
3. **Moi truong:** Code duoc toi uu hoa cho moi truong Windows va he thong tap tin NTFS.

---
Lab: An Toan Va Phuc hoi du lieu