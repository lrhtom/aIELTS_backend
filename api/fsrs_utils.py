"""
FSRS-4.5 间隔重复算法 —— 纯 Python 实现，无外部依赖
参考：https://github.com/open-spaced-repetition/fsrs4anki/wiki/The-Algorithm
"""
import math
from datetime import datetime, timedelta, timezone

# ── FSRS-4.5 默认权重 ─────────────────────────────────────────────────────
W = [
    0.4072, 1.1829, 3.1262, 15.4722,   # w[0-3] 新卡四个评分的初始稳定性
    7.2102,                              # w[4]  初始难度基准（评分=3 时）
    0.5316,                              # w[5]  初始难度调节斜率
    1.0651,                              # w[6]  难度变化系数
    0.0589,                              # w[7]  难度均值回归权重
    1.4330,                              # w[8]  回忆稳定性增益（指数因子）
    0.1544,                              # w[9]  回忆稳定性 S 指数
    1.0070,                              # w[10] 回忆稳定性 R 指数
    1.9741,                              # w[11] 遗忘稳定性基础
    0.1000,                              # w[12] 遗忘稳定性难度指数
    0.2975,                              # w[13] 遗忘稳定性 S 指数
    0.2414,                              # w[14] 遗忘稳定性 R 指数
    0.2047,                              # w[15] Hard 惩罚因子
    2.9898,                              # w[16] Easy 奖励因子
    0.5100,                              # w[17] 短期稳定性调节系数
    0.0, 0.0, 0.0,                       # w[18-20] 未使用
]

# 遗忘曲线衰减参数：R(t,S) = (1 + FACTOR * t / S) ^ DECAY
DECAY = -0.5
FACTOR = 0.9 ** (1.0 / DECAY) - 1      # ≈ 0.2346

# ── 状态常量 ──────────────────────────────────────────────────────────────
NEW        = 0
LEARNING   = 1
REVIEW     = 2
RELEARNING = 3


# ── 核心公式 ──────────────────────────────────────────────────────────────

def _retrievability(elapsed: float, s: float) -> float:
    """当前可提取性 R（0-1）"""
    if s <= 0:
        return 0.0
    return (1.0 + FACTOR * elapsed / s) ** DECAY


def _init_stability(rating: int) -> float:
    return max(W[rating - 1], 0.1)


def _init_difficulty(rating: int) -> float:
    d = W[4] - math.exp(W[5] * (rating - 1)) + 1
    return min(max(d, 1.0), 10.0)


def _next_difficulty(d: float, rating: int) -> float:
    """难度随评分更新，并向最优难度均值回归"""
    raw = d - W[6] * (rating - 3)
    # 均值回归（向 Easy 状态下的初始难度靠拢）
    opt = _init_difficulty(4)
    reverted = W[7] * opt + (1 - W[7]) * raw
    return min(max(reverted, 1.0), 10.0)


def _short_term_stability(s: float, rating: int) -> float:
    """学习/重学阶段的短期稳定性调整"""
    return max(s * math.exp(W[17] * (rating - 3 + W[18])), 0.1)


def _recall_stability(d: float, s: float, r: float, rating: int) -> float:
    """成功回忆后的稳定性增长"""
    hard_penalty = W[15] if rating == 2 else 1.0
    easy_bonus   = W[16] if rating == 4 else 1.0
    gain = (
        math.exp(W[8]) * (11 - d) * (s ** -W[9])
        * (math.exp((1 - r) * W[10]) - 1)
        * hard_penalty * easy_bonus
    )
    return max(s * (gain + 1.0), 0.1)


def _forget_stability(d: float, s: float, r: float) -> float:
    """遗忘后的稳定性（重新学习起点）"""
    return max(
        W[11] * (d ** -W[12]) * ((s + 1) ** W[13] - 1) * math.exp((1 - r) * W[14]),
        0.1,
    )


# ── 公开接口 ──────────────────────────────────────────────────────────────

