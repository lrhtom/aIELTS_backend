import os
import django
import sys
import json
import urllib.request
import urllib.parse
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.contrib.auth import get_user_model
from api.models import VocabBook, WordBookMembership, LearningPlan, LearningPlanEntry, Word

User = get_user_model()

def youdao_translate(word):
    url = f"https://dict.youdao.com/suggest?q={urllib.parse.quote(word)}&num=1&doctype=json"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data.get('result', {}).get('code') == 200:
                entries = data.get('data', {}).get('entries', [])
                if entries:
                    explain = entries[0].get('explain', '')
                    if explain:
                        return explain
    except Exception as e:
        print(f"Error fetching {word}: {e}")
    return ""

def run():
    print("--- 扫描并收集所有的无中文词汇 ---")
    
    missing_words_set = set()
    
    # 1. 刘洪波官方词汇
    books = VocabBook.objects.filter(name__icontains='刘洪波')
    for book in books:
        memberships = WordBookMembership.objects.filter(book=book).select_related('word')
        for m in memberships:
            w = m.word
            has_zh = False
            if w.definitions:
                for d in w.definitions:
                    if 'meaning' in d and any('\u4e00' <= char <= '\u9fff' for char in str(d['meaning'])):
                        has_zh = True
                        break
            if not has_zh:
                missing_words_set.add(w.word)
    
    # 2. 雅思必会单词计划
    user = User.objects.filter(username='lrhtom').first()
    plans = LearningPlan.objects.filter(user=user, name__icontains='雅思必会') if user else LearningPlan.objects.filter(name__icontains='雅思必会')
    
    for plan in plans:
        entries = LearningPlanEntry.objects.filter(plan=plan)
        for e in entries:
            if not e.zh or e.zh.strip() == '':
                missing_words_set.add(e.word)
                
    print(f"总计找到 {len(missing_words_set)} 个需要修复的单词。开始在线获取释义...")
    
    word_zh_map = {}
    for i, word in enumerate(missing_words_set):
        zh = youdao_translate(word)
        if zh:
            word_zh_map[word] = zh
            print(f"[{i+1}/{len(missing_words_set)}] {word} -> {zh}")
        else:
            print(f"[{i+1}/{len(missing_words_set)}] {word} -> 获取失败")
        time.sleep(0.1) # be polite to API
        
    print("--- 获取完成，开始写入数据库 ---")
    
    # 写入 Word 表
    updated_words = 0
    words_to_update = []
    
    for word_text, zh in word_zh_map.items():
        w = Word.objects.filter(word=word_text).first()
        if w:
            if not w.definitions or not isinstance(w.definitions, list):
                w.definitions = []
            
            # Check if it already has Chinese, if not, append or overwrite
            has_zh = False
            for d in w.definitions:
                if 'meaning' in d and any('\u4e00' <= char <= '\u9fff' for char in str(d['meaning'])):
                    has_zh = True
                    break
            
            if not has_zh:
                w.definitions.append({"pos": "", "meaning": zh})
                words_to_update.append(w)
                updated_words += 1
                
    if words_to_update:
        Word.objects.bulk_update(words_to_update, ['definitions'])
    print(f"成功更新 Word (全局词库) 表的 {updated_words} 个单词")
    
    # 写入 LearningPlanEntry 表
    updated_entries = 0
    entries_to_update = []
    
    for plan in plans:
        entries = LearningPlanEntry.objects.filter(plan=plan)
        for e in entries:
            if (not e.zh or e.zh.strip() == '') and e.word in word_zh_map:
                e.zh = word_zh_map[e.word]
                entries_to_update.append(e)
                updated_entries += 1
                
    if entries_to_update:
        LearningPlanEntry.objects.bulk_update(entries_to_update, ['zh'])
    print(f"成功更新 LearningPlanEntry (个人计划缓存) 表的 {updated_entries} 个记录")
    
    print("修复完成！")

if __name__ == '__main__':
    run()
