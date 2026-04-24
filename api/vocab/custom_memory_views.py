from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.core.fsrs_utils import fsrs_schedule
from api.models import CustomMemoryCard, CustomMemoryDeck


def _deck_to_dict(deck: CustomMemoryDeck, card_count: int | None = None) -> dict:
    return {
        'id': deck.pk,
        'title': deck.title,
        'daily_count': deck.daily_count,
        'source_text': deck.source_text,
        'card_count': card_count if card_count is not None else deck.cards.count(),
        'has_activity_today': False,
        'today_target': 0,
        'studied_today': 0,
        'created_at': deck.created_at.isoformat(),
        'updated_at': deck.updated_at.isoformat(),
    }


def _card_to_dict(card: CustomMemoryCard) -> dict:
    return {
        'id': card.pk,
        'deck_id': card.deck_id,
        'front_text': card.front_text,
        'back_text': card.back_text,
        'order': card.order,
        'due': card.due.isoformat(),
        'stability': card.stability,
        'difficulty': card.difficulty,
        'elapsed_days': card.elapsed_days,
        'scheduled_days': card.scheduled_days,
        'reps': card.reps,
        'lapses': card.lapses,
        'state': card.state,
        'last_review': card.last_review.isoformat() if card.last_review else None,
    }


def _stats(cards: list[CustomMemoryCard], now) -> dict:
    total = len(cards)
    new_count = sum(1 for c in cards if c.state == 0)
    due_count = sum(1 for c in cards if c.state != 0 and c.due <= now)
    return {'total': total, 'new': new_count, 'due': due_count}


def _parse_line_to_pair(line: str) -> tuple[str, str]:
    separators = [' - ', ' | ', '\t', ':', '\uFF1A', ' \u2014 ']
    for sep in separators:
        if sep in line:
            left, right = line.split(sep, 1)
            return left.strip(), right.strip()
    return line.strip(), ''


