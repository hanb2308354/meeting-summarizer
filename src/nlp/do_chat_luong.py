# Thước đo chất lượng trích xuất (precision, recall) so với nhãn tay.
# Không sửa luật, không ghi vào outputs/. Cách dùng:
#   python src/nlp/do_chat_luong.py              đo tất cả file trong data/nhan_dap_an.json
#   python src/nlp/do_chat_luong.py --chi-tiet   in thêm toàn bộ kết quả sinh ra
#   python src/nlp/do_chat_luong.py --tu-kiem    tự kiểm hàm so_sanh, không chạy pipeline
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

GOC_REPO = Path(__file__).resolve().parents[2]
DUONG_DAN_NHAN = GOC_REPO / "data" / "nhan_dap_an.json"
THU_MUC_TRANSCRIPT = GOC_REPO / "data" / "transcripts"

# Các loại kết quả của một việc
DUNG = "ĐÚNG"
SAI_HAN = "SAI_HẠN"
HAN_BI_THAY = "HẠN_BỊ_THAY"
THIEU = "THIẾU"
CAM = "CẤM"
TRUNG = "TRÙNG"
GIA = "GIẢ"
TUY_CHON = "TÙY_CHỌN"
CAC_LOAI_LOI = (SAI_HAN, HAN_BI_THAY, THIEU, CAM, TRUNG, GIA)

# Tiền tố bỏ khi so hạn, theo đúng thứ tự: "trước " rồi "ngày "
TIEN_TO_HAN = ("trước ", "ngày ")


def chuan_hoa(gia_tri):
    """Chữ thường, gộp khoảng trắng; None thành chuỗi rỗng."""
    if gia_tri is None:
        return ""
    return " ".join(str(gia_tri).lower().split())


def chuan_han(han):
    """Chuẩn hóa hạn để so bằng; hạn rỗng hoặc None trả về None."""
    chuoi = chuan_hoa(han)
    for tien_to in TIEN_TO_HAN:
        if chuoi.startswith(tien_to):
            chuoi = chuoi[len(tien_to):]
    return chuoi or None


def chua_tat_ca(van_ban, tu_khoa):
    """Văn bản chứa mọi từ khóa (danh sách rỗng thì luôn đúng)."""
    nen = chuan_hoa(van_ban)
    return all(chuan_hoa(tu) in nen for tu in (tu_khoa or []))


def khop_viec(task, muc):
    """Việc sinh ra khớp mục nhãn theo chủ (bằng) và từ khóa (mô tả chứa tất cả)."""
    if chuan_hoa(task.get("owner")) != chuan_hoa(muc.get("chu")):
        return False
    return chua_tat_ca(task.get("task"), muc.get("tu_khoa"))


def khop_cam(task, muc):
    """Việc sinh ra khớp một mục cấm (chu null là bất kỳ chủ, từ khóa rỗng là mọi từ khóa)."""
    chu = muc.get("chu")
    tu_khoa = muc.get("tu_khoa") or []
    if chu is None and not tu_khoa:
        return False
    if chu is not None and chuan_hoa(task.get("owner")) != chuan_hoa(chu):
        return False
    return chua_tat_ca(task.get("task"), tu_khoa)


def so_sanh_viec(nhan, tasks):
    """Phân loại từng việc sinh ra và từng mục bắt buộc."""
    bat_buoc = nhan.get("viec_bat_buoc", [])
    tuy_chon = nhan.get("viec_tuy_chon", [])
    cam = nhan.get("viec_cam", [])

    la_cam = {i for i, task in enumerate(tasks) if any(khop_cam(task, muc) for muc in cam)}
    da_dung = set()
    ghep = {}  # chỉ số mục bắt buộc -> (chỉ số việc, loại)

    # Lượt 1: chủ + từ khóa + hạn đều khớp
    for m, muc in enumerate(bat_buoc):
        han_muc = chuan_han(muc.get("han"))
        for i, task in enumerate(tasks):
            if i in la_cam or i in da_dung:
                continue
            if khop_viec(task, muc) and chuan_han(task.get("deadline")) == han_muc:
                ghep[m] = (i, DUNG)
                da_dung.add(i)
                break

    # Lượt 2: chủ + từ khóa khớp, hạn khác
    for m, muc in enumerate(bat_buoc):
        if m in ghep:
            continue
        han_thay = chuan_han(muc.get("han_bi_thay"))
        for i, task in enumerate(tasks):
            if i in la_cam or i in da_dung:
                continue
            if khop_viec(task, muc):
                han_sinh = chuan_han(task.get("deadline"))
                loai = HAN_BI_THAY if han_thay is not None and han_sinh == han_thay else SAI_HAN
                ghep[m] = (i, loai)
                da_dung.add(i)
                break

    dong = []
    loai_theo_viec = {}
    for m, (i, loai) in ghep.items():
        loai_theo_viec[i] = loai
    for m, muc in enumerate(bat_buoc):
        if m not in ghep:
            dong.append({"loai": THIEU, "chu": muc.get("chu"), "han": muc.get("han"),
                         "mo_ta": f"từ khóa {muc.get('tu_khoa')}", "task": None})

    da_tuy_chon = set()
    for i, task in enumerate(tasks):
        if i in loai_theo_viec:
            loai = loai_theo_viec[i]
        elif i in la_cam:
            loai = CAM
        elif any(khop_viec(task, muc) for muc in bat_buoc):
            loai = TRUNG
        else:
            loai = GIA
            for k, muc in enumerate(tuy_chon):
                if khop_viec(task, muc):
                    if k in da_tuy_chon:
                        loai = TRUNG
                    else:
                        da_tuy_chon.add(k)
                        loai = TUY_CHON
                    break
        dong.append({"loai": loai, "chu": task.get("owner"), "han": task.get("deadline"),
                     "mo_ta": task.get("task"), "task": task})

    dem = Counter(d["loai"] for d in dong)
    return {
        "dong": dong,
        "dem": dem,
        "so_sinh_ra": len(tasks),
        "so_tuy_chon": dem[TUY_CHON],
        "so_bat_buoc": len(bat_buoc),
    }


