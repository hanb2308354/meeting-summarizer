# Tóm tắt nội dung chính của cuộc họp: TextRank + điểm cộng/phạt + chọn câu kiểu MMR
import re
import sys
import time
from pathlib import Path

import networkx as nx
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from doc_transcript import doc_transcript
from tien_xu_ly import tien_xu_ly
from tu_dien import DIEM_BO_SUNG

sys.stdout.reconfigure(encoding="utf-8")

# Hằng số của riêng tom_tat.py (cố ý không đụng tu_dien.py để dễ hoàn tác)
TY_LE_TOM_TAT = 0.4        # số câu chọn ~ 40% số câu ứng viên
SO_CAU_TOI_THIEU = 4
SO_CAU_TOI_DA = 7
HE_SO_TRUNG_LAP = 0.5      # MMR: càng cao càng tránh chọn câu giống câu đã chọn
DIEM_CAU_MO_DAU = 0.3      # câu ứng viên đầu tiên thường nêu mục đích buổi họp
PHAT_GIAO_VIEC = 0.2       # câu thuần giao việc: đã có ở mục "Việc cần làm"
TU_NOI_DUNG = ("nguyên nhân", "vì vậy", "tập trung", "vấn đề", "kết quả", "budget", "ngân sách")
PHAT_LICH_HOP = 0.5        # câu nói về buổi họp sau: đã có ở mục "Cuộc họp tiếp theo"
PHAT_DA_CO = 0.3           # câu trùng với mục Quyết định/Việc (nếu truyền vào)
TOI_DA_TU_CAU = 40         # câu dài hơn thì tách ở dấu ; hoặc cắt ở dấu , gần ngưỡng nhất
TOI_DA_TU_TOM_TAT = 150    # tổng số từ tối đa của bản tóm tắt
MO_DAU = re.compile(r"^(?:đầu tiên|tiếp theo|thứ\s+\d+|cuối cùng|ngoài ra|bên cạnh đó)\s*(?:là)?\s*[,:]?\s*", re.I)
VE_THI = re.compile(r"^về\s+(?P<chu_de>[^,]{2,30}?)\s+thì\s+", re.I)
DUOI_CUT = re.compile(r"\s*,?\s*cuối cùng là\s+\S+(?:\s+\S+){0,2}\s*$", re.I)

def cat_cau_dai(text, toi_da=TOI_DA_TU_CAU):
    """Câu quá dài (Whisper không đặt chấm): cắt ở dấu ; hoặc , cuối cùng trước ngưỡng."""
    tu = text.split()
    if len(tu) <= toi_da:
        return text
    dau = " ".join(tu[:toi_da])
    vi_tri = max(dau.rfind(";"), dau.rfind(","))
    if vi_tri >= len(dau) // 2:
        dau = dau[:vi_tri]
    return dau.rstrip(" ,;")

def rut_gon(text):
    """Gọt từ nối đầu câu, đuôi bị Whisper cắt, đại từ 'mình'; đưa chủ đề lên đầu."""
    t = DUOI_CUT.sub("", text.strip())
    chu_de = None
    m = VE_THI.match(t)
    if m:
        chu_de = m.group("chu_de").strip()
        t = t[m.end():]
    t = MO_DAU.sub("", t)
    t = re.sub(r"\b(?:bên|của)\s+mình\b", "công ty", t)
    t = re.sub(r"\bmình\s+(?=(?:sẽ|đã|định|có|họp)\b)", "", t, flags=re.I)
    t = re.sub(r",\s*vì vậy,\s*", ". Vì vậy, ", t)
    t = re.sub(r"\b(?:lúc đầu|ban đầu)\s+", "", t)
    t = re.sub(r"\s+", " ", t).strip(" ,;")
    if chu_de:
        t = f"{chu_de.capitalize()}: {t}"
    t = cat_cau_dai(t)
    t = t[0].upper() + t[1:] if t else t
    return t if t.endswith(".") else t + "."

