# Nhận diện hạn chót trong câu transcript đã làm sạch
import re


def tim_han_chot(van_ban):
    """Trích xuất hạn chót từ mệnh đề hoặc câu, có thể trả về nhiều giá trị trong cùng câu."""
    van_ban = van_ban.strip()
    if not van_ban:
        return []
    van_ban = re.sub(r"(?:,\s*)?(?:còn\s+)?(?:ai\s+có\s+ý\s+kiến\s+gì\s+không\?|có\s+ai\s+.*\bý\s+kiến\b.*\?|cảm\s+ơn.*)$", "", van_ban, flags=re.IGNORECASE)
    if re.match(r"^thứ\s+\d+\s+là\b", van_ban, flags=re.IGNORECASE):
        return []

    ket_qua = []
    for mau in [
        r"(?:deadline|hạn chót|chậm nhất|hạn)\s*(?:là|:)\s*([^,.]+?)(?:,|\.|$)",
        r"\b(?:trước|sớm hơn)\s+([^,.]+?)(?:,|\.|$)",
        r"\b(?:ngày\s+\d+\s+tháng\s+\d+|thứ\s+\d+\s+(?:tuần\s+(?:này|sau)|\w+)|thứ\s+\d+\s+tuần\s+(?:này|sau)|chủ nhật|cuối\s+tuần)\b([^,.]*?)(?:,|\.|$)",
    ]:
        for match in re.finditer(mau, van_ban, flags=re.IGNORECASE):
            if match.lastindex:
                gia_tri = match.group(1).strip()
            else:
                gia_tri = match.group(0).strip()
            gia_tri = re.sub(r"^(?:là|đó\s+là|đây\s+là)\s*", "", gia_tri, flags=re.IGNORECASE)
            gia_tri = gia_tri.replace(".", "").strip()
            if not gia_tri or gia_tri.lower() in {"là", "đây", "đó"}:
                continue
            if re.search(r"\b(?:điều này|ý kiến|có ai|đến|gặp|lúc)\b", gia_tri, flags=re.IGNORECASE):
                continue
            ket_qua.append(gia_tri)

    ket_qua = list(dict.fromkeys(ket_qua))
    return ket_qua