def _parse_source_text(raw_text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        front, back = _parse_line_to_pair(line)
        if not front:
            continue
        key = (front, back)
        if key in seen:
            continue
        seen.add(key)
        pairs.append(key)

    return pairs


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _daily_stats(deck: CustomMemoryDeck, cards: list[CustomMemoryCard]) -> tuple[int, int, int]:
    today = timezone.localdate()
    tz = timezone.get_current_timezone()
    studied_today = sum(
        1
        for c in cards
        if c.last_review is not None and c.last_review.astimezone(tz).date() == today
    )
    remaining_today = max(0, deck.daily_count - studied_today)
    today_target = max(studied_today, min(deck.daily_count, len(cards)))
    return studied_today, remaining_today, today_target


class CustomMemoryDeckCreateView(APIView):
    """POST /custom-memory/decks/ Create an isolated custom memory deck from free text."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        decks = (
            CustomMemoryDeck.objects
            .filter(user=request.user)
            .annotate(card_total=Count('cards'))
            .order_by('-created_at')
        )

        result = []
        for deck in decks:
            cards = list(
                CustomMemoryCard.objects
                .filter(deck=deck, user=request.user)
                .only('last_review')
            )
            studied_today, _, today_target = _daily_stats(deck, cards)
            payload = _deck_to_dict(deck, card_count=deck.card_total)
            payload['has_activity_today'] = studied_today > 0
            payload['today_target'] = today_target
            payload['studied_today'] = studied_today
            result.append(payload)

        return Response({'decks': result})

    def post(self, request):
        raw_text = str(request.data.get('text', '')).strip()
        title = str(request.data.get('title', '')).strip()
        try:
            daily_count = int(request.data.get('daily_count', 20))
            if not (1 <= daily_count <= 200):
                raise ValueError
        except (TypeError, ValueError):
            return Response({'error': 'daily_count must be 1..200'}, status=status.HTTP_400_BAD_REQUEST)

        pairs: list[tuple[str, str]] = []
        if raw_text:
            pairs = _parse_source_text(raw_text)
            if not pairs:
                return Response(
                    {'error': 'No valid card content found. Use "front - back" or plain lines.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if len(pairs) > 300:
                return Response({'error': 'At most 300 cards can be created at once'}, status=status.HTTP_400_BAD_REQUEST)

        if not title:
            title = f'Custom Memory Deck {timezone.now().strftime("%m-%d %H:%M")}'
        title = title[:100]

        now = timezone.now()
        with transaction.atomic():
            deck = CustomMemoryDeck.objects.create(
                user=request.user,
                title=title,
                daily_count=daily_count,
                source_text=raw_text,
            )
            if pairs:
                cards = [
                    CustomMemoryCard(
                        deck=deck,
                        user=request.user,
                        front_text=front,
                        back_text=back,
                        order=idx,
                        due=now,
                    )
                    for idx, (front, back) in enumerate(pairs, start=1)
                ]
                CustomMemoryCard.objects.bulk_create(cards)

        card_list = list(CustomMemoryCard.objects.filter(deck=deck, user=request.user).order_by('due', 'order'))
        studied_today, remaining_today, today_target = _daily_stats(deck, card_list)
        session_cards = card_list[:remaining_today] if remaining_today > 0 else []
        stats = _stats(card_list, now)
        stats.update({
            'studied_today': studied_today,
            'remaining_today': remaining_today,
            'today_target': today_target,
        })

        return Response(
            {
                'deck': _deck_to_dict(deck, card_count=len(card_list)),
                'cards': [_card_to_dict(c) for c in session_cards],
                'stats': stats,
            },
            status=status.HTTP_201_CREATED,
        )


class CustomMemoryDeckStartView(APIView):
    """POST /custom-memory/decks/:id/start/ Return this deck's study queue."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        deck = get_object_or_404(CustomMemoryDeck, pk=pk, user=request.user)
        now = timezone.now()
        due_only = _as_bool(request.data.get('due_only', False))
        use_daily_limit = _as_bool(request.data.get('use_daily_limit', True))

        qs = CustomMemoryCard.objects.filter(deck=deck, user=request.user)
        all_cards = list(qs.order_by('due', 'order'))
        studied_today, remaining_today, today_target = _daily_stats(deck, all_cards)

        if due_only:
            session_cards = [c for c in all_cards if c.state == 0 or c.due <= now]
        else:
            session_cards = all_cards

        if use_daily_limit:
            session_cards = session_cards[:remaining_today] if remaining_today > 0 else []

        stats = _stats(all_cards, now)
        stats.update({
            'studied_today': studied_today,
            'remaining_today': remaining_today,
            'today_target': today_target,
        })

        return Response(
            {
                'deck': _deck_to_dict(deck, card_count=len(all_cards)),
                'cards': [_card_to_dict(c) for c in session_cards],
                'stats': stats,
            }
        )


class CustomMemoryDeckAppendView(APIView):
    """POST /custom-memory/decks/:id/append/ Append cards into an existing deck."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        deck = get_object_or_404(CustomMemoryDeck, pk=pk, user=request.user)
        raw_text = str(request.data.get('text', '')).strip()

        if not raw_text:
            return Response({'error': 'Text is required'}, status=status.HTTP_400_BAD_REQUEST)

        pairs = _parse_source_text(raw_text)
        if not pairs:
            return Response(
                {'error': 'No valid card content found. Use "front - back" or plain lines.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(pairs) > 300:
            return Response({'error': 'At most 300 cards can be appended at once'}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        with transaction.atomic():
            last_card = (
                CustomMemoryCard.objects
                .filter(deck=deck, user=request.user)
                .order_by('-order')
                .first()
            )
            base_order = last_card.order if last_card else 0

            cards = [
                CustomMemoryCard(
                    deck=deck,
                    user=request.user,
                    front_text=front,
                    back_text=back,
                    order=base_order + idx,
                    due=now,
                )
                for idx, (front, back) in enumerate(pairs, start=1)
            ]
            CustomMemoryCard.objects.bulk_create(cards)

            if deck.source_text:
                deck.source_text = f"{deck.source_text.rstrip()}\n{raw_text}"
            else:
                deck.source_text = raw_text
            deck.save(update_fields=['source_text', 'updated_at'])

        all_cards = list(CustomMemoryCard.objects.filter(deck=deck, user=request.user).only('last_review'))
        studied_today, remaining_today, today_target = _daily_stats(deck, all_cards)
        stats = _stats(all_cards, now)
        stats.update({
            'studied_today': studied_today,
            'remaining_today': remaining_today,
            'today_target': today_target,
        })

        payload = _deck_to_dict(deck, card_count=len(all_cards))
        payload['has_activity_today'] = studied_today > 0
        payload['today_target'] = today_target
        payload['studied_today'] = studied_today

        return Response(
            {
                'deck': payload,
                'cards_added': len(cards),
                'stats': stats,
            },
            status=status.HTTP_201_CREATED,
        )


class CustomMemoryReviewView(APIView):
    """POST /custom-memory/review/ Submit custom-memory card rating."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            card_id = int(request.data.get('card_id'))
        except (TypeError, ValueError):
            return Response({'error': 'card_id must be an integer'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            rating = int(request.data.get('rating'))
            if rating not in (1, 2, 3, 4):
                raise ValueError
        except (TypeError, ValueError):
            return Response({'error': 'rating must be 1..4'}, status=status.HTTP_400_BAD_REQUEST)

        client_last_review = request.data.get('client_last_review')
        now = timezone.now()

        with transaction.atomic():
            card = get_object_or_404(
                CustomMemoryCard.objects.select_for_update(),
                pk=card_id,
                user=request.user,
            )

            stored_lr = card.last_review.isoformat() if card.last_review else None
            if client_last_review is not None and client_last_review != stored_lr:
                return Response(
                    {'error': 'Card updated on another client', 'server_last_review': stored_lr},
                    status=status.HTTP_409_CONFLICT,
                )

            new_state = fsrs_schedule(
                {
                    'state': card.state,
                    'stability': card.stability,
                    'difficulty': card.difficulty,
                    'reps': card.reps,
                    'lapses': card.lapses,
                    'last_review': card.last_review,
                },
                rating,
                now,
            )

            card.due = new_state['due']
            card.stability = new_state['stability']
            card.difficulty = new_state['difficulty']
            card.elapsed_days = new_state['elapsed_days']
            card.scheduled_days = new_state['scheduled_days']
            card.reps = new_state['reps']
            card.lapses = new_state['lapses']
            card.state = new_state['state']
            card.last_review = now
            card.save(
                update_fields=[
                    'due',
                    'stability',
                    'difficulty',
                    'elapsed_days',
                    'scheduled_days',
                    'reps',
                    'lapses',
                    'state',
                    'last_review',
                ]
            )

        return Response({'card': _card_to_dict(card)})


