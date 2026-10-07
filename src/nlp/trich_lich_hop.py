# Nhận diện và trích xuất lịch họp tiếp theo từ transcript đã làm sạch
import re

from vet import ghi_vet


# Câu nhắc tới buổi họp/gặp sau: "họp tiếp theo", "buổi họp kế tiếp", "buổi gặp kế tiếp",
# "lần họp tới", "lần sau mình gặp"
MAU_NHAC_LICH_HOP = re.compile(
    r"họp\s+(?:tiếp theo|kế\s+tiếp|sau|tiếp)"
    r"|buổi\s+họp\s+(?:tiếp theo|sau)"
    r"|\b(?:buổi|cuộc|lần)\s+(?:họp|gặp)\s+(?:tiếp\s+theo|kế\s+tiếp|sau|tới)\b"
    r"|\bhọp\s+lần\s+(?:tới|sau|tiếp\s+theo)\b"
    r"|\blần\s+sau\s+(?:(?:mình|chúng\s+ta|cả\s+nhóm)\s+)?(?:gặp|họp)\b",
    flags=re.IGNORECASE,
)


def la_lich_hop(van_ban):
    """Nhận diện câu/chữ về lịch họp tiếp theo."""
    if re.search(r"\b(?:bắt đầu|mở đầu|chào mọi người).*\b(?:buổi\s+họp|họp\s+giao\s+ban)\b", van_ban, flags=re.IGNORECASE):
        ghi_vet("LOAI_LICH_HOP_MO_DAU", None, van_ban, "loại")
        return False
    if MAU_NHAC_LICH_HOP.search(van_ban):
        ghi_vet("GIU_LICH_HOP", None, van_ban, "giữ")
        return True
    if re.search(r"\b(?:tối|sáng|chiều|buổi|ngày)\s+.*(?:họp|meeting)\b", van_ban, flags=re.IGNORECASE) and re.search(r"\b(?:lúc|tại|online|Google Meet|thứ)\b", van_ban, flags=re.IGNORECASE):
        ghi_vet("GIU_LICH_HOP", None, van_ban, "giữ")
        return True
    ghi_vet("LOAI_KHONG_LICH_HOP", None, van_ban, "loại")
    return False


# Mốc nhắc tới buổi họp tiếp theo: "họp tiếp theo", "buổi họp sau", "lịch họp lần tới" ...
# kèm từ nối tùy chọn ("chốt là", "sẽ tổ chức vào") rồi tới phần giá trị
MAU_MOC_LICH = re.compile(
    r"(?:(?:buổi|cuộc|lần)\s+(?:họp|gặp)\s+(?:tiếp\s+theo|kế\s+tiếp|sau|tới)"
    r"|(?:buổi\s+)?họp\s+(?:tiếp\s+theo|kế\s+tiếp|sau)"
    r"|(?:lịch\s+)?họp\s+lần\s+(?:tới|sau)"
    r"|lần\s+sau\s+(?:(?:mình|chúng\s+ta|cả\s+nhóm)\s+)?(?:gặp|họp)(?:\s+(?:nhau|lại))?"
    r"|lịch\s+họp(?:\s+(?:tiếp\s+theo|kế\s+tiếp|sau|tới))?)"
    r"(?:\s+(?:chốt|dự\s+kiến|sẽ\s+tổ\s+chức|sẽ\s+diễn\s+ra|sẽ))?"
    r"\s*(?:là|vào|:)?\s*(?P<gia_tri>.*?)(?:\.(?=\s|$)|$)",
    flags=re.IGNORECASE,
)

# Mẫu dự phòng: lấy từ "tối/sáng/chiều/buổi" tới hết câu (không dừng ở dấu phẩy đầu,
# vì địa điểm thường đứng sau dấu phẩy: "thứ Năm lúc 15 giờ 30, phòng B.204")
MAU_THOI_GIAN_DU_PHONG = re.compile(
    r"\b(?:tối|sáng|chiều|buổi)\s+.*?(?:\.(?=\s|$)|$)",
    flags=re.IGNORECASE,
)

# Câu liền sau chỉ được coi là địa điểm khi chính nó mở đầu như một câu nói về nơi họp
# ("Họp online trên Google Meet.", "Địa điểm là phòng họp A."), không phải câu bất kỳ có chữ "ở/tại"
MAU_CAU_DIA_DIEM = re.compile(
    r"^\s*(?:họp\s+)?(?:địa\s+điểm|tại|ở|trên|online|trực\s+tuyến|phòng|hội\s+trường"
    r"|google\s+meet|zoom|teams|room)\b",
    flags=re.IGNORECASE,
)
SO_TU_DIA_DIEM_TOI_DA = 10

