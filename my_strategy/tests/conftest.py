"""Pytest fixture setup: 把 my_strategy/ 与仓库根加入 sys.path。

集中处理后，各测试文件无需各自 sys.path.insert。
"""
import sys
from pathlib import Path

_PROJECT_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _PROJECT_DIR.parent

for p in (_PROJECT_DIR, _REPO_ROOT):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)
