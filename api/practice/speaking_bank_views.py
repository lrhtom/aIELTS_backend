"""
Speaking question-bank endpoints.
Pull real IELTS topics from SpeakingTopicBank instead of AI generation.
Selection: least-used topics first, with times_used incremented after selection.
"""
import random

from django.db.models import F
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from api.core.rate_limit import check_rate_limit
from api.models import SpeakingTopicBank


# ── Helper ────────────────────────────────────────────────────────────────

def _select_least_used(qs, n: int):
    """Pick up to n items from qs, ordering by times_used ASC.
    When multiple items share the same times_used, shuffle them for variety."""
    items = list(qs.order_by('times_used'))
    if not items:
        return []
    # Group by times_used, shuffle within each group, then flatten
    groups = {}
    for item in items:
        groups.setdefault(item.times_used, []).append(item)
    result = []
    for used in sorted(groups):
        group = groups[used]
        random.shuffle(group)
        result.extend(group)
        if len(result) >= n:
            break
    return result[:n]


def _increment_times_used(ids):
    """Increment times_used for the given topic IDs."""
    if ids:
        SpeakingTopicBank.objects.filter(id__in=ids).update(
            times_used=F('times_used') + 1
        )


# ── Part 1: Select 3 topics from bank ─────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bank_generate_part1(request):
    """
    Generate Part 1 questions from the real IELTS question bank.
    Real IELTS Part 1 structure:
      Part A (mandatory): examiner picks ONE from two fixed groups —
        Group 1: Work or Studies
        Group 2: Hometown or Accommodation (Home)
      Part B (random): 2 everyday topics from the remaining pool.
    Returns greeting + mandatory topic questions + 2 random topic questions.
    """
    limit_resp = check_rate_limit(request.user.id, 'bank_part1', max_calls=20, window=60)
    if limit_resp:
        return limit_resp

    part1_qs = SpeakingTopicBank.objects.filter(part=1, is_active=True)
    if not part1_qs.exists():
        return JsonResponse({'error': 'No Part 1 topics in bank'}, status=500)

    # ── Part A: mandatory topic (二选一) ──
    # Group 1: WorkorStudies
    # Group 2: Home/Accommodation or Hometown (pick one randomly)
    group_a = list(part1_qs.filter(topic_en='WorkorStudies'))
    group_b = list(part1_qs.filter(topic_en__in=['Home/Accommodation', 'Hometown']))
    random.shuffle(group_b)

    mandatory_pool = group_a + group_b  # pick least-used from combined pool
    mandatory = _select_least_used(
        SpeakingTopicBank.objects.filter(id__in=[t.id for t in mandatory_pool]),
        1
    )
    mandatory_topic = mandatory[0] if mandatory else None

    # ── Part B: 2 random everyday topics (exclude the mandatory one) ──
    exclude_ids = {mandatory_topic.id} if mandatory_topic else set()
    random_pool = part1_qs.exclude(id__in=exclude_ids)
    chosen_random = _select_least_used(random_pool, 2)

    # If we didn't get enough random topics, pad from full pool
    while len(chosen_random) < 2:
        fallback = part1_qs.exclude(id__in=exclude_ids | {t.id for t in chosen_random}).first()
        if not fallback:
            break
        chosen_random.append(fallback)

    chosen = []
    if mandatory_topic:
        chosen.append(mandatory_topic)
    chosen.extend(chosen_random)

    _increment_times_used([t.id for t in chosen])

    questions = []
    # Greeting
    questions.append({
        'topic': 'Intro',
        'question': 'Good morning. Could you tell me your full name, please?',
    })

    for topic in chosen:
        qs_list = topic.questions_json
        if not isinstance(qs_list, list):
            continue
        taken = qs_list[:4]
        for q in taken:
            questions.append({
                'topic': topic.topic_en,
                'question': str(q).strip(),
            })

    return JsonResponse({
        'questions': questions,
        'bank_topics': [t.topic_en for t in chosen],
        'mandatory_topic': mandatory_topic.topic_en if mandatory_topic else '',
        'source': '环球教育 2025年9-12月口语题库',
    })


# ── Part 2: Select 1 cue card from bank ───────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bank_generate_part2(request):
    """
    Generate Part 2 cue card from the real IELTS question bank.
    Selects 1 least-used topic, returns cue card with bullet points.
    """
    limit_resp = check_rate_limit(request.user.id, 'bank_part2', max_calls=20, window=60)
    if limit_resp:
        return limit_resp

    part2_qs = SpeakingTopicBank.objects.filter(part=2, is_active=True)
    if not part2_qs.exists():
        return JsonResponse({'error': 'No Part 2 topics in bank'}, status=500)

    chosen = _select_least_used(part2_qs, 1)
    if not chosen:
        return JsonResponse({'error': 'No Part 2 topics available'}, status=500)

    topic = chosen[0]
    _increment_times_used([topic.id])

    # Build cue card text in official IELTS format
    cue_lines = [topic.cue_card.strip()]
    bullets = topic.bullet_points_json
    if isinstance(bullets, list) and bullets:
        cue_lines.append('You should say:')
        for bp in bullets:
            cue_lines.append(f'- {bp}')
    full_cue = '\n'.join(cue_lines)

    return JsonResponse({
        'questions': [{
            'topic': topic.topic_zh,
            'question': full_cue,
        }],
        'bank_topic': topic.topic_zh,
        'source': '环球教育 2025年9-12月口语题库',
    })


# ── Part 3: Follow-up questions linked to Part 2 topic ─────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bank_generate_part3(request):
    """
    Generate Part 3 discussion questions from the bank.
    Matches the Part 2 topic (by topic_zh) and returns its Part 3 questions.
    """
    limit_resp = check_rate_limit(request.user.id, 'bank_part3', max_calls=20, window=60)
    if limit_resp:
        return limit_resp

    part2_topic_zh = str(request.data.get('part2_topic', '')).strip()
    if not part2_topic_zh:
        return JsonResponse({'error': 'part2_topic is required'}, status=400)

    # Find Part 3 questions linked to this Part 2 topic
    part3_qs = SpeakingTopicBank.objects.filter(
        part=3, topic_zh=part2_topic_zh, is_active=True
    )
    if not part3_qs.exists():
        # Fallback: pick any 6 random Part 3 questions
        fallback = SpeakingTopicBank.objects.filter(part=3, is_active=True).order_by('?')[:6]
        questions = []
        for item in fallback:
            for q in item.questions_json[:2]:
                questions.append({
                    'topic': item.topic_zh,
                    'question': str(q).strip(),
                })
        return JsonResponse({
            'questions': questions[:6],
            'source': '环球教育 2025年9-12月口语题库 (随机)',
        })

    entry = part3_qs.first()
    _increment_times_used([entry.id])

    qs_list = entry.questions_json
    if not isinstance(qs_list, list):
        qs_list = []

    questions = []
    for q in qs_list[:6]:
        questions.append({
            'topic': entry.topic_zh,
            'question': str(q).strip(),
        })

    return JsonResponse({
        'questions': questions,
        'bank_topic': part2_topic_zh,
        'source': '环球教育 2025年9-12月口语题库',
    })
