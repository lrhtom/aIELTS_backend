"""Fix unreasonable Chinese translations across vocab tables.

Modes (orthogonal; combine with --apply once you're confident):

  --pos-split     B-class fix: re-parse Word.definitions where POS tag
                  ("n.", "v.", "adj."...) bled into the `meaning` string.
                  Pure string operation, no LLM.

  --fill-empty    A-class fix: use DeepSeek to generate definitions for
                  Word rows where definitions == []. Dry-run by default;
                  writes staging JSON to --staging (default fill_empty_staging.json).

  --apply-staged  Apply translations from a previously-generated staging
                  JSON. Used to separate LLM cost from DB writes.

  --typo-check    LLM-driven spelling check: sweep Word.word, batch-ask DeepSeek
                  if any are misspelled. Report-only (no auto-rename — Word.word
                  is FK'd by WordBookMembership and NotebookWord).

  --expand-thin   E-class fix: ADD missing meanings to known polysemous
                  IELTS words (lead, bear, draw, etc.) via DeepSeek.

Usage:
    python manage.py fix_translations --pos-split                # dry-run
    python manage.py fix_translations --pos-split --apply
    python manage.py fix_translations --fill-empty --batch 20    # LLM → staging
    python manage.py fix_translations --apply-staged fill_empty_staging.json
    python manage.py fix_translations --typo-check --batch 80    # report only
"""
import json
import os
import time
import traceback
from django.core.management.base import BaseCommand
from django.db import transaction

from api.models.vocab import Word, LearningPlanEntry
from .import_book import parse_definition, POS_RE


# ── B-class helpers ───────────────────────────────────────────────────────────

def needs_pos_split(definitions):
    if not isinstance(definitions, list):
        return False
    for d in definitions:
        if not isinstance(d, dict):
            return False
        meaning = (d.get('meaning') or '').lstrip()
        if POS_RE.match(meaning):
            return True
    return False


def normalize_pos(definitions):
    new_defs = []
    changed = False
    for d in definitions:
        meaning = (d.get('meaning') or '').strip()
        pos = (d.get('pos') or '').strip()
        if not meaning:
            new_defs.append({'pos': pos, 'meaning': meaning})
            continue
        if POS_RE.match(meaning):
            parsed, _ = parse_definition(meaning)
            if parsed:
                if pos and len(parsed) == 1 and not parsed[0]['pos']:
                    parsed[0]['pos'] = pos
                new_defs.extend(parsed)
                changed = True
            else:
                new_defs.append({'pos': pos, 'meaning': meaning})
        else:
            new_defs.append({'pos': pos, 'meaning': meaning})
    return new_defs, changed


# ── Shared LLM helper ─────────────────────────────────────────────────────────

def _ai():
    from api.core.ai_client import AIClient
    return AIClient(provider=os.environ.get('FIX_AI_PROVIDER', 'deepseek'))


def llm_json(system_prompt, user_prompt, retries=2):
    """Call AIClient with no user_id (skips AT deduction), expect a dict back.
    Returns dict or None on failure."""
    client = _ai()
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt},
    ]
    last_err = None
    for attempt in range(retries + 1):
        try:
            result = client.generate(
                messages,
                expect_json=True,
                temperature=0.2,
                user_id=None,
                cache=False,
            )
            # AIClient.generate may return (dict, at_cost) tuple in some paths, else dict
            if isinstance(result, tuple):
                result = result[0]
            if isinstance(result, dict):
                return result
            last_err = f'non-dict result: {type(result).__name__}'
        except Exception as e:
            last_err = f'{type(e).__name__}: {e}'
            traceback.print_exc()
        if attempt < retries:
            time.sleep(2)
    print(f'  [WARN] llm_json failed after retries: {last_err}')
    return None


# ── A-class: fill empty definitions ───────────────────────────────────────────

