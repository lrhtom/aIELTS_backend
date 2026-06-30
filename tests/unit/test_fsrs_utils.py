"""L1 单元测试：api.core.fsrs_utils.fsrs_schedule

覆盖目标：
- 输入校验
- 4 个状态（New/Learning/Review/Relearning）× 4 个评分（1/2/3/4）的迁移
- stability / difficulty 的不变量（边界、范围）
- elapsed_days 的日历日计算
- last_review 输入的兼容（str / datetime / None）
- 遗忘路径：REVIEW + Again → RELEARNING & lapses+1
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from api.core.fsrs_utils import (
    NEW, LEARNING, REVIEW, RELEARNING,
    fsrs_schedule,
)


# ── 输入校验 ─────────────────────────────────────────────────────────────────

class TestInputValidation:
    def test_rating_out_of_range_raises(self, frozen_now):
        card = {'state': NEW, 'stability': 0, 'difficulty': 0, 'reps': 0, 'lapses': 0}
        with pytest.raises(ValueError, match='rating 必须为 1-4'):
            fsrs_schedule(card, 0, frozen_now)
        with pytest.raises(ValueError, match='rating 必须为 1-4'):
            fsrs_schedule(card, 5, frozen_now)

    def test_last_review_as_iso_string(self, frozen_now):
        """ISO 格式字符串带 Z 后缀应正确解析为 UTC。"""
        prev = (frozen_now - timedelta(days=3)).isoformat().replace('+00:00', 'Z')
        card = {
            'state': REVIEW, 'stability': 10, 'difficulty': 5,
            'reps': 5, 'lapses': 0, 'last_review': prev,
        }
        out = fsrs_schedule(card, 3, frozen_now)
        assert out['elapsed_days'] == 3.0

    def test_last_review_none_yields_zero_elapsed(self, frozen_now):
        card = {'state': NEW, 'stability': 0, 'difficulty': 0, 'reps': 0, 'lapses': 0}
        out = fsrs_schedule(card, 3, frozen_now)
        assert out['elapsed_days'] == 0.0

    def test_last_review_naive_datetime_treated_as_utc(self, frozen_now):
        prev = (frozen_now - timedelta(days=2)).replace(tzinfo=None)
        card = {
            'state': REVIEW, 'stability': 10, 'difficulty': 5,
            'reps': 5, 'lapses': 0, 'last_review': prev,
        }
        out = fsrs_schedule(card, 3, frozen_now)
        assert out['elapsed_days'] == 2.0


# ── New 卡片转移 ────────────────────────────────────────────────────────────

class TestNewCardTransitions:
    @pytest.fixture
    def fresh_card(self):
        return {
            'state': NEW, 'stability': 0, 'difficulty': 0,
            'reps': 0, 'lapses': 0, 'last_review': None,
        }

    @pytest.mark.parametrize('rating', [1, 2, 3])
    def test_new_again_hard_good_goes_to_learning(self, fresh_card, frozen_now, rating):
        out = fsrs_schedule(fresh_card, rating, frozen_now)
        assert out['state'] == LEARNING
        assert out['scheduled_days'] == 1
        assert out['reps'] == 1
        assert out['lapses'] == 0

    def test_new_easy_jumps_to_review(self, fresh_card, frozen_now):
        out = fsrs_schedule(fresh_card, 4, frozen_now)
        assert out['state'] == REVIEW
        assert out['scheduled_days'] >= 1
        assert out['stability'] > 0
        assert 1.0 <= out['difficulty'] <= 10.0


# ── Learning / Relearning 转移 ──────────────────────────────────────────────

class TestLearningTransitions:
    @pytest.fixture
    def learning_card(self, frozen_now):
        return {
            'state': LEARNING, 'stability': 1.0, 'difficulty': 5.0,
            'reps': 1, 'lapses': 0,
            'last_review': frozen_now - timedelta(days=1),
        }

    def test_learning_again_stays_learning_with_min_stability(self, learning_card, frozen_now):
        out = fsrs_schedule(learning_card, 1, frozen_now)
        assert out['state'] == LEARNING
        assert out['scheduled_days'] == 1
        # 连续 Again 不应让 stability 跌穿 0
        assert out['stability'] > 0

    @pytest.mark.parametrize('rating', [2, 3])
    def test_learning_hard_good_stays_learning(self, learning_card, frozen_now, rating):
        out = fsrs_schedule(learning_card, rating, frozen_now)
        assert out['state'] == LEARNING
        assert out['scheduled_days'] == 1

    def test_learning_easy_graduates_to_review(self, learning_card, frozen_now):
        out = fsrs_schedule(learning_card, 4, frozen_now)
        assert out['state'] == REVIEW
        assert out['scheduled_days'] >= 1

    def test_relearning_easy_graduates_to_review(self, frozen_now):
        card = {
            'state': RELEARNING, 'stability': 2.0, 'difficulty': 6.0,
            'reps': 3, 'lapses': 1,
            'last_review': frozen_now - timedelta(days=1),
        }
        out = fsrs_schedule(card, 4, frozen_now)
        assert out['state'] == REVIEW


# ── Review 卡片转移（核心遗忘路径） ──────────────────────────────────────────

class TestReviewTransitions:
    @pytest.fixture
    def review_card(self, frozen_now):
        return {
            'state': REVIEW, 'stability': 10.0, 'difficulty': 5.0,
            'reps': 5, 'lapses': 0,
            'last_review': frozen_now - timedelta(days=7),
        }

    def test_review_again_demotes_to_relearning_and_increments_lapses(
        self, review_card, frozen_now,
    ):
        out = fsrs_schedule(review_card, 1, frozen_now)
        assert out['state'] == RELEARNING
        assert out['lapses'] == 1
        assert out['scheduled_days'] == 0  # 当天 5 分钟内
        # 5 分钟后 due
        assert (out['due'] - frozen_now) <= timedelta(minutes=10)

    @pytest.mark.parametrize('rating', [2, 3, 4])
    def test_review_success_keeps_state_and_grows_stability(self, review_card, frozen_now, rating):
        prev_s = review_card['stability']
        out = fsrs_schedule(review_card, rating, frozen_now)
        assert out['state'] == REVIEW
        assert out['lapses'] == 0
        # 成功回忆应不减反增（rating 3/4），Hard 可能持平甚至略升
        if rating >= 3:
            assert out['stability'] >= prev_s


# ── 不变量 / 属性 ────────────────────────────────────────────────────────────

class TestInvariants:
    @pytest.mark.parametrize('state', [NEW, LEARNING, REVIEW, RELEARNING])
    @pytest.mark.parametrize('rating', [1, 2, 3, 4])
    def test_difficulty_stays_in_1_to_10(self, state, rating, frozen_now):
        card = {
            'state': state, 'stability': 5.0, 'difficulty': 5.0,
            'reps': 3, 'lapses': 1,
            'last_review': frozen_now - timedelta(days=2),
        }
        out = fsrs_schedule(card, rating, frozen_now)
        assert 1.0 <= out['difficulty'] <= 10.0

    @pytest.mark.parametrize('state', [NEW, LEARNING, REVIEW, RELEARNING])
    @pytest.mark.parametrize('rating', [1, 2, 3, 4])
    def test_stability_stays_positive(self, state, rating, frozen_now):
        card = {
            'state': state, 'stability': 0.1, 'difficulty': 5.0,
            'reps': 3, 'lapses': 1,
            'last_review': frozen_now - timedelta(days=2),
        }
        out = fsrs_schedule(card, rating, frozen_now)
        assert out['stability'] > 0

    def test_reps_always_increments(self, frozen_now):
        for state in (NEW, LEARNING, REVIEW, RELEARNING):
            card = {
                'state': state, 'stability': 5.0, 'difficulty': 5.0,
                'reps': 7, 'lapses': 0,
                'last_review': frozen_now - timedelta(days=1),
            }
            out = fsrs_schedule(card, 3, frozen_now)
            assert out['reps'] == 8, f'state={state} 应让 reps 自增'

    def test_deterministic_given_same_inputs(self, frozen_now):
        card = {
            'state': REVIEW, 'stability': 12.5, 'difficulty': 4.2,
            'reps': 6, 'lapses': 1,
            'last_review': frozen_now - timedelta(days=10),
        }
        a = fsrs_schedule(dict(card), 3, frozen_now)
        b = fsrs_schedule(dict(card), 3, frozen_now)
        assert a == b


# ── 日历日边界 ──────────────────────────────────────────────────────────────

class TestCalendarDayEdge:
    def test_same_day_review_yields_zero_elapsed(self, frozen_now):
        card = {
            'state': REVIEW, 'stability': 5.0, 'difficulty': 5.0,
            'reps': 3, 'lapses': 0,
            'last_review': frozen_now - timedelta(hours=2),
        }
        out = fsrs_schedule(card, 3, frozen_now)
        assert out['elapsed_days'] == 0.0

    def test_crossing_midnight_counts_one_day_even_if_minutes(self):
        """23:55 学习，00:05 复习 → elapsed = 1（按日历日，不按小时）。"""
        late = datetime(2026, 6, 26, 23, 55, tzinfo=timezone.utc)
        early = datetime(2026, 6, 27, 0, 5, tzinfo=timezone.utc)
        card = {
            'state': REVIEW, 'stability': 5.0, 'difficulty': 5.0,
            'reps': 3, 'lapses': 0,
            'last_review': late,
        }
        out = fsrs_schedule(card, 3, early)
        assert out['elapsed_days'] == 1.0
