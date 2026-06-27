"""Audit vocab translations — flags suspect rows, writes UTF-8 report.

Categories (all read-only, no DB writes):
  A. Empty / missing — Word.definitions == [] or no Chinese in any meaning
  B. Schema-bad   — definitions item is not the {pos,meaning} dict shape, or
                    'meaning' contains "n./v./adj." prefix instead of being in pos
  C. Suspect-long — meaning > 80 CJK chars (often AI-truncated dump)
  D. Non-Chinese  — definitions/zh that contain no CJK chars at all
  E. Schoolbook  vs  IELTS bias — single-meaning entry where the word is
                    famously polysemous in IELTS context (lead, flat, post,
                    mean, ground, etc.) — heuristic list
  F. Plan-entry word-column anomaly — word column has space/slash/comma
                    (i.e. a phrase row that shouldn't sit in a word table)
  G. Plan-entry zh mismatch — zh field contains only ASCII (English, not zh)
"""
import os, sys, io, re, json
import django

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from api.models.vocab import Word, LearningPlan, LearningPlanEntry

CJK_RE = re.compile(r'[一-鿿]')
POS_PREFIX_RE = re.compile(r'^\s*(n|v|adj|adv|prep|conj|pron|num|art|interj)\.\s*', re.IGNORECASE)
# Known polysemous IELTS-relevant words to flag if they only have one short meaning
POLY = {
    'lead', 'flat', 'post', 'mean', 'ground', 'spring', 'fair', 'fine',
    'plant', 'bear', 'kind', 'right', 'left', 'park', 'bank', 'play',
    'race', 'present', 'subject', 'object', 'matter', 'state', 'point',
    'mark', 'order', 'note', 'force', 'fire', 'cool', 'just', 'long',
    'rest', 'rule', 'sound', 'spell', 'square', 'star', 'still', 'stick',
    'stress', 'tend', 'term', 'tip', 'train', 'turn', 'wave', 'will',
    'work', 'yard', 'last', 'light', 'figure', 'face', 'set', 'run',
    'draw', 'cross', 'check', 'capital', 'arms', 'address', 'account',
}

results = {k: [] for k in 'ABCDEFG'}


def cjk_chars(s):
    return len(CJK_RE.findall(s or ''))


def has_cjk(s):
    return bool(CJK_RE.search(s or ''))


# ── Word table ──
for w in Word.objects.all().iterator():
    defs = w.definitions or []
    flat_zh = []
    for d in defs:
        if isinstance(d, dict):
            flat_zh.append(d.get('meaning', '') or '')
        elif isinstance(d, str):
            flat_zh.append(d)

    if not defs:
        results['A'].append((w.id, w.word, repr(defs)))
        continue
    if not any(has_cjk(s) for s in flat_zh):
        results['D'].append((w.id, w.word, repr(defs)[:120]))

    bad_schema = False
    for d in defs:
        if not isinstance(d, dict) or set(d.keys()) - {'pos', 'meaning', 'examples'}:
            bad_schema = True
            break
        m = d.get('meaning', '') or ''
        if POS_PREFIX_RE.match(m):
            bad_schema = True
            break
    if bad_schema:
        results['B'].append((w.id, w.word, repr(defs)[:160]))

    longest = max((cjk_chars(s) for s in flat_zh), default=0)
    if longest > 80:
        results['C'].append((w.id, w.word, longest, repr(defs)[:140]))

    if w.word.lower() in POLY:
        # flag if total ≤ ~5 CJK chars across all defs (too thin for polysemous word)
        total = sum(cjk_chars(s) for s in flat_zh)
        if total <= 5:
            results['E'].append((w.id, w.word, repr(defs)))

# ── LearningPlanEntry table ──
for e in LearningPlanEntry.objects.select_related('plan').iterator():
    w = e.word or ''
    if re.search(r'[\s/,]', w):
        results['F'].append((e.id, e.plan_id, w[:60], repr(e.zh)[:60]))
    if e.zh and not has_cjk(e.zh):
        results['G'].append((e.id, e.plan_id, w[:60], repr(e.zh)[:80]))


# ── Write report ──
lines = []
lines.append(f'Word total: {Word.objects.count()}    LearningPlanEntry total: {LearningPlanEntry.objects.count()}')
lines.append('')
TITLES = {
    'A': 'A. EMPTY definitions (Word.definitions == [])',
    'B': 'B. SCHEMA issues (non-dict shape, or "n./v." prefix bled into meaning)',
    'C': 'C. SUSPECT-LONG meaning (>80 CJK chars, likely AI dump / truncated)',
    'D': 'D. NON-CHINESE definitions (no CJK chars anywhere)',
    'E': 'E. POLYSEMOUS-IELTS word with single thin meaning (manual review)',
    'F': 'F. PLAN entry word column contains space/slash/comma (phrase row)',
    'G': 'G. PLAN entry zh column is English-only (no CJK)',
}
for k, title in TITLES.items():
    rows = results[k]
    lines.append('=' * 78)
    lines.append(f'{title} — count={len(rows)}')
    lines.append('=' * 78)
    for r in rows[:60]:
        lines.append('  ' + '  |  '.join(str(x) for x in r))
    if len(rows) > 60:
        lines.append(f'  ... (+{len(rows) - 60} more)')
    lines.append('')

report = '\n'.join(lines)
print(report[:4000])
with open('translation_audit.txt', 'w', encoding='utf-8') as f:
    f.write(report)
print('\n--- full report → translation_audit.txt ---')

# Summary counts to stderr for quick eyeball
summary = {k: len(v) for k, v in results.items()}
print('SUMMARY:', summary)
