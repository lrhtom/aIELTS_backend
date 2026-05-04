"""
Import parsed IELTS speaking question bank JSON into SpeakingTopicBank table.
Usage: python manage.py import_speaking_bank
"""
import json
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import SpeakingTopicBank


class Command(BaseCommand):
    help = 'Import parsed IELTS speaking question bank JSON into the database'

    def handle(self, *args, **options):
        json_path = os.path.join(
            os.path.dirname(__file__), '..', '..', '..', '..',
            'scripts', 'ielts_speaking_bank.json'
        )
        json_path = os.path.abspath(json_path)

        if not os.path.exists(json_path):
            self.stderr.write(f'File not found: {json_path}')
            return

        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        created = {'part1': 0, 'part2': 0}
        skipped = 0

        with transaction.atomic():
            # Clear existing data (full refresh)
            SpeakingTopicBank.objects.all().delete()

            # Part 1 topics
            for t in data.get('part1', []):
                if not t.get('topic_en') or not t.get('questions'):
                    skipped += 1
                    continue
                SpeakingTopicBank.objects.create(
                    part=1,
                    category=t.get('category', ''),
                    date='',
                    topic_en=t['topic_en'],
                    topic_zh='',
                    questions_json=t['questions'],
                    cue_card='',
                    bullet_points_json=[],
                )
                created['part1'] += 1

            # Part 2 topics (includes Part 3 questions)
            for t in data.get('part2', []):
                if not t.get('topic_zh') or (not t.get('cue_card') and not t.get('part3_questions')):
                    skipped += 1
                    continue
                SpeakingTopicBank.objects.create(
                    part=2,
                    category=t.get('category', ''),
                    date=t.get('date', ''),
                    topic_en='',
                    topic_zh=t['topic_zh'],
                    questions_json=[],
                    cue_card=t.get('cue_card', ''),
                    bullet_points_json=t.get('bullet_points', []),
                )
                created['part2'] += 1

                # Store Part 3 questions as separate entries (part=3)
                p3_qs = t.get('part3_questions', [])
                if p3_qs:
                    SpeakingTopicBank.objects.create(
                        part=3,
                        category=t.get('category', ''),
                        date=t.get('date', ''),
                        topic_en='',
                        topic_zh=t['topic_zh'],
                        questions_json=p3_qs,
                        cue_card='',
                        bullet_points_json=[],
                    )
                    created.setdefault('part3', 0)
                    created['part3'] += 1

        self.stdout.write(self.style.SUCCESS(
            f'Imported: Part1={created["part1"]}, Part2={created["part2"]}, '
            f'Part3={created.get("part3", 0)}, skipped={skipped}'
        ))