FILL_SYSTEM = (
    '你是雅思词典编辑。我会给你一批英文单词或短语，请按 IELTS 考试用语境，'
    '为每个条目输出最常用的 1-3 个义项的中文释义。\n'
    '输出 JSON 格式：{"items":[{"word":"<原词>","defs":[{"pos":"n.|v.|adj.|adv.|...","meaning":"中文释义"}]}]}。\n'
    '规则：\n'
    '1) pos 必须是英文缩写并带句点（如 n.、v.、adj.、adv.、prep.、conj.、pron.、num.、interj.）；\n'
    '   实在判断不出词性就留空字符串。\n'
    '2) meaning 是简短中文释义，多义项用中文分号"；"分隔；不要带词性前缀。\n'
    '3) 如果某个词是明显的拼写错误（如 suger、graden），仍按拼写错误返回，'
    '   但把 defs 置为 [] 并补一个字段 "typo_of":"正确拼写"。\n'
    '4) 序数词（1st、100th 等）、纯数字、人名不要乱编释义，defs=[]，加 "skip":"reason"。\n'
    '5) 不要添加任何 JSON 外的文字。'
)


def fill_empty(opts):
    """LLM-fill Word rows with empty definitions. Writes staging JSON."""
    qs = Word.objects.filter(definitions=[]).order_by('id')
    if opts['limit']:
        qs = qs[:opts['limit']]

    targets = list(qs.values_list('id', 'word'))
    print(f'[fill-empty] {len(targets)} empty-definition rows to process')

    batch_size = opts['batch'] or 20
    out_path = opts['staging']
    results = {'items': {}, 'meta': {'batch_size': batch_size, 'failures': []}}

    # Resume support: if staging file exists, skip words already in it
    if os.path.exists(out_path):
        try:
            with open(out_path, 'r', encoding='utf-8') as f:
                prev = json.load(f)
            results['items'] = prev.get('items', {})
            print(f'[fill-empty] Resuming: {len(results["items"])} already cached')
        except Exception:
            pass
    done = set(results['items'].keys())

    pending = [(i, w) for i, w in targets if w not in done]
    print(f'[fill-empty] {len(pending)} pending after resume filter')

    for batch_start in range(0, len(pending), batch_size):
        batch = pending[batch_start: batch_start + batch_size]
        words = [w for _, w in batch]
        user_prompt = '请为以下条目生成义项 JSON:\n' + '\n'.join(f'- {w}' for w in words)

        print(f'  batch {batch_start // batch_size + 1}/{(len(pending) + batch_size - 1) // batch_size}: {len(words)} words')
        data = llm_json(FILL_SYSTEM, user_prompt)
        if not data or 'items' not in data:
            results['meta']['failures'].append({'batch_start': batch_start, 'words': words})
            print(f'    [FAIL] saving failure, continuing')
            continue

        for item in data['items']:
            word = (item.get('word') or '').strip()
            if not word:
                continue
            results['items'][word.lower()] = item

        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f'    saved → {out_path} ({len(results["items"])} total)')

    print(f'[fill-empty] DONE. {len(results["items"])} cached; {len(results["meta"]["failures"])} failed batches.')
    print(f'  Review {out_path}, then run: python manage.py fix_translations --apply-staged {out_path}')


