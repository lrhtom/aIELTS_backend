"""补签卡上线的数据迁移：
1) 商城上架"补签卡"商品（10000 AT/张）；
2) 给每位存量用户发 1 张补签卡；
3) 回填历史 UserDailyStats.checkin_streak（连续签到天数）。
"""
from django.db import migrations


def forwards(apps, schema_editor):
    User = apps.get_model('api', 'User')
    UserItem = apps.get_model('api', 'UserItem')
    StoreProduct = apps.get_model('api', 'StoreProduct')
    UserDailyStats = apps.get_model('api', 'UserDailyStats')

    # 1) 商城上架补签卡（按名称幂等）
    StoreProduct.objects.get_or_create(
        name='补签卡',
        defaults={
            'description': '在签到日历上补回最近 7 天内漏签的一天，接续你的连续签到记录。',
            'price_amount': 10000,
            'price_currency': 'AT_COIN',
            'reward_type': 'MAKEUP_CARD',
            'reward_amount': 1,
            'is_active': True,
        },
    )

    # 2) 给每位存量用户发 1 张补签卡（已有记录则跳过，保证幂等）
    for uid in User.objects.values_list('id', flat=True).iterator():
        UserItem.objects.get_or_create(
            user_id=uid, item_type='makeup_card', defaults={'quantity': 1}
        )

    # 3) 回填历史连续签到天数（按用户、日期升序累计；断一天即清零重来）
    rows = list(
        UserDailyStats.objects
        .filter(is_checked_in=True)
        .order_by('user_id', 'date')
        .only('id', 'user_id', 'date', 'checkin_streak')
    )
    last_uid = None
    last_date = None
    streak = 0
    pending = []
    for s in rows:
        if s.user_id != last_uid:
            streak = 1
        elif last_date is not None and (s.date - last_date).days == 1:
            streak += 1
        else:
            streak = 1
        if s.checkin_streak != streak:
            s.checkin_streak = streak
            pending.append(s)
        last_uid = s.user_id
        last_date = s.date

    for i in range(0, len(pending), 500):
        UserDailyStats.objects.bulk_update(pending[i:i + 500], ['checkin_streak'])


def backwards(apps, schema_editor):
    # 数据回填不可逆；仅下架补签卡商品，保留用户已持有的物品与已回填的 streak。
    StoreProduct = apps.get_model('api', 'StoreProduct')
    StoreProduct.objects.filter(name='补签卡', reward_type='MAKEUP_CARD').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0050_userdailystats_checkin_streak_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
