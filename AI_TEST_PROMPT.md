# AI 测试总控 Prompt

---

你现在是这个项目的测试负责人。请对当前仓库执行一次"尽可能自动化、可复现、可落地"的完整测试，并把发现的问题整理成文档，方便开发者逐条修复。

## 项目版本背景

当前代码基于 **v2.2**，工作区正在引入 **v3.0 功能集**。这些功能尚未视为稳定发布版，测试目标是尽早发现集成缺口、回归风险和高风险文件操作问题。

相较于上一轮测试，当前工作区新增了以下模块。这些模块是测试重点，现有测试用例几乎未覆盖：

| 新模块 | 路径 | 职责 |
|---|---|---|
| `source_manager` | `desktop_agent/source_manager.py` | 多来源配置（Source 数据类、路径校验、快照路径） |
| `incremental_scanner` | `desktop_agent/incremental_scanner.py` | 增量扫描（快照存取、新旧对比过滤） |
| `suggestion_queue` | `desktop_agent/suggestion_queue.py` | 建议队列 CRUD（追加、持久化、确认执行、路径验证） |
| `pattern_analyzer` | `desktop_agent/pattern_analyzer.py` | 历史纠错分析 → 规则建议 |
| `scheduler` | `desktop_agent/scheduler.py` | Windows 计划任务创建 / 删除 / 查询 |
| `workflow`（v3 部分） | `desktop_agent/workflow.py` | `run_suggestion_workflow`、`confirm_suggestions`、`auto_run_workflow` |
| `pages_suggestions` | `desktop_agent_ui/pages_suggestions.py` | 建议队列 GUI 页面 |
| `pages_dashboard` | `desktop_agent_ui/pages_dashboard.py` | 仪表板 GUI 页面 |

## 目标

1. 先阅读项目结构，理解核心模块、启动方式、GUI/CLI 主流程、文件读写路径和高风险操作。
2. 能自动化的优先自动化，直接编写并运行测试代码。
3. 不能自动化的部分，明确列出手工测试步骤，不要只说"手动点一点看看"。
4. 每发现一个 bug，写进 Markdown 文档，包含复现方式、实际结果、预期结果、影响范围、修复建议。
5. 修 bug 时不要顺手做无关重构，除非不改就没法稳定测试。

## 测试前置检查（必须先做）

在写测试或改代码前，先完成这些检查，并把结论写进测试报告：

1. 记录当前 Git 状态：
   - 运行 `git status --short`
   - 标明当前工作区是否有未提交改动
   - 不要回滚用户已有改动

2. 记录当前版本与发布配置：
   - 读取 `desktop_agent/version.py`
   - 检查 `README.md`、`build_release.py`、`config.release.json` 是否与当前版本/功能集一致
   - 特别检查 `config.release.json` 是否包含 v3.0 所需字段：`sources`、`suggestion_mode`、`schedule`

3. 记录现有测试基线：
   - 统计 `tests/` 下已有测试文件
   - 运行 `python tools/run_test_audit.py`
   - 如果基线失败，先记录失败，不要直接覆盖报告

4. 记录 CLI 命令现状：
   - 运行 `python desktop_agent_cli.py --help`
   - 确认帮助信息是否列出新增命令：`auto-run`, `suggestions`, `confirm`, `sources`, `schedule`, `analyze`, `multi-scan`

5. 记录 GUI 页面注册现状：
   - 检查 `desktop_agent_ui/app.py` 中是否注册了 `Suggestions` 页面
   - 启动 GUI smoke test，至少切换 `Home`、`Review`、`Settings`、`Suggestions`、`Advanced`

## 你要重点覆盖的范围

### 1. 启动与基础可用性
- `desktop_agent_gui.py` GUI 启动（`DesktopAgentGUI` 初始化、所有页面能切换且无异常）
- `desktop_agent_cli.py` CLI 帮助和命令分发（**必须验证所有新命令都在 `--help` 中出现**：`auto-run`, `suggestions`, `confirm`, `sources`, `schedule`, `analyze`, `multi-scan`）
- `config.json` 缺失 / 默认配置生成；旧格式（无 `sources` 字段）自动迁移到新多来源格式
- 日志初始化

### 2. 核心业务链路（旧）
- 扫描桌面 → 生成整理计划 → 创建人工审核文件 → Dryrun 预演 → Apply 执行 → Undo 撤销 → 计划解释生成 → 整理记忆读写

