import re

with open('api/vocab/learning_plan_views.py', 'r', encoding='utf-8') as f:
    code = f.read()

new_views = '''

# ─────────────────────────────────────────────────────────────────
# Story Mode — Click-to-learn story reading mode
# ─────────────────────────────────────────────────────────────────

class StoryModeGenerateView(APIView):
    """GET /plans/:id/story-mode/ — generate or retrieve today's story."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        plan = get_object_or_404(LearningPlan, pk=pk, user=request.user)
        today = _user_today()
        force_refresh = str(request.query_params.get('refresh', '')).strip().lower() in {'1', 'true', 'yes'}

        entries = list(plan.entries.all())
        word_zh_map = {e.word.lower(): e.zh for e in entries}

        if not force_refresh:
            cached = StoryModeCache.objects.filter(
                user=request.user, plan=plan, date=today,
            ).first()
            if cached:
                boundaries = _build_boundaries(cached.story_text)
                titles = cached.story_title.split('\\n')
                for i, b in enumerate(boundaries):
                    if i < len(titles):
                        b['title'] = titles[i]
                return Response({
                    'story_title': cached.story_title,
                    'story_text': cached.story_text,
                    'clicked_words': cached.clicked_words,
                    'target_words': cached.target_words,
                    'article_boundaries': boundaries,
                    'cached': True,
                    'atConsumed': 0,
                })

        limit_resp = check_rate_limit(request.user.id, 'story_mode_generate', max_calls=5, window=300)
        if limit_resp:
            return limit_resp

        if not entries:
            return Response({'error': '计划中没有单词，请先添加单词'}, status=400)

        all_cards = list(
            VocabFSRS.objects.filter(user=request.user, word__in=[e.word for e in entries], plan_id=plan.pk).order_by('due')
        )
        _, session_cards, _ = _build_today_summary(plan, all_cards)
        target_words = [c.word for c in session_cards]

        if not target_words:
            return Response({'error': '今天没有需要学习的单词'}, status=400)

        word_count = len(target_words)
        num_groups = max(1, (word_count - 1) // 100)
        group_size = (word_count + num_groups - 1) // num_groups
        word_groups = [target_words[i:i + group_size] for i in range(0, word_count, group_size)]

        provider = request.headers.get('X-AI-Provider', 'deepseek')
        client = AIClient(provider=provider)

        all_titles = []
        all_texts = []
        total_at_cost = 0

        for gi, group_words in enumerate(word_groups):
            words_str = ', '.join(group_words)
            prompt = STORY_MODE_PROMPT.format(words=words_str)
            scope = f'story_mode_{plan.pk}_{today.isoformat()}_g{gi}'

            try:
                response_data, at_cost = client.generate(
                    [{'role': 'user', 'content': prompt}],
                    expect_json=True,
                    temperature=0.8,
                    user_id=request.user.id,
                    singleflight_scope=scope,
                )
                total_at_cost += at_cost
            except Exception as e:
                return Response({'error': f'AI 生成第{gi + 1}组失败: {str(e)}'}, status=500)

            if not isinstance(response_data, dict):
                return Response({'error': f'AI 第{gi + 1}组返回的不是合法的 JSON 对象'}, status=500)

            title = str(response_data.get('story_title', f'Story {gi + 1}')).strip()
            text = str(response_data.get('story_text', '')).strip()

            if not text:
                return Response({'error': f'AI 第{gi + 1}组返回内容不完整（缺少 story_text）'}, status=500)

            text = text.replace('\\r\\n', '\\n').replace('\\r', '\\n')

            # Validate missing words
            text_lower = text.lower()
            missing = [w for w in group_words if w.lower() not in text_lower]
            if missing:
                text += "\\n\\n[附加] "
                for w in missing:
                    text += f"[[{w}|{word_zh_map.get(w.lower(), '')}]], "
                text = text.rstrip(", ")

            all_titles.append(title)
            all_texts.append(text)

        concatenated_text = ARTICLE_SEPARATOR.join(all_texts)
        concatenated_titles = '\\n'.join(all_titles)

        StoryModeCache.objects.update_or_create(
            user=request.user,
            plan=plan,
            date=today,
            defaults={
                'story_title': concatenated_titles,
                'story_text': concatenated_text,
                'target_words': target_words,
                'ai_provider': provider,
            }
        )
        
        boundaries = _build_boundaries(concatenated_text)
        titles = concatenated_titles.split('\\n')
        for i, b in enumerate(boundaries):
            if i < len(titles):
                b['title'] = titles[i]

        return Response({
            'story_title': concatenated_titles,
            'story_text': concatenated_text,
            'clicked_words': [],
            'target_words': target_words,
            'article_boundaries': boundaries,
            'cached': False,
            'atConsumed': total_at_cost,
        })


class StoryModeSaveProgressView(APIView):
    """POST /plans/:id/story-mode/save/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        plan = get_object_or_404(LearningPlan, pk=pk, user=request.user)
        clicked_words = request.data.get('clicked_words', [])
        
        if not isinstance(clicked_words, list):
            return Response({'error': 'clicked_words must be a list'}, status=400)

        today = _user_today()
        cache = StoryModeCache.objects.filter(user=request.user, plan=plan, date=today).first()
        if cache:
            cache.clicked_words = clicked_words
            cache.save(update_fields=['clicked_words', 'updated_at'])
            return Response({'status': 'ok'})
        return Response({'error': 'No story generated today'}, status=404)


class StoryModeCompleteView(APIView):
    """POST /plans/:id/story-mode/complete/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        plan = get_object_or_404(LearningPlan, pk=pk, user=request.user)
        today = _user_today()
        review_days = int(request.data.get('reviewDays', 0))

        cache = StoryModeCache.objects.filter(user=request.user, plan=plan, date=today).first()
        if not cache:
            return Response({'error': 'No story cache found for today'}, status=400)

        target_words = cache.target_words
        if not target_words:
            return Response({'error': 'No target words found'}, status=400)

        user = request.user
        entries = {e.word.lower(): e.zh for e in plan.entries.all()}
        
        now = timezone.now()
        marked_count = 0
        due_map = {}

        for w in target_words:
            w_low = w.lower()
            zh = entries.get(w_low, '')
            
            fsrs, _ = VocabFSRS.objects.get_or_create(
                user=user,
                plan=plan,
                word=w_low,
                defaults={'zh': zh, 'due': now},
            )

            fsrs.scheduled_days = review_days
            if review_days > 0:
                fsrs.due = _next_day_midnight(now, review_days)
                fsrs.state = 2  # Review
            else:
                fsrs.due = now
                fsrs.state = 2

            update_fields = ['due', 'scheduled_days', 'state']

            if fsrs.state == 2:
                if fsrs.stability <= 0:
                    fsrs.stability = 1.0
                    update_fields.append('stability')
                if fsrs.difficulty <= 0:
                    fsrs.difficulty = 5.0
                    update_fields.append('difficulty')

            fsrs.last_review = now
            fsrs.reps = max(1, int(fsrs.reps or 0) + 1)
            update_fields.extend(['last_review', 'reps'])

            fsrs.save(update_fields=update_fields)

            _sync_notebook_mastery(user, w_low, fsrs)
            due_map[w_low] = fsrs.due.isoformat()
            marked_count += 1

        return Response({
            'marked_count': marked_count,
            'due_map': due_map,
        })
'''
if 'class StoryModeGenerateView' not in code:
    with open('api/vocab/learning_plan_views.py', 'a', encoding='utf-8') as f:
        f.write(new_views)
    print("Added StoryMode views")
else:
    print("StoryMode views already exist")