def apply_staged(opts):
    """Read staging JSON and write definitions back to DB."""
    path = opts['apply_staged']
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    items = data.get('items', {})
    print(f'[apply-staged] {len(items)} items in staging file')

    applied = 0
    skipped = 0
    typo_log = []

    with transaction.atomic():
        for key, item in items.items():
            word_text = (item.get('word') or key).strip()
            defs = item.get('defs') or []
            typo_of = item.get('typo_of')
            skip_reason = item.get('skip')

            if typo_of:
                typo_log.append((word_text, typo_of))

            if skip_reason:
                skipped += 1
                continue

            # Strict shape validation
            clean_defs = []
            for d in defs:
                if not isinstance(d, dict):
                    continue
                pos = (d.get('pos') or '').strip()
                meaning = (d.get('meaning') or '').strip()
                if not meaning:
                    continue
                clean_defs.append({'pos': pos, 'meaning': meaning})

            if not clean_defs:
                skipped += 1
                continue

            try:
                obj = Word.objects.get(word__iexact=word_text)
            except Word.DoesNotExist:
                skipped += 1
                continue

            # Only write if still empty (safety: don't clobber concurrent edits)
            if obj.definitions:
                skipped += 1
                continue

            obj.definitions = clean_defs
            obj.save(update_fields=['definitions', 'updated_at'])
            applied += 1

        if not opts['apply']:
            transaction.set_rollback(True)

    print(f'[apply-staged] {"APPLIED" if opts["apply"] else "DRY-RUN"}: '
          f'wrote {applied}, skipped {skipped}')
    if typo_log:
        print(f'[apply-staged] {len(typo_log)} typo flags (not auto-renamed):')
        for w, fix in typo_log[:30]:
            print(f'    {w}  ?->  {fix}')


# ── Typo check (report-only) ──────────────────────────────────────────────────

TYPO_SYSTEM = (
    '你是英语拼写检查员。我会给你一批词（可能含拼写错误，也可能含合法的多词短语）。\n'
    '只标记**明显的拼写错误**：如 suger、graden、recieve、occured。\n'
    '不要标记：1) 合法的英美拼写差异（color/colour 都对）；2) 多词短语；3) 复数 / 词形变化；4) 大小写问题。\n'
    '输出 JSON：{"typos":[{"word":"<原词>","correct":"<正确拼写>"}]}。如全部正确返回 {"typos":[]}。'
)


def typo_check(opts):
    qs = Word.objects.all().order_by('id')
    if opts['limit']:
        qs = qs[:opts['limit']]
    words = list(qs.values_list('word', flat=True))
    print(f'[typo-check] scanning {len(words)} words')

    batch_size = opts['batch'] or 80
    out_path = opts['staging'] if opts['staging'] != 'fill_empty_staging.json' else 'typo_check_report.json'

    found = []
    failures = []
    for i in range(0, len(words), batch_size):
        batch = words[i: i + batch_size]
        user_prompt = '请检查这批词:\n' + '\n'.join(f'- {w}' for w in batch)
        print(f'  batch {i // batch_size + 1}/{(len(words) + batch_size - 1) // batch_size}')
        data = llm_json(TYPO_SYSTEM, user_prompt)
        if not data:
            failures.append({'batch_start': i})
            continue
        for t in data.get('typos', []):
            found.append(t)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump({'typos': found, 'failures': failures}, f, ensure_ascii=False, indent=2)

    print(f'[typo-check] DONE. {len(found)} typos flagged → {out_path}')


# ── E-class: expand thin polysemous defs ──────────────────────────────────────

EXPAND_SYSTEM = (
    '你是雅思词典编辑。我会给你一批英文单词和它们当前数据库里的中文释义。\n'
    '你的任务：**只补充明显严重缺失的核心义项**，宁缺勿滥。\n'
    '\n'
    '【必须补充】当前释义只有 1 个词性，但该词另一词性是 IELTS 中常见用法。例如：\n'
    '  - storm 当前 "n. 暴风雨" → 补 v. 猛攻；怒骂\n'
    '  - lead 当前 "n. 铅" → 补 v. 引领；率领 / n. 领先\n'
    '  - flat 当前 "adj. 水平的" → 补 n. 公寓\n'
    '  - draw 当前 "v. 画" → 补 n. 平局；抽签\n'
    '\n'
    '【不要补充】以下情况一律 SKIP（不返回该词）：\n'
    '  - 单义简单名词（monday, garlic, coconut, basketball, strawberry, clarinet）\n'
    '  - 当前释义已经简短但准确（gloves=手套 / shirt=衬衫 已足够，不必加"一双""男式"）\n'
    '  - 仅微调或加同义词（如 hall=大厅 已够，不必加门厅/走廊）\n'
    '  - 序数词、日期、月份、星期\n'
    '  - 当前释义已涵盖核心多义\n'
    '\n'
    '输出 JSON：{"items":[{"word":"<原词>","add_defs":[{"pos":"...","meaning":"中文"}]}]}。\n'
    'pos 必须是带句点的缩写（n. v. adj. adv. prep. conj. pron.）。\n'
    'meaning 是简短中文释义，多个义项用中文分号"；"分隔，不带词性前缀。\n'
    '**只输出真正需要新增的条目**；不需要的词整条省略，不要返回 add_defs=[]。\n'
    '不要输出任何 JSON 外的文字。'
)


