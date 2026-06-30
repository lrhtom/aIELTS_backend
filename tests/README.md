# 后端测试套件使用解说

> 目录：`backend/tests/`
> 框架：`pytest` + `pytest-django` + `responses` + `factory_boy` + `fakeredis`
> 配置：`backend/pytest.ini` + `backend/conftest.py` + `backend/tests/conftest.py`

---

## 1. 一句话总览

```
backend/tests/
├── conftest.py            ← 公共 fixture（HTTP mock / Redis mock / 时间锚 / provider env）
├── unit/                  ← L1：纯函数 + mock，无 DB，无网络
│   ├── test_fsrs_utils.py     算法层
│   └── test_ai_client.py      AI 客户端层
└── integration/           ← L2：真实 MySQL test schema（暂为空，下一阶段）
```

跑测试只需在 `backend/` 目录执行 `pytest`。

---

## 2. 第一次跑：环境准备

```bash
cd backend

# 1. 装测试栈（已加入 requirements.txt）
pip install -r requirements.txt

# 2. 跑全部 unit 测试
pytest tests/unit -v

# 3. 跑某个文件
pytest tests/unit/test_fsrs_utils.py -v

# 4. 跑某个类 / 某个用例
pytest tests/unit/test_fsrs_utils.py::TestReviewTransitions -v
pytest tests/unit/test_ai_client.py::TestGenerateJSON::test_clean_json_response -v

# 5. 看覆盖率（核心模块要求 ≥ 90%）
pytest tests/unit --cov=api.core.fsrs_utils --cov=api.core.ai_client --cov-report=term-missing
```

---

## 3. 测试分层与 marker

| 层级 | marker | 何时跑 | DB 依赖 | 网络依赖 |
|---|---|---|---|---|
| **L1 unit** | `unit`（自动加）| 每次保存 / pre-commit | ❌ | ❌（mock） |
| **L2 integration** | `integration` | PR / 本地手动 | ✅ MySQL test schema | ❌（mock） |
| **L4 端到端** | `slow` | CI 夜跑 | ✅ | ❌（mock 上游） |
| **真打 AI 上游** | `live_ai` | 手动 | ❌ | ✅ 真打 |
| **限流相关** | `rate_limit` | 按需 | ❌ | fakeredis |

筛选用法：

```bash
pytest -m unit                     # 只跑 L1
pytest -m "not slow"               # 跳过慢测试（本地开发常用）
pytest -m "integration and not slow"
pytest -m live_ai                  # 手动触发真实 AI 调用
```

---

## 4. 共享 fixture 速查（`tests/conftest.py`）

| Fixture | 类型 | 作用 |
|---|---|---|
| `mocked_responses` | `responses.RequestsMock` | 拦截所有 `requests` 出站，注册路由 + 断言调用 |
| `frozen_now` | `datetime` | 固定时间锚 `2026-06-27 12:00 UTC`，FSRS 测试用 |
| `fake_redis` | `fakeredis.FakeStrictRedis` | monkeypatch `get_redis()` 返回内存 Redis |
| `deepseek_env` | env vars | 注入 DeepSeek 的 `AI_BASE_URL` / `AI_API_KEY` / `AI_MODEL` |
| `gpt5_mini_env` | env vars | 注入 Azure GPT-5.4-mini 的环境（含 api-version 自动升级） |
| `deepseek_chat_response` | callable | 生成 OpenAI 风格响应骨架，`(text, tokens)` 参数 |

### 典型用法：AI 客户端测试

```python
def test_my_ai_call(mocked_responses, deepseek_env, deepseek_chat_response):
    mocked_responses.add(
        responses.POST,
        'https://api.deepseek.com/chat/completions',
        json=deepseek_chat_response(text='{"k": 1}', tokens=50),
        status=200,
    )
    client = AIClient(provider='deepseek')
    result, at_cost = client.generate(
        messages=[{'role': 'user', 'content': 'q'}],
        expect_json=True,
        user_id=None,   # ← 关键：跳过余额预检和扣费
    )
    assert result == {'k': 1}
    assert at_cost == 100
```

### 典型用法：限流 / 缓存测试（L2 才用）

```python
@pytest.mark.rate_limit
def test_rate_limit_blocks_after_5(fake_redis):
    from api.core.rate_limit import check_rate_limit
    for _ in range(5):
        assert check_rate_limit(user_id=1, endpoint='reading', max_calls=5, window=60)
    assert not check_rate_limit(user_id=1, endpoint='reading', max_calls=5, window=60)
```

---

## 5. 已覆盖范围（截至 L1 阶段）

### `tests/unit/test_fsrs_utils.py`

- ✅ 输入校验（rating 越界、last_review 三种类型）
- ✅ 新卡 4 个评分迁移（Again/Hard/Good → Learning；Easy → Review）
- ✅ Learning 阶段 4 个评分迁移
- ✅ Relearning 阶段 Easy 毕业
- ✅ Review + Again → Relearning 且 `lapses` 自增
- ✅ Review + 成功回忆 stability 单调不降
- ✅ 不变量：difficulty ∈ [1, 10]、stability > 0、reps 必增
- ✅ 确定性：相同输入两次调用结果完全相等
- ✅ 日历日边界：跨午夜算 1 天