MAU_GIAO_VIEC = re.compile(
    r"\b(?:sẽ|phải)\s+(?:làm|gửi|viết|sửa|test|update|cập nhật|nộp|hoàn thành"
    r"|chuẩn bị|liên hệ|chạy|thiết kế|thực hiện)\b"
    r"|phụ trách|giao cho|chậm nhất"
    r"|trước\s+(?:thứ|ngày|chủ nhật)"
    r"|để\s+(?:mình|tôi|em)\s+(?:sẽ\s+)?làm",
    flags=re.IGNORECASE,
)
MAU_LICH_HOP = re.compile(
    r"họp\s+(?:lại|tiếp|lần\s+sau)\b"
    r"|(?:buổi|cuộc)\s+họp\s+(?:sau|tiếp)"
    r"|buổi\s+gặp\s+(?:kế\s+)?tiếp"
    r"|\bhọp\b.*(?:\d+\s*(?:giờ|h)\b|thứ\s+\d|chủ nhật|tuần sau|tuần tới)"
    r"|google\s+meet|phòng\s+họp",
    flags=re.IGNORECASE,
)

MAU_TACH_CAU = re.compile(r"(?<=[.!?])(?:\s+|(?=[A-ZÀ-ỸĐ]))")
MAU_XA_GIAO_THEM = re.compile(
    r"nghe rõ không|bắt đầu\s+(?:buổi\s+)?(?:họp|cuộc họp)|có ai\s+(?:muốn|có)"
    r"|chắc là đủ rồi|cảm ơn|không tính thành việc", re.I)
MAU_GIU_LAI = re.compile(r"quyết định|thống nhất|đồng ý", re.I)


def tach_thanh_cau(cac_cau):
    """Tách mỗi đoạn Whisper thành từng câu; câu quá dài thì tách thêm ở dấu chấm phẩy."""
    ket_qua = []
    for cau in cac_cau:
        manh = [m.strip() for m in MAU_TACH_CAU.split(cau["sach"]) if m and m.strip()]
        manh_moi = []
        for m in manh:
            if len(m.split()) > TOI_DA_TU_CAU and ";" in m:
                manh_moi.extend(p.strip() for p in m.split(";") if p.strip())
            else:
                manh_moi.append(m)
        for k, m in enumerate(manh_moi):
            moi = dict(cau)
            moi["sach"] = m
            moi["start"] = cau["start"] + k * 1e-3
            ket_qua.append(moi)
    return ket_qua

def chon_cau_ung_vien(cac_cau, so_tu_toi_thieu=7):
    """Lọc ra các câu có giá trị cho việc tóm tắt, bỏ xã giao và câu quá ngắn."""
    ket_qua = []
    for cau in cac_cau:
        text = cau["sach"].strip()
        if cau["xa_giao"] or MAU_XA_GIAO_THEM.search(text):
            continue
        if len(text.split()) < so_tu_toi_thieu:
            continue
        ket_qua.append(cau)
    return ket_qua


def phat_diem_bo_sung(cau):
    """Cộng điểm cho câu có yếu tố nội dung quan trọng của cuộc họp."""
    text = cau["sach"].lower()
    diem = 0.0
    for tu_khoa, gia_tri in DIEM_BO_SUNG.items():
        if tu_khoa in text:
            diem += gia_tri
    if re.search(r"\d+%|\d+\s+triệu|\d+\s+tỷ|\d+\s+đơn|\d+\s+giờ", cau["sach"], flags=re.IGNORECASE):
        diem += 0.15
    if any(tu in text for tu in TU_NOI_DUNG):
        diem += 0.2
    return diem


def diem_phat(cau, cau_da_co):
    """Trừ điểm câu đã có chỗ riêng ở các mục khác của bản tóm tắt."""
    text = cau["sach"]
    phat = 0.0
    if MAU_GIAO_VIEC.search(text):
        phat += PHAT_GIAO_VIEC
    if MAU_LICH_HOP.search(text):
        phat += PHAT_LICH_HOP
    chuan = text.lower().strip(" .,;")
    for da_co in cau_da_co:
        mau = da_co.lower().strip(" .,;")
        if mau and (mau in chuan or chuan in mau):
            phat += PHAT_DA_CO
            break
    return phat


