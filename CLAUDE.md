# CLAUDE.md

* 全程使用中文回答
* 不允许静默处理和降级操作，要暴露异常
Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

# Project: Backtrader 量化回测

## Purpose

This repo is used for **AI-assisted quantitative backtesting** using the backtrader framework. The primary goal is learning and building strategies — the source code is kept local so AI can read it directly.

## Repository Layout

```
backtrader/               ← git repo root (also the Python package source)
├── backtrader/           ← backtrader library source (imported by all scripts)
│   ├── cerebro.py        ← engine entry point
│   ├── strategy.py       ← base Strategy class
│   ├── indicator.py      ← base Indicator class
│   ├── feed.py           ← base DataFeed class
│   ├── broker.py         ← broker facade
│   ├── brokers/bbroker.py  ← BackBroker implementation
│   ├── analyzers/        ← built-in analyzers (sharpe, drawdown, etc.)
│   ├── indicators/       ← built-in indicators (EMA, MACD, etc.)
│   ├── feeds/            ← built-in data feeds (pandafeed, csvgeneric, etc.)
│   └── filters/          ← data filters (resample, calendar, etc.)
└── learn_backtrader/     ← tutorial lessons (Lesson1–7)
    ├── Data/
    │   ├── daily_price.csv     ← sample OHLCV data
    │   ├── trade_info.csv      ← sample fundamental data
    │   └── tushare_token.json  ← Tushare API token (do not commit changes)
    └── Lesson1.py … Lesson7.py
```

**Import resolution**: scripts in `learn_backtrader/` resolve `import backtrader` to the local `backtrader/backtrader/` package because the parent directory is on `sys.path`. The pip-installed version is shadowed and not used.

## Running Lessons

```powershell
cd backtrader\learn_backtrader
python Lesson1.py   # runs individual lesson
```

Batch test all lessons:
```powershell
cd backtrader\learn_backtrader
python -c "
import subprocess, sys
lessons = ['Lesson1.py','Lesson2.py','Lesson3.py','Lesson4.py','Lesson5.py','Lesson6.py','Lesson7.py']
for l in lessons:
    r = subprocess.run([sys.executable, l], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
    print(('OK' if r.returncode==0 else 'FAIL'), l)
    if r.returncode != 0: print(r.stderr[-500:])
"
```

## Error Handling Policy

**No silent degradation.** When something fails, raise the real error. Do not:
- Catch exceptions and return `None` silently
- Use `try/except pass` to hide failures
- Fall back to a default that masks the root cause

The only accepted pattern is graceful degradation for **optional dependencies** (e.g., pyfolio), where the absence is explicitly printed:
```python
try:
    import pyfolio as pf
except ImportError:
    raise ImportError("pyfolio is required for this feature. Install with: pip install pyfolio")
```

## backtrader Architecture: Key Concepts for AI

**Execution model**: `cerebro.run()` drives a bar-by-bar loop. Each bar calls `Strategy.next()`. Indicators are computed lazily via `LineBuffer`.

**MetaParams**: `bt.Strategy`, `bt.Indicator`, `bt.Analyzer` all use `MetaParams` metaclass. The `params` class attribute must be a tuple of `(name, default)` pairs — never use `...` (Ellipsis) or non-string names, it will raise `TypeError: attribute name must be string`.

**Lines protocol**: Every data feed and indicator exposes `.lines` (a `Lines` object). Access by index (`self.data.lines[0]`) or name (`self.data.lines.close`). `[0]` = current bar, `[-1]` = previous bar.

**Order lifecycle**: `buy()`/`sell()` returns an `Order` object immediately, but execution happens on the **next bar** by default. Use `notify_order()` to track status changes (Submitted → Accepted → Complete/Rejected).

**Key source files to read when debugging**:
- `cerebro.py` — `run()`, `runstrategies()`, optimization loop
- `brokers/bbroker.py` — order matching, slippage, commission logic
- `feeds/pandafeed.py` — how PandasData maps DataFrame columns to lines
- `strategy.py` — `next()`, `notify_order()`, `notify_trade()` hooks

## Data

- `Data/daily_price.csv`: A-share daily OHLCV, columns: `date, open, high, low, close, volume`
- `Data/tushare_token.json`: `{"token": "..."}` — read by Lesson2/3/7 for live Tushare API calls
- Tushare data requires a valid token; if the token is expired or rate-limited, the API call will raise an exception — do not catch and suppress it

## Known Constraints

- Python 3.14+: `......` (two consecutive `...` tokens) is a `SyntaxError`. Use single `...` inside class/function bodies.
- `cerebro.signal_concurrent(True)` — not `signal_concurrency` (wrong name raises `AttributeError`)
- `pyfolio` is not installed; any code path requiring it must either install it or raise a clear error
- Lessons 4, 5, 6, and parts of 7 contain reference/pseudo-code wrapped in `if False:` — this is intentional to keep educational content without causing runtime errors

## 文档维护规则（强制）

每次完成新需求 / 功能改动后，**必须同时更新以下两份文件**，否则任务视为未完成：

1. **`docs/FEATURES.md`** — 功能总览（当前快照）
   - 若改动影响某模块的输入/输出/配置/行为，更新对应章节
   - 若新增模块，增加新章节并更新目录结构与命令速查
   - 若仅是内部重构、不改变外部行为，可在对应章节末尾用一行注明（或不更新）

2. **`docs/CHANGELOG.md`** — 更新记录（追加式）
   - 在文件**顶部**追加一条记录，格式：
     ```
     ## YYYY-MM-DD — 一句话标题
     - 需求：用户原始需求摘要
     - 改动：新增/修改/删除的文件与要点
     - 影响：对其他模块的影响（可选）
     ```
   - 日期使用绝对日期；同一天多条改动各占一条

适用范围：仅限 `my_strategy/` 下的功能演进。修改 `learn_backtrader/` 教程或 `backtrader/` 框架源码不在此规则内。


## 7. 使用 superpowers 前先确认 Git 工作区干净

**调用任何 superpowers skill（如 brainstorming、writing-plans、executing-plans、subagent-driven-development、test-driven-development 等）前，`MUST` 先检查 Git 工作区状态，不得在被污染的环境中开始工作。**

- 执行 superpowers 流程前，先运行 `git status`，确认是否存在未提交的修改、未跟踪文件或未合并状态。
- 工作区干净时方可直接开始；如存在未提交改动，`MUST` 向用户列出改动范围并取得明确确认（"可以在当前状态下继续" 或 "先提交/暂存再开始"），不得自行判断改动是否相关。
- 不允许在多任务改动堆叠的状态下直接进入新一轮 superpowers 流程；新任务的 diff 必须可与既有改动清晰区分。
- 用户明确要求"忽略当前未提交改动直接开始"时方可继续，并在执行说明中记录该例外。