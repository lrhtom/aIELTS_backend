import os
import re
import sys
import django
from collections import OrderedDict

SCRIPT_DIR = os.path.dirname(__file__)
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
BACKEND_ROOT = os.path.join(REPO_ROOT, 'backend')
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from api.models import User, LearningPlan, LearningPlanEntry, Word  # noqa: E402

RAW_FILE = os.path.join(os.path.dirname(__file__), 'lrhtom_reading_vocab_raw.txt')
USERNAME = 'lrhtom'
PLAN_NAME = '阅读必会词汇'


def normalize_key(raw_word: str) -> str:
    key = raw_word.strip().lower()
    key = re.sub(r'\s+', ' ', key)
    key = re.sub(r"^[^a-z0-9]+", '', key)
    key = re.sub(r"[^a-z0-9-]+$", '', key)
    return key


def parse_lines(text: str):
    entries: OrderedDict[str, str] = OrderedDict()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if '将这些单词放入' in line:
            line = line.split('将这些单词放入', 1)[0].strip()
            if not line:
                break

        parts = line.split(maxsplit=1)
        if not parts:
            continue

        en = normalize_key(parts[0])
        if not en or not re.search(r'[a-z]', en):
            continue

        zh = parts[1].strip() if len(parts) > 1 else ''

        if en in entries:
            old = entries[en]
            if zh and zh not in old:
                entries[en] = f"{old};{zh}" if old else zh
        else:
            entries[en] = zh

    return entries


def upsert_words(entries: OrderedDict[str, str], plan):
    existing_words = set(plan.entries.values_list('word', flat=True))

    added = 0
    existed = 0
    merged_zh = 0
    to_create = []

    for en, zh in entries.items():
        word_obj, _ = Word.objects.get_or_create(word=en)
        if zh and not word_obj.definitions:
            word_obj.definitions = [{"pos": "", "meaning": zh}]
            word_obj.save(update_fields=['definitions'])

        if en in existing_words:
            existed += 1
            if zh:
                updated = LearningPlanEntry.objects.filter(plan=plan, word=en, zh='').update(zh=zh[:500])
                if updated:
                    merged_zh += updated
            continue

        to_create.append(LearningPlanEntry(plan=plan, word=en, zh=zh[:500]))
        added += 1

    if to_create:
        LearningPlanEntry.objects.bulk_create(to_create, ignore_conflicts=True, batch_size=500)

    return {
        'parsed_unique': len(entries),
        'added': added,
        'already_in_plan': existed,
        'merged_zh': merged_zh,
    }


def main():
    if not os.path.exists(RAW_FILE):
        raise FileNotFoundError(f'Raw vocab file not found: {RAW_FILE}')

    with open(RAW_FILE, 'r', encoding='utf-8') as f:
        raw_text = f.read()

    entries = parse_lines(raw_text)

    user = User.objects.get(username=USERNAME)
    plan = LearningPlan.objects.get(user=user, name=PLAN_NAME)

    stats = upsert_words(entries, plan)
    total_after = plan.entries.count()

    print('=== Import Completed ===')
    print(f"username={USERNAME}, plan_id={plan.id}, plan_name={plan.name}")
    print(f"parsed_unique={stats['parsed_unique']}")
    print(f"added={stats['added']}")
    print(f"already_in_plan={stats['already_in_plan']}")
    print(f"merged_zh={stats['merged_zh']}")
    print(f"plan_total_after={total_after}")


if __name__ == '__main__':
    main()