import re as _re
_CJK = _re.compile(r'[一-鿿]')


def expand_thin(opts):
    """Scan all single-def Words; batch through LLM; only insufficient ones get add_defs."""
    cjk_max = opts.get('cjk_max') or 14

    candidates = []
    for w in Word.objects.exclude(definitions=[]).iterator():
        if not isinstance(w.definitions, list) or len(w.definitions) != 1:
            continue
        d = w.definitions[0]
        if not isinstance(d, dict):
            continue
        m = d.get('meaning', '') or ''
        cjk = len(_CJK.findall(m))
        if cjk == 0 or cjk > cjk_max:
            continue
        candidates.append(w)

    if opts['limit']:
        candidates = candidates[:opts['limit']]
    print(f'[expand-thin] {len(candidates)} single-def candidates (cjk≤{cjk_max})')

    batch_size = opts['batch'] or 25
    out_path = opts['staging'] if opts['staging'] != 'fill_empty_staging.json' else 'expand_thin_staging.json'

    all_items = []
    failures = []

    # Resume
    if os.path.exists(out_path):
        try:
            prev = json.load(open(out_path, 'r', encoding='utf-8'))
            all_items = prev.get('items', [])
            done_words = {it['word'].lower() for it in all_items if 'word' in it}
            done_processed = set(prev.get('processed', []))
            candidates = [c for c in candidates if c.word.lower() not in done_processed]
            print(f'[expand-thin] Resuming: {len(all_items)} items already, '
                  f'{len(candidates)} candidates left')
        except Exception:
            done_processed = set()
    else:
        done_processed = set()

    for i in range(0, len(candidates), batch_size):
        batch = candidates[i: i + batch_size]
        lines = [f'- {w.word}: {json.dumps(w.definitions, ensure_ascii=False)}' for w in batch]
        user_prompt = '请审查并补充缺失义项：\n' + '\n'.join(lines)
        print(f'  batch {i // batch_size + 1}/{(len(candidates) + batch_size - 1) // batch_size}: '
              f'{len(batch)} words')
        data = llm_json(EXPAND_SYSTEM, user_prompt)
        if not data:
            failures.append({'batch_start': i})
            continue
        new_items = data.get('items', []) or []
        all_items.extend(new_items)
        for w in batch:
            done_processed.add(w.word.lower())

        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump({
                'items': all_items,
                'failures': failures,
                'processed': sorted(done_processed),
            }, f, ensure_ascii=False, indent=2)

    print(f'[expand-thin] DONE. {len(all_items)} flagged for expansion, '
          f'{len(failures)} failed batches → {out_path}')
    print(f'  Apply: python manage.py fix_translations --apply-expand {out_path} --apply')


def _format_full_zh(definitions):
    """Concatenate all definitions into a single string for entry.zh.
    Returns 'n. 铅；引领；率领; v. 引领, ...' style. Truncated to 480 chars
    (DB field is 500)."""
    if not isinstance(definitions, list):
        return ''
    parts = []
    for d in definitions:
        if not isinstance(d, dict):
            continue
        pos = (d.get('pos') or '').strip()
        meaning = (d.get('meaning') or '').strip()
        if not meaning:
            continue
        if pos:
            parts.append(f'{pos} {meaning}')
        else:
            parts.append(meaning)
    s = '; '.join(parts)
    if len(s) > 480:
        s = s[:477] + '...'
    return s


