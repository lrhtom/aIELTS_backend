import os
import re
import sys
from collections import OrderedDict

SCRIPT_DIR = os.path.dirname(__file__)
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
BACKEND_ROOT = os.path.join(REPO_ROOT, 'backend')
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

import django  # noqa: E402

django.setup()

from api.models import User, LearningPlan, LearningPlanEntry, Word  # noqa: E402

RAW_FILE = os.path.join(SCRIPT_DIR, 'lrhtom_spelling_vocab_raw.txt')
USERNAME = 'lrhtom'
PLAN_NAME = '雅思必须会的拼写词'

CJK_RE = re.compile(r'[\u4e00-\u9fff]')


def normalize_english_key(raw_word: str) -> str:
    key = raw_word.strip().lower()
    key = key.replace('–', '-').replace('—', '-')
    key = re.sub(r'\s+', ' ', key)
    key = re.sub(r'^[\-–—•·,;:\[\]{}"\'\s]+', '', key)
    key = re.sub(r'[\-–—,;:\[\]{}"\'\s]+$', '', key)
    # 清理由于“英文词 + 空格 + （中文说明）”造成的悬空左括号，例如 "grant ("
    key = re.sub(r'\s*\($', '', key)
    return key


def split_line(line: str):
    if '将这些单词放入' in line:
        line = line.split('将这些单词放入', 1)[0].strip()
    if not line:
        return None, None

    m = CJK_RE.search(line)
    if m:
        idx = m.start()
        en = line[:idx].strip()
        zh = line[idx:].strip()
        return en, zh

    parts = line.split(maxsplit=1)
    if not parts:
        return None, None
    en = parts[0].strip()
    zh = parts[1].strip() if len(parts) > 1 else ''
    return en, zh


def parse_vocab_text(text: str):
    result: OrderedDict[str, str] = OrderedDict()

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        en_raw, zh = split_line(line)
        if not en_raw:
            continue

        en = normalize_english_key(en_raw)
        if not en or not re.search(r'[a-z]', en):
            continue

        zh = zh.strip()
        if en in result:
            if zh and zh not in result[en]:
                result[en] = f"{result[en]}; {zh}" if result[en] else zh
        else:
            result[en] = zh

    return result


def import_to_plan(entries: OrderedDict[str, str], plan: LearningPlan):
    existing = dict(plan.entries.values_list('word', 'zh'))

    to_create = []
    added = 0
    existed = 0
    merged_zh = 0

    for en, zh in entries.items():
        word_obj, _ = Word.objects.get_or_create(word=en)
        if zh and not word_obj.definitions:
            word_obj.definitions = [{"pos": "", "meaning": zh[:500]}]
            word_obj.save(update_fields=['definitions'])

        if en in existing:
            existed += 1
            if zh and not (existing.get(en) or '').strip():
                updated = LearningPlanEntry.objects.filter(plan=plan, word=en, zh='').update(zh=zh[:500])
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
        raise FileNotFoundError(f'Raw file not found: {RAW_FILE}')

    with open(RAW_FILE, 'r', encoding='utf-8') as f:
        raw_text = f.read()

    parsed = parse_vocab_text(raw_text)

    user = User.objects.get(username=USERNAME)
    plan = LearningPlan.objects.get(user=user, name=PLAN_NAME)

    stats = import_to_plan(parsed, plan)

    print('=== Import Completed ===')
    print(f"username={USERNAME}, plan_id={plan.id}, plan_name={plan.name}")
    print(f"parsed_unique={stats['parsed_unique']}")
    print(f"added={stats['added']}")
    print(f"already_in_plan={stats['already_in_plan']}")
    print(f"merged_zh={stats['merged_zh']}")
    print(f"plan_total_after={plan.entries.count()}")


if __name__ == '__main__':
    main()