# Lịch bị hủy hoặc chưa chốt: coi như không có lịch họp
MAU_LICH_CHUA_CHOT = re.compile(
    r"\b(?:thông\s+báo\s+lại|báo\s+lại\s+sau|chưa\s+(?:chốt|có\s+lịch|biết|rõ)|(?:bị\s+)?hủy)\b",
    flags=re.IGNORECASE,
)

# Tách "<thời gian> [tại|ở] <địa điểm>" kể cả khi không có dấu phẩy;
# "online ..." và "phòng ..." giữ nguyên chữ đầu vì chính là địa điểm
MAU_TACH_DIA_DIEM = re.compile(
    r"^(?P<tg>\S.*?)(?:\s*,\s*|\s+)"
    r"(?:(?:tại|ở)\s+(?P<dd1>\S.*)|(?P<dd2>(?:online|phòng|hội\s+trường)\b.*))$",
    flags=re.IGNORECASE,
)


def tach_thoi_gian_dia_diem(gia_tri):
    """Trả (thời gian, địa điểm hoặc None) từ phần giá trị sau mốc 'họp tiếp theo'."""
    gia_tri = gia_tri.strip().rstrip(",. ")
    khop = MAU_TACH_DIA_DIEM.match(gia_tri)
    if not khop:
        return gia_tri, None
    dia_diem = (khop.group("dd1") or khop.group("dd2")).strip().rstrip(",. ")
    return khop.group("tg").strip().rstrip(",. "), dia_diem


def lay_lich_hop(cac_cau):
    """Trích xuất thời gian và địa điểm của buổi họp tiếp theo."""
    for i, cau in enumerate(cac_cau):
        text = cau["sach"]
        stt_cau = cau.get("stt", None)
        if not la_lich_hop(text):
            ghi_vet("LOAI_KHONG_LICH_HOP", stt_cau, text, "loại")
            continue
        ghi_vet("GIU_LICH_HOP", stt_cau, text, "giữ")
        if MAU_LICH_CHUA_CHOT.search(text):
            ghi_vet("LOAI_LICH_HOP_CHUA_CHOT", stt_cau, text, "loại: lịch bị hủy/chưa chốt")
            continue
        thoi_gian = None
        dia_diem = None

        match = MAU_MOC_LICH.search(text)
        if match:
            thoi_gian, dia_diem = tach_thoi_gian_dia_diem(match.group("gia_tri"))
            ghi_vet("GAN_THOI_GIAN_LICH_HOP", stt_cau, match.group("gia_tri"), f"gắn {thoi_gian}")
            if dia_diem:
                ghi_vet("GAN_DIA_DIEM_LICH_HOP", stt_cau, match.group("gia_tri"), f"gắn {dia_diem}")

        if not thoi_gian:
            match = MAU_THOI_GIAN_DU_PHONG.search(text)
            if match:
                thoi_gian, dia_diem = tach_thoi_gian_dia_diem(match.group(0))
                ghi_vet("GAN_THOI_GIAN_LICH_HOP", stt_cau, match.group(0), f"gắn {thoi_gian}")

        if dia_diem is None and i + 1 < len(cac_cau):
            text_tiep = cac_cau[i + 1]["sach"]
            stt_tiep = cac_cau[i + 1].get("stt", None)
            if MAU_CAU_DIA_DIEM.match(text_tiep):
                dia_diem = text_tiep.strip().rstrip(".")
                dia_diem = re.sub(r"^(?:họp\s+)?(?:địa\s+điểm\s*(?:là|:)?\s*)?(?:tại|ở)?\s*", "", dia_diem, flags=re.IGNORECASE)
                dia_diem = dia_diem.strip()
                if len(dia_diem.split()) > SO_TU_DIA_DIEM_TOI_DA:
                    ghi_vet("LOAI_DIA_DIEM_CAU_DAI", stt_tiep, text_tiep, "loại: câu liền sau quá dài để là địa điểm")
                    dia_diem = None
                else:
                    ghi_vet("GAN_DIA_DIEM_LICH_HOP", stt_tiep, text_tiep, f"gắn {dia_diem}")

        if thoi_gian or dia_diem:
            ghi_vet("TAO_LICH_HOP", stt_cau, text, "giữ")
            return {
                "time": thoi_gian,
                "place": dia_diem,
                "start": cau["start"],
            }
        ghi_vet("LOAI_LICH_HOP_THIEU", stt_cau, text, "loại")
    return None