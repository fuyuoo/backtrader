# Domain Docs

This repo uses a single-context domain documentation layout.

## Before exploring, read these

- `CONTEXT.md` at the repo root for domain language.
- `docs/adr/` for architectural decisions that touch the area being worked on.
- `docs/architecture/project-structure.md` for where new modules, commands, scripts, and tests belong.

If these files do not exist, proceed silently. The producer skill creates them lazily when terms or decisions are resolved.

## File structure

```text
/
├── CONTEXT.md
├── docs/adr/
├── docs/architecture/
└── attbacktrader/
```

## Use the glossary's vocabulary

When output names a domain concept in an issue title, refactor proposal, hypothesis, or test name, use the term as defined in `CONTEXT.md`. Do not drift to synonyms the glossary explicitly avoids.

If the concept needed is not in the glossary yet, either reconsider the language or note the gap for a future `grill-with-docs` session.

## Flag ADR conflicts

If output contradicts an existing ADR, surface it explicitly rather than silently overriding it.
