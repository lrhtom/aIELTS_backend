"""Fix Word.word typos by migrating refs to the correct word, then deleting.

For each (bad, good) pair:
  - If good already exists: move all WordBookMembership and NotebookWord
    refs from bad → good, then delete bad.
  - If good doesn't exist: rename bad → good directly.

Dry-run by default. Pass --apply to commit.
"""
import os
import sys
import io
import django

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.db import transaction
from api.models.vocab import Word, WordBookMembership, NotebookWord, VocabFSRS, LearningPlanEntry


TYPOS = [
    ('suger', 'sugar'),
    ('chooce', 'choose'),
    ('fider', 'fibre'),
    ('graden', 'garden'),
    ('hostal', 'hostel'),
    ('calender', 'calendar'),
    ('galler', 'gallery'),
    ('supplie', 'supply'),
    ('unbanization', 'urbanization'),
]


def migrate_or_rename(bad: str, good: str, apply: bool):
    bad_obj = Word.objects.filter(word__iexact=bad).first()
    if not bad_obj:
        print(f'  [skip] {bad} not in DB')
        return
    good_obj = Word.objects.filter(word__iexact=good).first()

    # Counts that reference bad_obj
    mem_count = WordBookMembership.objects.filter(word=bad_obj).count()
    nb_count = NotebookWord.objects.filter(word=bad_obj).count()
    # VocabFSRS / LearningPlanEntry use word as string, not FK
    fsrs_count = VocabFSRS.objects.filter(word__iexact=bad).count()
    plan_count = LearningPlanEntry.objects.filter(word__iexact=bad).count()

    if good_obj:
        # Merge path
        print(f'  MERGE {bad} (id={bad_obj.id}) → {good} (id={good_obj.id})  '
              f'memberships={mem_count} notebook_entries={nb_count} '
              f'fsrs={fsrs_count} plan_entries={plan_count}')
        if apply:
            # Re-point WordBookMembership — skip if would dup (book,good)
            for m in WordBookMembership.objects.filter(word=bad_obj):
                exists = WordBookMembership.objects.filter(word=good_obj, book=m.book).exists()
                if exists:
                    m.delete()
                else:
                    m.word = good_obj
                    m.save(update_fields=['word'])
            # Re-point NotebookWord — skip if would dup (notebook, good)
            for nw in NotebookWord.objects.filter(word=bad_obj):
                exists = NotebookWord.objects.filter(notebook=nw.notebook, word=good_obj).exists()
                if exists:
                    nw.delete()
                else:
                    nw.word = good_obj
                    nw.save(update_fields=['word'])
            # Rename string columns
            VocabFSRS.objects.filter(word__iexact=bad).update(word=good)
            LearningPlanEntry.objects.filter(word__iexact=bad).update(word=good)
            bad_obj.delete()
    else:
        # Pure rename path
        print(f'  RENAME {bad} (id={bad_obj.id}) → {good}  '
              f'memberships={mem_count} notebook_entries={nb_count} '
              f'fsrs={fsrs_count} plan_entries={plan_count}')
        if apply:
            bad_obj.word = good
            bad_obj.save(update_fields=['word', 'updated_at'])
            VocabFSRS.objects.filter(word__iexact=bad).update(word=good)
            LearningPlanEntry.objects.filter(word__iexact=bad).update(word=good)


def main():
    apply = '--apply' in sys.argv
    print(f'Mode: {"APPLY" if apply else "DRY-RUN"}')
    print()
    with transaction.atomic():
        for bad, good in TYPOS:
            migrate_or_rename(bad, good, apply)
        if not apply:
            transaction.set_rollback(True)
    print()
    print(f'{"APPLIED" if apply else "DRY-RUN (rolled back)"}')


if __name__ == '__main__':
    main()
