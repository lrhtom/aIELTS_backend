"""Read-only survey of vocab translation data.

Run from backend/:  python survey_translations.py
Writes UTF-8 report to backend/translation_survey.txt
"""
import os
import sys
import io
import django

# Force UTF-8 stdout when piping; main report also written to file
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from collections import Counter
from api.models.vocab import VocabBook, Word, LearningPlan, LearningPlanEntry, WordBookMembership


REPORT = io.StringIO()
def out(s=''):
    print(s)
    REPORT.write(s + '\n')


def main():
    out('=' * 70)
    out('VOCAB BOOKS')
    out('=' * 70)
    for b in VocabBook.objects.all():
        n = WordBookMembership.objects.filter(book=b).count()
        out(f'  [{b.id:>3}] {b.name:<40} {n:>6} words   cached={b.word_count}')

    total_words = Word.objects.count()
    out(f'\nTotal Word rows: {total_words}')

    out('\n' + '=' * 70)
    out('LEARNING PLANS (per-user)')
    out('=' * 70)
    plans = LearningPlan.objects.select_related('user').all()
    out(f'Total plans: {plans.count()}')
    for p in plans[:40]:
        n = LearningPlanEntry.objects.filter(plan=p).count()
        out(f'  plan#{p.id:<5} user={p.user.username:<25} name={p.name:<25} entries={n}')

    out(f'Total LearningPlanEntry rows: {LearningPlanEntry.objects.count()}')

    out('\n' + '=' * 70)
    out('SAMPLE: Word.definitions JSON (random 30)')
    out('=' * 70)
    import random
    pks = list(Word.objects.values_list('pk', flat=True))
    random.seed(42)
    sample_pks = random.sample(pks, min(30, len(pks)))
    for w in Word.objects.filter(pk__in=sample_pks):
        out(f'  {w.word:<25} -> {w.definitions!r}')

    out('\n' + '=' * 70)
    out('SAMPLE: LearningPlanEntry.zh (random 30)')
    out('=' * 70)
    epks = list(LearningPlanEntry.objects.values_list('pk', flat=True))
    if epks:
        sample_epks = random.sample(epks, min(30, len(epks)))
        for e in LearningPlanEntry.objects.filter(pk__in=sample_epks).select_related('plan'):
            out(f'  plan#{e.plan_id} {e.word:<25} -> {e.zh!r}')

    out('\n' + '=' * 70)
    out('DEFINITIONS-EMPTY CHECK')
    out('=' * 70)
    empty_defs = Word.objects.filter(definitions=[]).count()
    out(f'Word rows with definitions == []: {empty_defs}')

    # Check first-def shape
    out('\nDefinitions shape histogram (first 200 words):')
    shapes = Counter()
    for w in Word.objects.all()[:200]:
        if not w.definitions:
            shapes['empty'] += 1
            continue
        d = w.definitions[0]
        if isinstance(d, dict):
            shapes[tuple(sorted(d.keys()))] += 1
        else:
            shapes[f'non-dict:{type(d).__name__}'] += 1
    for k, v in shapes.most_common():
        out(f'  {k}: {v}')


if __name__ == '__main__':
    main()
    with open('translation_survey.txt', 'w', encoding='utf-8') as f:
        f.write(REPORT.getvalue())
    print('--- report saved to translation_survey.txt ---')
