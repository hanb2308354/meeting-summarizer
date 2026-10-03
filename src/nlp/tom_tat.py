# Tóm tắt nội dung chính của cuộc họp bằng TextRank + điểm cộng
import re
import sys
import time
from pathlib import Path

import networkx as nx
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from doc_transcript import doc_transcript
from tien_xu_ly import tien_xu_ly

sys.stdout.reconfigure(encoding="utf-8")

SO_CAU_TOI_THIEU = 2
SO_CAU_TOI_DA = 5
DIEM_BO_SUNG = {
    "chốt": 0.35,
    "thống nhất": 0.35,
    "quyết định": 0.4,
    "đồng ý": 0.3,
    "%": 0.15,
    "tỷ": 0.15,
    "hôm nay": 0.1,
    "mục tiêu": 0.15,
    "tối thiểu": 0.15,
}


def chon_cau_ung_vien(cac_cau):
    """Lọc ra các câu có giá trị cho việc tóm tắt, bỏ xã giao và câu quá ngắn."""
    ket_qua = []
    for cau in cac_cau:
        text = cau["sach"].strip()
        if cau["xa_giao"]:
            continue
        if len(text.split()) < 4:
            continue
        ket_qua.append(cau)
    return ket_qua


def phat_diem_bo_sung(cau):
    """Cộng điểm cho câu có yếu tố quan trọng của cuộc họp."""
    text = cau["sach"].lower()
    diem = 0.0
    for tu_khoa, gia_tri in DIEM_BO_SUNG.items():
        if tu_khoa in text:
            diem += gia_tri
    if re.search(r"\d+%|\d+\s+triệu|\d+\s+tỷ|\d+\s+đơn|\d+\s+giờ", cau["sach"], flags=re.IGNORECASE):
        diem += 0.15
    if re.search(r"\b(?:bạn|anh|chị|mình|mọi người)\b", cau["sach"], flags=re.IGNORECASE):
        diem += 0.1
    return diem


def tom_tat(cac_cau):
    """Tóm tắt văn bản bằng TextRank trên ma trận tương đồng cosine."""
    ung_vien = chon_cau_ung_vien(cac_cau)
    if len(ung_vien) <= 2:
        return " ".join(cau["sach"] for cau in ung_vien)

    texts = [cau["sach"] for cau in ung_vien]
    tfidf = TfidfVectorizer(lowercase=True, token_pattern=r"(?u)\b\w+\b")
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
        scores = {i: 1.0 / len(ung_vien) for i in range(len(ung_vien))}
    else:
        scores = nx.pagerank(graph, weight="weight")

    for i, cau in enumerate(ung_vien):
        scores[i] += phat_diem_bo_sung(cau)

    so_cau = min(SO_CAU_TOI_DA, max(SO_CAU_TOI_THIEU, int(round(len(ung_vien) * 0.3))))
    selected = sorted(range(len(ung_vien)), key=lambda idx: scores[idx], reverse=True)[:so_cau]
    selected = sorted(selected, key=lambda idx: ung_vien[idx]["start"])

    ket_qua = []
    for idx in selected:
        text = ung_vien[idx]["sach"]
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
