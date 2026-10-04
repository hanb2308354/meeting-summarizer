# Vết trích xuất: chỉ ghi nhận, không làm đổi kết quả trích xuất.
VET = []
_BAT = False


def bat_vet():
    """Bật chế độ ghi vết."""
    global _BAT
    _BAT = True


def ghi_vet(ma_quy_tac, stt_cau, noi_dung, ket_qua):
    """Ghi một dòng vết khi đã bật; khi chưa bật thì không làm gì."""
    if not _BAT:
        return
    VET.append(
        {
            "ma": ma_quy_tac,
            "stt": stt_cau,
            "noi_dung": noi_dung,
            "ket_qua": ket_qua,
        }
    )


def lay_vet():
    """Trả về danh sách vết đã ghi."""
    return VET