def tom_tat(cac_cau, cau_da_co=()):
    """Tóm tắt văn bản. cau_da_co: các chuỗi đã nằm ở mục Quyết định/Việc (tùy chọn)."""
    cac_cau = tach_thanh_cau(cac_cau)
    ung_vien = chon_cau_ung_vien(cac_cau)
    if len(ung_vien) < SO_CAU_TOI_THIEU:
        ung_vien = chon_cau_ung_vien(cac_cau, 4)
    for mau in (MAU_LICH_HOP, MAU_GIAO_VIEC):
        con_lai = [c for c in ung_vien
                   if not mau.search(c["sach"]) or MAU_GIU_LAI.search(c["sach"])]
        if len(con_lai) >= SO_CAU_TOI_THIEU:
            ung_vien = con_lai
    if len(ung_vien) <= SO_CAU_TOI_THIEU:
        return " ".join(rut_gon(cau["sach"]) for cau in ung_vien)
    texts = [cau["sach"] for cau in ung_vien]
    tfidf = TfidfVectorizer(lowercase=True, token_pattern=r"(?u)\b\w+\b",
                            ngram_range=(1, 2), sublinear_tf=True)
    matrix = tfidf.fit_transform(texts)
    similarity = cosine_similarity(matrix)

    graph = nx.Graph()
    for i in range(len(ung_vien)):
        graph.add_node(i)
    for i in range(len(ung_vien)):
        for j in range(i + 1, len(ung_vien)):
            if similarity[i, j] > 0:
                graph.add_edge(i, j, weight=float(similarity[i, j]))

    if graph.number_of_edges() == 0:
        scores = {i: 1.0 for i in range(len(ung_vien))}
    else:
        scores = nx.pagerank(graph, weight="weight")
        cao_nhat = max(scores.values()) or 1.0
        scores = {i: v / cao_nhat for i, v in scores.items()}

    for i, cau in enumerate(ung_vien):
        scores[i] += phat_diem_bo_sung(cau) - diem_phat(cau, cau_da_co)
    scores[0] += DIEM_CAU_MO_DAU

    so_cau = min(SO_CAU_TOI_DA, max(SO_CAU_TOI_THIEU, int(round(len(ung_vien) * TY_LE_TOM_TAT))))
    so_cau = min(so_cau, len(ung_vien))

    # Chọn lần lượt câu điểm cao nhưng không giống các câu đã chọn (MMR), dừng khi đủ số từ
    da_chon = []
    tong_tu = 0
    con_lai = list(range(len(ung_vien)))
    while con_lai and len(da_chon) < so_cau:
        def gia_tri(i):
            trung = max((similarity[i, j] for j in da_chon), default=0.0)
            return scores[i] - HE_SO_TRUNG_LAP * trung
        tot_nhat = max(con_lai, key=gia_tri)
        con_lai.remove(tot_nhat)
        so_tu = min(len(ung_vien[tot_nhat]["sach"].split()), TOI_DA_TU_CAU)
        if da_chon and tong_tu + so_tu > TOI_DA_TU_TOM_TAT:
            continue
        da_chon.append(tot_nhat)
        tong_tu += so_tu

    selected = sorted(da_chon, key=lambda idx: ung_vien[idx]["start"])

    ket_qua = []
    for idx in selected:
        text = rut_gon(ung_vien[idx]["sach"])
        if not ket_qua or not re.search(rf"^{re.escape(text[:20])}", ket_qua[-1]):
            ket_qua.append(text)
    return " ".join(ket_qua)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Cách dùng: python src/nlp/tom_tat.py <đường dẫn file transcript JSON>")

    duong_dan = Path(sys.argv[1])
    if not duong_dan.exists():
        sys.exit(f"Không tìm thấy file: {duong_dan}")

    bat_dau = time.time()
    ket_qua = tom_tat(tien_xu_ly(doc_transcript(duong_dan)))
    print(ket_qua)
    print(f"\nThời gian: {time.time() - bat_dau:.2f} giây")