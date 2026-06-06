# build_release.py

import os
import json
import stat
import time
import shutil
import subprocess
from pathlib import Path


try:
    from desktop_agent.version import APP_EXE_NAME, APP_VERSION
except Exception:
    APP_EXE_NAME = "QwenDesktopAgent"
    APP_VERSION = "v2.0"


APP_NAME = APP_EXE_NAME
VERSION = APP_VERSION

# =====================================================
# 打包选项
# =====================================================

# 是否把大模型(.gguf)一起打包进发布包。
#   False = 安装包更小，模型由 App 首次运行时“下载 / 手动选择”（推荐）
#   True  = 把 models/ 一起打进发布包（包很大，但开箱即用、可离线分发）
BUNDLE_MODEL = False

# 模型下载直链(.gguf)。打包时会写入发布版 config.json 的 builtin_model_url，
# 这样发布版在首次引导里点“现在下载”即可自动获取模型。
# 默认用 hf-mirror.com（huggingface 的国内镜像，中国大陆可直连）；程序内也会自动在
# huggingface.co 与 hf-mirror.com 之间互为备用源重试。
# 留空则发布版只能用“我已经有模型文件”手动选择本地 .gguf。
MODEL_DOWNLOAD_URL = "https://hf-mirror.com/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"

# 是否让发布版首次启动弹出引导向导（选择分类方式 + 获取模型）。
# 强烈建议 True：否则用户拿到包不会被引导去下载模型。
FORCE_FIRST_RUN_WIZARD = True


PROJECT_DIR = Path(__file__).resolve().parent
DIST_DIR = PROJECT_DIR / "dist"
BUILD_DIR = PROJECT_DIR / "build"
RUNTIME_DIR = PROJECT_DIR / "runtime"
MODELS_DIR = PROJECT_DIR / "models"

PYINSTALLER_SPEC = PROJECT_DIR / "desktop_agent_gui.spec"

RAW_DIST_APP_DIR = DIST_DIR / "desktop_agent_gui"
RELEASE_DIR = PROJECT_DIR / f"{APP_NAME}_{VERSION}"

GUI_FILE = PROJECT_DIR / "desktop_agent_gui.py"
RELEASE_CONFIG = PROJECT_DIR / "config.release.json"
MEMORY_FILE = PROJECT_DIR / "agent_memory.json"


README_TEXT = f"""桌面整理助手 (Qwen Desktop Organizer Agent) {VERSION}

一、这是什么？
一个桌面文件整理小工具。它会扫描你的桌面，自动把文件分门别类，
生成一份整理方案，你确认后再整理（默认复制，不删原文件）。

二、第一次使用
双击：{APP_NAME}.exe

第一次打开会弹出引导，让你确认两件事：
1) 整理后的文件放在哪个目录；
2) 用哪种分类方式：
   - 智能分类（推荐）：用软件自带的 AI 判断每个文件归到哪类，更准。
   - 极速规则分类：只按文件类型快速归类，不用 AI，最快。

关于 AI 模型：
为了让安装包更小，本软件默认【不自带】AI 模型。
如果你选择“智能分类”，引导会让你选择获取模型的方式：
   - 现在下载（推荐）：联网自动下载并安装到软件目录；
   - 我已经有模型文件：选择本地 .gguf 文件，复制进来；
   - 暂时跳过：先用极速规则分类，之后可在“设置”里切回智能分类。
模型只需获取一次，之后可离线使用。

三、日常使用流程（在「整理桌面」页面）
1. 看顶部状态卡，显示“一切就绪”就可以开始。
2. 点 ① 扫描并生成整理方案（此步不会移动文件）。
3. 点 ② 查看并调整方案：用开关启用/跳过，用下拉直接改分类。
4. 点 ③ 确认并开始整理，核对摘要后正式整理。

四、安全说明
1. ① 扫描只生成方案，不会移动任何文件。
2. ③ 整理前会显示完整摘要并二次确认。
3. 默认 folder_mode = copy（复制），原文件保留。
4. 如果误操作，可在「高级操作」里点 Undo 尝试撤销。
5. 建议先小范围测试。

五、几种分类模式（在「设置 → AI 模式」里切换，普通用户用默认即可）
- builtin：软件自带 AI，无需安装 Ollama 或 API Key（推荐）。
- none：只按规则分类，速度最快，不使用 AI。
- ollama：本地 Ollama + Qwen（需自行安装 Ollama 并下载模型）。
- openai_compatible：云端 API。

六、默认整理目录
D:\\Desktop_Sorted（可在引导或「设置」里修改）

七、云端 API Key 安全建议
若使用 openai_compatible 模式，不建议把 API Key 写进 config.json 后发给别人。
推荐用环境变量：
   PowerShell 临时：$env:DESKTOP_AGENT_API_KEY="你的 API Key"
   永久设置：       setx DESKTOP_AGENT_API_KEY "你的 API Key"
程序会优先读取环境变量 DESKTOP_AGENT_API_KEY。
"""


