import os
import django
import sys
import json
import urllib.request
import urllib.parse
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from api.models import LearningPlanEntry, Word, VocabFSRS

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
        pass
    return ""

def _extract_zh_from_defs(defs):
    if isinstance(defs, list) and defs:
        for d in defs:
            if 'meaning' in d and any('\u4e00' <= char <= '\u9fff' for char in str(d['meaning'])):
                return d['meaning']
        return defs[0].get('meaning', '')
    return ''

def run():
    print("--- 全局扫描并修复所有的为空的 LearningPlanEntry 和 VocabFSRS 的 zh ---")
    
    empty_entries = list(LearningPlanEntry.objects.filter(zh__exact=''))
    empty_entries += list(LearningPlanEntry.objects.filter(zh__isnull=True))
    empty_entries = [e for e in empty_entries if not e.zh or not e.zh.strip()]

    empty_cards = list(VocabFSRS.objects.filter(zh__exact=''))
    empty_cards += list(VocabFSRS.objects.filter(zh__isnull=True))
    empty_cards = [c for c in empty_cards if not c.zh or not c.zh.strip()]
    
    print(f"找到 {len(empty_entries)} 个缺失 zh 的 LearningPlanEntry 实例。")
    print(f"找到 {len(empty_cards)} 个缺失 zh 的 VocabFSRS (复习卡) 实例。")
    
    words_needed = set(e.word for e in empty_entries) | set(c.word for c in empty_cards)
    print(f"共涉及 {len(words_needed)} 个不同的单词。")

    if not words_needed:
        print("无空缺字段，已完美修复。")
        return

    global_word_objs = {w.word: w for w in Word.objects.filter(word__in=words_needed)}
    translations = {}
    
    for w_str in words_needed:
        w_obj = global_word_objs.get(w_str)
        if w_obj and w_obj.definitions:
            zh = _extract_zh_from_defs(w_obj.definitions)
            if zh:
                translations[w_str] = zh

    remaining_words = words_needed - set(translations.keys())
    if remaining_words:
        print(f"有 {len(remaining_words)} 个单词内部完全没有中文释义，开始外网查询...")
        for i, word in enumerate(remaining_words):
            zh = youdao_translate(word)
            if zh:
                translations[word] = zh
                print(f"[{i+1}/{len(remaining_words)}] {word} -> {zh}")
            time.sleep(0.1)

    # Update LearningPlanEntry
    updated_entries = []
    for e in empty_entries:
        if e.word in translations:
            e.zh = translations[e.word]
            updated_entries.append(e)

    if updated_entries:
        batch_size = 500
        for i in range(0, len(updated_entries), batch_size):
            LearningPlanEntry.objects.bulk_update(updated_entries[i:i+batch_size], ['zh'])
    print(f"成功填充并更新了 {len(updated_entries)} 条 LearningPlanEntry")

    # Update VocabFSRS
    updated_cards = []
    for c in empty_cards:
        if c.word in translations:
            c.zh = translations[c.word]
            updated_cards.append(c)

    if updated_cards:
        batch_size = 500
        for i in range(0, len(updated_cards), batch_size):
            VocabFSRS.objects.bulk_update(updated_cards[i:i+batch_size], ['zh'])
    print(f"成功填充并更新了 {len(updated_cards)} 条 VocabFSRS")

    print("--- 修复完美收官 ---")

if __name__ == '__main__':
    run()
