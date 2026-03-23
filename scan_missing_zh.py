import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.contrib.auth import get_user_model
from api.models import VocabBook, WordBookMembership, LearningPlan, LearningPlanEntry, Word

User = get_user_model()

def run():
    print("--- 扫描: 刘洪波官方词汇 ---")
    books = VocabBook.objects.filter(name__icontains='刘洪波')
    if not books.exists():
        print("未找到包含'刘洪波'的词书")
    else:
        for book in books:
            memberships = WordBookMembership.objects.filter(book=book).select_related('word')
            missing_words = []
            for m in memberships:
                w = m.word
                has_zh = False
                if w.definitions:
                    for d in w.definitions:
                        if 'meaning' in d and any('\u4e00' <= char <= '\u9fff' for char in str(d['meaning'])):
                            has_zh = True
                            break
                if not has_zh:
                    missing_words.append(w.word)
            print(f"词书 [{book.name}] (共 {memberships.count()} 词): 缺失中文释义 {len(missing_words)} 词")
            if len(missing_words) > 0:
                print(f"样例: {missing_words[:20]}")

    print("\n--- 扫描: lrhtom 的 雅思必会单词 计划 ---")
    user = User.objects.filter(username='lrhtom').first()
    if not user:
        print("未找到用户 lrhtom")
        plans = LearningPlan.objects.filter(name__icontains='雅思必会')
    else:
        plans = LearningPlan.objects.filter(user=user, name__icontains='雅思必会')
    
    for plan in plans:
        entries = LearningPlanEntry.objects.filter(plan=plan)
        missing_entries = []
        for e in entries:
            if not e.zh or e.zh.strip() == '':
                missing_entries.append(e.word)
        print(f"计划 [{plan.name}] (共 {entries.count()} 词): 缺失中文(zh字段为空) {len(missing_entries)} 词")
        if len(missing_entries) > 0:
            print(f"样例: {missing_entries[:20]}")

if __name__ == '__main__':
    run()
