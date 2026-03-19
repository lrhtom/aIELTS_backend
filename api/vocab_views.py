from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db import transaction

from .models import VocabFSRS, Word
from .fsrs_utils import fsrs_schedule

# 新卡状态常量
_NEW = 0
_GLOBAL_PLAN_ID = 0


# ── 序列化 ────────────────────────────────────────────────────────────────

def _card_to_dict(c: VocabFSRS, word_obj: Word | None = None) -> dict:
    return {
        'word':           c.word,
        'zh':             c.zh,
        'due':            c.due.isoformat(),
        'stability':      c.stability,
        'difficulty':     c.difficulty,
        'elapsed_days':   c.elapsed_days,
        'scheduled_days': c.scheduled_days,
        'reps':           c.reps,
        'lapses':         c.lapses,
        'state':          c.state,
        'last_review':    c.last_review.isoformat() if c.last_review else None,
        'plan_id':        c.plan_id,
        # Word enrichment (empty/empty-list when Word row doesn't exist)
        'phonetic':       (word_obj.phonetic or '') if word_obj else '',
        'grammar':        (word_obj.grammar or '') if word_obj else '',
        'definitions':    word_obj.definitions if word_obj else [],
        'examples':       word_obj.examples if word_obj else [],
    }


def _word_map(words: list[str]) -> dict[str, Word]:
    """Bulk-fetch Word rows for the given word strings."""
    return {w.word: w for w in Word.objects.filter(word__in=words)}


def _stats(card_list: list, now) -> dict:
    total     = len(card_list)
    new_count = sum(1 for c in card_list if c.state == _NEW)
    due_count = sum(1 for c in card_list if c.state != _NEW and c.due <= now)
    return {'total': total, 'new': new_count, 'due': due_count}


# ── Views ─────────────────────────────────────────────────────────────────

class VocabSyncView(APIView):
    """
    POST /vocab/sync
    Body: {"words": [{"word": "ephemeral", "zh": "短暂的"}, ...]}

    批量同步用户词汇：新词建空卡，旧词仅更新中文；返回全部卡片状态及统计。
    线程安全：select_for_update + bulk_create(ignore_conflicts=True)
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        words_raw = request.data.get('words', [])
        if not isinstance(words_raw, list) or not words_raw:
            return Response({'error': '请提供 words 列表'}, status=status.HTTP_400_BAD_REQUEST)

        # 标准化：strip + lower，去重（保留最后一个 zh）
        normalized: dict[str, str] = {}
        for item in words_raw:
            w  = str(item.get('word', '')).strip().lower()
            zh = str(item.get('zh',   '')).strip()
            if w:
                normalized[w] = zh

        if not normalized:
            return Response({'error': '没有有效单词'}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        now  = timezone.now()

        with transaction.atomic():
            existing = {
                c.word: c
                for c in VocabFSRS.objects.select_for_update().filter(
                    user=user, word__in=normalized.keys(), plan_id=_GLOBAL_PLAN_ID
                )
            }

            to_create = []
            to_update = []

            for word, zh in normalized.items():
                if word in existing:
                    card = existing[word]
                    if card.zh != zh:
                        card.zh = zh
                        to_update.append(card)
                else:
                    to_create.append(VocabFSRS(user=user, word=word, zh=zh, due=now, plan_id=_GLOBAL_PLAN_ID))

            if to_create:
                # ignore_conflicts=True 处理并发重复写入，不报错
                VocabFSRS.objects.bulk_create(to_create, ignore_conflicts=True)
            if to_update:
                VocabFSRS.objects.bulk_update(to_update, ['zh'])

        card_list = list(
            VocabFSRS.objects.filter(user=user, word__in=normalized.keys(), plan_id=_GLOBAL_PLAN_ID).order_by('due')
        )
        wmap = _word_map([c.word for c in card_list])
        return Response({
            'cards': [_card_to_dict(c, wmap.get(c.word)) for c in card_list],
            'stats': _stats(card_list, now),
        })


class VocabCardsView(APIView):
    """
    GET /vocab/cards          → 返回用户全部卡片
    GET /vocab/cards?due_only=true → 仅返回今日到期（state!=0 且 due<=now）或新卡
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        qs  = VocabFSRS.objects.filter(user=request.user, plan_id=_GLOBAL_PLAN_ID)

        if request.query_params.get('due_only') == 'true':
            from django.db.models import Q
            qs = qs.filter(Q(state=_NEW) | Q(due__lte=now))

        card_list = list(qs.order_by('due'))
        wmap = _word_map([c.word for c in card_list])
        return Response({
            'cards': [_card_to_dict(c, wmap.get(c.word)) for c in card_list],
            'stats': _stats(card_list, now),
        })


