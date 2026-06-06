import os
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from desktop_agent.version import APP_VERSION


def main():
    ref_name = os.environ.get("GITHUB_REF_NAME", "").strip()
    if not ref_name:
        raise SystemExit("缺少 GITHUB_REF_NAME，无法校验 tag。")

    if ref_name != APP_VERSION:
        raise SystemExit(
            f"Git tag 与代码版本不一致：tag={ref_name}，APP_VERSION={APP_VERSION}\n"
            "请先更新 desktop_agent/version.py，或重新创建正确的 tag。"
        )

    print(f"Tag/version 校验通过：{ref_name} == {APP_VERSION}")


if __name__ == "__main__":
    main()
