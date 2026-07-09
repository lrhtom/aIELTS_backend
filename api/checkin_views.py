"""
Daily check-in with AT coin rewards.

连续签到（streak）为核心：断签清零重算。里程碑奖励基于**连续**天数，
连续每满 30 天赠 1 张补签卡。补签卡可补回最近 7 天内的漏签（补发基础奖励，
不触发里程碑），接续连续记录。
"""
from datetime import date, timedelta

from django.db import transaction
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from api.models import UserDailyStats, UserDailyLearningTime, UserItem

MAKEUP_WINDOW_DAYS = 7      # 补签可回溯的天数
MAKEUP_BONUS = 1000         # 补签发放的基础 AT（不含里程碑）
STREAK_CARD_EVERY = 30      # 连续每满 N 天赠 1 张补签卡


def _compute_bonus(streak: int) -> int:
    """基于**连续**签到天数计算奖励；断签后 streak 重置，里程碑随之重来。"""
    bonus = 1000  # base
    if streak % 7 == 0:
        bonus += 10_000
    if streak % 30 == 0:
        bonus += 30_000
    if streak % 100 == 0:
        bonus += 100_000
    if streak % 365 == 0:
        bonus += 1_000_000
    if streak % 1000 == 0:
        bonus += 10_000_000
    return bonus


def _streak_ending(user, day: date) -> int:
    """截至 day（含）的连续签到天数；day 未签到则返回 0。"""
    s = UserDailyStats.objects.filter(user=user, date=day, is_checked_in=True).first()
    return s.checkin_streak if s else 0


