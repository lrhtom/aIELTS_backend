"""
AI Skills — 所有 AI 技能提示的集中管理模块
=============================================
按功能域分区:
  speaking/  — 口语练习
  writing/   — 写作练习
  listening/ — 听力练习
  assistant/ — 个人 Agent / Router / React Agent
  creative/  — 创意工坊
"""

from .speaking import *  # noqa: F401,F403
from .writing import *  # noqa: F401,F403
from .listening import *  # noqa: F401,F403
from .assistant import *  # noqa: F401,F403
from .creative import *  # noqa: F401,F403
