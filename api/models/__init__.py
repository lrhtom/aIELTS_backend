"""api.models — split into per-domain modules.

Originally everything lived in one 865-line ``models.py``. Splitting by domain keeps
each file small and lets you grep "where does the X model live" by name. All
re-exports stay flat so ``from api.models import Foo`` continues to work unchanged
for every caller in the codebase.

Layout:

- ``user``       — User (AUTH_USER_MODEL)
- ``feedback``   — AIPrompt, Feedback (user-submitted)
- ``vocab``      — VocabBook, Word, WordBookMembership, Notebook, NotebookWord,
                    NotebookWordTag, VocabFSRS, LearningPlan, LearningPlanEntry,
                    ArticleCopyCache, StoryModeCache, CustomMemoryDeck,
                    CustomMemoryCard
- ``practice``   — SpeakingScenarioHistory, SpeakingTopicBank,
                    WritingServiceRecord, AIQuestion
- ``finance``    — TransactionRecord, StoreProduct, CartItem
- ``stats``      — UserDailyLearningTime, UserDailyStats
- ``assistant``  — UserTodoItem, UserShortcut, CreativeWorkshopPage, MarkdownNote
"""

from .user import User, BannedIP
from .feedback import AIPrompt, Feedback
from .vocab import (
    VocabBook,
    Word,
    WordBookMembership,
    Notebook,
    NotebookWord,
    NotebookWordTag,
    VocabFSRS,
    LearningPlan,
    LearningPlanEntry,
    ArticleCopyCache,
    StoryModeCache,
    CustomMemoryDeck,
    CustomMemoryCard,
)
from .practice import (
    SpeakingScenarioHistory,
    SpeakingTopicBank,
    WritingServiceRecord,
    AIQuestion,
)
from .finance import StoreProduct, CartItem, TransactionRecord
from .inventory import UserItem
from .stats import UserDailyLearningTime, UserDailyStats
from .assistant import (
    UserTodoItem,
    UserShortcut,
    CreativeWorkshopPage,
    MarkdownNote,
)

__all__ = [
    'User', 'BannedIP',
    'AIPrompt', 'Feedback',
    'VocabBook', 'Word', 'WordBookMembership',
    'Notebook', 'NotebookWord', 'NotebookWordTag',
    'VocabFSRS',
    'LearningPlan', 'LearningPlanEntry',
    'ArticleCopyCache', 'StoryModeCache',
    'CustomMemoryDeck', 'CustomMemoryCard',
    'SpeakingScenarioHistory', 'SpeakingTopicBank',
    'WritingServiceRecord', 'AIQuestion',
    'StoreProduct', 'CartItem', 'TransactionRecord',
    'UserItem',
    'UserDailyLearningTime', 'UserDailyStats',
    'UserTodoItem', 'UserShortcut',
    'CreativeWorkshopPage', 'MarkdownNote',
]