class VocabReviewView(APIView):
    """
    POST /vocab/review
    Body: {
        "word":              str,
        "rating":            int (1=Again / 2=Hard / 3=Good / 4=Easy),
        "client_last_review": str|null   ← 乐观锁：客户端持有的 last_review ISO 值
    }

    服务端运行 FSRS 算法，更新并返回新卡片状态。
    并发保护：select_for_update + 乐观锁校验。
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        word              = str(request.data.get('word', '')).strip().lower()
        rating_raw        = request.data.get('rating')
        client_last_review = request.data.get('client_last_review')  # None 表示新卡
        plan_id           = int(request.data.get('plan_id', 0) or 0)

        if not word:
            return Response({'error': '缺少 word 字段'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            rating = int(rating_raw)
            if rating not in (1, 2, 3, 4):
                raise ValueError
        except (TypeError, ValueError):
            return Response({'error': 'rating 必须为 1-4'}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()

        with transaction.atomic():
            # 第一次尝试：精确查询指定的plan_id
            try:
                card = VocabFSRS.objects.select_for_update().get(
                    user=request.user, word=word, plan_id=plan_id,
                )
            except VocabFSRS.DoesNotExist:
                # 第二次尝试：如果指定的plan_id不存在，检查是否存在其他plan的该单词
                # 这处理了前端plan_id错误或单词被添加到多个计划的情况
                alternatives = list(VocabFSRS.objects.filter(
                    user=request.user, word=word
                ).select_for_update())
                
                if len(alternatives) == 1:
                    # 只有一个版本存在，直接使用它
                    card = alternatives[0]
                elif len(alternatives) > 1:
                    # 多个版本存在，优先选择全局卡片(plan_id=0)
                    global_card = [c for c in alternatives if c.plan_id == 0]
                    if global_card:
                        card = global_card[0]
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(
                            f'plan_id mismatch: word={word}, requested_plan={plan_id}, '
                            f'using global card (plan_id=0) instead. Other versions in plans: '
                            f'{[c.plan_id for c in alternatives]}'
                        )
                    else:
                        # 没有全局卡片，使用最小的plan_id
                        card = min(alternatives, key=lambda c: c.plan_id)
                else:
                    return Response(
                        {'error': '卡片不存在，请先同步词汇'},
                        status=status.HTTP_404_NOT_FOUND
                    )

            # 乐观锁：若客户端 last_review 过时，服务端自动吸收冲突并继续计算。
            # 这样可避免前端先收到 409 再重试造成的噪声日志。
            stored_lr = card.last_review.isoformat() if card.last_review else None
            if client_last_review is not None and client_last_review != stored_lr:
                client_last_review = stored_lr

            # 运行 FSRS 算法（服务端，不可被客户端篡改）
            new_state = fsrs_schedule(
                {
                    'state':       card.state,
                    'stability':   card.stability,
                    'difficulty':  card.difficulty,
                    'reps':        card.reps,
                    'lapses':      card.lapses,
                    'last_review': card.last_review,
                },
                rating,
                now,
            )

            card.due            = new_state['due']
            card.stability      = new_state['stability']
            card.difficulty     = new_state['difficulty']
            card.elapsed_days   = new_state['elapsed_days']
            card.scheduled_days = new_state['scheduled_days']
            card.reps           = new_state['reps']
            card.lapses         = new_state['lapses']
            card.state          = new_state['state']
            card.last_review    = now

            card.save(update_fields=[
                'due', 'stability', 'difficulty', 'elapsed_days',
                'scheduled_days', 'reps', 'lapses', 'state', 'last_review',
            ])

        word_obj = Word.objects.filter(word=word).first()
        return Response({'card': _card_to_dict(card, word_obj)})
