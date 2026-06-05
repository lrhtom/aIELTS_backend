# 前端国际化 (i18n) 核心组件重构计划 - Phase 1

由于涉及的文件多达 68 个，为了保证代码稳定性和避免冲突，我们将分批次进行国际化重构。第一阶段（Phase 1）我们将优先解决**全局框架**和**最高频使用的核心页面**。

## 重构范围 (Phase 1 Scope)

本次计划将针对以下最核心的 10 个组件进行彻底的 i18n 替换：

### 1. 全局布局与导航 (Global Layout & Navigation)
- `components/layout/Layout.tsx` (彻底补充 `useLang`)
- `components/layout/AppNavbar.tsx` (提取顶部栏中文)
- `components/layout/Sidebar.tsx` (提取侧边栏残留中文)
- `components/common/GlobalAssistantBall.tsx` (全局悬浮球)

### 2. 个人主页与财政面板 (Profile & Finance)
- `pages/profile_page.tsx`
- `components/profile/UserFinance.tsx` (我们刚才优化的财政面板)
- `components/profile/UserSettings.tsx`
- `components/profile/UserHome.tsx`

### 3. 系统核心页面 (Core Dashboards)
- `pages/home_page.tsx` (应用首页)
- `App.tsx` (根组件，包含路由提示和全局报错等)

## 执行步骤 (Proposed Changes)

1. **扩充多语言字典树 (Expand Dictionary Interface)**
   - 修改 `frontend/src/i18n/translations.ts`，增加对应的接口定义（例如新增 `profile` 命名空间，扩充 `common` 命名空间）。
2. **填充中英文字典 (Populate Locales)**
   - 更新 `translations.zh.ts`，将提取出的写死中文字符串填入。
   - 更新 `translations.en.ts`，进行精准的英文翻译。
3. **注入并替换 (Inject & Replace)**
   - 遍历上述 10 个目标 `.tsx` 文件。
   - 补充 `import { useLang } from '../../i18n/LanguageContext';`。
   - 将所有中文字符串替换为 `t.namespace.key` 的形式。

## Verification Plan

1. 运行我们之前写的 `check_i18n.py` 脚本，确保这 10 个核心文件从“包含硬编码中文”的警报列表中彻底消失。
2. 启动前端服务，在页面上切换中英文（通常在个人主页或右上角设置），确保目标页面的文字能够实时无缝切换，且布局不因为文字长短变化而崩坏。

---

## User Review Required

> [!IMPORTANT]
> 第一阶段挑选的这 10 个核心文件是否符合您的预期？如果您希望把某些特定的模块（例如背单词或大小作文批改页面）加入第一批次，请随时告知。确认无误后我将立即开始批量修改字典和代码！