def so_sanh_quyet_dinh(nhan, decisions):
    """Ghép một-một quyết định sinh ra với mục nhãn (mô tả chứa tất cả từ khóa)."""
    bat_buoc = nhan.get("quyet_dinh", [])
    tuy_chon = nhan.get("quyet_dinh_tuy_chon", [])
    da_dung = set()
    khop = 0
    thieu = []
    for muc in bat_buoc:
        tu_khoa = muc.get("tu_khoa", [])
        tim = next((i for i, qd in enumerate(decisions)
                    if i not in da_dung and chua_tat_ca(qd.get("text"), tu_khoa)), None)
        if tim is None:
            thieu.append(tu_khoa)
        else:
            da_dung.add(tim)
            khop += 1
    da_tuy_chon = set()
    thua = []
    for i, qd in enumerate(decisions):
        if i in da_dung:
            continue
        gan = next((k for k, muc in enumerate(tuy_chon)
                    if k not in da_tuy_chon and chua_tat_ca(qd.get("text"), muc.get("tu_khoa", []))), None)
        if gan is None:
            thua.append(qd.get("text"))
        else:
            da_tuy_chon.add(gan)
    return {"khop": khop, "bat_buoc": len(bat_buoc), "thieu": thieu, "thua": thua}


def so_sanh_lich_hop(nhan, next_meeting):
    """ĐẠT/KHÔNG ĐẠT theo nhãn; khóa vắng là không kiểm, null là phải không có."""
    cau_hinh = nhan.get("lich_hop", {})
    gio = (next_meeting or {}).get("time")
    noi = (next_meeting or {}).get("place")
    ly_do = []
    if "thoi_gian_chua" in cau_hinh:
        mong = cau_hinh["thoi_gian_chua"]
        if mong is None:
            if gio:
                ly_do.append(f"phải không có thời gian, thực tế {gio!r}")
        elif chuan_hoa(mong) not in chuan_hoa(gio):
            ly_do.append(f"thời gian {gio!r} không chứa {mong!r}")
    if "noi_bang" in cau_hinh:
        mong = cau_hinh["noi_bang"]
        if mong is None:
            if noi:
                ly_do.append(f"phải không có địa điểm, thực tế {noi!r}")
        elif chuan_hoa(mong) != chuan_hoa(noi):
            ly_do.append(f"địa điểm {noi!r} khác {mong!r}")
    return {"dat": not ly_do, "ly_do": ly_do}


def so_sanh(nhan_file, tasks, decisions, next_meeting):
    """Hàm so sánh thuần: chỉ nhận dữ liệu có sẵn, không đọc file, không chạy pipeline."""
    return {
        "viec": so_sanh_viec(nhan_file, tasks),
        "quyet_dinh": so_sanh_quyet_dinh(nhan_file, decisions),
        "lich_hop": so_sanh_lich_hop(nhan_file, next_meeting),
    }


