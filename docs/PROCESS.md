# How work happens in SSTeVe

How a change gets filed, labelled, built and released. Written 2026-09-11, when
the tracker held four theme milestones that could never reach zero and no answer
to "what is left before the app exists".

The structure is lifted from Bearpaw's `docs/PROCESS.md`, which was written
after a release cycle ended in a scramble. Borrowing it before SSTeVe has
shipped anything is the cheap version of that lesson.

Every rule names what enforces it. A rule with no enforcement says so, and
unenforced rules are the ones to suspect first when reality disagrees.

## The principle: one home per fact

| Question | The one home |
| --- | --- |
| What kind of change is this, and how bad? | Labels — one value per axis |
| What is in this release? | The milestone |
| When might this happen, if ever? | The project board's `Horizon` field |
| Where is this right now? | The project board's `Status` field |
| What changed for a user? | `CHANGELOG.md` |
| Is this branch finished? | It does not exist — merged branches are deleted |

Where two objects could answer the same question, one of them is wrong. The
`blocked: frontend` label is the one survivor of the old scheme: it marks work
that cannot start until the shell renders, and it goes away when v0.1.0 ships.

## 1. File an issue first

**Every `feat` links an issue.** A feature is planned work: the issue carries
the user story, the labels and the milestone, and the pull request closes it
with `Closes #123`.

**A `fix`, `docs` or `chore` does not need one.** Most fixes here are
*discovered* — found at the bench, in a live listen, or while measuring
something else. Three of the four bugs open today were found that way in a
single session. Demanding an issue for each would make the rule noise.

File an issue for a fix when you want it tracked: something you are not fixing
today, something that needs hardware you do not have, anything that should
appear in a release scope query.

### Every issue opens by saying who it is for

A `feat` starts with a **user story**, written situation-first:

> When I'm *&lt;situation&gt;*, I want *&lt;capability&gt;*, so that *&lt;outcome&gt;*.

Situation first because PRODUCT.md designs for *operating situations*, not user
archetypes — at the desk, field ops, degraded signal, receive-only, eyes-free,
scripted. Four archetypes were retired on 2026-08-07 for being unsourced; an
issue that can only say "as an operator" is usually a solution looking for a
problem.

A `bug` answers the same question as **impact**: who is affected and what they
cannot do. That is what sets the severity.

A `chore` has neither, on purpose.

## 2. Label it on four axes

| Axis | How many | Values |
| --- | --- | --- |
| **type** | exactly one | `bug`, `feat`, `docs`, `chore` |
| **area** | one or more | `engine`, `sdr`, `api`, `desktop`, `cli`, `ci`, `accessibility` |
| **severity** | required on `bug`, absent otherwise | `severity: high`, `severity: medium`, `severity: low` |
| **size** | only when it is not an item | `goal`, `epic` |

Areas map to the tree: `engine` is DSP, decode and encode; `sdr` is
SpyServer/USB/demodulation; `api` covers the REST/WebSocket layer, database and
config; `desktop` is `sstv_desktop/`; `cli` is the command line; `ci` is
workflows and packaging; `accessibility` is eyes-free operation and sonification.

Severity, in this project's terms:

- **high** — data loss, **a record that lies**, or the headline feature does not
  work. A record that lies is high because the damage leaves SSTeVe: a remote
  reception exported as a QSO lands in LoTW and eQSL, in other operators' logs.
- **medium** — a real functional problem with a workaround or a narrower
  trigger. A mode that fails to decode is here unless it is the only mode.
- **low** — polish, test reliability, documentation.

There is deliberately **no release label**: the milestone already says that.

## 3. Put it in a milestone — if it is an item

| Size | Label | Milestone? |
| --- | --- | --- |
| **Goal** — a direction, possibly years | `goal` | **Never** |
| **Epic** — a container that spawns items across releases | `epic` | **Never** |
| **Item** — one shippable change | none | **Always** |

A milestone has to be able to reach zero, because the release gate will read it.
An epic spans releases by definition, so an epic inside one keeps it open
forever. That is how the four theme milestones ("2: Frontend enablement",
"4: SDR epoch") became unanswerable: they mixed epics, hardware-blocked work and
shippable items, so "what is left" had no cheap answer.

Attach an epic's children with **sub-issues**, which gives it a real progress
bar rather than a list in prose that nothing can read.

### The releases

| Milestone | One sentence |
| --- | --- |
| `v0.1.0` | Listen to a SpyServer: the first bundled app, receive-only. |
| `v0.2.0` | Your own radio: sound-card receive and transmit, PTT, local USB SDR. |
| `v0.3.0` | The log: QSO logging, reception reports, ADIF, MMSSTV import. |
| `v1.0.0` | Beta: calibration and validation against real use, signed installers. |

If you cannot say what a release is in one sentence, it is too big.

### Where intent lives instead