### 3. 核心业务链路（v3.0 新增，重点）
- **多来源扫描**：`scan_all_sources`，多个 Source 同时扫描，重复路径去重。必须断言两个 Source 指向同一路径或扫描出同一文件时，最终 observation / plan 不重复处理同一 `path`。
- **增量扫描**：首次运行（无快照）等同全量；第二次运行只返回新出现的文件；快照正确更新。必须断言损坏快照、空快照、缺失快照都会 fallback 到全量。
- **建议模式完整链路**：`run_suggestion_workflow` → 写入 `suggestion_queue.json` → GUI 建议页展示 → `confirm_suggestions` 实际移动文件 → 执行后队列被清空。必须断言 `selected_paths=None` 清空全队列，指定 `selected_paths` 时只移除已执行项、保留未选项。
- **自动运行**：`auto_run_workflow(silent=True)` 根据 `config.suggestion_mode` 分别走建议流和多来源流
- **历史纠错分析**：`pattern_analyzer.analyze_correction_history` 从 `history/` 读取历史 review 文件，识别重复纠错并生成规则建议；已有的规则不重复建议；`accept_suggestion` 写入记忆
- **计划任务**：`scheduler.create_scheduled_task` / `delete_scheduled_task` / `get_task_status`（mock `subprocess.run`）
- **`source_manager.validate_source_path`**：驱动器根目录、home 目录、不存在的路径均拒绝；合法子目录通过
- **`suggestion_queue` 边界**：追加重复路径不产生重复项；`validate_queue` 移除不存在路径；`plan_items_from_queue` 正确生成 executor 可用格式
- **发布模板配置**：`config.release.json` 必须能生成包含 v3.0 字段的运行配置；旧版配置经 `load_config()` 后必须自动补齐 `sources`、`suggestion_mode`、`schedule`。

### 4. Windows 特有逻辑
- 当前用户桌面 + 公用桌面合并扫描（Source id=`desktop`，path 为空时自动加 `C:\Users\Public\Desktop`）
- 快捷方式 `.lnk` / `.url` 分类路径
- `os.startfile` / `explorer` 打开目录（需 mock）
- Windows 路径与中文路径兼容性

### 5. GUI 稳定性（更新版）
- 首页扫描后跳转
- 整理方案页加载
- **设置页**：
  - 保存 / 导入 / 导出
  - 多来源管理（Source 增删、路径编辑、`scan_mode` 下拉框保存为 `"full"` / `"incremental"` 内部值而非显示文字）
  - 多来源管理中，空路径的 desktop 来源必须仍表示当前用户桌面 + 公用桌面，而不是错误保存成字面值
  - 计划任务设置（enabled、frequency、day、hour）
  - 语言切换不触发不必要的全窗口重建（仅在语言实际变化时重建）
- **建议队列页（新）**：
  - 空队列时显示使用指引而非报错
  - 加载队列项目后可勾选 / 取消、修改分类
  - 「确认并执行」调用 `_worker_execute_suggestions`，使用 `QueueWriter`（从 `utils.py` 导入，无 `NameError`）
  - 「清空队列」 / 「验证路径」按钮正常工作
  - 分类下拉框显示本地化名称，但保存到队列时仍使用内部中文分类 key
- **仪表板页（新）**：页面可正常加载，数据展示无报错
- 计划解释页展示
- 整理记忆页增删改存
- 运行日志页按钮
- 帮助页更新检查

### 6. 边界与异常（更新版）
- 缺少输入文件时的提示（观察文件、计划文件、审核文件均缺失时）
- 非法配置（`normal_target_root` 为空）
- 空数据（建议队列为空、历史 review 为空、无启用来源）
- 路径不存在（来源目录不存在时跳过而不崩溃）
- 目标目录已存在重名文件（executor 冲突解决）
- 用户取消操作
- 模型未下载 / 无网络 / 更新源异常
- **增量扫描快照损坏或为空**：应 fallback 到全量扫描
- **建议队列文件损坏**：`load_queue()` 应返回空队列而不抛异常
- **计划任务创建失败**（无管理员权限）：函数返回 `False` 而不崩溃

## 执行要求

1. 先查看仓库里是否已有：
   - `tests/`（当前有 12 个测试文件，覆盖旧模块）
   - `tools/run_test_audit.py`
   - `test_reports/latest_test_report.md`

2. 先运行现有基线测试：

```bash
python tools/run_test_audit.py
```

   **已知问题**：上一轮测试的 CLI smoke test 输出仍显示旧命令列表（缺少 `auto-run` 等新命令），请在新一轮中验证并修复该问题。

3. **重点补充以下新测试文件**（现有测试完全缺失）：