def chi_so_viec(cac_viec):
    """Gộp nhiều kết quả việc rồi tính precision, recall, recall_chu_tu_khoa."""
    dem = Counter()
    sinh_ra = tuy_chon = bat_buoc = 0
    for kq in cac_viec:
        dem.update(kq["dem"])
        sinh_ra += kq["so_sinh_ra"]
        tuy_chon += kq["so_tuy_chon"]
        bat_buoc += kq["so_bat_buoc"]
    mau_so_p = sinh_ra - tuy_chon
    precision = dem[DUNG] / mau_so_p if mau_so_p > 0 else 0.0
    recall = dem[DUNG] / bat_buoc if bat_buoc > 0 else 0.0
    recall_ck = (dem[DUNG] + dem[SAI_HAN] + dem[HAN_BI_THAY]) / bat_buoc if bat_buoc > 0 else 0.0
    return {"dem": dem, "sinh_ra": sinh_ra, "bat_buoc": bat_buoc,
            "precision": precision, "recall": recall, "recall_ck": recall_ck}


def dong_so_lieu(ten, cac_viec, cac_qd, cac_lich):
    """Một dòng số liệu cho một file hoặc một tập."""
    cs = chi_so_viec(cac_viec)
    dem = cs["dem"]
    qd_khop = sum(q["khop"] for q in cac_qd)
    qd_bb = sum(q["bat_buoc"] for q in cac_qd)
    qd_thua = sum(len(q["thua"]) for q in cac_qd)
    lich_dat = sum(1 for lich in cac_lich if lich["dat"])
    return (
        f"{ten:<22} sinh={cs['sinh_ra']:<3} bb={cs['bat_buoc']:<3} "
        f"P={cs['precision']:.2f} R={cs['recall']:.2f} Rck={cs['recall_ck']:.2f} | "
        f"{DUNG}={dem[DUNG]} {SAI_HAN}={dem[SAI_HAN]} {HAN_BI_THAY}={dem[HAN_BI_THAY]} "
        f"{THIEU}={dem[THIEU]} {CAM}={dem[CAM]} {TRUNG}={dem[TRUNG]} {GIA}={dem[GIA]} | "
        f"QĐ {qd_khop}/{qd_bb} thừa={qd_thua} | Lịch {lich_dat}/{len(cac_lich)}"
    )


def chay_pipeline(ten_file):
    """Chạy pipeline trong bộ nhớ (không ghi outputs/), trả về tasks, decisions, next_meeting."""
    from doc_transcript import doc_transcript
    from kiem_cau import chay_loi

    bai_doc = doc_transcript(THU_MUC_TRANSCRIPT / ten_file)
    ket_qua = chay_loi(bai_doc)
    return ket_qua["tasks"], ket_qua["decisions"], ket_qua["next_meeting"]


def in_loi(ten_file, kq):
    """Liệt kê từng lỗi của một file."""
    for dong in kq["viec"]["dong"]:
        if dong["loai"] in CAC_LOAI_LOI:
            print(f"{dong['loai']} | {ten_file} | {dong['chu']} | {dong['mo_ta']} | hạn={dong['han']}")
    for tu_khoa in kq["quyet_dinh"]["thieu"]:
        print(f"QĐ_THIẾU | {ten_file} | - | từ khóa {tu_khoa}")
    for van_ban in kq["quyet_dinh"]["thua"]:
        print(f"QĐ_THỪA | {ten_file} | - | {van_ban}")
    for ly_do in kq["lich_hop"]["ly_do"]:
        print(f"LỊCH_KHÔNG_ĐẠT | {ten_file} | - | {ly_do}")


def in_chi_tiet(ten_file, tasks, decisions, next_meeting):
    print(f"--- {ten_file}: toàn bộ kết quả sinh ra ---")
    for task in tasks:
        print(f"  VIỆC | {task.get('owner')} | {task.get('task')} | hạn={task.get('deadline')}")
    for qd in decisions:
        print(f"  QUYẾT ĐỊNH | {qd.get('text')}")
    print(f"  LỊCH HỌP | {next_meeting}")


def chay_do(chi_tiet):
    """Đo tất cả file trong file nhãn; mã thoát luôn 0 (đây là thước đo, không phải cổng chặn)."""
    with open(DUONG_DAN_NHAN, encoding="utf-8") as f:
        nhan = json.load(f)
    ket_qua = {}
    for ten_file, nhan_file in nhan.items():
        if not (THU_MUC_TRANSCRIPT / ten_file).exists():
            print(f"BỎ QUA | {ten_file} | không có trong data/transcripts/")
            continue
        tasks, decisions, next_meeting = chay_pipeline(ten_file)
        ket_qua[ten_file] = (nhan_file.get("tap", "khong_ro"),
                             so_sanh(nhan_file, tasks, decisions, next_meeting),
                             (tasks, decisions, next_meeting))
    print("=== Số liệu từng file ===")
    for ten_file, (tap, kq, _) in ket_qua.items():
        print(dong_so_lieu(ten_file, [kq["viec"]], [kq["quyet_dinh"]], [kq["lich_hop"]]))
    print("=== Tổng theo tập ===")
    for tap in sorted({tap for tap, _, _ in ket_qua.values()}):
        nhom = [kq for t, kq, _ in ket_qua.values() if t == tap]
        print(dong_so_lieu(tap, [k["viec"] for k in nhom], [k["quyet_dinh"] for k in nhom],
                           [k["lich_hop"] for k in nhom]))
    print("=== Từng lỗi ===")
    for ten_file, (_, kq, _) in ket_qua.items():
        in_loi(ten_file, kq)
    if chi_tiet:
        for ten_file, (_, _, thuc_te) in ket_qua.items():
            in_chi_tiet(ten_file, *thuc_te)
    return 0