On the **`Horizon`** field of the
[SSTeVe project](https://github.com/users/jeremyfuksa/projects/3) — `Now` /
`Next` / `Later` / `Someday`. Nothing gates on it, so it is free to be
aspirational. HackRF support (#155) sits at `Someday` with no milestone:
visible on the roadmap, invisible to any gate.

## 4. Triaging a bug found mid-flight

| Severity | Goes to | Effect |
| --- | --- | --- |
| `high` | the current release | blocks it |
| `medium`, `low` | the next milestone | delays nothing |

Keep the next milestone open as well as the current one, so a bug found today
has somewhere obvious to go that is not "the thing we are trying to ship".

This matters more here than the commit count suggests. Four of the five
measurable defects found on 2026-09-11 were discovered while building something
else, and none of them were the thing being built. Discovery is the normal
state of this project, not an exception to plan around.

## 5. Track it on the board

The `SSTeVe` project board carries `Status` and `Horizon`. **The board is a
view, not a source of truth** — its data lives outside the repository and cannot
gate CI. Where the board and the milestone disagree, the milestone wins.

## 6. Branch, then PR. Never commit to main.

Off `main`, prefixed with the type: `fix/`, `feat/`, `docs/`, `chore/`, `ci/`,
`test/`. Three commits went straight to main on 2026-08-19 and had to be
unwound.

Stacking a branch on an unmerged branch is allowed when the work genuinely
depends on it — #136 → #139 → #141 were stacked deliberately — but the parent
is squash-merged, so rebase the child with `--onto origin/main <old-parent-sha>`
and expect to do it for each one.

`delete_branch_on_merge` is on, and a global post-merge hook prunes local
branches whose upstream is gone. Leave both alone: sixteen undeleted branches
were why the Bearpaw 1.1 cycle felt like work had been lost.

## 7. Keep it small and single-purpose

One concern per pull request. If a branch grows a second idea, say so and offer
to split rather than shipping both quietly.

Unrelated mess found while working gets **filed, not fixed**. Audits and reviews
report first and change nothing until approved.

## 8. Green before push

All three gates pass **locally**, from `sstv_core/`, before you push:

```bash
uv run pytest              # the whole suite, no exclusions (~10 min)
uv run ruff check src/
uv run mypy src/
```

CI takes about 10 minutes per run, so "push and see" costs half an hour a round
trip. Run the suite in the background and do other work while it runs — but do
not open the PR until it comes back green.

Run the **whole** suite, not the part you think you touched: on 2026-08-19 a
decode change passed every decode test while breaking the CLI and SDR
roundtrips. Run it from `sstv_core/` — from the repository root pytest collects
nothing and exits in a second, which looks like success if you only read the
exit code. That happened three times in one session on 2026-09-11.

API changes additionally regenerate `docs/core/openapi.json` and keep
`backend-spec.md` in step (`scripts/export_api_docs.py`).

Decode changes follow the `ssteve-decode-verification` skill: **pin the render,
never a statistic.** A gate that would have passed uniform random noise was
nearly shipped as decode-quality protection. Verify a new gate by injecting a
real regression and watching it fail.

## 8a. The shell is checked against the engine, not trusted to match

`sstv_desktop/src/core.ts` is hand-written, and so is its copy of the band
table. Both are checked from the Python suite rather than assumed:

| check | catches |
|---|---|
| `tests/test_shell_client_matches_the_contract.py` | a call to a route the engine does not serve, and a field the window reads that no schema sends |
| `tests/test_band_table_matches_the_shell.py` | the two band tables drifting apart |

Each has a companion test asserting the parser still finds something, because
a check that silently matches nothing passes forever.

If one of these fails, the engine and the window disagree. Decide which is
right before changing either.

## 9. Merge deliberately

Wait for both checks, then `gh pr merge <n> --squash --delete-branch`. Then
verify on merged main — for a decode change, that means decoding something and
looking at the picture.

## 10. Release

**Write the changelog entry in the PR that makes the change.** `CHANGELOG.md`
holds what an operator would notice; if nobody would, leave it out. The entry
is cheap now and expensive later: reconstructing one at release time is how
five user-visible fixes went missing from Bearpaw 1.1, because by then nobody
could tell which commits had a user on the other end.

Three things enforce this, and only one of them blocks:

| | When | Blocks? |
|---|---|---|
| `preflight` (`.github/workflows/pr-preflight.yml`) | every PR | **No — and it must never be made required.** A required check that does not run on every PR makes those PRs permanently unmergeable. |
| `release gate` (`.github/workflows/release-gate.yml`) | `v*` tags | **Yes.** No release is built until it passes. |
| `scripts/release_status.py` | whenever you ask | n/a — it is what the gate runs |

Before tagging, ask:

```bash
python3 scripts/release_status.py v0.1.0     # --offline skips the milestone check
```

It answers in one screen: do the four version strings agree
(`pyproject.toml`, `package.json`, `tauri.conf.json`, `Cargo.toml` — all four
ship), does `CHANGELOG.md` have a non-empty section for the version, does the
milestone exist and has it reached zero. Exit 0 means a tag would be safe.

The gate runs that same script rather than reimplementing it, so the answer
before you tag is the answer after.

## When a rule here disagrees with reality

Follow the code, and say so. Every rule was true when written; a stale
*procedure* is more dangerous than a stale fact, because a procedure gets
followed rather than read. Before acting on a step that depends on a repository,
service or tool setting, **check the setting** — docs are evidence, the API is
truth.
