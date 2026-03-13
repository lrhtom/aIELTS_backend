"""
Management command: import words from data.sqlite → lrhtom's 雅思简单词 notebook.

Usage:
    python manage.py import_sqlite_words
    python manage.py import_sqlite_words --sqlite e:/path/to/data.sqlite
    python manage.py import_sqlite_words --dry-run
"""

import sqlite3
import os
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import User, Notebook, Word, NotebookWord, NotebookWordTag

SQLITE_PATH_DEFAULT = os.path.abspath(os.path.join(
    os.path.dirname(__file__),          # commands/
    '..', '..', '..', '..', 'data.sqlite',  # 4 levels up → aIELTS/
))


class Command(BaseCommand):
    help = 'Import words from data.sqlite into the target notebook'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sqlite',
            default=os.path.abspath(SQLITE_PATH_DEFAULT),
            help='Path to data.sqlite (default: <project_root>/data.sqlite)',
        )
        parser.add_argument(
            '--username',
            default='lrhtom',
            help='Target username (default: lrhtom)',
        )
        parser.add_argument(
            '--notebook',
            default='雅思简单词',
            help='Target notebook title (default: 雅思简单词)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview counts without writing to DB',
        )

    def handle(self, *args, **options):
        sqlite_path = options['sqlite']
        username    = options['username']
        nb_title    = options['notebook']
        dry_run     = options['dry_run']

        # ── 验证 sqlite 文件 ────────────────────────────────────────────────
        if not os.path.exists(sqlite_path):
            raise CommandError(f'找不到 SQLite 文件: {sqlite_path}')

        # ── 读取源数据 ──────────────────────────────────────────────────────
        conn = sqlite3.connect(sqlite_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            'SELECT word, tag, pos, meaning FROM word ORDER BY id'
        ).fetchall()
        conn.close()
        self.stdout.write(f'从 SQLite 读取到 {len(rows)} 条单词')

        if dry_run:
            self.stdout.write(self.style.WARNING('--dry-run 模式，不写入数据库'))
            for r in rows[:10]:
                self.stdout.write(f'  {r["word"]} | {r["pos"]} | {r["meaning"]} | [{r["tag"]}]')
            self.stdout.write('...')
            return

        # ── 获取目标用户和笔记本 ────────────────────────────────────────────
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'用户不存在: {username}')

        nb, created = Notebook.objects.get_or_create(
            user=user,
            title=nb_title,
            defaults={'cover_color': 'teal', 'description': '从本地词库导入'},
        )
        if created:
            self.stdout.write(f'已创建笔记本「{nb_title}」(id={nb.pk})')
        else:
            self.stdout.write(f'使用已有笔记本「{nb_title}」(id={nb.pk}，已有 {nb.entries.count()} 词)')

        # ── 批量写入 ────────────────────────────────────────────────────────
        added = skipped = 0

        with transaction.atomic():
            for row in rows:
                raw_word = (row['word'] or '').strip().lower()
                if not raw_word:
                    continue

                pos     = (row['pos']     or '').strip()
                meaning = (row['meaning'] or '').strip()
                tag     = (row['tag']     or '').strip().lower()

                # meaning 多义用 | 分隔，转中文分号
                zh = '；'.join(
                    p.strip() for p in meaning.split('|') if p.strip()
                )

                # 1. Get or create global Word
                word_obj, _ = Word.objects.get_or_create(word=raw_word)
                # 2. Write grammar (pos) if the Word doesn't have one yet
                if pos and not word_obj.grammar:
                    word_obj.grammar = pos
                    word_obj.save(update_fields=['grammar'])

                # 3. Create NotebookWord (skip if already exists)
                entry, created_entry = NotebookWord.objects.get_or_create(
                    notebook=nb,
                    word=word_obj,
                    defaults={'custom_zh': zh},
                )
                if not created_entry:
                    skipped += 1
                    continue

                added += 1

                # 4. Tag
                if tag:
                    NotebookWordTag.objects.get_or_create(
                        notebook_word=entry,
                        name=tag,
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f'完成：新增 {added} 词，跳过（已存在）{skipped} 词'
            )
        )
