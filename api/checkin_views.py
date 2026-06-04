"""
Daily check-in with AT coin rewards.
Rewards: 1k base every day, escalating bonuses at milestone check-in counts.
"""
from datetime import date

from django.db import transaction
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from api.models import UserDailyStats, UserDailyLearningTime


def _compute_bonus(count: int) -> int:
    """Calculate bonus for a check-in with given cumulative count."""
    bonus = 1000  # base
    if count % 7 == 0:
        bonus += 10_000
    if count % 30 == 0:
        bonus += 30_000
    if count % 100 == 0:
        bonus += 100_000
    if count % 365 == 0:
        bonus += 1_000_000
    if count % 1000 == 0:
        bonus += 10_000_000
    return bonus


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def daily_checkin(request):
    """Perform daily check-in and award AT coins."""
    today = date.today()
    user = request.user

    with transaction.atomic():
        # Prevent double check-in
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

        # Calculate cumulative check-in count
        prev_count = UserDailyStats.objects.filter(
            user=user, is_checked_in=True
        ).exclude(date=today).count()

        new_count = prev_count + 1
        bonus = _compute_bonus(new_count)

        stats.is_checked_in = True
        stats.has_activity = True
        stats.practice_count = max(stats.practice_count, 1)
        stats.checkin_bonus = bonus
        stats.checkin_count = new_count
        stats.save()

        # Award AT coins
        from api.models import TransactionRecord
        TransactionRecord.record(user, TransactionRecord.Currency.AT_COIN, bonus, f'每日签到奖励 (累计 {new_count} 天)')

    return JsonResponse({
        'ok': True,
        'bonus': bonus,
        'checkin_count': new_count,
        'balance': user.at_balance,
        'message': f'签到成功！获得 {bonus:,} AT 币。',
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

    # Total check-ins
    total_checkins = UserDailyStats.objects.filter(user=user, is_checked_in=True).count()

    # Calendar data: all dates from registration to today with activity
    from datetime import timedelta
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
    from datetime import timedelta as td
    one_year_ago = today - td(days=364)
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
        'today_checked': today_checked,
        'total_checkins': total_checkins,
        'today_bonus': today_stat.checkin_bonus if today_stat else 0,
        'calendar': calendar,
        'registered_date': reg_date.isoformat(),
        'total_year_seconds': total_year_seconds,
    })
