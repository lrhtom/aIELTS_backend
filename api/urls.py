from django.urls import path
from .practice import reading_views
from .practice import listening_views
from .practice import speaking_views
from .practice import speaking_part1_views
from .practice import speaking_part23_views
from .practice import speaking_bank_views
from .practice import writing_views
from .practice import writing_chart_views
from .practice import writing_task2_views
from .practice import writing_ai_teacher_views
from .practice import writing_task1_ai_teacher_views
from .practice import writing_record_views
from .practice import ai_question_views
from .extra import prompt_views
from .auth import auth_views
from .auth import balance_views
from .auth import feedback_views
from .auth import background_views
from .auth import admin_views
from .auth.admin_views import AdminRoutesView
from .vocab import vocab_views
from .vocab import custom_memory_views
from .vocab import notebook_views
from .vocab import learning_plan_views
from .extra import store_views
from .extra import creative_workshop_views
from .extra import assistant_views
from .assistant_views import UserTodoItemViewSet, UserShortcutViewSet
from .extra import markdown_notes_views
from . import checkin_views
from . import inventory_views
from . import analytics_views
from . import finance_views
from .auth.auth_views import (
    SendVerificationCodeView, CustomLoginView, LogoutView, CookieAwareTokenRefreshView,
)
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
)

urlpatterns = [
    # ---- 鉴权与用�?API ----
    path('auth/register', auth_views.UserRegistrationView.as_view(), name='auth_register'),
    path('auth/send-code', SendVerificationCodeView.as_view(), name='auth_send_code'),
    path('auth/login', CustomLoginView.as_view(), name='token_obtain_pair'),
    path('auth/logout', LogoutView.as_view(), name='auth_logout'),
    path('auth/token/refresh', CookieAwareTokenRefreshView.as_view(), name='token_refresh'),
    path('auth/profile', auth_views.UserProfileView.as_view(), name='auth_profile'),
    path('auth/settings', auth_views.UserSettingsView.as_view(), name='user_settings'),
    path('auth/avatar', auth_views.AvatarUploadView.as_view(), name='avatar_upload'),
    path('auth/delete-account', auth_views.DeleteAccountView.as_view(), name='delete_account'),
    path('auth/background', background_views.BackgroundSettingsView.as_view(), name='user_background'),
    path('auth/background/image', background_views.BackgroundImageUploadView.as_view(), name='user_background_image'),
    path('auth/reset-password', auth_views.ResetPasswordView.as_view(), name='reset_password'),
    path('auth/change-username', auth_views.ChangeUsernameView.as_view(), name='change_username'),

    # ---- 签到 API ----
    path('checkin', checkin_views.daily_checkin, name='daily_checkin'),
    path('checkin/status', checkin_views.checkin_status, name='checkin_status'),
    path('checkin/makeup', checkin_views.makeup_checkin, name='makeup_checkin'),
    path('backpack', inventory_views.backpack, name='backpack'),

    # ---- AT币管�?API ----
    path('balance', balance_views.get_balance, name='get_balance'),
    path('balance/check', balance_views.check_balance, name='check_balance'),
    path('balance/consume', balance_views.consume_at, name='consume_at'),
    path('balance/add', balance_views.add_at, name='add_at'),

    # ---- 财政分析 API ----
    path('finance/stats', finance_views.finance_stats, name='finance_stats'),
    path('finance/transactions', finance_views.TransactionListView.as_view(), name='finance_transactions'),

    # ---- 商店 API ----
    path('store/products', store_views.list_products, name='list_products'),
    path('store/purchase', store_views.purchase_product, name='purchase_product'),
    path('store/cart/', store_views.cart_list, name='cart_list'),
    path('store/cart/add', store_views.cart_add, name='cart_add'),
    path('store/cart/remove', store_views.cart_remove, name='cart_remove'),
    path('store/cart/checkout', store_views.cart_checkout, name='cart_checkout'),

    # ---- 业务 API ----
    path('reading/generate', reading_views.generate_reading, name='generate_reading'),
    path('reading/full', reading_views.generate_reading_full, name='generate_reading_full'),
    path('reading/meta', reading_views.reading_meta, name='reading_meta'),
    path('listening/generate', listening_views.generate_listening, name='generate_listening'),
    path('listening/full', listening_views.generate_listening_full, name='generate_listening_full'),
    path('listening/meta', listening_views.listening_meta, name='listening_meta'),
    path('listening/audio', listening_views.generate_listening_audio, name='listening_audio'),
    path('speaking/chat', speaking_views.speaking_chat, name='speaking_chat'),
    path('speaking/transcribe', speaking_views.speaking_transcribe, name='speaking_transcribe'),
    path('speaking/check-scenario', speaking_views.check_scenario, name='check_scenario'),
    path('speaking/scenario-chat', speaking_views.scenario_chat, name='scenario_chat'),
    path('speaking/scenario-opening', speaking_views.scenario_opening, name='scenario_opening'),
    path('speaking/scenario/random', speaking_views.generate_random_scenario, name='generate_random_scenario'),
    path('speaking/session/start', speaking_views.speaking_session_start, name='speaking_session_start'),
    path('speaking/part1/generate', speaking_part1_views.generate_part1_questions, name='generate_part1_questions'),
    path('speaking/part1/evaluate', speaking_part1_views.evaluate_part1_answer, name='evaluate_part1_answer'),
    path('speaking/part1/summary', speaking_part1_views.generate_part1_summary, name='generate_part1_summary'),
    path('speaking/part2/generate', speaking_part23_views.generate_part2_questions, name='generate_part2_questions'),
    path('speaking/part2/evaluate', speaking_part23_views.evaluate_part2_answer, name='evaluate_part2_answer'),
    path('speaking/part2/summary', speaking_part23_views.generate_part2_summary, name='generate_part2_summary'),
    path('speaking/part3/generate', speaking_part23_views.generate_part3_questions, name='generate_part3_questions'),
    path('speaking/part3/evaluate', speaking_part23_views.evaluate_part3_answer, name='evaluate_part3_answer'),
    path('speaking/part3/summary', speaking_part23_views.generate_part3_summary, name='generate_part3_summary'),
    path('speaking/bank/part1/generate', speaking_bank_views.bank_generate_part1, name='bank_generate_part1'),
    path('speaking/bank/part2/generate', speaking_bank_views.bank_generate_part2, name='bank_generate_part2'),
    path('speaking/bank/part3/generate', speaking_bank_views.bank_generate_part3, name='bank_generate_part3'),
    path('writing/generate', writing_views.generate_writing, name='generate_writing'),
    path('writing/chat', writing_views.writing_chat, name='writing_chat'),
    path('writing/chart/generate', writing_chart_views.generate_chart, name='generate_chart'),
    path('writing/task2/generate', writing_task2_views.generate_task2, name='generate_task2'),
    path('writing/task2/opinion-drill/generate', writing_task2_views.generate_opinion_drill_questions, name='generate_opinion_drill_questions'),
    path('writing/task2/opinion-drill/evaluate', writing_task2_views.evaluate_opinion_drill_answer, name='evaluate_opinion_drill_answer'),
    path('writing/ai-teacher/generate', writing_ai_teacher_views.generate_ai_teacher_lesson, name='generate_ai_teacher_lesson'),
    path('writing/task1-ai-teacher/generate', writing_task1_ai_teacher_views.generate_task1_ai_teacher_lesson, name='generate_task1_ai_teacher_lesson'),
    
    # Writing Records
    path('writing/records', writing_record_views.writing_records_list, name='writing_records_list'),
    path('writing/records/<int:record_id>', writing_record_views.writing_record_detail, name='writing_record_detail'),

    # ---- AI 题库 API ----
    path('ai-questions/', ai_question_views.list_ai_questions, name='ai_question_list'),
    path('ai-questions/<int:pk>/', ai_question_views.ai_question_detail, name='ai_question_detail'),
    path('ai-questions/<int:pk>/submit/', ai_question_views.submit_ai_question, name='ai_question_submit'),
    path('ai-questions/<int:pk>/favorite/', ai_question_views.toggle_ai_question_favorite, name='ai_question_favorite'),

    path('prompts/', prompt_views.prompt_list, name='prompt_list'),
    path('prompts/<int:pk>/like/', prompt_views.prompt_like, name='prompt_like'),
    path('prompts/<int:pk>/favorite/', prompt_views.prompt_favorite, name='prompt_favorite'),
    path('feedback/submit', feedback_views.FeedbackCreateView.as_view(), name='feedback_submit'),

    # ---- 词汇 FSRS API ----
    path('vocab/sync',   vocab_views.VocabSyncView.as_view(),   name='vocab_sync'),
    path('vocab/cards',  vocab_views.VocabCardsView.as_view(),  name='vocab_cards'),
    path('vocab/review', vocab_views.VocabReviewView.as_view(), name='vocab_review'),
    path('custom-memory/decks/', custom_memory_views.CustomMemoryDeckCreateView.as_view(), name='custom_memory_deck_create'),
    path('custom-memory/decks/<int:pk>/append/', custom_memory_views.CustomMemoryDeckAppendView.as_view(), name='custom_memory_deck_append'),
    path('custom-memory/decks/<int:pk>/start/', custom_memory_views.CustomMemoryDeckStartView.as_view(), name='custom_memory_deck_start'),
    path('custom-memory/review/', custom_memory_views.CustomMemoryReviewView.as_view(), name='custom_memory_review'),

    # ---- 创意工坊 API ----
    path('creative-workshop/projects/', creative_workshop_views.CreativeWorkshopProjectListView.as_view(), name='creative_workshop_project_list'),
    path('creative-workshop/projects/generate/', creative_workshop_views.CreativeWorkshopProjectGenerateView.as_view(), name='creative_workshop_project_generate'),
    path('creative-workshop/projects/<int:pk>/', creative_workshop_views.CreativeWorkshopProjectDetailView.as_view(), name='creative_workshop_project_detail'),
    path('creative-workshop/projects/<int:pk>/favorite/', creative_workshop_views.CreativeWorkshopProjectFavoriteView.as_view(), name='creative_workshop_project_favorite'),
    path('creative-workshop/projects/<int:pk>/edit/', creative_workshop_views.CreativeWorkshopProjectEditView.as_view(), name='creative_workshop_project_edit'),

    # ---- Markdown 笔记 API ----
    path('markdown-notes/', markdown_notes_views.MarkdownNoteListView.as_view(), name='markdown_note_list'),
    path('markdown-notes/<int:pk>/', markdown_notes_views.MarkdownNoteDetailView.as_view(), name='markdown_note_detail'),

    
    # ---- 助手额外功能 API ----
    path('assistant/todos/', UserTodoItemViewSet.as_view({'get': 'list', 'post': 'create'}), name='assistant_todos'),
    path('assistant/todos/<int:pk>/', UserTodoItemViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'}), name='assistant_todo_detail'),
    path('assistant/todos/clear-completed/', UserTodoItemViewSet.as_view({'post': 'clear_completed'}), name='assistant_todo_clear_completed'),
    
    path('assistant/shortcuts/', UserShortcutViewSet.as_view({'get': 'list', 'post': 'create'}), name='assistant_shortcuts'),
    path('assistant/shortcuts/<int:pk>/', UserShortcutViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'}), name='assistant_shortcut_detail'),

    # ---- 全局助手 API ----
    path('assistant/personal-chat', assistant_views.personal_agent_chat, name='assistant_personal_chat'),
    path('assistant/mcp/capabilities', assistant_views.assistant_mcp_capabilities, name='assistant_mcp_capabilities'),
    path('assistant/mcp/route', assistant_views.assistant_mcp_route, name='assistant_mcp_route'),
    path('assistant/mcp/open-pages', assistant_views.assistant_mcp_open_pages, name='assistant_mcp_open_pages'),
    path('assistant/mcp/react-browser', assistant_views.assistant_mcp_react_browser, name='assistant_mcp_react_browser'),

    # ---- 笔记�?API ----
    path('notebooks/',                              notebook_views.NotebookListView.as_view(),      name='notebook_list'),
    path('notebooks/<int:pk>/',                     notebook_views.NotebookDetailView.as_view(),    name='notebook_detail'),
    path('notebooks/<int:pk>/words/',               notebook_views.NotebookWordListView.as_view(),  name='notebook_words'),
    path('notebooks/<int:pk>/words/<int:eid>/',     notebook_views.NotebookWordDetailView.as_view(),name='notebook_word_detail'),

    # ---- 学习计划 API ----
    path('plans/',                                  learning_plan_views.PlanListView.as_view(),         name='plan_list'),
    path('plans/<int:pk>/',                         learning_plan_views.PlanDetailView.as_view(),        name='plan_detail'),
    path('plans/<int:pk>/words/',                   learning_plan_views.PlanWordListView.as_view(),      name='plan_words'),
    path('plans/<int:pk>/words/<int:eid>/',         learning_plan_views.PlanWordDetailView.as_view(),    name='plan_word_detail'),
    path('plans/<int:pk>/start/',                   learning_plan_views.PlanStartView.as_view(),         name='plan_start'),
    path('plans/<int:pk>/article-copy/',           learning_plan_views.ArticleCopyGenerateView.as_view(), name='plan_article_copy'),
    path('plans/<int:pk>/article-copy/complete/',  learning_plan_views.ArticleCopyCompleteView.as_view(), name='plan_article_copy_complete'),
    path('plans/<int:pk>/article-copy/progress/',  learning_plan_views.ArticleCopyProgressView.as_view(), name='plan_article_copy_progress'),
    path('plans/<int:pk>/story-mode/',             learning_plan_views.StoryModeGenerateView.as_view(), name='plan_story_mode'),
    path('plans/<int:pk>/story-mode/complete/',    learning_plan_views.StoryModeCompleteView.as_view(), name='plan_story_mode_complete'),
    path('plans/<int:pk>/story-mode/save/',        learning_plan_views.StoryModeSaveProgressView.as_view(), name='plan_story_mode_save'),
    path('learning-time/today/',                    learning_plan_views.LearningTimeTodayView.as_view(), name='learning_time_today'),
    path('vocab/books/',                            learning_plan_views.VocabBookListView.as_view(),     name='vocab_book_list'),
    path('vocab/books/<int:pk>/words/',             learning_plan_views.VocabBookWordsView.as_view(),    name='vocab_book_words'),

    # ---- 管理后台 API ----
    path('admin/feedback', admin_views.AdminFeedbackListView.as_view(), name='admin_feedback_list'),   # reload-trigger
    path('admin/feedback/<int:pk>', admin_views.AdminFeedbackUpdateView.as_view(), name='admin_feedback_update'),
    path('admin/feedback/<int:pk>/delete', admin_views.AdminFeedbackDeleteView.as_view(), name='admin_feedback_delete'),
    path('admin/users', admin_views.AdminUserListView.as_view(), name='admin_user_list'),
    path('admin/users/<int:pk>/ban', admin_views.AdminUserBanToggleView.as_view(), name='admin_user_ban_toggle'),
    path('admin/users/<int:pk>/delete', admin_views.AdminUserDeleteView.as_view(), name='admin_user_delete'),
    path('admin/users/<int:pk>/adjust-at', admin_views.AdminUserAdjustATView.as_view(), name='admin_user_adjust_at'),
    path('admin/users/<int:pk>/promote', admin_views.AdminUserPromoteToggleView.as_view(), name='admin_user_promote_toggle'),
    path('admin/routes',                   AdminRoutesView.as_view(),                   name='admin_routes_live'),
    path('admin/ai-usage',                 admin_views.AdminAIUsageView.as_view(),       name='admin_ai_usage'),
    path('admin/code-stats',               admin_views.AdminCodeStatsView.as_view(),     name='admin_code_stats'),
    path('admin/users/search',             admin_views.AdminUserSearchView.as_view(),    name='admin_users_search'),
    path('admin/banned-ips',               admin_views.AdminBannedIPListView.as_view(),  name='admin_banned_ips'),
    path('admin/banned-ips/<int:pk>',      admin_views.AdminBannedIPDeleteView.as_view(),name='admin_banned_ip_delete'),
    path('admin/users/<int:pk>/ban-ip',    admin_views.AdminUserBanIPView.as_view(),     name='admin_user_ban_ip'),

    # ---- 学习分析 API ----
    path('analytics/vocab',                 analytics_views.VocabAnalyticsView.as_view(),     name='analytics_vocab'),
    path('analytics/scheduled-words',       analytics_views.ScheduledWordsView.as_view(),     name='analytics_scheduled_words'),
    path('analytics/writing',               analytics_views.WritingAnalyticsView.as_view(),   name='analytics_writing'),
    path('analytics/practice',              analytics_views.PracticeAnalyticsView.as_view(),  name='analytics_practice'),
    path('analytics/speaking',              analytics_views.SpeakingAnalyticsView.as_view(),  name='analytics_speaking'),
]