def _recompute_streaks_from(user, start_date: date) -> None:
    """补签后重算 start_date..today 每一天的 checkin_streak（范围很小，≤ 窗口天数）。"""
    today = date.today()
    running = _streak_ending(user, start_date - timedelta(days=1))
    stats_map = {
        s.date: s for s in UserDailyStats.objects.filter(
            user=user, date__gte=start_date, date__lte=today
        )
    }
    to_update = []
    cur = start_date
    while cur <= today:
        s = stats_map.get(cur)
        if s and s.is_checked_in:
            running += 1
            if s.checkin_streak != running:
                s.checkin_streak = running
                to_update.append(s)
        else:
            running = 0
        cur += timedelta(days=1)
    if to_update:
        UserDailyStats.objects.bulk_update(to_update, ['checkin_streak'])


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def daily_checkin(request):
    """执行每日签到并发放 AT 币；连续满 30 天额外赠补签卡。"""
    today = date.today()
    user = request.user

    with transaction.atomic():
        stats, created = UserDailyStats.objects.select_for_update().get_or_create(
            user=user, date=today,
            defaults={'is_checked_in': True, 'has_activity': True, 'practice_count': 1}
        )
        if not created and stats.is_checked_in:
            return JsonResponse({
                'ok': False,
                'message': '今天已经签到过了，明天再来吧！',
                'today_bonus': stats.checkin_bonus,
            })

        # 连续签到天数：昨天签到则接续，否则从 1 开始
        new_streak = _streak_ending(user, today - timedelta(days=1)) + 1
        bonus = _compute_bonus(new_streak)

        # 累计签到总数（仅用于展示）
        prev_total = UserDailyStats.objects.filter(
            user=user, is_checked_in=True
        ).exclude(date=today).count()
        new_count = prev_total + 1

        stats.is_checked_in = True
        stats.has_activity = True
        stats.practice_count = max(stats.practice_count, 1)
        stats.checkin_bonus = bonus
        stats.checkin_count = new_count
        stats.checkin_streak = new_streak
        stats.is_makeup = False
        stats.save()

        # 连续每满 30 天赠 1 张补签卡
        card_awarded = 0
        if new_streak % STREAK_CARD_EVERY == 0:
            UserItem.grant(user, UserItem.ItemType.MAKEUP_CARD, 1)
            card_awarded = 1

        # 发放 AT 币
        from api.models import TransactionRecord
        TransactionRecord.record(
            user, TransactionRecord.Currency.AT_COIN, bonus,
            f'每日签到奖励 (连续 {new_streak} 天)'
        )

    msg = f'签到成功！获得 {bonus:,} AT 币。'
    if card_awarded:
        msg += f' 连续满 {new_streak} 天，额外获得 1 张补签卡！'

    return JsonResponse({
        'ok': True,
        'bonus': bonus,
        'checkin_count': new_count,
        'checkin_streak': new_streak,
        'card_awarded': card_awarded,
        'balance': user.at_balance,
        'message': msg,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def makeup_checkin(request):
    """使用补签卡补回最近 7 天内的漏签日；补发基础奖励并接续连续记录。"""
    user = request.user
    today = date.today()

    date_str = request.data.get('date')
    if not date_str:
        return JsonResponse({'ok': False, 'message': '缺少日期参数'}, status=400)
    try:
        target = date.fromisoformat(str(date_str))
    except ValueError:
        return JsonResponse({'ok': False, 'message': '日期格式无效'}, status=400)

    # 范围校验：过去、且在最近 7 天内、且不早于注册日
    if target >= today:
        return JsonResponse({'ok': False, 'message': '只能补签过去的日期'}, status=400)
    if target < today - timedelta(days=MAKEUP_WINDOW_DAYS):
        return JsonResponse({'ok': False, 'message': f'只能补签最近 {MAKEUP_WINDOW_DAYS} 天内的漏签'}, status=400)
    reg_date = user.date_joined.date() if user.date_joined else target
    if target < reg_date:
        return JsonResponse({'ok': False, 'message': '不能补签注册之前的日期'}, status=400)

    with transaction.atomic():
        existing = UserDailyStats.objects.select_for_update().filter(user=user, date=target).first()
        if existing and existing.is_checked_in:
            return JsonResponse({'ok': False, 'message': '这一天已经签到过了'}, status=400)

        # 先扣卡，库存不足直接拒绝
        if not UserItem.consume(user, UserItem.ItemType.MAKEUP_CARD, 1):
            return JsonResponse({'ok': False, 'message': '补签卡不足，去商城购买或连续签到获取吧'}, status=402)

        count_upto = UserDailyStats.objects.filter(
            user=user, is_checked_in=True, date__lte=target
        ).count() + 1  # 含本次补签

        if existing:
            existing.is_checked_in = True
            existing.is_makeup = True
            existing.checkin_bonus = MAKEUP_BONUS
            existing.checkin_count = count_upto
            existing.has_activity = True
            existing.save()
        else:
            UserDailyStats.objects.create(
                user=user, date=target,
                is_checked_in=True, is_makeup=True,
                checkin_bonus=MAKEUP_BONUS, checkin_count=count_upto,
                has_activity=True,
            )

        # 重算受影响区间的连续天数
        _recompute_streaks_from(user, target)

        # 发放补签基础奖励
        from api.models import TransactionRecord
        TransactionRecord.record(
            user, TransactionRecord.Currency.AT_COIN, MAKEUP_BONUS,
            f'补签奖励 ({target.isoformat()})'
        )

    remaining = UserItem.count(user, UserItem.ItemType.MAKEUP_CARD)
    return JsonResponse({
        'ok': True,
        'bonus': MAKEUP_BONUS,
        'balance': user.at_balance,
        'date': target.isoformat(),
        'makeup_cards': remaining,
        'message': f'补签成功！获得 {MAKEUP_BONUS:,} AT 币。',
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def checkin_status(request):
    """Get today's check-in status and stats for calendar view."""
    user = request.user
    today = date.today()

    # Today's status
    today_stat = UserDailyStats.objects.filter(user=user, date=today).first()
    today_checked = today_stat is not None and today_stat.is_checked_in

    # 当前连续签到天数：今天已签用今天的；否则用昨天的（今天仍可继续）
    if today_checked:
        current_streak = today_stat.checkin_streak
    else:
        current_streak = _streak_ending(user, today - timedelta(days=1))

    # Total check-ins
    total_checkins = UserDailyStats.objects.filter(user=user, is_checked_in=True).count()

    # 补签卡数量
    makeup_cards = UserItem.count(user, UserItem.ItemType.MAKEUP_CARD)

    # Calendar data: all dates from registration to today with activity
    reg_date = user.date_joined.date() if user.date_joined else today - timedelta(days=365)

    stats_qs = UserDailyStats.objects.filter(
        user=user, date__gte=reg_date, date__lte=today
    ).order_by('date')

    # Build a seconds lookup from UserDailyLearningTime
    time_qs = UserDailyLearningTime.objects.filter(
        user=user, study_date__gte=reg_date, study_date__lte=today
    ).values_list('study_date', 'total_seconds')
    seconds_map = {row[0]: row[1] for row in time_qs}

    # Total learning seconds in past year
    one_year_ago = today - timedelta(days=364)
    total_year_seconds = sum(
        s for d, s in seconds_map.items() if d >= one_year_ago
    )

    # Build calendar entries — take the UNION of both tables so that days
    # with learning time but no check-in record are still shown.
    stats_map = {s.date: s for s in stats_qs}
    all_dates = sorted(set(stats_map.keys()) | set(seconds_map.keys()))

    calendar = []
    for d in all_dates:
        s = stats_map.get(d)
        secs = seconds_map.get(d, 0)
        has_activity = (s and s.has_activity) or (secs > 0)
        calendar.append({
            'date': d.isoformat(),
            'checked': s.is_checked_in if s else False,
            'makeup': s.is_makeup if s else False,
            'streak': s.checkin_streak if s else 0,
            'bonus': s.checkin_bonus if s else 0,
            'count': s.checkin_count if s else 0,
            'activity': has_activity,
            'practice': s.practice_count if s else 0,
            'speaking': s.speaking_count if s else 0,
            'listening': s.listening_count if s else 0,
            'reading': s.reading_count if s else 0,
            'writing': s.writing_count if s else 0,
            'vocab': s.vocab_count if s else 0,
            'learning_seconds': secs,
        })

    return JsonResponse({
        'today': today.isoformat(),
        'today_checked': today_checked,
        'total_checkins': total_checkins,
        'current_streak': current_streak,
        'makeup_cards': makeup_cards,
        'makeup_window_days': MAKEUP_WINDOW_DAYS,
        'today_bonus': today_stat.checkin_bonus if today_stat else 0,
        'calendar': calendar,
        'registered_date': reg_date.isoformat(),
        'total_year_seconds': total_year_seconds,
    })
