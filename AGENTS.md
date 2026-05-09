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

<claude-mem-context>
# Memory Context

# [backtrader] recent context, 2026-05-09 6:44pm GMT+8

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision 🚨security_alert 🔐security_note
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (19,902t read) | 526,699t work | 96% savings

### May 9, 2026
S433 Build an intelligent stock factor screening system with entry timing, multi-timeframe MACD analysis, sector alignment filters, MA60 distance thresholds, take-profit optimization, and position-sizing rules — with backtesting and auto parameter tuning. (May 9, 3:34 PM)
S434 新增智能股票因子筛选系统：MA60距离过滤 + 个股均线多头排列 + 周线/月线MACD区间过滤，并将这些参数化以便对比回测 (May 9, 3:47 PM)
1187 3:50p 🔵 Indicator CSVs Already Contain week_macd_zone and month_macd_zone Columns
1188 " 🔵 MACD Zone Calculation Pipeline in calc_indicators.py
1189 " 🔵 MACD Zone Schema and Critical Data Gap: sector_momentum is Empty
1190 3:51p 🔵 backtest.py Has Two addstrategy Call Sites
1191 " 🔵 Second addstrategy Call is Single-Stock Mode with max_positions=1
1192 3:52p 🟣 StockData Feed Extended with ma144, week_macd_zone, month_macd_zone Lines
1193 " 🟣 Three New Filter Parameters Added to MyStrategy
1194 " 🟣 Entry Filter Logic Implemented in MyStrategy.next() for MA Bull and Multi-Timeframe MACD
1195 " 🔴 MACD Zone String-to-Integer Encoding Added in load_feeds()
S435 查看股票回测归因结果并运行并行回测脚本 (May 9, 3:54 PM)
S438 Backtest completion check and full strategy comparison analysis across v2_dist5pct_no_add, v3_ma_bull, v3_week_macd, v3_month_macd (May 9, 4:13 PM)
1198 4:27p 🔵 Backtest Status Check in Backtrader Project
1199 " 🔵 Parallel Backtest Running with Three Strategies
1201 4:28p 🔵 All Three Parallel Backtests Completed Successfully
1202 " 🔵 trade_summary.csv Not Generated; Reports Use Different File Naming
1204 " 🔵 All Three Strategies Producing Identical Results — Possible Bug in run_parallel.py
1205 " 🔵 trade_summary.csv Located in results/ Not reports/ Directory
1206 " 🔵 ConstantInputWarning Flooding v3_ma_bull_err.log from Spearman Correlation in Attribution
1208 4:29p 🔵 Strategy Filter Parameters Flow Traced: CLI Flags → backtest.py cfg → strategy.py
1209 " 🔵 backtest.py main() Confirmed: --tag Sets Output Dirs, Filter Flags Are Separate
1210 " 🔵 Strategy Entry Filter Logic: Sequential Guards with MACD Zone and MA Bull Conditions
1212 4:30p 🔵 results/ Directory Contains Both Untagged Root Files and Tagged Subdirectories
1213 " 🔵 trade_list.csv Confirmed in v3_ma_bull Subdirectory; python3 Command Absent on Windows
1215 " 🔵 Strategies Have Different trade_list.csv Row Counts But Identical Aggregated Statistics — Confirmed Reporting Bug
1217 4:31p 🔵 trade_summary.csv Schema Confirmed: 40+ Fields Including Per-Trade Alpha, MFE/MAE, and Forward Returns
1218 " 🔵 Strategy Filter Performance Comparison: v3_ma_bull and v3_month_macd Outperform Base Strategy
1219 " 🔵 Attribution Runner Receives cfg But May Read trade_summary from Wrong Path
1220 " 🔵 attribution_runner.py Correctly Reads trade_summary from cfg Results Dir; 5-Step Pipeline Confirmed
1221 4:32p 🔴 Root Cause Confirmed: attribution.py Hardcodes results/trade_summary.csv — Ignores cfg results_dir
1222 " 🔴 Fixed: attribution.py trade_summary Path Now Uses cfg results_dir
1223 4:33p 🔵 Full Strategy Performance Comparison: v3_ma_bull Best Quality, v2 Base Highest Total PnL
1224 " 🔵 Exit Reason Analysis: MA60 Stop-Loss Dominates at 57%; Strategies Share Identical Holding Day Profiles
S440 Universal Backtesting System Design — Architecture for a strategy research platform with automated attribution, regime detection, and parameter optimization (May 9, 4:33 PM)
1226 4:37p ⚖️ Universal Backtesting System Design Requirements Defined
S441 全面系统分析（gap analysis）：当前量化交易系统的能力盘点与缺口识别，输出分层改造建议 (May 9, 4:37 PM)
1227 5:00p 🔵 Comprehensive System Gap Analysis Requested for Trading Strategy Project
1228 " 🔵 Backtrader-Based Strategy System Gap Analysis Plan Initiated
1229 " 🔵 Backtrader Project Root Structure Mapped
1230 5:01p 🔵 Core Strategy Logic: MA+DEA-Based Entry with ATR Dynamic Take-Profit
1231 " 🔵 Backtest Pipeline: PIT Universe Filtering, Multi-Stock Cerebro, Auto-Attribution
1232 " 🔵 Config: Backtest Parameters, SW Industry Codes, Indicator Profiles
1233 " 🔵 Attribution Pipeline: 5-Stage Post-Backtest Analysis Architecture
1234 " 🔵 Roadmap: Scorer, Market Timing, Walk-Forward, Auto-Tune All Planned But Not Implemented
1235 " 🔵 Auto-Tuning Design Spec: Master-Worker Claude Agent Architecture for Parameter Optimization
1236 " 🔵 Parallel Backtest Runner: run_parallel.py Launches 3 Configuration Variants Simultaneously
S442 全面系统分析（gap analysis）完成后的进度检查点——Claude响应为空（无新工作内容） (May 9, 5:05 PM)
S443 Backtrader my_strategy refactoring & CSI 300 constituent mapping — architecture planning discussion (Chinese), no implementation done (May 9, 5:06 PM)
1237 5:15p ⚖️ Backtrader Strategy Refactoring & CSI 300 Constituent Mapping Plan
S444 Write a platformization design document for the my_strategy backtrader research project (May 9, 5:16 PM)
1238 5:21p 🔵 Trading Strategy Project Structure Identified
1239 " 🔵 Windows Sandbox Shell Execution Failing with CreateProcessAsUserW Error 1312
1240 5:23p 🔵 Backtrader Strategy Project Spec Document Inventory
1241 5:26p 🟣 my_strategy Platformization Design Document Created
1252 6:37p ✅ Strategy Platformization Design Document Created for Backtrader Project
S447 Write a strategy platformization design document based on the spec file at docs/superpowers/specs/2026-05-09-my-strategy-platformization-design.md using the brainstorming skill (May 9, 6:37 PM)
1253 6:43p 🔵 Pre-Commit Repository State in backtrader Project
1254 " ✅ AGENTS.md Substantially Expanded with 222 New Lines
1255 6:44p 🔵 learn_backtrader Is a Nested Git Repository with 7 Lesson Files

Access 527k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>