### `tests/unit/test_ai_client.py`

- ✅ Provider 路由（deepseek / gpt5_mini / unknown 兜底）
- ✅ 文本模式：返回 `(content, at_cost)`，费率 1 token = 2 AT
- ✅ `<think>...</think>` 推理标记剥离
- ✅ JSON 模式：干净 JSON 解析
- ✅ JSON 模式：Markdown 代码块包裹去除
- ✅ JSON 模式：前后含杂质文字时正则抽取
- ✅ JSON 模式：解析失败抛错
- ✅ 上游 401 / 500 错误抛出
- ✅ `user_id=None` 跳过 User 表访问（不扣费）
- ✅ 请求头：DeepSeek 用 `Authorization: Bearer`，Azure 用 `api-key`
- ✅ payload：temperature 透传、expect_json 自动加 `response_format`

---

## 6. 写新测试的约定

### A. 测试文件位置
- 纯函数 / mock 测试 → `tests/unit/test_<模块名>.py`
- 走 DB 的集成测试 → `tests/integration/test_<模块名>.py` 并加 `@pytest.mark.integration`
- 走 LiveServer 的端到端 → `tests/integration/test_e2e_<场景>.py` 加 `@pytest.mark.slow`

### B. 命名
- 文件：`test_xxx.py`
- 类：`TestXxx`（按行为聚类，不按方法堆叠）
- 函数：`test_xxx_does_yyy_when_zzz`，描述行为不描述实现

### C. 必守纪律
1. **绝对不要在测试里真打 AI 上游**。所有 HTTP 调用用 `mocked_responses` 注册路由。需要真打的极少数测试加 `@pytest.mark.live_ai`，CI 默认跳过。
2. **不要 hardcode 当前时间**。需要时间用 `frozen_now` fixture。
3. **DB 写操作**要用 `@pytest.mark.django_db(transaction=True)`，事务结束自动回滚。
4. **不要在 `setUp` / fixture 里造海量数据**。用 `factory_boy` 按需造，整个文件别超过 50 个对象。
5. **断言要具体**：测 `assert result == {'k': 1}`，而不是 `assert result`。
6. **一个测试一个行为**。出现"测一组功能"的需求，拆成多个 `test_*` 用 `parametrize` 或同一 `TestXxx` 类。

### D. mock 何时用、不用

| 场景 | mock 谁 | 工具 |
|---|---|---|
| AI 上游 HTTP | `requests.post` | `responses` |
| Redis | `get_redis()` | `fake_redis` fixture |
| 当前时间 | `datetime.now()` | `frozen_now` fixture（推荐传参，而非 patch） |
| 邮件发送 | `EmailService.send` | `monkeypatch` |
| DB | **不要 mock** | 走真实 MySQL test schema |
| Django ORM 内部 | **不要 mock** | 测真实查询 |

---

## 7. 加新 fixture 时

放到 `tests/conftest.py`。文件级唯一用的 fixture 才放到测试文件顶部。

```python
@pytest.fixture
def my_fixture():
    ...
    yield value
    # teardown
```

---

## 8. CI 集成（计划）

```yaml
# .github/workflows/backend-tests.yml
jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.13' }
      - run: pip install -r backend/requirements.txt
      - run: cd backend && pytest tests/unit -v --cov=api.core --cov-report=xml
      - uses: codecov/codecov-action@v4
```

整合上去的时间点视团队节奏决定。本地开发先用 pre-commit hook：

```bash
# .git/hooks/pre-commit
cd backend && pytest tests/unit -q || exit 1
```

---

## 9. 常见坑

### "Database access not allowed" 报错
你写的 unit 测试不小心引入了 ORM 查询。要么改成纯函数测试，要么把测试搬到 `tests/integration/` 并加 `@pytest.mark.django_db`。

### responses 报 "Connection refused"
忘了 add 路由。每个 HTTP 调用都需要预先 `mocked_responses.add(...)`。或者写 `responses.add_passthru('https://safe-url.com')` 让某些 URL 直通。

### Azure GPT-5 测试断言 base_url 失败
`AIClient.__init__` 会把 `api-version=2024-02-01` 自动升级为 `2025-04-01-preview`。断言时认准升级后的版本号。

### fakeredis 数据没清掉
`fake_redis` fixture 每个测试都给新实例。如果你写多个测试共享数据，要么用 fixture scope='module'，要么显式 `r.flushall()`。

### 测试里 import Django 模型报错
`pytest-django` 已经处理了，但确保 `pytest.ini` 里 `DJANGO_SETTINGS_MODULE = backend.settings` 正确。

---

## 10. 下一阶段（L2 起步信号）

确定 L1 跑通后开始：

1. 测试数据库准备（本地 docker MySQL 或 Aiven test schema）
2. `tests/factories.py` 加 User / Word / VocabBook / LearningPlan 工厂
3. `tests/integration/test_vocab_views.py` 等业务路由集成测试
4. 横向越权 / 并发 / 余额一致性专项

参考主对话里给出的"L2 业务路由集成测试"风险表。
