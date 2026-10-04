# Script kiểm tra nhanh pipeline NLP trên file mẫu và bộ phát triển
import argparse
import json
import re
import sys
from pathlib import Path

from chay_nlp import chay_nlp
from dap_an import DAP_AN

sys.stdout.reconfigure(encoding="utf-8")

TUONG_DONG = {"người chủ trì": "người chủ trì", "mình": "người chủ trì", "tôi": "người chủ trì", "em": "người chủ trì"}
DONG_TU_HANH_DONG = (
    "làm", "update", "sửa", "fix", "viết", "gửi", "upload", "cập nhật",
    "phụ trách", "chạy", "test", "thiết kế", "hoàn thành", "nộp", "điều",
    "xong", "hỗ trợ", "nhớ", "thực hiện", "cố gắng", "gửi"
)
TU_MANG_Y_NGIA = ("làm", "update", "sửa", "fix", "viết", "gửi", "upload", "cập nhật", "chạy", "xong", "test", "giao")
TU_REJECT = {"làm", "để", "phụ trách", "xong", "test chung", "ai", "hôm", "nếu"}
TU_CHUC_NANG = {
    "mình", "tôi", "em", "anh", "chị", "bạn", "làm", "để", "sẽ", "phải",
    "cần", "này", "phần", "còn", "trước", "sau", "hôm", "ok",
}
TEN_CONG_TY = {"minh phát"}
TU_MANG_Y_NGIA = tuple(dict.fromkeys(TU_MANG_Y_NGIA + (
    "rà soát", "đối chiếu", "hoàn tất", "tổng hợp", "kiểm tra", "biên soạn",
)))
DANH_SACH_DONG_TU = tuple(
    sorted(set(DONG_TU_HANH_DONG + TU_MANG_Y_NGIA), key=len, reverse=True)
)


def chuan_hoa(text):
    """Chuẩn hóa chuỗi để so sánh không phân biệt hoa/thường, bỏ khoảng trắng thừa."""
    if text is None:
        return ""
    text = re.sub(r"\s+", " ", str(text).strip())
    return text.lower().strip()


def chuan_hoa_chu(owner, source_text=""):
    """Chuẩn hóa nguyên tên chủ việc, chỉ áp dụng bí danh khi khớp toàn bộ."""
    ten = chuan_hoa(owner)
    if ten in TEN_CONG_TY or re.search(r"\bcông ty\s+minh phát\b", ten):
        return ""
    if ten in TUONG_DONG and ten not in {"người chủ trì"}:
        hanh_dong = "|".join(
            re.escape(dong_tu)
            for dong_tu in sorted(TU_MANG_Y_NGIA, key=len, reverse=True)
        )
        chu_the = r"(?:mình|tôi|em)"
        if not re.search(
            rf"\b(?:{chu_the}\s+(?:sẽ|phải|cần)\s+(?:{hanh_dong})|"
            rf"để\s+{chu_the}\s+(?:{hanh_dong}))\b",
            chuan_hoa(source_text),
        ):
            return ""
        return TUONG_DONG[ten]
    if ten in TU_CHUC_NANG:
        return ""
    return TUONG_DONG.get(ten, ten)


def khop_nguyen_tu(text, phrase):
    """So khớp cụm nguyên vẹn, không phân biệt hoa/thường."""
    text = chuan_hoa(text)
    phrase = chuan_hoa(phrase)
    return bool(phrase and re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text))


def co_tu_hanh_dong(text):
    """Mệnh đề có ít nhất một động từ hành động, không chỉ là mảnh câu."""
    text = chuan_hoa(text)
    if not text:
        return False
    if len(text.split()) <= 2:
        return False
    return any(khop_nguyen_tu(text, tu) for tu in TU_MANG_Y_NGIA)


def task_hop_le(task_item, source_text=""):
    """Task hợp lệ phải mang nghĩa hành động, không phải tiêu đề hoặc từ đệm."""
    return not ly_do_task_khong_hop_le(task_item, source_text)


