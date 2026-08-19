---
name: ssteve-pr
description: >
  Use this skill whenever working in the SSTeVe repository
  (`/Users/jeremyfuksa/Dev/SSTeVe`) and about to commit, push, open a PR, or
  merge. Triggers on: any commit/push/PR in that repo, "ship this", "open a
  PR", "land this", "merge on green", or creating a `fix/*`, `feat/*`,
  `chore/*`, `test/*`, or `docs/*` branch. Encodes this repo's Definition of
  Done (three gates, all run from `sstv_core/`), the ~25 minute CI reality
  that makes local verification non-optional, and the branch-then-PR rule.
  Load-bearing because on 2026-08-19 three commits were made directly to main
  in this repo and had to be unwound, and PR bodies with apostrophes broke
  `gh pr create` twice when passed inline instead of via `--body-file`.
---

# SSTeVe shipping discipline

SSTeVe only (`/Users/jeremyfuksa/Dev/SSTeVe`). Somewhere else, this doesn't apply.

## Always `cd sstv_core` first

pytest, uv, ruff, mypy, and alembic are all rooted there, not at the repo root.
Running them from the top gives confusing failures or silently finds nothing.
Shell working directory resets between tool calls — use absolute paths or
re-`cd` in each command rather than assuming it persisted.

## Definition of Done

From `sstv_core/`, all three before you push:

```bash
uv run pytest              # full suite, no exclusions
uv run ruff check src/     # clean for files you changed
uv run mypy src/           # clean for files you changed
```

The gradient roundtrip gate in `tests/decode/regression/test_roundtrip.py` is
the canary for encoder/sync regressions. Never skip it.

API changes additionally require `docs/core/backend-spec.md` and
`docs/core/openapi.json` regenerated via `scripts/export_api_docs.py`.

## The suite takes ~10 minutes locally, ~25 in CI

Long enough that "push and see" wastes half an hour per round trip. Run it
locally, in the background, and do other work while it runs — but do not open
a PR before it comes back green.

**Run the whole suite, not the subset you think you touched.** On 2026-08-19 a
decode change passed every decode test while breaking the CLI and SDR
roundtrips; only the full run caught it.

## Renaming a CI job breaks every merge

Branch protection on main requires the workflow's job names as status checks,
with `strict` set. Rename a job and the old required check never reports
again, so every PR sits `BLOCKED` with all its checks green -- including PRs
that have nothing to do with CI.

On 2026-08-19 renaming `python-tests` to `fast` and `slow` did exactly that.
The fix is to update the required-checks list in the same change:

```bash
echo '{"strict":true,"contexts":["fast","slow"]}' | \
  gh api -X PATCH repos/jeremyfuksa/ssteve/branches/main/protection/required_status_checks --input -
```

That is a repo-wide security setting, so expect to hand it to Jeremy rather
than run it unprompted.

## Branch, then PR. Never commit to main.

This repo has CI, so main is off limits for direct pushes. If you find you
have already committed to main:

```bash
git checkout -b <type>/<slug>       # carries the commits with you
git branch -f main origin/main      # put main back
```

One concern per PR. If a branch has grown two unrelated ideas, say so in the
PR body and offer to split rather than quietly shipping both.

## Commit messages

Semantic subject: `type(scope): summary` — `feat`, `fix`, `docs`, `chore`,
`test`, `ci`, `release`. Body explains *why*, and carries the measurement when
there is one. This repo's history is unusually good at this; match it.

Always via HEREDOC, never `-m` with embedded quotes:

```bash
git commit -q -F - <<'MSG'
fix(sdr): let --gain reach the samples, not just the analog stage

...body...

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

## PR bodies go in a file

`gh pr create --body "..."` breaks on apostrophes — it happened twice on
2026-08-19. Write the body to the scratchpad and pass `--body-file`:

```bash
gh pr create --title "..." --body-file "$SCRATCH/pr.md"
```

End PR bodies with:

```
🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

## Merging

`deleteBranchOnMerge` is on, and a global post-merge hook prunes local
branches whose upstream is gone. So:

```bash
gh pr merge <n> --squash --delete-branch
```

Then verify on merged main — not just that CI passed. For decode changes that
means actually decoding something and looking at the picture.

## What "done" means

Not "pushed". Merged, and verified working on main. If part of the work is
blocked, finish everything else and say plainly what you left and why.