def tu_kiem():
    """Tự kiểm so_sanh bằng dữ liệu giả, không chạy pipeline; trả về mã thoát."""
    nhan = {
        "tap": "thu",
        "viec_bat_buoc": [
            {"chu": "Lan", "tu_khoa": ["báo cáo"], "han": "thứ 6"},
            {"chu": "Nam", "tu_khoa": ["api"], "han": "ngày 5 tháng 11", "han_bi_thay": "thứ 3 tuần sau"},
        ],
        "viec_tuy_chon": [{"chu": "Hà", "tu_khoa": ["slide"]}],
        "viec_cam": [{"chu": "Tuấn", "tu_khoa": []}],
        "quyet_dinh": [{"tu_khoa": ["react"]}, {"tu_khoa": ["kpi"]}],
        "quyet_dinh_tuy_chon": [],
        "lich_hop": {"thoi_gian_chua": None, "noi_bang": None},
    }

    def viec(chu, mo_ta, han):
        return {"owner": chu, "task": mo_ta, "deadline": han}

    lan = viec("Lan", "gửi báo cáo", "thứ 6")
    nam = viec("Nam", "làm API đăng nhập", "ngày 5 tháng 11")
    ca = []

    kq = so_sanh_viec(nhan, [lan, nam])
    cs = chi_so_viec([kq])
    ca.append(("(i) khớp hoàn hảo cho P=R=1", cs["precision"] == 1.0 and cs["recall"] == 1.0))

    kq = so_sanh_viec(nhan, [lan])
    cs = chi_so_viec([kq])
    ca.append(("(ii) thiếu một việc nên recall giảm", cs["recall"] == 0.5 and kq["dem"][THIEU] == 1))

    kq = so_sanh_viec(nhan, [lan, dict(lan), nam])
    ca.append(("(iii) việc trùng cho TRÙNG", kq["dem"][TRUNG] == 1 and kq["dem"][DUNG] == 2))

    kq = so_sanh_viec(nhan, [lan, viec("Nam", "làm API", "thứ 3 tuần sau")])
    ca.append(("(iv) hạn cũ cho HẠN_BỊ_THAY", kq["dem"][HAN_BI_THAY] == 1 and kq["dem"][SAI_HAN] == 0))

    kq = so_sanh_viec(nhan, [lan, nam, viec("Tuấn", "viết test", None)])
    ca.append(("(v) chủ bị cấm cho CẤM", kq["dem"][CAM] == 1 and kq["dem"][GIA] == 0))

    kq = so_sanh_viec(nhan, [lan, nam, viec("Hà", "làm slide", None)])
    cs = chi_so_viec([kq])
    ca.append(("(vi) việc tùy chọn không giảm precision", cs["precision"] == 1.0 and kq["dem"][GIA] == 0))

    kq = so_sanh_viec(nhan, [viec("Lan", "gửi báo cáo", "trước thứ 6"), nam])
    ca.append(("(vii) hạn 'trước thứ 6' khớp nhãn 'thứ 6'", kq["dem"][DUNG] == 2))

    qd = so_sanh_quyet_dinh(nhan, [{"text": "Chốt dùng React và KPI tối thiểu 30 đơn"}])
    ca.append(("(viii) hai ý dính một quyết định chỉ khớp một",
               qd["khop"] == 1 and qd["bat_buoc"] == 2 and len(qd["thieu"]) == 1))

    tat_ca_dat = True
    for ten, dat in ca:
        print(f"{'ĐẠT' if dat else 'KHÔNG ĐẠT'} | {ten}")
        tat_ca_dat = tat_ca_dat and dat
    print(f"Tổng kết: {sum(1 for _, d in ca if d)}/{len(ca)} ca ĐẠT")
    return 0 if tat_ca_dat else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Đo chất lượng trích xuất so với nhãn tay.")
    parser.add_argument("--chi-tiet", action="store_true", help="in toàn bộ kết quả sinh ra")
    parser.add_argument("--tu-kiem", action="store_true", help="tự kiểm so_sanh, không chạy pipeline")
    tham_so = parser.parse_args()
    if tham_so.tu_kiem:
        sys.exit(tu_kiem())
    sys.exit(chay_do(tham_so.chi_tiet))