| 测试文件 | 覆盖目标 |
|---|---|
| `tests/test_source_manager.py` | `validate_source_path`、`load_sources`、`get_enabled_sources`、`Source.resolved_path` |
| `tests/test_incremental_scanner.py` | `save_snapshot`、`load_snapshot`、`filter_new_items`、`scan_incremental_or_full` |
| `tests/test_suggestion_queue.py` | `append_suggestions`（去重）、`validate_queue`（移除失效路径）、`plan_items_from_queue`、`load_queue`（文件损坏 fallback） |
| `tests/test_pattern_analyzer.py` | `analyze_correction_history`（空历史、低于阈值、达到阈值、已在记忆中则跳过）、`accept_suggestion` |
| `tests/test_scheduler.py` | `create_scheduled_task`、`delete_scheduled_task`、`get_task_status`（全部 mock `subprocess.run`） |
| `tests/test_workflow_v3.py` | `run_suggestion_workflow`（mock scan+plan）、`confirm_suggestions`（mock apply）、`auto_run_workflow`（mock config） |

除新增文件外，也要补充或更新已有测试：

| 现有测试 | 需要补充 |
|---|---|
| `tests/test_config.py` | 旧配置迁移到 `sources`、`suggestion_mode`、`schedule`；`config.release.json` 字段完整性 |
| `tests/test_scanner_full.py` | `scan_all_sources` 多来源合并、重复路径去重、来源路径不存在时跳过 |
| `tests/test_executor_full.py` | suggestion confirm 生成的 review 文件能被 executor 正确消费 |
| `tests/test_plan_explainer.py` | 多来源、建议模式相关摘要字段不报错 |

4. 测试规范：
   - 使用 `unittest` + `tempfile` + `unittest.mock`
   - 避免污染真实桌面、真实配置、真实任务计划表
   - mock `load_config()`、`os.startfile()`、`subprocess.Popen()` / `subprocess.run()`
   - mock 网络请求（`urllib.request`、`requests`）
   - 测试涉及 `config.json`、`suggestion_queue.json`、`desktop_agent_plan.json`、`desktop_human_review.json`、`snapshots/`、`history/` 时，必须在 `tempfile.TemporaryDirectory()` 内切换工作目录或 mock 路径
   - 测试不能依赖真实 `C:\Users\Public\Desktop`、真实用户桌面、真实下载目录

5. 自动化测试完成后，请输出：
   - 新增/修改了哪些测试文件
   - 哪些测试通过
   - 哪些测试失败（含完整 traceback）
   - 新发现的 bug 列表
   - 哪些部分必须人工测试

6. 如果发现实现与本 prompt 不一致：
   - 先判断这是测试预期错误、实现缺口，还是产品需求未定
   - 在报告里单独列为「需求/实现不一致」
   - 不要为了让测试通过而静默降低测试标准

## Bug 文档要求

如果自动化测试失败，或者手工测试发现问题，把问题写到：

`test_reports/latest_test_report.md`

每个 bug 至少包含：

- 标题
- 影响模块
- 复现步骤
- 实际结果
- 预期结果
- 严重程度（P0 崩溃 / P1 功能缺失 / P2 显示异常 / P3 体验问题）
- 修复建议

## 人工测试要求

如果某部分不适合自动化，请给出明确手工步骤，例如：

**建议模式完整链路（需真实 LLM）**：
1. 在设置页为桌面来源开启"建议模式"
2. 点击"扫描"，等待完成
3. 进入"建议队列"页，确认有条目出现
4. 修改 1 条建议的分类
5. 点击"确认并执行"
6. 检查目标目录结构是否按修改后的分类移动
7. 检查队列是否已清空

**计划任务（需管理员权限）**：
1. 在设置页开启"定时整理"，设置为每周日 09:00
2. 保存设置
3. 打开 Windows 任务计划程序，确认出现 `DesktopAgentAutoRun` 任务
4. 再次关闭"定时整理"并保存，确认任务被删除

**GUI 设置页 Source 下拉框翻译验证**：
1. 打开设置 → 整理来源管理
2. 确认"模式"下拉框显示"完整"/"增量"（中文），不是"full"/"incremental"
3. 切换选项并保存，重新打开设置，确认值持久化正确

不要只写"人工确认页面正常"。

## 输出风格

- 优先给结论
- 再列 bug
- 最后列测试覆盖缺口
- 不要泛泛而谈
- 不要只给建议，不写实际执行结果

---

如果你发现某部分无法自动化，请明确说明"为什么不能自动化"和"建议如何人工测试"。