def ly_do_task_khong_hop_le(task_item, source_text=""):
    """Trả về các lý do task không hợp lệ theo đúng các điều kiện hiện tại."""
    ly_do = []
    if not task_item:
        return ["task rỗng"]
    owner = chuan_hoa_chu(task_item.get("owner"), source_text)
    task = chuan_hoa(task_item.get("task") or "")
    deadline = chuan_hoa(task_item.get("deadline") or "")
    if not owner or not task:
        return ["thiếu người phụ trách" if not owner else "thiếu mô tả việc"]
    if owner in {"", "để", "ok"}:
        ly_do.append(f"người phụ trách không hợp lệ: {task_item.get('owner')!r}")
    if task in TU_REJECT or task.split()[:2] == ["để"]:
        ly_do.append(f"mô tả việc thuộc nhóm từ/cụm bị loại: {task_item.get('task')!r}")
    if len(task.split()) < 3:
        ly_do.append(f"mô tả việc quá ngắn ({len(task.split())} từ)")
    if not co_tu_hanh_dong(task):
        ly_do.append("mô tả việc không có từ hành động được nhận diện")
    if deadline and re.fullmatch(r"(?:thứ\s+\d+|chủ nhật|ngày\s+\d+\s+tháng\s+\d+|tháng\s+\d+|cả\s+tuần)", deadline) is None and not re.search(r"(tuần|tháng|ngày|thứ|chủ nhật)", deadline):
        ly_do.append(f"hạn không khớp mẫu thời gian hiện tại: {task_item.get('deadline')!r}")
    return ly_do


def mo_ta_task(task):
    """Tạo mô tả gọn để in task thực tế theo dạng (người, việc, hạn)."""
    return (
        task.get("owner"),
        task.get("task"),
        task.get("deadline"),
    )


def mo_ta_cap(owner, deadline):
    return f"({json.dumps(owner, ensure_ascii=False)}, {json.dumps(deadline, ensure_ascii=False)})"


def la_cung_menh_de_liet_ke(tasks, cac_cau):
    """Chỉ cho phép lặp hạn khi cùng chủ và cùng mệnh đề liệt kê."""
    if not tasks:
        return False
    starts = {task.get("start") for task in tasks}
    if len(starts) != 1 or None in starts:
        return False
    cau = next((item for item in cac_cau if item.get("start") in starts), None)
    if cau is None:
        return False

    van_ban = chuan_hoa(cau.get("text") or cau.get("sach") or "")
    chu = {
        chuan_hoa_chu(task.get("owner"), van_ban)
        for task in tasks
    }
    if len(chu) != 1 or "" in chu:
        return False

    vi_tri_dong_tu = []
    for task in tasks:
        mo_ta = chuan_hoa(task.get("task") or "")
        match = next(
            (
                re.search(rf"(?<!\w){re.escape(dong_tu)}(?!\w)", van_ban)
                for dong_tu in DANH_SACH_DONG_TU
                if khop_nguyen_tu(mo_ta, dong_tu)
                and re.search(rf"(?<!\w){re.escape(dong_tu)}(?!\w)", van_ban)
            ),
            None,
        )
        if match is None:
            return False
        vi_tri_dong_tu.append(match.span())

    vi_tri_dong_tu.sort()
    for truoc, sau in zip(vi_tri_dong_tu, vi_tri_dong_tu[1:]):
        noi_tu = van_ban[truoc[1]:sau[0]]
        if re.search(r"(?:,|\b(?:và|với|cùng|đồng thời)\b)", noi_tu):
            return True
    return False