def fsrs_schedule(card: dict, rating: int, now: datetime) -> dict:
    """
    给定当前卡片状态和本次评分，返回新的卡片状态。

    参数
    ----
    card    : dict，字段：state, stability, difficulty, reps, lapses, last_review(ISO str 或 None)
    rating  : int (1=Again / 2=Hard / 3=Good / 4=Easy)
    now     : timezone-aware datetime

    返回
    ----
    dict，字段：due(datetime), stability, difficulty, elapsed_days,
               scheduled_days, reps, lapses, state
    """
    if rating not in (1, 2, 3, 4):
        raise ValueError(f'rating 必须为 1-4，收到：{rating}')

    state   = int(card.get('state', 0))
    s       = float(card.get('stability') or 0)
    d       = float(card.get('difficulty') or 0)
    reps    = int(card.get('reps') or 0)
    lapses  = int(card.get('lapses') or 0)

    # 解析 last_review
    raw_lr = card.get('last_review')
    if isinstance(raw_lr, str) and raw_lr:
        lr = datetime.fromisoformat(raw_lr.replace('Z', '+00:00'))
        if lr.tzinfo is None:
            lr = lr.replace(tzinfo=timezone.utc)
    elif isinstance(raw_lr, datetime):
        lr = raw_lr.astimezone(timezone.utc) if raw_lr.tzinfo else raw_lr.replace(tzinfo=timezone.utc)
    else:
        lr = None

    elapsed = int((now - lr).days) if lr else 0

    # 保底：若 d 为 0，用评分 3 的初始难度
    if d <= 0:
        d = _init_difficulty(3)

    # ── 新卡（首次学习） ──────────────────────────────────────────────────
    if state == NEW:
        new_s      = _init_stability(rating)
        new_d      = _init_difficulty(rating)
        new_lapses = lapses
        new_reps   = reps + 1

        if rating == 1:    # Again → 1 天后
            new_state  = LEARNING
            sched_days = 1
            due        = now + timedelta(days=1)
        elif rating == 2:  # Hard → 1 天后
            new_state  = LEARNING
            sched_days = 1
            due        = now + timedelta(days=1)
        elif rating == 3:  # Good → 1 天后
            new_state  = LEARNING
            sched_days = 1
            due        = now + timedelta(days=1)
        else:              # Easy → 直接进入复习阶段
            new_state  = REVIEW
            sched_days = max(1, round(new_s))
            due        = now + timedelta(days=sched_days)

    # ── 学习中 / 重学 ────────────────────────────────────────────────────
    elif state in (LEARNING, RELEARNING):
        base_s = s if s > 0 else _init_stability(rating)
        new_s  = _short_term_stability(base_s, rating)
        new_d  = _next_difficulty(d, rating)
        new_lapses = lapses
        new_reps   = reps + 1

        if rating == 1:    # Again → 1 天后重来
            new_state  = state
            new_s      = _init_stability(1)
            sched_days = 1
            due        = now + timedelta(days=1)
        elif rating in (2, 3):  # Hard / Good → 1 天后
            new_state  = state
            sched_days = 1
            due        = now + timedelta(days=1)
        else:              # Easy → 毕业进入复习
            new_state  = REVIEW
            sched_days = max(1, round(new_s))
            due        = now + timedelta(days=sched_days)

    # ── 复习阶段 ─────────────────────────────────────────────────────────
    else:  # REVIEW
        r      = _retrievability(elapsed, s)
        new_d  = _next_difficulty(d, rating)
        new_reps = reps + 1

        if rating == 1:    # Again → 重学
            new_s      = _forget_stability(d, s, r)
            new_state  = RELEARNING
            new_lapses = lapses + 1
            sched_days = 0
            due        = now + timedelta(minutes=5)
        else:
            new_s      = _recall_stability(d, s, r, rating)
            new_state  = REVIEW
            new_lapses = lapses
            sched_days = max(1, round(new_s))
            due        = now + timedelta(days=sched_days)

    return {
        'due':            due,
        'stability':      round(new_s, 4),
        'difficulty':     round(new_d, 4),
        'elapsed_days':   elapsed,
        'scheduled_days': sched_days,
        'reps':           new_reps,
        'lapses':         new_lapses,
        'state':          new_state,
    }