def sync_zh(opts):
    """Resync LearningPlanEntry.zh and VocabFSRS.zh from Word.definitions.
    Skips plan IDs listed in --skip-plans (default 16,3)."""
    skip_ids = {int(x) for x in (opts['skip_plans'] or '').split(',') if x.strip().isdigit()}
    print(f'[sync-zh] Skipping plan IDs: {sorted(skip_ids)}')

    # Build word → fresh zh map for all words in DB
    word_zh_map = {}
    for w in Word.objects.exclude(definitions=[]).iterator():
        word_zh_map[w.word.lower()] = _format_full_zh(w.definitions)
    print(f'[sync-zh] Indexed {len(word_zh_map)} words with definitions')

    # LearningPlanEntry
    plan_updated = 0
    plan_scanned = 0
    with transaction.atomic():
        qs = LearningPlanEntry.objects.select_related('plan').exclude(plan_id__in=skip_ids)
        for e in qs.iterator():
            plan_scanned += 1
            fresh = word_zh_map.get(e.word.lower())
            if fresh is None:
                continue
            if (e.zh or '').strip() == fresh.strip():
                continue
            if opts['apply']:
                e.zh = fresh
                e.save(update_fields=['zh'])
            plan_updated += 1
        if not opts['apply']:
            transaction.set_rollback(True)

    # VocabFSRS
    from api.models.vocab import VocabFSRS
    fsrs_updated = 0
    fsrs_scanned = 0
    with transaction.atomic():
        qs = VocabFSRS.objects.exclude(plan_id__in=skip_ids)
        for r in qs.iterator():
            fsrs_scanned += 1
            fresh = word_zh_map.get(r.word.lower())
            if fresh is None:
                continue
            if (r.zh or '').strip() == fresh.strip():
                continue
            if opts['apply']:
                r.zh = fresh
                r.save(update_fields=['zh'])
            fsrs_updated += 1
        if not opts['apply']:
            transaction.set_rollback(True)

    label = 'APPLIED' if opts['apply'] else 'DRY-RUN'
    print(f'[sync-zh] LearningPlanEntry: scanned {plan_scanned}, {label} {plan_updated} updates')
    print(f'[sync-zh] VocabFSRS:         scanned {fsrs_scanned}, {label} {fsrs_updated} updates')


def apply_expand(opts):
    path = opts['apply_expand']
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    items = data.get('items', [])
    print(f'[apply-expand] {len(items)} items to merge')

    applied = 0
    with transaction.atomic():
        for item in items:
            word_text = (item.get('word') or '').strip()
            add_defs = item.get('add_defs') or []
            if not word_text or not add_defs:
                continue
            try:
                obj = Word.objects.get(word__iexact=word_text)
            except Word.DoesNotExist:
                continue
            existing_keys = {(d.get('pos', '').strip(), d.get('meaning', '').strip())
                             for d in obj.definitions or []}
            merged = list(obj.definitions or [])
            for d in add_defs:
                pos = (d.get('pos') or '').strip()
                meaning = (d.get('meaning') or '').strip()
                if not meaning or (pos, meaning) in existing_keys:
                    continue
                merged.append({'pos': pos, 'meaning': meaning})
                existing_keys.add((pos, meaning))
            if len(merged) > len(obj.definitions or []):
                obj.definitions = merged
                obj.save(update_fields=['definitions', 'updated_at'])
                applied += 1
        if not opts['apply']:
            transaction.set_rollback(True)
    print(f'[apply-expand] {"APPLIED" if opts["apply"] else "DRY-RUN"}: merged {applied}')


