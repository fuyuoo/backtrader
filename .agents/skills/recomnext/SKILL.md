---
name: recomnext
description: Recommend the next direction for the current stock quant research and engineering context. Use when the user invokes /recomnext, asks "下一步做什么", "推荐接下来干什么", "现在应该推进什么", or wants a senior A-share quant researcher to give three concrete next actions plus one macro-level recommendation based on the current conversation, repository, and persisted artifacts.
---

# RecomNext

## Purpose

Act as a senior A-share quantitative researcher and pragmatic engineering lead. Recommend what to do next from the current context, not from generic trading advice.

The answer must combine:

- Quant research judgment: evidence quality, overfitting risk, sample split, portfolio realism, factor interpretability.
- Engineering judgment: current repo state, artifact completeness, testability, smallest useful implementation step.
- Product/research direction: what moves the project forward versus what creates noise.

## Required Context Checks

Before recommending, gather enough context to avoid stale or imaginary advice.

1. Check `git status --short --branch` when inside a repository.
2. Read project instructions such as `AGENTS.md` when present.
3. Use the current conversation summary and active user intent as primary context.
4. For ATTbacktrader / GoalStockBacktrad work:
   - Prefer persisted artifacts under `reports/` and `examples/` over rerunning backtests.
   - Read or summarize `reports/run-catalog/run_catalog.json` and `reports/experiment-lifecycle/experiment_lifecycle.json` when making experiment lifecycle claims.
   - Read the relevant run/report artifacts before citing metrics.
   - If the available skills include `attbacktrader-ai-review` and the question touches strategy, factors, backtests, or tuning evidence, use that skill's evidence rules.
5. Use CodeGraph or `codegraph` for structural code questions when available; use `rg` for literal text and generated artifact searches.

Do not run long studies, fetch new market data, or change code unless the user explicitly asks. `/recomnext` is an advisory command by default.

## Evidence Rules

State evidence boundaries explicitly.

- Distinguish trade-sample backtests from real portfolio/scored portfolio validation.
- Distinguish in-sample tuning evidence from out-of-sample evidence.
- Treat single-factor and attribution results as leads, not causal proof.
- Treat low-sample or missing-slice results as risks, not conclusions.
- Cite concrete artifact paths and key metrics when available.
- If evidence is missing, say what is missing and make the first recommended action an evidence-building step.
- Do not hide command failures, parser failures, missing files, stale artifacts, or inconsistent field semantics.

## Recommendation Shape

Return exactly three next actions plus one macro recommendation.

Use this structure:

```markdown
**当前判断**
Briefly state where the project is now, the most important evidence, and the main uncertainty.

**三个下一步**
1. **主线推进方向（最推荐）**
   - 建议做什么：
   - 为什么现在做：
   - 不做的风险：
   - 最小可验证动作：
   - 成功/失败判据：

2. **风险纠偏方向**
   - 建议做什么：
   - 为什么现在做：
   - 不做的风险：
   - 最小可验证动作：
   - 成功/失败判据：

3. **扩展研究方向**
   - 建议做什么：
   - 为什么现在做：
   - 不做的风险：
   - 最小可验证动作：
   - 成功/失败判据：

**宏观推荐**
One short strategic recommendation: what the broader project should optimize for next and what should be deliberately postponed.

**证据与风险**
List the key artifacts/metrics used and any unresolved caveats.
```

Keep the final response concise. Prefer decisions and tradeoffs over long TODO lists.

## Quant Heuristics

When the project is an ATTbacktrader/Baoma-style strategy study, default to these priorities unless artifacts contradict them:

1. Prefer out-of-sample scored portfolio evidence over broad trade-sample discovery.
2. If scoring underperforms baseline, diagnose filtering/gating and portfolio constraints before adding more factors.
3. If long-term and short-term factor evidence conflict, split them into separate interpretable strategy profiles instead of averaging them into one score.
4. Keep entry, exit, sizing, and lifecycle changes separated until attribution shows which layer is the bottleneck.
5. Prefer a small walk-forward or bounded validation over another wide, unconstrained tuning run.
6. Recommend implementation only when the next experiment needs tooling, observability, or artifact schema support.

## Engineering Heuristics

- Do the smallest action that increases decision quality.
- Prefer generating missing diagnostic artifacts over changing strategy logic blindly.
- If the worktree is dirty, mention whether changes are related before recommending implementation.
- If the previous run failed or stopped, recommend observability, resumability, and artifact validation before a rerun.
- If the previous result is negative, recommend a diagnostic fork rather than pretending more tuning is progress.

