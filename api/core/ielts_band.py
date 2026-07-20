"""IELTS 原始分 → 9 分制换算（后端侧）。

与前端 `frontend/src/utils/ielts_band.ts` 保持同一张官方对照表（剑桥 Academic）。
仅用于「全套」40 题卷的服务端聚合（管理员学情统计需要在后端按 band 求均值，
单靠前端逐题换算无法做全站聚合）。两处改动务必同步。
"""

# (min_raw, band) —— 从高到低，第一个满足 correct >= min_raw 的即为 band。
LISTENING_BANDS = [
    (39, 9.0), (37, 8.5), (35, 8.0), (32, 7.5), (30, 7.0),
    (26, 6.5), (23, 6.0), (18, 5.5), (16, 5.0), (13, 4.5),
    (10, 4.0), (8, 3.5), (6, 3.0), (4, 2.5), (2, 2.0), (1, 1.0),
]

READING_BANDS = [
    (39, 9.0), (37, 8.5), (35, 8.0), (33, 7.5), (30, 7.0),
    (27, 6.5), (23, 6.0), (19, 5.5), (15, 5.0), (13, 4.5),
    (10, 4.0), (8, 3.5), (6, 3.0), (4, 2.5), (2, 2.0), (1, 1.0),
]


def raw_to_band(skill, correct, total):
    """把全套卷答对题数换算成 9 分制；total < 38 视为非全套 → 返回 None（不计入）。"""
    if total is None or total < 38:
        return None
    table = READING_BANDS if skill == 'reading' else LISTENING_BANDS
    for min_raw, band in table:
        if correct >= min_raw:
            return band
    return 1.0 if correct > 0 else 0.0


def round_ielts_overall(mean):
    """四科均分 → 雅思官方总分舍入：<.25 舍、[.25,.75) 取 .5、>=.75 进位。"""
    clamped = max(0.0, min(9.0, mean))
    floor = int(clamped)
    frac = clamped - floor
    if frac < 0.25:
        return float(floor)
    if frac < 0.75:
        return floor + 0.5
    return float(floor + 1)
