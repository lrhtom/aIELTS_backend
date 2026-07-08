"""Seed a comprehensive full-stack technical vocabulary learning plan for user tg-studio.

Purpose: prepare graduation defense (毕业答辩) — covers every layer of the aIELTS project:
frontend, backend, database, AI/LLM, testing, concurrency, cache, FSRS, security,
deployment, networking.

The plan uses the standard `flashcard` mode via the LearningPlan pipeline
(NOT the CustomMemoryDeck path). Word rows are upserted into the global
`vocabulary_words` table so that `_entry_dict()` renders phonetic + definitions + examples.

Usage:
    python manage.py seed_tg_studio_defense_plan
    python manage.py seed_tg_studio_defense_plan --wipe   # drop-and-recreate plan
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import User, Word, LearningPlan, LearningPlanEntry


PLAN_NAME = '毕业答辩·全栈技术词汇'
TARGET_USERNAME = 'tg-studio'
DAILY_COUNT = 20


# ── Vocabulary corpus ──────────────────────────────────────────────────────────
# tuple: (word, phonetic, grammar, definitions[{pos,meaning}], examples[{en,zh}])

WORDS: list[tuple[str, str, str, list, list]] = [
    # ─── Frontend ───
    ('react', '/riˈækt/', 'n.',
     [{'pos': 'n.', 'meaning': 'Facebook 开源的声明式前端库；本项目前端框架（React 19）'}],
     [{'en': 'The frontend is built with React 19 and Vite.', 'zh': '前端采用 React 19 + Vite 搭建。'}]),
    ('component', '/kəmˈpəʊnənt/', 'n.',
     [{'pos': 'n.', 'meaning': 'React 组件；可复用的 UI 单元'}],
     [{'en': 'AppNavbar is a shared layout component.', 'zh': 'AppNavbar 是共享的布局组件。'}]),
    ('hook', '/hʊk/', 'n.',
     [{'pos': 'n.', 'meaning': 'React Hook；在函数组件里管理状态与副作用的机制'}],
     [{'en': 'We call useState and useEffect hooks inside function components.', 'zh': '在函数组件里调用 useState、useEffect 等 Hook。'}]),
    ('jsx', '/ˌdʒeɪ es ˈeks/', 'n.',
     [{'pos': 'n.', 'meaning': 'JavaScript 语法扩展，允许在 JS 里书写类 HTML 标签'}],
     [{'en': 'JSX compiles to React.createElement calls.', 'zh': 'JSX 会被编译成 React.createElement 调用。'}]),
    ('typescript', '/ˈtaɪpskrɪpt/', 'n.',
     [{'pos': 'n.', 'meaning': 'TypeScript；带静态类型系统的 JavaScript 超集'}],
     [{'en': 'All frontend .tsx files are type-checked by TypeScript.', 'zh': '所有前端 .tsx 文件都由 TypeScript 做类型检查。'}]),
    ('vite', '/viːt/', 'n.',
     [{'pos': 'n.', 'meaning': 'Vite；基于 ESBuild + Rollup 的极速前端构建工具'}],
     [{'en': 'Vite starts the dev server on port 5173.', 'zh': 'Vite 本地开发服务器跑在 5173 端口。'}]),
    ('router', '/ˈruːtə/', 'n.',
     [{'pos': 'n.', 'meaning': '路由器；将 URL 映射到组件的机制'}],
     [{'en': 'App.tsx wires up all page routes via React Router.', 'zh': 'App.tsx 用 React Router 挂载所有页面路由。'}]),
    ('spa', '/ˌes piː ˈeɪ/', 'n.',
     [{'pos': 'n.', 'meaning': 'Single Page Application；单页应用架构'}],
     [{'en': 'aIELTS is an SPA served over nginx with a fallback to index.html.', 'zh': 'aIELTS 是单页应用，nginx 兜底返回 index.html。'}]),
    ('context', '/ˈkɒntekst/', 'n.',
     [{'pos': 'n.', 'meaning': 'React Context；跨组件传递数据、绕开 props drilling'}],
     [{'en': 'AuthContext exposes the current user to the whole tree.', 'zh': 'AuthContext 向整棵组件树暴露当前登录用户。'}]),
    ('state', '/steɪt/', 'n.',
     [{'pos': 'n.', 'meaning': '组件状态；驱动 UI 重渲染的响应式数据'}],
     [{'en': 'useState returns a stateful value and a setter function.', 'zh': 'useState 返回一份状态值和一个 setter 函数。'}]),
    ('props', '/prɒps/', 'n.',
     [{'pos': 'n.', 'meaning': '组件属性；父组件向子组件传参的通道'}],
     [{'en': 'Layout accepts children as props.', 'zh': 'Layout 组件通过 props 接收 children。'}]),
    ('render', '/ˈrendə/', 'v.',
     [{'pos': 'v.', 'meaning': '渲染；把状态转换成真实 DOM'}],
     [{'en': 'React re-renders the component whenever state changes.', 'zh': '状态一变，React 就重新渲染组件。'}]),
    ('bundler', '/ˈbʌndlə/', 'n.',
     [{'pos': 'n.', 'meaning': '打包器；把多个源文件合成可部署产物'}],
     [{'en': 'Vite uses Rollup as its production bundler.', 'zh': 'Vite 用 Rollup 做生产环境打包器。'}]),
    ('hmr', '/ˌeɪtʃ em ˈɑː/', 'n.',
     [{'pos': 'n.', 'meaning': 'Hot Module Replacement；模块热替换'}],
     [{'en': 'Vite HMR patches modules without reloading the page.', 'zh': 'Vite 的 HMR 让改动即时生效而无需刷新整页。'}]),
    ('viewport', '/ˈvjuːpɔːt/', 'n.',
     [{'pos': 'n.', 'meaning': '视口；浏览器可见区域'}],
     [{'en': 'Responsive CSS media queries target viewport widths.', 'zh': '响应式 CSS 根据视口宽度切换样式。'}]),

    # ─── Backend framework ───
    ('django', '/ˈdʒæŋɡəʊ/', 'n.',
     [{'pos': 'n.', 'meaning': 'Django；Python 的全功能 Web 框架，本项目后端主体'}],
     [{'en': 'The backend runs Django with DRF on gunicorn.', 'zh': '后端用 Django + DRF，跑在 gunicorn 上。'}]),
    ('drf', '/ˌdiː ɑːr ˈef/', 'n.',
     [{'pos': 'n.', 'meaning': 'Django REST Framework；构建 REST API 的官方生态'}],
     [{'en': 'DRF viewsets handle authentication, permissions, and serialization.', 'zh': 'DRF 的 viewset 负责鉴权、权限和序列化。'}]),
    ('orm', '/ˌəʊ ɑːr ˈem/', 'n.',
     [{'pos': 'n.', 'meaning': 'Object-Relational Mapping；对象关系映射，用类替代 SQL'}],
     [{'en': 'Django ORM translates Python queries into MySQL SQL.', 'zh': 'Django ORM 把 Python 查询翻译成 MySQL SQL。'}]),
    ('middleware', '/ˈmɪdlweə/', 'n.',
     [{'pos': 'n.', 'meaning': '中间件；请求-响应管道上的拦截器'}],
     [{'en': 'A middleware blocks banned IPs before the view runs.', 'zh': '中间件在视图执行前拦掉被封禁的 IP。'}]),
    ('serializer', '/ˈsɪərɪəlaɪzə/', 'n.',
     [{'pos': 'n.', 'meaning': '序列化器；把模型对象转 JSON，反向也做校验'}],
     [{'en': 'DRF serializers validate incoming JSON payloads.', 'zh': 'DRF 序列化器负责校验入站的 JSON 数据。'}]),
    ('migration', '/maɪˈɡreɪʃn/', 'n.',
     [{'pos': 'n.', 'meaning': '迁移；描述数据库结构变更的可版本化脚本'}],
     [{'en': 'Migration 0048 adds the BannedIP table.', 'zh': '第 0048 号迁移新增 BannedIP 表。'}]),
    ('gunicorn', '/ˈɡʌnɪkɔːn/', 'n.',
     [{'pos': 'n.', 'meaning': 'Gunicorn；Python 的 WSGI 服务器，生产托管 Django'}],
     [{'en': 'Nginx reverse-proxies /api/ to gunicorn on 127.0.0.1:8000.', 'zh': 'Nginx 把 /api/ 反代到 127.0.0.1:8000 的 gunicorn。'}]),
    ('nginx', '/ˈendʒɪnks/', 'n.',
     [{'pos': 'n.', 'meaning': 'Nginx；高性能反向代理与静态资源服务器'}],
     [{'en': 'Nginx terminates TLS and forwards HTTPS traffic to gunicorn.', 'zh': 'Nginx 负责 TLS 终结，再把 HTTPS 流量转给 gunicorn。'}]),
    ('wsgi', '/ˈwɪzɡi/', 'n.',
     [{'pos': 'n.', 'meaning': 'Web Server Gateway Interface；Python Web 服务器接口标准'}],
     [{'en': 'Django exposes a WSGI application object for gunicorn to load.', 'zh': 'Django 暴露一个 WSGI 应用对象供 gunicorn 加载。'}]),
    ('rest', '/rest/', 'n.',
     [{'pos': 'n.', 'meaning': 'Representational State Transfer；面向资源的 HTTP 架构风格'}],
     [{'en': 'Our REST endpoints follow /nouns/:id/verbs/ conventions.', 'zh': 'REST 接口遵循 /名词/:id/动词/ 的命名惯例。'}]),
    ('endpoint', '/ˈendpɔɪnt/', 'n.',
     [{'pos': 'n.', 'meaning': '端点；一个可被调用的具体 URL + 方法组合'}],
     [{'en': 'The /vocab/review endpoint accepts POST with an FSRS rating.', 'zh': '/vocab/review 端点接收带 FSRS 评分的 POST 请求。'}]),
    ('jwt', '/ˌdʒeɪ dʌbljuː ˈtiː/', 'n.',
     [{'pos': 'n.', 'meaning': 'JSON Web Token；带签名的无状态凭据'}],
     [{'en': 'Auth issues JWT access + refresh tokens.', 'zh': '鉴权发放 JWT 的 access 与 refresh token。'}]),
    ('cors', '/kɔːz/', 'n.',
     [{'pos': 'n.', 'meaning': 'Cross-Origin Resource Sharing；浏览器同源限制的官方放行机制'}],
     [{'en': 'CORS headers allow the SPA to call the API from a different origin.', 'zh': 'CORS 头允许前端 SPA 跨域调用 API。'}]),
    ('throttle', '/ˈθrɒtl/', 'n./v.',
     [{'pos': 'n./v.', 'meaning': '节流；限制单位时间的调用次数'}],
     [{'en': 'AI endpoints are throttled to 5 requests per minute per user.', 'zh': 'AI 接口按每用户每分钟 5 次做节流限制。'}]),
    ('decorator', '/ˈdekəreɪtə/', 'n.',
     [{'pos': 'n.', 'meaning': '装饰器；用高阶函数增强被装饰函数的语法糖'}],
     [{'en': 'The @permission_classes decorator gates who can call a view.', 'zh': '@permission_classes 装饰器控制谁能访问视图。'}]),

    # ─── Database ───
    ('mysql', '/ˌmaɪ es kjuː ˈel/', 'n.',
     [{'pos': 'n.', 'meaning': 'MySQL；开源关系型数据库，本项目主存储'}],
     [{'en': 'Our production MySQL is hosted on Aiven us-east-1.', 'zh': '生产 MySQL 托管在 Aiven us-east-1。'}]),
    ('aiven', '/ˈaɪvən/', 'n.',
     [{'pos': 'n.', 'meaning': 'Aiven；多云托管数据库 SaaS'}],
     [{'en': 'Aiven exposes MySQL over TLS on port 16262.', 'zh': 'Aiven 在 16262 端口对外提供 TLS 加密的 MySQL。'}]),
    ('schema', '/ˈskiːmə/', 'n.',
     [{'pos': 'n.', 'meaning': '模式；数据库的表结构定义'}],
     [{'en': 'A migration alters the schema without losing data.', 'zh': '迁移在不丢数据的前提下改动数据库模式。'}]),
    ('transaction', '/trænˈzækʃn/', 'n.',
     [{'pos': 'n.', 'meaning': '事务；一组要么全成功要么全回滚的写操作'}],
     [{'en': 'transaction.atomic wraps FSRS review writes.', 'zh': 'transaction.atomic 包裹 FSRS 复习写入。'}]),
    ('index', '/ˈɪndeks/', 'n.',
     [{'pos': 'n.', 'meaning': '索引；用空间换查询速度的辅助数据结构'}],
     [{'en': 'idx_vocab_fsrs_user_plan_due speeds up the due-cards query.', 'zh': 'idx_vocab_fsrs_user_plan_due 索引加速"到期卡片"查询。'}]),
    ('constraint', '/kənˈstreɪnt/', 'n.',
     [{'pos': 'n.', 'meaning': '约束；数据库强制执行的规则（唯一/非空/外键等）'}],
     [{'en': 'unique_together enforces one FSRS row per (user, word, plan).', 'zh': 'unique_together 保证每个 (用户,单词,计划) 只有一行 FSRS。'}]),
    ('rollback', '/ˈrəʊlbæk/', 'n./v.',
     [{'pos': 'n./v.', 'meaning': '回滚；撤销未提交的事务变更'}],
     [{'en': 'An exception inside atomic triggers an automatic rollback.', 'zh': 'atomic 块内抛异常会自动触发回滚。'}]),
    ('deadlock', '/ˈdedlɒk/', 'n.',
     [{'pos': 'n.', 'meaning': '死锁；两个事务互相持有对方需要的锁'}],
     [{'en': 'Always acquire locks in the same order to avoid deadlocks.', 'zh': '按同一顺序申请锁，能避免死锁。'}]),
    ('acid', '/ˈæsɪd/', 'n.',
     [{'pos': 'n.', 'meaning': 'Atomicity/Consistency/Isolation/Durability；事务四大属性'}],
     [{'en': 'MySQL InnoDB gives us ACID guarantees.', 'zh': 'MySQL 的 InnoDB 引擎提供 ACID 保证。'}]),
    ('foreignkey', '/ˈfɒrənˌkiː/', 'n.',
     [{'pos': 'n.', 'meaning': '外键；引用另一张表主键的字段'}],
     [{'en': 'NotebookWord has foreign keys to both Notebook and Word.', 'zh': 'NotebookWord 上有两个外键，分别指向 Notebook 和 Word。'}]),

    # ─── AI / LLM ───
    ('llm', '/ˌel el ˈem/', 'n.',
     [{'pos': 'n.', 'meaning': 'Large Language Model；大语言模型的统称'}],
     [{'en': 'The writing correction feature calls an LLM to grade essays.', 'zh': '写作批改功能调用大语言模型给作文打分。'}]),
    ('prompt', '/prɒmpt/', 'n.',
     [{'pos': 'n.', 'meaning': '提示词；喂给 LLM 的指令与上下文'}],
     [{'en': 'Each skill module owns a versioned system prompt.', 'zh': '每个 skill 模块都有一份带版本的 system prompt。'}]),
    ('deepseek', '/ˈdiːpsiːk/', 'n.',
     [{'pos': 'n.', 'meaning': 'DeepSeek；本项目默认 LLM 供应商，OpenAI 兼容接口'}],
     [{'en': 'DeepSeek is called via an OpenAI-compatible chat completions API.', 'zh': 'DeepSeek 通过 OpenAI 兼容的 chat completions 接口调用。'}]),
    ('gpt', '/ˌdʒiː piː ˈtiː/', 'n.',
     [{'pos': 'n.', 'meaning': 'Generative Pre-trained Transformer；OpenAI 的模型家族'}],
     [{'en': 'Azure GPT-5.4-mini is the fallback provider.', 'zh': 'Azure GPT-5.4-mini 作为备用模型供应商。'}]),
    ('token', '/ˈtəʊkən/', 'n.',
     [{'pos': 'n.', 'meaning': '令牌；LLM 计费与上下文长度的最小单位（约 3-4 字符）'}],
     [{'en': 'We charge 2 AT per token consumed by the model.', 'zh': '每消耗 1 个 token 扣 2 点 AT。'}]),
    ('temperature', '/ˈtemprətʃə/', 'n.',
     [{'pos': 'n.', 'meaning': '温度参数；调节 LLM 输出随机性'}],
     [{'en': 'Lower temperature yields more deterministic answers.', 'zh': '温度越低，模型输出越确定。'}]),
    ('inference', '/ˈɪnfərəns/', 'n.',
     [{'pos': 'n.', 'meaning': '推理；用已训练模型产出预测的过程'}],
     [{'en': 'Cached responses skip inference entirely.', 'zh': '命中缓存时完全跳过一次推理。'}]),
    ('embedding', '/ɪmˈbedɪŋ/', 'n.',
     [{'pos': 'n.', 'meaning': '嵌入向量；把文本映射到高维向量的表示'}],
     [{'en': 'Embeddings power semantic search over vocabulary.', 'zh': '嵌入向量支撑对词汇做语义检索。'}]),
    ('hallucination', '/həˌluːsɪˈneɪʃn/', 'n.',
     [{'pos': 'n.', 'meaning': '幻觉；LLM 编造貌似合理但事实错误的输出'}],
     [{'en': 'Fabricated citations are a classic LLM hallucination.', 'zh': '编造引用是典型的大模型幻觉。'}]),
    ('multimodal', '/ˌmʌltiˈməʊdl/', 'adj.',
     [{'pos': 'adj.', 'meaning': '多模态的；能处理文本+图像+音频等多种输入'}],
     [{'en': 'FLUX.2-pro is the multimodal image generator we use for map questions.', 'zh': 'FLUX.2-pro 是我们地图题使用的多模态图像生成模型。'}]),
    ('flux', '/flʌks/', 'n.',
     [{'pos': 'n.', 'meaning': 'FLUX.2-pro；Azure BFL 提供的图像生成模型'}],
     [{'en': 'Map images are rendered by FLUX.2-pro and stored under MEDIA_ROOT.', 'zh': '地图图片由 FLUX.2-pro 生成并存到 MEDIA_ROOT。'}]),
    ('rubric', '/ˈruːbrɪk/', 'n.',
     [{'pos': 'n.', 'meaning': '评分量规；结构化的多维评分标准'}],
     [{'en': 'Task 2 essays are scored against a four-dimension IELTS rubric.', 'zh': 'Task 2 作文按雅思四维量规打分。'}]),

    # ─── Testing ───
    ('pytest', '/ˈpaɪtest/', 'n.',
     [{'pos': 'n.', 'meaning': 'pytest；Python 主流测试框架'}],
     [{'en': 'Backend unit tests run under pytest with pytest-django.', 'zh': '后端单元测试跑在 pytest + pytest-django 上。'}]),
    ('fixture', '/ˈfɪkstʃə/', 'n.',
     [{'pos': 'n.', 'meaning': '夹具；测试用的可复用初始化对象'}],
     [{'en': 'The fake_redis fixture monkeypatches get_redis to an in-memory client.', 'zh': 'fake_redis 夹具把 get_redis() 替换为内存 Redis。'}]),
    ('mock', '/mɒk/', 'n./v.',
     [{'pos': 'n./v.', 'meaning': '模拟；用假实现替换真实依赖以隔离被测代码'}],
     [{'en': 'We mock the AI upstream with the responses library.', 'zh': '用 responses 库 mock 掉真实 AI 上游。'}]),
    ('fakeredis', '/ˈfeɪkredɪs/', 'n.',
     [{'pos': 'n.', 'meaning': 'fakeredis；纯 Python 的 Redis 内存替身，用于测试'}],
     [{'en': 'Rate-limit tests use fakeredis so no real Upstash calls happen.', 'zh': '限流测试用 fakeredis，避免真打 Upstash。'}]),
    ('coverage', '/ˈkʌvərɪdʒ/', 'n.',
     [{'pos': 'n.', 'meaning': '覆盖率；被测试执行到的代码行占比'}],
     [{'en': 'Core modules must maintain ≥90% test coverage.', 'zh': '核心模块必须保持 90% 以上覆盖率。'}]),
    ('assertion', '/əˈsɜːʃn/', 'n.',
     [{'pos': 'n.', 'meaning': '断言；测试里表达"预期结果"的语句'}],
     [{'en': 'Prefer specific assertions like assert result == 42.', 'zh': '断言应尽量具体，例如 assert result == 42。'}]),
    ('marker', '/ˈmɑːkə/', 'n.',
     [{'pos': 'n.', 'meaning': 'pytest 标记；用来给测试打标签以便按需筛选'}],
     [{'en': 'live_ai marker gates tests that actually call the AI provider.', 'zh': 'live_ai 标记用于筛出真打 AI 上游的测试。'}]),
    ('harness', '/ˈhɑːnɪs/', 'n.',
     [{'pos': 'n.', 'meaning': '脚手架；驱动、装载、评估被测系统的框架'}],
     [{'en': 'Our test harness covers unit + integration + live-AI layers.', 'zh': '测试脚手架分单元、集成、真打 AI 三层。'}]),
    ('tdd', '/ˌtiː diː ˈdiː/', 'n.',
     [{'pos': 'n.', 'meaning': 'Test-Driven Development；测试驱动开发方法论'}],
     [{'en': 'TDD says: write a failing test first, then the production code.', 'zh': 'TDD 强调先写失败的测试，再写生产代码。'}]),
    ('regression', '/rɪˈɡreʃn/', 'n.',
     [{'pos': 'n.', 'meaning': '回归；改动后旧功能被意外破坏的情况'}],
     [{'en': 'A golden set catches prompt regressions across model swaps.', 'zh': '一份 golden set 能在换模型时抓住 prompt 回归。'}]),

    # ─── Concurrency / Parallel ───
    ('concurrency', '/kənˈkʌrənsi/', 'n.',
     [{'pos': 'n.', 'meaning': '并发；多个任务在时间上重叠执行'}],
     [{'en': 'Optimistic locks protect FSRS review under concurrency.', 'zh': '并发场景下用乐观锁保护 FSRS 复习写入。'}]),
    ('thread', '/θred/', 'n.',
     [{'pos': 'n.', 'meaning': '线程；进程内共享内存的最小调度单元'}],
     [{'en': 'AI generation runs on a daemon thread so the request returns 202 fast.', 'zh': 'AI 生成放到守护线程里跑，请求可以立刻返回 202。'}]),
    ('daemon', '/ˈdiːmən/', 'n.',
     [{'pos': 'n.', 'meaning': '守护进程/线程；后台运行、不阻挡主流程退出'}],
     [{'en': 'A daemon thread dies automatically when the process exits.', 'zh': '守护线程会随主进程退出而结束。'}]),
    ('asyncio', '/eɪˈsɪŋk aɪ əʊ/', 'n.',
     [{'pos': 'n.', 'meaning': 'asyncio；Python 的原生异步 IO 框架'}],
     [{'en': 'asyncio uses a single-threaded event loop with await points.', 'zh': 'asyncio 用单线程事件循环 + await 切换任务。'}]),
    ('atomic', '/əˈtɒmɪk/', 'adj.',
     [{'pos': 'adj.', 'meaning': '原子的；要么全部生效、要么全不生效'}],
     [{'en': 'transaction.atomic makes the AT deduction and review write atomic.', 'zh': 'transaction.atomic 让扣费和复习写入成为原子操作。'}]),
    ('semaphore', '/ˈseməfɔː/', 'n.',
     [{'pos': 'n.', 'meaning': '信号量；限制同时进入临界区的并发数'}],
     [{'en': 'A semaphore of 6 caps parallel Semantic Scholar API calls.', 'zh': '用容量 6 的信号量限制并行调用 Semantic Scholar 的次数。'}]),
    ('mutex', '/ˈmjuːteks/', 'n.',
     [{'pos': 'n.', 'meaning': '互斥锁；同一时刻仅允许一个线程持有的锁'}],
     [{'en': 'A mutex ensures only one thread mutates the shared cache.', 'zh': '互斥锁保证同一时刻只有一个线程修改共享缓存。'}]),
    ('singleflight', '/ˈsɪŋɡlflaɪt/', 'n.',
     [{'pos': 'n.', 'meaning': '单飞；把并发的重复请求合并成一次真实调用'}],
     [{'en': 'Singleflight collapses duplicate cache-miss AI calls into one.', 'zh': '单飞把并发的缓存未命中 AI 调用合并成一次。'}]),
    ('optimistic', '/ˌɒptɪˈmɪstɪk/', 'adj.',
     [{'pos': 'adj.', 'meaning': '乐观的；乐观锁假定冲突罕见，只在提交时检测版本'}],
     [{'en': 'The review view uses optimistic locking via client_last_review.', 'zh': '复习接口用 client_last_review 实现乐观锁。'}]),
    ('debounce', '/dɪˈbaʊns/', 'n./v.',
     [{'pos': 'n./v.', 'meaning': '防抖；短时间内的重复触发合并为一次'}],
     [{'en': 'The search box debounces keystrokes by 300 ms.', 'zh': '搜索框对键盘输入做 300 毫秒的防抖。'}]),

    # ─── Cache / Redis ───
    ('redis', '/ˈredɪs/', 'n.',
     [{'pos': 'n.', 'meaning': 'Redis；内存 KV 存储，用于缓存/限流/会话等'}],
     [{'en': 'Redis backs rate limiting and AI response caching.', 'zh': 'Redis 承载限流与 AI 响应缓存。'}]),
    ('upstash', '/ˈʌpstæʃ/', 'n.',
     [{'pos': 'n.', 'meaning': 'Upstash；无服务器托管 Redis，用 HTTP REST 协议'}],
     [{'en': 'Upstash Redis is called over HTTP so no persistent socket is needed.', 'zh': 'Upstash Redis 走 HTTP，不需要长连接。'}]),
    ('cache', '/kæʃ/', 'n.',
     [{'pos': 'n.', 'meaning': '缓存；用更快介质保存热点数据的副本'}],
     [{'en': 'AI response cache uses key ai_cache:{model}:{md5(messages)}.', 'zh': 'AI 响应缓存键为 ai_cache:{model}:{md5(messages)}。'}]),
    ('ttl', '/ˌtiː tiː ˈel/', 'n.',
     [{'pos': 'n.', 'meaning': 'Time To Live；缓存条目的自动过期时间'}],
     [{'en': 'Balance cache has a 5-second TTL.', 'zh': '余额缓存的 TTL 是 5 秒。'}]),
    ('singleton', '/ˈsɪŋɡltən/', 'n.',
     [{'pos': 'n.', 'meaning': '单例模式；进程内唯一实例的构造方式'}],
     [{'en': 'get_redis() returns a module-level singleton client.', 'zh': 'get_redis() 返回模块级的单例客户端。'}]),

    # ─── FSRS / Spaced Repetition ───
    ('fsrs', '/ˌef es ɑːr ˈes/', 'n.',
     [{'pos': 'n.', 'meaning': 'Free Spaced Repetition Scheduler；开源间隔重复算法'}],
     [{'en': 'FSRS-4.5 drives all flashcard scheduling on this platform.', 'zh': 'FSRS-4.5 驱动本平台所有记忆卡的调度。'}]),
    ('stability', '/stəˈbɪləti/', 'n.',
     [{'pos': 'n.', 'meaning': '稳定性 S；记忆能保持多少天不掉到 90% 检索率'}],
     [{'en': 'A higher stability means longer intervals between reviews.', 'zh': '稳定性越高，两次复习之间的间隔就越长。'}]),
    ('retention', '/rɪˈtenʃn/', 'n.',
     [{'pos': 'n.', 'meaning': '保持率；目标 recall 概率，FSRS 依此排下一次复习'}],
     [{'en': 'FSRS targets 90% retention when picking the next due date.', 'zh': 'FSRS 以 90% 保持率为目标推算下次复习日期。'}]),
    ('mastery', '/ˈmɑːstəri/', 'n.',
     [{'pos': 'n.', 'meaning': '掌握度；本项目里 NotebookWord 上的 0-5 分离散指标'}],
     [{'en': 'mastery_level ranges 0-5 and syncs to FSRS on review.', 'zh': 'mastery_level 取 0-5，复习时同步给 FSRS。'}]),
    ('flashcard', '/ˈflæʃkɑːd/', 'n.',
     [{'pos': 'n.', 'meaning': '记忆卡；正反两面翻转的间隔重复学习卡片'}],
     [{'en': 'This plan uses flashcard mode with a 3D flip animation.', 'zh': '本计划采用记忆卡模式，带 3D 翻转动画。'}]),

    # ─── Security ───
    ('https', '/ˌeɪtʃ tiː tiː piː ˈes/', 'n.',
     [{'pos': 'n.', 'meaning': 'HTTPS；HTTP over TLS，加密的网页协议'}],
     [{'en': 'aielts.xyz enforces HTTPS with a 301 redirect from HTTP.', 'zh': 'aielts.xyz 强制 HTTPS，HTTP 请求 301 跳转。'}]),
    ('tls', '/ˌtiː el ˈes/', 'n.',
     [{'pos': 'n.', 'meaning': 'Transport Layer Security；SSL 的现代继任者'}],
     [{'en': 'Nginx terminates TLS with a Let\'s Encrypt certificate.', 'zh': 'Nginx 用 Let\'s Encrypt 证书完成 TLS 终结。'}]),
    ('hsts', '/ˌeɪtʃ es tiː ˈes/', 'n.',
     [{'pos': 'n.', 'meaning': 'HTTP Strict Transport Security；强制浏览器只走 HTTPS'}],
     [{'en': 'HSTS is enabled to prevent SSL-strip downgrades.', 'zh': '启用 HSTS 可以防止 SSL 剥离降级攻击。'}]),
    ('xss', '/ˌeks es ˈes/', 'n.',
     [{'pos': 'n.', 'meaning': '跨站脚本攻击；把恶意 JS 注入他人页面执行'}],
     [{'en': 'Escape all user-supplied HTML to prevent XSS.', 'zh': '所有用户提交的 HTML 必须转义以防 XSS。'}]),
    ('csrf', '/ˌsiː es ɑːr ˈef/', 'n.',
     [{'pos': 'n.', 'meaning': '跨站请求伪造；利用受害者已有会话发起未授权请求'}],
     [{'en': 'Django enforces a CSRF token on cookie-authenticated POSTs.', 'zh': 'Django 对 cookie 鉴权的 POST 请求强制校验 CSRF token。'}]),
    ('sanitize', '/ˈsænɪtaɪz/', 'v.',
     [{'pos': 'v.', 'meaning': '清洗；剔除输入中的危险内容以防注入'}],
     [{'en': 'Sanitize markdown before rendering to strip <script> tags.', 'zh': '渲染 markdown 前先清洗，剔除 <script> 标签。'}]),
    ('owasp', '/ˈəʊwɒsp/', 'n.',
     [{'pos': 'n.', 'meaning': 'OWASP；关注 Web 安全的开放社区，出品 Top 10 清单'}],
     [{'en': 'We audit against the OWASP Top 10 checklist.', 'zh': '按 OWASP Top 10 清单做安全自查。'}]),

    # ─── Deployment ───
    ('aliyun', '/ɑːˈliːjʊn/', 'n.',
     [{'pos': 'n.', 'meaning': '阿里云；本项目生产 IaaS 提供商'}],
     [{'en': 'Production ECS lives in Aliyun us-east-1 (Virginia).', 'zh': '生产 ECS 部署在阿里云的美东弗吉尼亚区。'}]),
    ('ecs', '/ˌiː siː ˈes/', 'n.',
     [{'pos': 'n.', 'meaning': 'Elastic Compute Service；阿里云的弹性云主机'}],
     [{'en': 'Our ECS is 2 vCPU / 4 GiB with 100 GiB ESSD.', 'zh': '生产 ECS 配 2 核 4G，挂 100G ESSD 云盘。'}]),
    ('baota', '/baʊˈtɑː/', 'n.',
     [{'pos': 'n.', 'meaning': '宝塔面板；国产可视化 Linux 服务器管理面板'}],
     [{'en': 'Baota manages nginx, SSL, and firewall on the ECS.', 'zh': '宝塔面板负责管理 ECS 上的 nginx、SSL 和防火墙。'}]),
    ('sftp', '/ˌes ef tiː ˈpiː/', 'n.',
     [{'pos': 'n.', 'meaning': 'SSH File Transfer Protocol；基于 SSH 的加密文件传输'}],
     [{'en': 'pack.py builds artifacts locally and pushes them via SFTP.', 'zh': 'pack.py 本地打包后用 SFTP 推送到服务器。'}]),
    ('devops', '/ˌdev ˈɒps/', 'n.',
     [{'pos': 'n.', 'meaning': 'DevOps；开发-运维一体化的实践与文化'}],
     [{'en': 'A pack script is our lightweight DevOps automation.', 'zh': '一个打包脚本就是我们轻量级的 DevOps 自动化。'}]),
    ('docker', '/ˈdɒkə/', 'n.',
     [{'pos': 'n.', 'meaning': 'Docker；主流容器运行时，用镜像分发应用'}],
     [{'en': 'The Dockerfile is deprecated in favor of native Baota deployment.', 'zh': '当前 Dockerfile 已停用，改走宝塔原生部署。'}]),
    ('deployment', '/dɪˈplɔɪmənt/', 'n.',
     [{'pos': 'n.', 'meaning': '部署；把代码送上生产环境并启动的过程'}],
     [{'en': 'Zero-downtime deployment relies on gunicorn graceful reload.', 'zh': '零停机部署依赖 gunicorn 的优雅重启。'}]),

    # ─── Networking ───
    ('dns', '/ˌdiː en ˈes/', 'n.',
     [{'pos': 'n.', 'meaning': 'Domain Name System；把域名解析到 IP 的分布式系统'}],
     [{'en': 'aielts.xyz DNS resolves to the Aliyun ECS public IP.', 'zh': 'aielts.xyz 的 DNS 解析到阿里云 ECS 的公网 IP。'}]),
    ('cdn', '/ˌsiː diː ˈen/', 'n.',
     [{'pos': 'n.', 'meaning': 'Content Delivery Network；地理分布的静态资源边缘缓存'}],
     [{'en': 'A CDN in front of MEDIA_ROOT would offload avatar traffic.', 'zh': '给 MEDIA_ROOT 前面套 CDN，可以分流头像流量。'}]),
    ('proxy', '/ˈprɒksi/', 'n.',
     [{'pos': 'n.', 'meaning': '代理；转发请求的中间服务器'}],
     [{'en': 'Nginx acts as a reverse proxy in front of gunicorn.', 'zh': 'Nginx 在 gunicorn 前充当反向代理。'}]),
    ('websocket', '/ˈwebsɒkɪt/', 'n.',
     [{'pos': 'n.', 'meaning': 'WebSocket；浏览器和服务器双向长连接协议'}],
     [{'en': 'Speaking chat could migrate from polling to WebSocket for lower latency.', 'zh': '语音口语对话可以从轮询迁到 WebSocket 以降低延迟。'}]),
]


class Command(BaseCommand):
    help = 'Seed the graduation-defense full-stack vocabulary learning plan for user tg-studio.'

    def add_arguments(self, parser):
        parser.add_argument('--wipe', action='store_true',
                            help='Delete existing plan with the same name and recreate.')

    def handle(self, *args, **opts):
        user = User.objects.filter(username=TARGET_USERNAME).first()
        if not user:
            raise CommandError(f'User {TARGET_USERNAME!r} not found.')

        self.stdout.write(f'user: id={user.id} username={user.username} is_staff={user.is_staff}')

        # Normalise word strings (lowercase, strip)
        rows = []
        seen: set[str] = set()
        for w, phon, gram, defs, exs in WORDS:
            key = w.strip().lower()
            if key in seen:
                self.stdout.write(self.style.WARNING(f'duplicate skipped: {key}'))
                continue
            seen.add(key)
            rows.append((key, phon, gram, defs, exs))

        self.stdout.write(f'corpus size: {len(rows)} unique words')

        with transaction.atomic():
            # ── 1. Upsert into global Word table ────────────────────────────
            existing = {w.word: w for w in Word.objects.filter(word__in=[r[0] for r in rows])}
            created_words = 0
            updated_words = 0
            for word_str, phon, gram, defs, exs in rows:
                w = existing.get(word_str)
                if w is None:
                    Word.objects.create(
                        word=word_str,
                        phonetic=phon,
                        grammar=gram,
                        definitions=defs,
                        examples=exs,
                    )
                    created_words += 1
                else:
                    # Only fill blanks; never overwrite an existing curated word
                    dirty = False
                    if not w.phonetic and phon:
                        w.phonetic = phon; dirty = True
                    if not w.grammar and gram:
                        w.grammar = gram; dirty = True
                    if not w.definitions and defs:
                        w.definitions = defs; dirty = True
                    if not w.examples and exs:
                        w.examples = exs; dirty = True
                    if dirty:
                        w.save(update_fields=['phonetic', 'grammar', 'definitions', 'examples', 'updated_at'])
                        updated_words += 1

            self.stdout.write(f'Word table: +{created_words} created, {updated_words} back-filled')

            # ── 2. Create / reset the learning plan ─────────────────────────
            plan = LearningPlan.objects.filter(user=user, name=PLAN_NAME).first()
            if plan and opts['wipe']:
                self.stdout.write(self.style.WARNING(f'wiping existing plan id={plan.id}'))
                plan.delete()
                plan = None

            if not plan:
                plan = LearningPlan(
                    user=user,
                    name=PLAN_NAME,
                    daily_count=DAILY_COUNT,
                    default_mode='flashcard',
                    mastery_target=2,
                    complete_difficulty='hint',
                )
                plan.save()
                self.stdout.write(self.style.SUCCESS(f'created plan id={plan.id} name={plan.name!r}'))
            else:
                self.stdout.write(f'plan already exists id={plan.id}; adding missing entries')

            # ── 3. Bulk-add entries ─────────────────────────────────────────
            existing_entry_words = set(
                LearningPlanEntry.objects.filter(plan=plan).values_list('word', flat=True)
            )
            to_add = []
            for word_str, _, _, defs, _ in rows:
                if word_str in existing_entry_words:
                    continue
                # zh comes from the first definition's meaning (with POS prefix)
                zh = (defs[0]['pos'] + ' ' + defs[0]['meaning']).strip() if defs else ''
                to_add.append(LearningPlanEntry(plan=plan, word=word_str, zh=zh[:500]))
            if to_add:
                LearningPlanEntry.objects.bulk_create(to_add, ignore_conflicts=True)
            self.stdout.write(self.style.SUCCESS(f'entries: +{len(to_add)} added, total now={plan.entries.count()}'))

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. tg-studio → plan {plan.id!r} "{plan.name}" with {plan.entries.count()} words.\n'
            f'Open /vocabulary/plans, click the plan, then "开始学习" to enter flashcard mode.'
        ))
