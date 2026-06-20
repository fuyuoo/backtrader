"""并行运行多组回测，每组独立 tag + 参数开关。"""
import subprocess
import sys
import os
from pathlib import Path

HERE = Path(__file__).parent

RUNS = [
    {
        'tag': 'v3_ma_bull',
        'args': ['--stock-ma-bull'],
        'log': 'logs/v3_ma_bull.log',
    },
    {
        'tag': 'v3_week_macd',
        'args': ['--week-macd-above-zero'],
        'log': 'logs/v3_week_macd.log',
    },
    {
        'tag': 'v3_month_macd',
        'args': ['--month-macd-above-zero'],
        'log': 'logs/v3_month_macd.log',
    },
]

procs = []
for run in RUNS:
    log_path = HERE / run['log']
    log_path.parent.mkdir(exist_ok=True)
    cmd = [sys.executable, '-u', 'backtest.py', '--tag', run['tag']] + run['args']
    f = open(log_path, 'w', encoding='utf-8')
    p = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=HERE)
    procs.append((run['tag'], p, f))
    print(f"[launcher] 启动 {run['tag']} PID={p.pid}")

print("[launcher] 等待所有回测完成...")
for tag, p, f in procs:
    p.wait()
    f.close()
    print(f"[launcher] {tag} 完成，退出码={p.returncode}")

print("[launcher] 全部完成")
