"""
Generic vocabulary book importer.

Usage:
    python manage.py import_book --name "刘洪波雅思真经" --file data/liuhongbo.tsv
"""
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import VocabBook, Word, WordBookMembership

# Regex that matches POS tags like  n.  v.  adj.  adv.  etc.
POS_RE = re.compile(
    r'(n\.|v\.|adj\.|adv\.|prep\.|int\.|num\.|det\.|ord\.|pron\.|conj\.)'
)

SKIP_RE = [
    re.compile(r'^Chapter', re.IGNORECASE),
    re.compile(r'^单词\s'),
    re.compile(r'^\s*$'),
]


def parse_definition(raw: str):
    """
    Parse  'n. 地幔; 斗篷 v. 覆盖'
    into   ([{pos:'n.', meaning:'地幔; 斗篷'}, {pos:'v.', meaning:'覆盖'}], 'n. v.')
    """
    raw = raw.strip()
    if not raw:
        return [], ''

    # Find every POS tag and its start position
    matches = list(POS_RE.finditer(raw))
    if not matches:
        return [{'pos': '', 'meaning': raw}], ''

    defs = []
    grammar_parts = []
    for i, m in enumerate(matches):
        pos = m.group(1)
        grammar_parts.append(pos)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        meaning = raw[start:end].strip().rstrip(';').strip()
        if meaning:
            defs.append({'pos': pos, 'meaning': meaning})

    return defs, ' '.join(grammar_parts)


class Command(BaseCommand):
    help = 'Import a vocabulary book from a TSV file (word<TAB>definition)'

    def add_arguments(self, parser):
        parser.add_argument('--name', required=True)
        parser.add_argument('--file', required=True)
        parser.add_argument('--description', default='')

    def handle(self, *args, **options):
        file_path = options['file']

        # ── 1. Read & parse ────────────────────────────────────────────
        entries = []
        with open(file_path, encoding='utf-8') as f:
            for line in f:
                line = line.rstrip('\n\r')
                if any(p.match(line) for p in SKIP_RE):
                    continue
                parts = line.split('\t', 1)
                if len(parts) < 2:
                    continue
                word_text = parts[0].strip()
                definition = parts[1].strip()
                if not word_text:
                    continue
                entries.append((word_text, definition))

        self.stdout.write(f'Parsed {len(entries)} word entries from {file_path}')

        # ── 2. Import ─────────────────────────────────────────────────
        with transaction.atomic():
            book, created = VocabBook.objects.get_or_create(
                name=options['name'],
                defaults={'description': options['description']},
            )
            action = 'Created' if created else 'Found existing'
            self.stdout.write(f'{action} book: {book.name}')

            new_words = 0
            new_memberships = 0

            for order, (word_text, raw_def) in enumerate(entries, 1):
                definitions, grammar = parse_definition(raw_def)

                word_obj, w_created = Word.objects.get_or_create(
                    word=word_text,
                    defaults={
                        'grammar': grammar,
                        'definitions': definitions,
                    },
                )
                if w_created:
                    new_words += 1

                _, m_created = WordBookMembership.objects.get_or_create(
                    word=word_obj,
                    book=book,
                    defaults={'order': order},
                )
                if m_created:
                    new_memberships += 1

            book.word_count = book.memberships.count()
            book.save(update_fields=['word_count'])

        self.stdout.write(self.style.SUCCESS(
            f'Done!  new_words={new_words}  new_memberships={new_memberships}  '
            f'book_total={book.word_count}'
        ))
