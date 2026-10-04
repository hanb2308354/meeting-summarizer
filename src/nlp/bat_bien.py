# Bất biến cho mô tả việc (task) trong bộ kiểm thử NLP.
# Chỉ chứa hằng số và một hàm thuần, không import file khác của dự án.
import re

TU_CAM_MO_DAU = (
    "lại",
    "xong",
    "để",
    "với",
    "và",
    "cho",
    "nữa",
    "thì",
    "mà",
    "nên",
    "rồi",
    "luôn",
)

DAU_CAU_THUA = (".", ",", ";", ":")

CUM_CHI_HAN = (
    "chậm nhất là",
    "hạn chót là",
    "deadline là",
    "trước thứ",
    "trước ngày",
)


def kiem_bat_bien_task(task):
    """Nhận dict việc (có task, deadline), trả về danh sách lý do vi phạm."""
    ly_do = []
    if not isinstance(task, dict):
        return ["việc không phải dict"]
    mo_ta_goc = task.get("task") or ""
    han_goc = task.get("deadline") or ""
    mo_ta = re.sub(r"\s+", " ", str(mo_ta_goc).strip()).lower().strip()
    han = re.sub(r"\s+", " ", str(han_goc).strip()).lower().strip()
    if not mo_ta:
        return ["thiếu mô tả việc"]
    tu_dau = mo_ta.split()[0]
    if tu_dau in TU_CAM_MO_DAU:
        ly_do.append(f"mô tả bắt đầu bằng từ cấm: {tu_dau!r}")
    mo_ta_goc_strip = str(mo_ta_goc).strip()
    if mo_ta_goc_strip[0] in DAU_CAU_THUA or mo_ta_goc_strip[-1] in DAU_CAU_THUA:
        ly_do.append("mô tả bắt đầu hoặc kết thúc bằng dấu câu thừa")
    if ".," in str(mo_ta_goc) or ",." in str(mo_ta_goc):
        ly_do.append("mô tả chứa cụm dấu câu '.,' hay ',.'")
    if han:
        if han in mo_ta:
            ly_do.append(f"mô tả chứa nguyên cụm deadline {han_goc!r}")
        for cum in CUM_CHI_HAN:
            if cum in mo_ta:
                ly_do.append(f"mô tả chứa cụm chỉ hạn {cum!r}")
    return ly_do