def run_command(command):
    print(f"\n[RUN] {command}")
    result = subprocess.run(command, shell=True)

    if result.returncode != 0:
        raise RuntimeError(f"命令执行失败：{command}")


def kill_leftover_processes():
    """
    打包/清理前，结束上一次发布版可能残留的进程。
    重点是 llama-server.exe —— 它由 App 在后台启动，关窗口不一定会退出，
    会一直占用 runtime/models 里的文件，导致旧目录无法删除、重新打包失败。
    """
    if os.name != "nt":
        return

    targets = [
        "llama-server.exe",
        f"{APP_NAME}.exe",
        "desktop_agent_gui.exe",
    ]

    for name in targets:
        try:
            result = subprocess.run(
                ["taskkill", "/F", "/IM", name, "/T"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                print(f"[KILL] 已结束进程：{name}")
        except Exception as e:
            print(f"[WARN] 结束进程 {name} 失败：{e}")

    # 给系统一点时间释放文件句柄
    time.sleep(1)


def _on_rm_error(func, path, exc_info):
    """rmtree 错误回调：去掉只读属性后重试。"""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def remove_path(path: Path):
    if not path.exists():
        return

    print(f"[REMOVE] {path}")

    last_error = None
    for attempt in range(1, 4):
        try:
            if path.is_dir():
                shutil.rmtree(path, onerror=_on_rm_error)
            else:
                try:
                    os.chmod(path, stat.S_IWRITE)
                except Exception:
                    pass
                path.unlink()

            if not path.exists():
                return
        except Exception as e:
            last_error = e

        # 还没删掉：可能文件仍被占用，杀进程后重试
        print(f"[REMOVE] 第 {attempt} 次未成功，尝试结束占用进程后重试…")
        kill_leftover_processes()
        time.sleep(1)

    raise RuntimeError(
        f"无法删除：{path}\n"
        "通常是文件被占用。请：\n"
        "  1) 关闭正在运行的程序窗口；\n"
        "  2) 在 PowerShell 执行：taskkill /F /IM llama-server.exe\n"
        f"     taskkill /F /IM {APP_NAME}.exe\n"
        "  3) 关闭打开了该目录的资源管理器 / 终端 / 编辑器，然后重试。\n"
        f"原始错误：{last_error}"
    )


def ensure_files():
    if not GUI_FILE.exists():
        raise FileNotFoundError(f"找不到 GUI 文件：{GUI_FILE}")

    if not RELEASE_CONFIG.exists():
        raise FileNotFoundError(f"找不到 release 配置文件：{RELEASE_CONFIG}")

    if not MEMORY_FILE.exists():
        print("[WARN] 找不到 agent_memory.json，将创建带示例规则的记忆文件。")
        MEMORY_FILE.write_text(
            '{\n'
            '  "rules": [\n'
            '    { "match": "简历", "category": "简历求职", "note": "示例规则：文件名含“简历”→简历求职（可删除）" },\n'
            '    { "match": "发票", "category": "证件合同", "note": "示例规则：含“发票”→证件合同（可删除）" },\n'
            '    { "match": "课程", "category": "课程资料", "note": "示例规则：含“课程”→课程资料（可删除）" }\n'
            '  ]\n'
            '}\n',
            encoding="utf-8",
        )


def clean_old_build():
    # 先结束可能占用文件的残留进程，避免 rmtree 失败
    kill_leftover_processes()

    remove_path(BUILD_DIR)
    remove_path(DIST_DIR)
    remove_path(PYINSTALLER_SPEC)
    remove_path(RELEASE_DIR)


def build_with_pyinstaller():
    # 注意：这里只把 config 和 memory 作为 add-data 打进去，
    # runtime/ 和 models/ 不走 PyInstaller，而是打包后再按需复制（见 create_release_folder）。
    command = (
        'pyinstaller --onedir --windowed '
        '--hidden-import customtkinter '
        '--add-data "config.release.json;." '
        '--add-data "agent_memory.json;." '
        'desktop_agent_gui.py'
    )

    run_command(command)


def patch_release_config(target_config: Path):
    """把发布版的 config.json 调整为：首次引导开启 + 写入模型下载地址。"""
    try:
        data = json.loads(target_config.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] 无法解析 release config.json，跳过补丁：{e}")
        return

    if FORCE_FIRST_RUN_WIZARD:
        data["first_run_completed"] = False

    if MODEL_DOWNLOAD_URL:
        data["builtin_model_url"] = MODEL_DOWNLOAD_URL
    else:
        data.setdefault("builtin_model_url", "")

    # 防止把云端 API Key 误打进发布包
    if data.get("api_key"):
        print("[WARN] release config.json 里含 api_key，已清空以防泄露。")
        data["api_key"] = ""

    target_config.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("[PATCH] 已更新 release config.json"
          f"（first_run_completed={data.get('first_run_completed')}, "
          f"builtin_model_url={'已设置' if data.get('builtin_model_url') else '空'}）")


def copy_runtime():
    """复制内置 AI 引擎 runtime（很小，始终打包）。"""
    if RUNTIME_DIR.exists():
        target_runtime = RELEASE_DIR / "runtime"
        print(f"[COPY] {RUNTIME_DIR} -> {target_runtime}")
        if target_runtime.exists():
            shutil.rmtree(target_runtime)
        shutil.copytree(RUNTIME_DIR, target_runtime)
    else:
        print("[WARN] runtime 文件夹不存在，跳过复制。builtin 模式将不可用。")


def copy_or_prepare_models():
    """根据 BUNDLE_MODEL 决定是否打包大模型。"""
    target_models = RELEASE_DIR / "models"

    if BUNDLE_MODEL:
        if MODELS_DIR.exists():
            print(f"[COPY] {MODELS_DIR} -> {target_models}")
            if target_models.exists():
                shutil.rmtree(target_models)
            shutil.copytree(MODELS_DIR, target_models)
        else:
            print("[WARN] BUNDLE_MODEL=True 但 models 文件夹不存在，跳过复制。")
    else:
        # 不打包模型：建一个空 models/ 目录，App 首次运行会把下载/选择的模型放进来
        target_models.mkdir(parents=True, exist_ok=True)
        print("[SKIP] 未打包大模型（BUNDLE_MODEL=False）。"
              "已创建空 models/ 目录，模型将在首次运行时获取。")


def create_release_folder():
    if not RAW_DIST_APP_DIR.exists():
        raise FileNotFoundError(f"找不到 PyInstaller 输出目录：{RAW_DIST_APP_DIR}")

    print(f"[COPY] {RAW_DIST_APP_DIR} -> {RELEASE_DIR}")
    shutil.copytree(RAW_DIST_APP_DIR, RELEASE_DIR)

    old_exe = RELEASE_DIR / "desktop_agent_gui.exe"
    new_exe = RELEASE_DIR / f"{APP_NAME}.exe"

    if old_exe.exists():
        print(f"[RENAME] {old_exe.name} -> {new_exe.name}")
        old_exe.rename(new_exe)
    else:
        print("[WARN] 没找到 desktop_agent_gui.exe，跳过重命名。")

    # 把 release 配置复制成正式 config.json
    target_config = RELEASE_DIR / "config.json"
    print("[COPY] config.release.json -> release/config.json")
    shutil.copy2(RELEASE_CONFIG, target_config)

    # 调整发布版 config（首次引导 + 模型下载地址 + 清空 api_key）
    patch_release_config(target_config)

    # 删除可能被 add-data 带进去的 config.release.json
    packaged_release_config = RELEASE_DIR / "config.release.json"
    if packaged_release_config.exists():
        packaged_release_config.unlink()

    # 确保记忆文件存在
    target_memory = RELEASE_DIR / "agent_memory.json"
    if not target_memory.exists():
        shutil.copy2(MEMORY_FILE, target_memory)

    # 内置 AI 引擎（始终打包）
    copy_runtime()

    # 大模型（默认不打包）
    copy_or_prepare_models()

    # 写说明
    readme = RELEASE_DIR / "README_使用说明.txt"
    readme.write_text(README_TEXT, encoding="utf-8")

    print(f"[OK] Release 已生成：{RELEASE_DIR}")


def verify_release_folder():
    required_paths = [
        RELEASE_DIR / f"{APP_NAME}.exe",
        RELEASE_DIR / "_internal",
        RELEASE_DIR / "config.json",
        RELEASE_DIR / "agent_memory.json",
        RELEASE_DIR / "README_使用说明.txt",
    ]

    optional_paths = [
        RELEASE_DIR / "runtime" / "llama-server.exe",
        RELEASE_DIR / "models" / "qwen-small.gguf",
    ]

    print("\n" + "=" * 80)
    print("Release Verify")
    print("=" * 80)

    ok = True

    for path in required_paths:
        if path.exists():
            print(f"[OK] {path}")
        else:
            print(f"[MISSING] {path}")
            ok = False

    if not ok:
        raise RuntimeError("Release 自检失败，有关键文件缺失。")

    print("[OK] Release 文件完整。")

    print("\nOptional builtin files:")

    for path in optional_paths:
        if path.exists():
            print(f"[OK] {path}")
        elif path.suffix == ".gguf" and not BUNDLE_MODEL:
            print(f"[SKIP] {path}（未打包大模型，首次运行时获取，属正常）")
        else:
            print(f"[OPTIONAL MISSING] {path}")


def main():
    print("=" * 80)
    print(f"Build Release: {APP_NAME} {VERSION}")
    print(f"BUNDLE_MODEL = {BUNDLE_MODEL} | MODEL_DOWNLOAD_URL = {'已设置' if MODEL_DOWNLOAD_URL else '空'}")
    print("=" * 80)

    ensure_files()
    clean_old_build()
    build_with_pyinstaller()
    create_release_folder()
    verify_release_folder()

    print("\n" + "=" * 80)
    print("打包完成。")
    print(f"发布目录：{RELEASE_DIR}")
    print(f"主程序：{RELEASE_DIR / (APP_NAME + '.exe')}")
    if not BUNDLE_MODEL:
        print("提示：本次未打包大模型，用户首次运行会被引导下载/选择模型。")
        if not MODEL_DOWNLOAD_URL:
            print("      （MODEL_DOWNLOAD_URL 为空：发布版只能“手动选择”模型，"
                  "如需“现在下载”，请填好直链再打包。）")
    print("=" * 80)


if __name__ == "__main__":
    main()