def kiem_tra_file(ten_file):
    """Kiểm tra một file transcript theo đáp án mẫu."""
    duong_dan = Path("data/transcripts") / ten_file
    with duong_dan.open(encoding="utf-8") as tep:
        cac_cau_goc = json.load(tep)
    ket_qua, _, _ = chay_nlp(duong_dan)
    dap_an = DAP_AN[ten_file]

    tasks = ket_qua.get("tasks", [])
    def cau_nguon(task):
        return next(
            (
                item.get("text") or item.get("sach") or ""
                for item in cac_cau_goc
                if item.get("start") == task.get("start")
            ),
            "",
        )

    tasks_hop_le = [
        task for task in tasks if task_hop_le(task, cau_nguon(task))
    ]
    ly_do_khong_dat = {"task": [], "decision": [], "next_meeting": []}
    ma_loi = {"task": [], "decision": [], "next_meeting": []}

    def ghi_loi(nhom, ma, ly_do):
        ma_loi[nhom].append(ma)
        ly_do_khong_dat[nhom].append(ly_do)

    ket_qua_task = {}
    for item in tasks_hop_le:
        owner = chuan_hoa_chu(item.get("owner"), cau_nguon(item))
        deadline = chuan_hoa(item.get("deadline"))
        ket_qua_task.setdefault(owner, []).append(deadline)

    ket_qua_metric = []
    for owner, han_mong_muon in dap_an["tasks"]:
        owner_key = chuan_hoa_chu(owner)
        if owner_key not in ket_qua_task:
            ket_qua_metric.append(False)
            ghi_loi(
                "task",
                "TASK_EXPECTED_OWNER_OR_DEADLINE_MISSING",
                f"thiếu cặp (người, hạn) mong đợi: {mo_ta_cap(owner, han_mong_muon)}; "
                f'việc thực tế của file: {[mo_ta_task(task) for task in tasks]!r}',
            )
            continue
        if han_mong_muon is None:
            ket_qua_metric.append(True)
            continue
        hop_le = any(
            khop_nguyen_tu(item, han_mong_muon)
            for item in ket_qua_task[owner_key]
            if item
        )
        ket_qua_metric.append(hop_le)
        if not hop_le:
            viec_cua_nguoi = [
                mo_ta_task(task)
                for task in tasks
                if chuan_hoa_chu(task.get("owner"), cau_nguon(task)) == owner_key
            ]
            ghi_loi(
                "task",
                "TASK_EXPECTED_OWNER_OR_DEADLINE_MISSING",
                f"thiếu cặp (người, hạn) mong đợi: {mo_ta_cap(owner, han_mong_muon)}; "
                f'việc thực tế của người này: {viec_cua_nguoi!r}; '
                f'việc thực tế của file: {[mo_ta_task(task) for task in tasks]!r}',
            )

    da_dung = set()
    for owner, tu_khoa in dap_an.get("required_task_descriptions", []):
        owner_key = chuan_hoa_chu(owner)
        match_index = next(
            (
                i
                for i, task in enumerate(tasks_hop_le)
                if i not in da_dung
                and chuan_hoa_chu(task.get("owner"), cau_nguon(task)) == owner_key
                and khop_nguyen_tu(task.get("task") or "", tu_khoa)
            ),
            None,
        )
        if match_index is None:
            ghi_loi(
                "task",
                "TASK_REQUIRED_DESCRIPTION_MISSING",
                f"thiếu việc của {owner!r} có từ khóa {tu_khoa!r}",
            )
        else:
            da_dung.add(match_index)

    for owner, tu_khoa, han_mong_muon in dap_an.get("required_task_deadlines", []):
        owner_key = chuan_hoa_chu(owner)
        task_match = next(
            (
                task
                for task in tasks_hop_le
                if chuan_hoa_chu(task.get("owner"), cau_nguon(task)) == owner_key
                and khop_nguyen_tu(task.get("task") or "", tu_khoa)
            ),
            None,
        )
        if task_match is None or not khop_nguyen_tu(
            task_match.get("deadline") or "", han_mong_muon
        ):
            ghi_loi(
                "task",
                "TASK_DEADLINE_MISMATCH_FOR_DESCRIPTION",
                f"hạn {han_mong_muon!r} chưa gắn đúng việc của {owner!r} có từ khóa {tu_khoa!r}",
            )

    for task in tasks:
        task_text = chuan_hoa(task.get("task") or "")
        for mo_ta_cam in dap_an.get("forbidden_task_descriptions", []):
            if khop_nguyen_tu(task_text, mo_ta_cam):
                ghi_loi(
                    "task",
                    "TASK_FORBIDDEN_DESCRIPTION_PRESENT",
                    f"mô tả việc nằm trong danh sách cấm của file mẫu: {task.get('task')!r}",
                )
        for cum_cam in dap_an.get("forbidden_task_phrases", []):
            if khop_nguyen_tu(task_text, cum_cam):
                ghi_loi(
                    "task",
                    "TASK_FORBIDDEN_PHRASE_PRESENT",
                    f"mô tả việc chứa cụm bị cấm trong file mẫu: {task.get('task')!r}",
                )
        for cum_cam in dap_an.get("forbidden_task_source_phrases", []):
            if khop_nguyen_tu(cau_nguon(task), cum_cam):
                ghi_loi(
                    "task",
                    "TASK_EXTRACTED_FROM_NON_ACTION_SOURCE",
                    f"task được trích từ câu không mang lời giao việc: {cum_cam!r}",
                )

    allowed_owners = {
        chuan_hoa_chu(owner)
        for owner, _ in dap_an["tasks"]
        if chuan_hoa_chu(owner)
    }
    for task in tasks:
        owner = chuan_hoa_chu(task.get("owner"), cau_nguon(task))
        if owner and owner not in allowed_owners:
            ghi_loi(
                "task",
                "TASK_UNEXPECTED_OWNER",
                f"chủ việc không có trong đáp án của file mẫu: {task.get('owner')!r}",
            )

    han_theo_gia_tri = {}
    for task in tasks:
        deadline = chuan_hoa(task.get("deadline") or "")
        if deadline:
            han_theo_gia_tri.setdefault(deadline, []).append(task)
    for deadline, cac_task in han_theo_gia_tri.items():
        if len(cac_task) > 1 and not la_cung_menh_de_liet_ke(cac_task, cac_cau_goc):
            ghi_loi(
                "task",
                "TASK_DEADLINE_REUSED_OUTSIDE_SHARED_LIST",
                f"hạn {deadline!r} gắn với nhiều việc không cùng chủ và cùng mệnh đề liệt kê: "
                f"{[mo_ta_task(task) for task in cac_task]!r}",
            )

    for task in tasks:
        ly_do_task = ly_do_task_khong_hop_le(task, cau_nguon(task))
        if ly_do_task:
            ghi_loi(
                "task",
                "TASK_INVALID_OUTPUT",
                f"task không hợp lệ {mo_ta_task(task)!r}: {'; '.join(ly_do_task)}",
            )

    so_quyet_dinh = len(ket_qua.get("decisions", []))
    quyet_dinh_dat = so_quyet_dinh >= dap_an["decision_count"]
    if not quyet_dinh_dat:
        ghi_loi(
            "decision",
            "DECISION_COUNT_BELOW_EXPECTATION",
            f"số quyết định thực tế {so_quyet_dinh} ít hơn yêu cầu {dap_an['decision_count']}"
        )

    next_time = chuan_hoa(ket_qua.get("next_meeting", {}).get("time")) if ket_qua.get("next_meeting") else ""
    next_meeting_time = dap_an.get("next_meeting_time")
    if next_meeting_time is None:
        lich_hop_dat = not next_time
    else:
        lich_hop_dat = (
            bool(next_time)
            and re.search(r"(?:thứ\s+\d+|chủ nhật|sáng|chiều|tối|giờ|tuần|ngày)", next_time)
            and khop_nguyen_tu(next_time, next_meeting_time)
        )
    if not lich_hop_dat:
        ghi_loi(
            "next_meeting",
            "NEXT_MEETING_TIME_MISSING_OR_MISMATCHED",
            f"không có thời gian họp tiếp theo hợp lệ; giá trị thực tế: {next_time!r}"
        )

    task_dat = (
        len(tasks_hop_le) >= 1
        and all(ket_qua_metric)
        and not ma_loi["task"]
    )

    return {
        "task": task_dat,
        "decision": quyet_dinh_dat,
        "next_meeting": lich_hop_dat,
        "reasons": ly_do_khong_dat,
        "codes": {
            category: list(dict.fromkeys(codes))
            for category, codes in ma_loi.items()
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Kiểm tra kết quả NLP trên transcript mẫu.")
    parser.add_argument("files", nargs="*", help="Tên transcript trong data/transcripts/")
    parser.add_argument(
        "--chi-tiet",
        action="store_true",
        help="In lý do đầy đủ, bao gồm nội dung việc, trên máy cục bộ.",
    )
    args = parser.parse_args()
    files = args.files or [
        "thu_nghiem.json",
        "thu_nghiem1.json",
        "thu_nghiem2.json",
        "phat_trien.json",
    ]
    for ten_file in files:
        if ten_file not in DAP_AN:
            parser.error(f"không có đáp án cho file: {ten_file}")
        ket_qua = kiem_tra_file(ten_file)
        codes = [
            code
            for category in ("task", "decision", "next_meeting")
            for code in ket_qua["codes"][category]
        ]
        if all(ket_qua[key] for key in ("task", "decision", "next_meeting")):
            codes.append("OK")
        if not args.chi_tiet:
            print(f"{ten_file}: {', '.join(codes)}")
            continue
        print(f"{ten_file}:")
        for ten_muc, khoa in (
            ("Người phụ trách + hạn chót", "task"),
            ("Quyết định", "decision"),
            ("Lịch họp tiếp theo", "next_meeting"),
        ):
            dat = ket_qua[khoa]
            print(f"  - {ten_muc}: {'ĐẠT' if dat else 'KHÔNG ĐẠT'}")
            if not dat:
                for ly_do in ket_qua["reasons"][khoa]:
                    print(f"    Lý do: {ly_do}")


if __name__ == "__main__":
    main()
