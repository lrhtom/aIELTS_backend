# backend/api 模块整理说明

本目录为 Django API 业务核心，按"入口层 / 基础能力 / 业务域"组织到子文件夹中。

## 目录结构

```
api/
├── __init__.py
├── models.py          # 核心数据模型（保留在根目录）
├── serializers.py     # 序列化与数据验证（保留在根目录）
├── urls.py            # 统一 API 路由入口（保留在根目录）
│
├── core/              # 基础能力层
│   ├── ai_client.py         # 统一 AI 模型调用封装
│   ├── authentication.py    # 单设备 JWT 认证逻辑
│   ├── rate_limit.py        # 接口限流
│   ├── redis_client.py      # Redis 客户端
│   ├── email_service.py     # 验证码发送与校验
│   ├── fsrs_utils.py        # FSRS 记忆算法工具
│   └── utils.py             # 通用 AI 调用辅助
│
├── auth/              # 鉴权与用户域
│   ├── auth_views.py        # 注册/登录/资料/设置
│   ├── background_views.py  # 用户背景设置
│   ├── admin_views.py       # 管理后台
│   ├── feedback_views.py    # 用户反馈
│   └── balance_views.py     # AT币余额管理
│
├── practice/          # 听说读写业务域
│   ├── reading_views.py
│   ├── listening_views.py
│   ├── speaking_views.py
│   ├── speaking_part1_views.py
│   ├── speaking_part23_views.py
│   ├── writing_views.py
│   ├── writing_chart_views.py
│   └── writing_task2_views.py
│
├── vocab/             # 词汇与学习计划域
│   ├── vocab_views.py           # FSRS 闪卡同步/复习
│   ├── learning_plan_views.py   # 学习计划 CRUD + 会话构建
│   ├── notebook_views.py        # 智能生词本
│   └── custom_memory_views.py   # 自定义记忆卡
│
├── extra/             # 其他业务域
│   ├── prompt_views.py              # 提示词广场
│   ├── store_views.py               # 商店与购物车
│   ├── creative_workshop_views.py   # 创意工坊
│   └── assistant_views.py          # 全局智能助手 + MCP
│
├── migrations/        # 数据库迁移
├── management/        # Django 管理命令
└── legacy/            # 历史归档（已下线代码）
```

## Import 规范

- 子目录间引用使用**绝对路径**：`from api.core.ai_client import AIClient`
- 引用根目录文件：`from api.models import ...`、`from api.serializers import ...`
- 同目录内引用可使用相对路径：`from .vocab_views import ...`

## 维护规则

1. 新增接口放入对应业务域子文件夹，避免碎片化。
2. 新模块命名建议采用 `*_views.py`，并在 `urls.py` 集中注册。
3. 不再使用的文件先移动到 `legacy/`，确认稳定后再清理。
4. 每次新增模块后更新本 README，保持结构可追踪。