# ── Original B-class command ──────────────────────────────────────────────────

def pos_split(opts):
    qs = Word.objects.exclude(definitions=[])
    if opts['limit']:
        qs = qs[:opts['limit']]

    report = [f"Mode: pos-split  apply={opts['apply']}", '=' * 78]
    changed_count = 0
    scanned = 0
    with transaction.atomic():
        for w in qs.iterator():
            scanned += 1
            if not needs_pos_split(w.definitions):
                continue
            new_defs, changed = normalize_pos(w.definitions)
            if not changed:
                continue
            changed_count += 1
            report.append(f'#{w.id} {w.word}')
            report.append(f'  BEFORE: {json.dumps(w.definitions, ensure_ascii=False)}')
            report.append(f'  AFTER : {json.dumps(new_defs, ensure_ascii=False)}')
            report.append('')
            if opts['apply']:
                w.definitions = new_defs
                w.save(update_fields=['definitions', 'updated_at'])
        if not opts['apply']:
            transaction.set_rollback(True)
    report.append('=' * 78)
    report.append(f'Scanned: {scanned}    Changed: {changed_count}')
    report.append(f'Mode: {"APPLIED" if opts["apply"] else "DRY-RUN (rolled back)"}')
    with open(opts['out'], 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))
    print(f'Scanned {scanned}, would-change {changed_count}. Report -> {opts["out"]}')


# ── Django command entry ──────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Fix unreasonable Chinese translations (multi-mode)'

    def add_arguments(self, parser):
        parser.add_argument('--pos-split', action='store_true')
        parser.add_argument('--fill-empty', action='store_true')
        parser.add_argument('--apply-staged', default=None,
                            help='Path to staging JSON to apply')
        parser.add_argument('--typo-check', action='store_true')
        parser.add_argument('--expand-thin', action='store_true')
        parser.add_argument('--apply-expand', default=None,
                            help='Path to expand-thin staging JSON to apply')
        parser.add_argument('--sync-zh', action='store_true',
                            help='Resync LearningPlanEntry.zh and VocabFSRS.zh from Word.definitions')
        parser.add_argument('--skip-plans', default='16,3',
                            help='Comma-separated plan IDs to skip during --sync-zh '
                                 '(default 16,3 — plan#16 uses intentional synonym groups)')

        parser.add_argument('--apply', action='store_true',
                            help='Write changes to DB. Default is dry-run.')
        parser.add_argument('--out', default='fix_translations_diff.txt')
        parser.add_argument('--staging', default='fill_empty_staging.json')
        parser.add_argument('--limit', type=int, default=0)
        parser.add_argument('--batch', type=int, default=0)
        parser.add_argument('--cjk-max', type=int, default=14,
                            help='expand-thin: only check single-def words with ≤N CJK chars')

    def handle(self, *args, **opts):
        modes = sum([
            bool(opts['pos_split']),
            bool(opts['fill_empty']),
            bool(opts['apply_staged']),
            bool(opts['typo_check']),
            bool(opts['expand_thin']),
            bool(opts['apply_expand']),
            bool(opts['sync_zh']),
        ])
        if modes == 0:
            self.stdout.write(self.style.ERROR(
                'Pick a mode: --pos-split | --fill-empty | --apply-staged FILE | '
                '--typo-check | --expand-thin | --apply-expand FILE'))
            return
        if modes > 1:
            self.stdout.write(self.style.ERROR('One mode at a time, please.'))
            return

        if opts['pos_split']:
            pos_split(opts)
        elif opts['fill_empty']:
            fill_empty(opts)
        elif opts['apply_staged']:
            apply_staged(opts)
        elif opts['typo_check']:
            typo_check(opts)
        elif opts['expand_thin']:
            expand_thin(opts)
        elif opts['apply_expand']:
            apply_expand(opts)
        elif opts['sync_zh']:
            sync_zh(opts)
