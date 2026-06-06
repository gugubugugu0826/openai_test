# 桌面整理助手 · Qwen Desktop Organizer Agent

> 一个 Windows 桌面文件整理工具：扫描桌面 → AI 自动分类 → 人工确认 → 一键整理。
> 自带可离线运行的小模型，**无需 Ollama、无需 API Key、无需联网也能用**（规则模式）。

![version](https://img.shields.io/badge/version-v1.0-blue) ![platform](https://img.shields.io/badge/platform-Windows-lightgrey) ![python](https://img.shields.io/badge/python-3.10%2B-green)

---

## 这是什么

桌面堆满了文件、文件夹、快捷方式？这个工具会扫描你**桌面第一层**的项目，根据「记忆规则 + 内置规则 + 可选 AI」判断每一项该归到哪一类，生成一份整理方案。你检查/微调后，再一键把文件整理到目标目录。

- **安全第一**：扫描只生成方案、不动文件；整理前显示完整摘要并二次确认；文件夹默认**复制**（原文件保留）。
- **开箱即用**：自带 AI 引擎，普通用户不用装任何环境。
- **可离线**：内置小模型在本地运行，断网也能智能分类。


---

## 功能特性

- 🗂️ 桌面第一层项目扫描（文件 / 文件夹 / 快捷方式）
- 🤖 四种分类模式：自带 AI（builtin）/ 纯规则（none）/ 本地 Ollama / 云端 API
- ✅ 卡片式人工审核：开关启用/跳过、下拉直接改分类、批量改分类
- 🧠 整理记忆：记住你的分类习惯（命中关键词 → 自动归类），表格化编辑
- 📋 计划解释：让 AI 解释本次整理方案（分类统计、风险项、建议）
- 🔒 安全机制：扫描不动文件、整理前摘要二次确认、复制模式、可撤销（Undo）
- 🩺 一键诊断报告（自动隐藏 API Key）
- 🖥️ 同时提供 GUI 和命令行（CLI）

---

## 四种分类模式

| 模式 | 说明 | 是否需要联网/额外安装 |
| --- | --- | --- |
| **builtin（自带 AI，推荐）** | 内置 `llama-server` + GGUF 小模型，本地运行 | 仅首次需联网下载模型（约 1GB），之后离线可用 |
| **none（极速规则）** | 只用记忆规则 + 内置规则，最快 | 不需要 |
| **ollama** | 调用本地 Ollama + Qwen | 需自行安装 Ollama 并拉取模型 |
| **openai_compatible** | 调用云端 OpenAI 兼容 API | 需 API Key（建议用环境变量） |

> 默认推荐 **builtin**。为减小安装包体积，程序**默认不打包大模型**，首次运行时由用户选择「下载 / 手动选择本地文件 / 暂时跳过」。

---

## 快速开始

### A. 普通用户（用打包好的发布版）

1. 到本仓库 **[Releases](../../releases)** 下载 `QwenDesktopAgent_v1.0.zip` 并解压。
2. 双击 `QwenDesktopAgent.exe`。
3. 第一次打开会有引导：选整理目录 + 选分类方式；若选「智能分类」且本机没有模型，会让你**下载 / 选择本地模型 / 暂时跳过**。
4. 进入「整理桌面」页，按 ① 扫描 → ② 查看调整 → ③ 确认整理。

### B. 开发者（从源码运行）

```bash
# 1. 克隆
git clone https://github.com/<你的用户名>/<仓库名>.git
cd <仓库名>

# 2. 安装依赖（建议用虚拟环境）
pip install -r requirements.txt

# 3. 运行 GUI
python desktop_agent_gui.py
```

环境要求：**Windows**（builtin 依赖 `llama-server.exe`，且程序使用了 Windows 资源管理器调用）、**Python 3.10+**。

---

## 使用流程（GUI）

在「**整理桌面**」页面，按引导三步走：

1. **① 扫描并生成整理方案** —— 扫描桌面、AI 自动分类，生成方案（此步**不会移动文件**）。
2. **② 查看并调整方案** —— 进入「整理方案」页：
   - 用「启用」开关决定某项是否整理（关 = 跳过）；
   - 用「我的分类」下拉直接改归类；
   - 需要批量改时，勾选若干行 → 点「勾选项改分类」；
   - 改完点绿色「保存」。
3. **③ 确认并开始整理** —— 核对摘要并二次确认后正式整理（默认复制，原文件保留）。

顶部状态卡会做环境自检，显示「一切就绪」即可开始。误操作可在「高级操作」页 **Undo** 尝试撤销。

---

## 获取 AI 模型（重要）

builtin 模式需要一个 GGUF 小模型（默认 **Qwen2.5-1.5B-Instruct / q4_k_m**，约 1GB）。

- **首次运行**会弹出「获取 AI 模型」：
  - **现在下载**：自动下载到 `models/qwen-small.gguf`；
  - **我已经有模型文件**：选本地 `.gguf` 复制进来；
  - **暂时跳过**：先用极速规则分类，之后可在「设置」里切回。
- **中国大陆访问 Hugging Face 常超时**，本程序默认使用国内镜像 **hf-mirror.com**，并会在 `huggingface.co` 与 `hf-mirror.com` 之间**自动互为备用源重试**：

  ```
  https://hf-mirror.com/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf?download=true
  ```

  也可在「设置 → 自带 AI 引擎 → 模型下载地址」自定义直链（例如你自己的对象存储，速度最稳）。
- 内置服务监听 `http://127.0.0.1:18080`，提供 OpenAI 兼容的 `/v1/chat/completions`。首次启动需等模型加载完成（视机器约十几秒到几十秒）。

---

## 命令行（CLI）

无需打开界面也能用：

```bash
python desktop_agent_cli.py <command>
```

| 命令 | 作用 |
| --- | --- |
| `check` | 环境自检 |
| `scan` | 扫描桌面 |
| `preview` | 生成整理计划 |
| `review` | 生成可人工修改的审核文件 |
| `learn` | 从人工审核中学习（写入记忆） |
| `dryrun` | 预演（不动文件） |
| `apply` | 正式执行整理 |
| `undo` | 撤销上一次整理 |
| `memory` | 查看记忆规则 |
| `state` | 查看状态 |
| `run` | 自动执行到人工审核（scan → preview → review） |
| `continue` | 人工审核后继续（learn → dryrun） |

推荐顺序：`run` → 编辑 `desktop_human_review.json` → `continue` → `apply`。

---

## 整理记忆

记忆让程序记住你的分类习惯。规则保存在 `agent_memory.json`：

```json
{
  "rules": [
    { "match": "简历", "category": "简历求职", "note": "文件名含“简历”→简历求职" },
    { "match": "发票", "category": "证件合同", "note": "含“发票”→证件合同" }
  ]
}
```

- `match`：出现在文件名/路径中的关键词；`category`：归到的分类（必须是下方分类之一）；`note`：备注。
- 记忆优先级最高，命中即按记忆归类。
- 在 GUI「整理记忆」页可**表格化增删改**，无需手写 JSON。
- 在审核页改过分类后执行 `learn`，会自动把你的修改沉淀为新规则。

### 内置分类（18 类）

```
课程资料、代码项目、作业报告、简历求职、证件合同、图片截图、视频音频、
压缩包、安装包、游戏相关、临时文件、浏览器通讯、办公学习、系统工具、
影音娱乐、网盘VPN、其他快捷方式、无法判断
```

---

## 配置说明

配置在 `config.json`（发布版由 `config.release.json` 生成）。GUI「设置」页可可视化修改。

| 字段 | 说明 | 默认 |
| --- | --- | --- |
| `llm_provider` | `builtin` / `none` / `ollama` / `openai_compatible` | `builtin`（发布版） |
| `desktop_path` | 扫描路径，留空 = 当前用户桌面 | 空 |
| `normal_target_root` | 整理目标目录 | `D:\Desktop_Sorted` |
| `folder_mode` | `copy`（推荐，保留原文件）或 `move` | `copy` |
| `batch_size` | 每批送 AI 的数量 | `8` |
| `max_internal_items_per_folder` | 文件夹内部采样数量 | `200` |
| `builtin_model_path` | 内置模型路径 | `models\qwen-small.gguf` |
| `builtin_server_path` | llama-server 路径 | `runtime\llama-server.exe` |
| `builtin_server_host` / `builtin_server_port` | 内置服务地址 | `127.0.0.1` / `18080` |
| `builtin_context_size` / `builtin_threads` | 上下文长度 / CPU 线程 | `4096` / `8` |
| `builtin_model_url` | 模型下载直链（可选） | hf-mirror 直链 |
| `model` / `ollama_url` | Ollama 模型 / 接口 | `qwen2.5-coder:14b` / `localhost:11434` |
| `api_base_url` / `api_model` / `api_key` | 云端 API 配置 | — |
| `first_run_completed` | 首次引导是否已完成 | `false`（发布版） |

> **API Key 安全**：不要把 Key 写进会提交/分发的文件。推荐用环境变量：
> ```powershell
> setx DESKTOP_AGENT_API_KEY "你的 Key"
> ```
> 程序会优先读取该环境变量。诊断报告会自动隐藏 Key。

---

## 打包发布

使用 `build_release.py`（基于 PyInstaller）：

```bash
pip install -r requirements.txt
python build_release.py
```

产物在 `QwenDesktopAgent_v1.0/`，主程序 `QwenDesktopAgent.exe`。脚本会：

- 用 PyInstaller `--onedir --windowed` 打包；
- 复制 `runtime/`（AI 引擎，体积小，始终打包）；
- 按 `BUNDLE_MODEL` 决定是否打包 `models/`（**默认 False**，让安装包更小，模型首次运行再获取）；
- 把 `config.release.json` 生成为发布版 `config.json`，并写入模型下载地址、开启首次引导、清空 API Key；
- 打包前自动结束残留的 `llama-server.exe` / 旧程序进程，避免目录占用导致删除/打包失败。

> 关键打包开关（`build_release.py` 顶部）：
> - `BUNDLE_MODEL`：是否把大模型一起打包（默认 False）
> - `MODEL_DOWNLOAD_URL`：发布版的模型下载直链（默认 hf-mirror 镜像）

---

## 项目结构

```
.
├─ desktop_agent_gui.py          # 图形界面（主程序入口）
├─ desktop_agent_cli.py          # 命令行入口
├─ build_release.py              # 打包脚本
├─ requirements.txt              # 依赖：customtkinter / requests / pyinstaller
├─ config.release.json           # 发布版配置模板（请勿放真实 Key）
├─ agent_memory.json             # 整理记忆（含演示规则）
├─ runtime/                      # llama-server.exe（不入库，见 .gitignore）
├─ models/                       # qwen-small.gguf（不入库，按需下载）
└─ desktop_agent/                # 核心包
   ├─ scanner.py                 # 扫描桌面
   ├─ planner.py                 # 生成计划
   ├─ reviewer.py                # 人工审核 / 学习
   ├─ executor.py                # 执行 / 撤销
   ├─ llm_provider.py            # 四种分类后端 + 分类提示词
   ├─ builtin_llm.py             # 内置 llama-server 启动 / 就绪检测
   ├─ memory.py                  # 记忆规则
   ├─ plan_explainer.py          # 计划解释
   ├─ healthcheck.py             # 环境自检
   ├─ config.py / storage.py     # 配置 / 读写
   ├─ categories.py / version.py # 分类 / 版本
   └─ workflow.py / state.py     # 流程编排 / 状态
```

### 运行时生成的文件（已在 .gitignore 中忽略）

`desktop_observation.json`、`desktop_agent_plan.json`、`desktop_human_review.json`、
`desktop_action_log.json`、`agent_state.json`、`desktop_agent_explanation.md/json`、
`logs/`、`diagnostic_reports/`、`desktop_undo_log.txt`。

---

## 常见问题（FAQ）

**Q：分类失败，原因里出现 `503 Service Unavailable`？**
A：内置模型还没加载完就被调用了。本程序已要求 `/health` 返回 200 才算就绪，并对 503 自动重试。第一次扫描会先等模型加载（几十秒属正常）。若持续 503，多半是内存不足或模型文件损坏，查看 `logs/builtin_llm_server.log`。

**Q：模型下载进度条卡住后报错（连接 huggingface.co 超时）？**
A：中国大陆访问 Hugging Face 不稳定。程序已默认用 hf-mirror.com 镜像并自动多源重试；也可在「设置」里改成自己的国内直链，或用「我已经有模型文件」手动导入。

**Q：旧的发布目录删不掉 / 重新打包失败？**
A：通常是 `llama-server.exe` 还在后台运行占用文件。先关程序窗口（程序关闭时会自动停掉内置服务），或在 PowerShell 执行：
```powershell
taskkill /F /IM llama-server.exe
taskkill /F /IM QwenDesktopAgent.exe
```
`build_release.py` 也会在打包前自动结束这些进程。

**Q：会不会误删我的文件？**
A：不会。扫描只生成方案；整理默认是**复制**，原文件保留；整理前有摘要二次确认；可用 Undo 撤销。建议先小范围测试。

**Q：一定要联网吗？**
A：规则模式（none）完全离线。builtin 模式只在首次下载模型时需要联网，之后离线可用。

---

## 开发说明

- GUI 基于 [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter)。
- 分类提示词在 `desktop_agent/llm_provider.py` 的 `build_classification_prompt`（中英双语）。
- 内置模型服务封装在 `desktop_agent/builtin_llm.py`。
- 欢迎提 Issue / PR。

---

## 致谢

- [Qwen](https://github.com/QwenLM/Qwen) 提供的开源模型
- [llama.cpp](https://github.com/ggml-org/llama.cpp) 提供的 `llama-server`
- [hf-mirror.com](https://hf-mirror.com) 公益镜像，便利国内下载

---

