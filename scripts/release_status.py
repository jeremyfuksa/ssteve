"""Answer "are we ready to tag?" without archaeology.

Four things have to agree before a tag means anything, and each of them
lives somewhere different: the milestone on GitHub, the section in
CHANGELOG.md, the four version strings across two languages, and the
working tree. Checking them by hand is how a release goes out half
finished -- not because anyone was careless, but because the fourth check
is the one nobody remembers.

    python3 scripts/release_status.py            # the next open milestone
    python3 scripts/release_status.py v0.1.0
    python3 scripts/release_status.py --json     # for the tag gate

Exit status is 0 when a tag would be safe and 1 when it would not, so
.github/workflows/release-gate.yml runs this rather than reimplementing
it. Needs `gh` on PATH and authenticated for the milestone check; pass
--offline to run only the local ones -- that can never report ready, because
a skipped check must not read as a passed one.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import tomllib

REPO = Path(__file__).resolve().parents[1]

#: Every file that states the product's version. Tauri bundles the desktop
#: app using tauri.conf.json, npm reads package.json, cargo reads
#: Cargo.toml, and the engine reports pyproject's -- so all four ship, and
#: any two of them disagreeing is a release that lies about itself.
VERSION_SOURCES: list[tuple[str, str]] = [
    ("sstv_core/pyproject.toml", "toml:project.version"),
    ("sstv_desktop/package.json", "json:version"),
    ("sstv_desktop/src-tauri/tauri.conf.json", "json:version"),
    ("sstv_desktop/src-tauri/Cargo.toml", "toml:package.version"),
]


@dataclass
class Report:
    """What a tag would run into, and whether it should be allowed."""

    tag: str | None = None
    version: str | None = None
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    versions: dict[str, str] = field(default_factory=dict)
    open_items: list[str] = field(default_factory=list)
    milestone_checked: bool = True

    @property
    def ready(self) -> bool:
        return not self.problems and self.milestone_checked


def read_version(relative: str, how: str) -> str:
    path = REPO / relative
    kind, dotted = how.split(":", 1)
    if kind == "toml":
        data: object = tomllib.loads(path.read_text())
    else:
        data = json.loads(path.read_text())
    for key in dotted.split("."):
        if not isinstance(data, dict):
            raise ValueError(f"{relative}: {dotted} does not lead to a version")
        data = data[key]
    if not isinstance(data, str):
        raise ValueError(f"{relative}: {dotted} is not a string")
    return data


def check_versions(report: Report, expected: str) -> None:
    for relative, how in VERSION_SOURCES:
        try:
            report.versions[relative] = read_version(relative, how)
        except (OSError, KeyError, ValueError) as e:
            report.problems.append(f"{relative}: cannot read a version ({e})")

    disagree = {v for v in report.versions.values() if v != expected}
    if disagree:
        wrong = ", ".join(
            f"{name} says {value}"
            for name, value in report.versions.items()
            if value != expected
        )
        report.problems.append(f"version sources disagree with {expected}: {wrong}")


def changelog_section(version: str) -> tuple[bool, str]:
    """Find the section for a version, and say whether it has content.

    A heading with nothing under it is the failure this is here to catch:
    it is what you get when someone adds the heading at release time and
    means to fill it in.
    """
    text = (REPO / "CHANGELOG.md").read_text()
    heading = re.compile(rf"^## \[{re.escape(version)}\][^\n]*$", re.M)
    match = heading.search(text)
    if not match:
        return False, ""
    rest = text[match.end() :]
    next_heading = re.search(r"^## ", rest, re.M)
    body = rest[: next_heading.start()] if next_heading else rest
    # Link definitions at the foot of the file are not release notes.
    body = re.sub(r"^\[[^\]]+\]:.*$", "", body, flags=re.M)
    return True, body.strip()


def check_changelog(report: Report, version: str) -> None:
    try:
        found, body = changelog_section(version)
    except OSError:
        report.problems.append("CHANGELOG.md is missing")
        return
    if not found:
        report.problems.append(f"CHANGELOG.md has no section for {version}")
        return
    if not body:
        report.problems.append(f"CHANGELOG.md's {version} section is empty")
        return
    if "unreleased" in body.lower().split("\n")[0]:
        report.notes.append(f"the {version} section still says unreleased")


def gh(*args: str) -> str:
    # Partial path on purpose: CI and a developer's machine put gh in
    # different places, and there is no untrusted input in args.
    return subprocess.run(  # noqa: S603
        ["gh", *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO,
    ).stdout


def check_milestone(report: Report, version: str) -> None:
    try:
        milestones = json.loads(gh("api", "repos/{owner}/{repo}/milestones?state=all"))
    except (OSError, subprocess.CalledProcessError) as e:
        report.problems.append(f"cannot reach GitHub to check the milestone ({e})")
        return

    match = next((m for m in milestones if m["title"] == version), None)
    if match is None:
        report.problems.append(f"no milestone called {version}")
        return

    try:
        open_items = json.loads(
            gh(
                "issue",
                "list",
                "--milestone",
                version,
                "--state",
                "open",
                "--limit",
                "100",
                "--json",
                "number,title",
            )
        )
    except (OSError, subprocess.CalledProcessError) as e:
        report.problems.append(f"cannot list the milestone's open items ({e})")
        return

    report.open_items = [f"#{i['number']} {i['title']}" for i in open_items]
    if report.open_items:
        report.problems.append(
            f"milestone {version} has {len(report.open_items)} open item(s)"
        )


def check_tree(report: Report) -> None:
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO,
    ).stdout.strip()
    if dirty:
        report.notes.append("the working tree has uncommitted changes")


def next_milestone() -> str | None:
    try:
        milestones = json.loads(gh("api", "repos/{owner}/{repo}/milestones?state=open"))
    except (OSError, subprocess.CalledProcessError):
        return None
    titles = sorted(m["title"] for m in milestones)
    return titles[0] if titles else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "tag", nargs="?", help="the tag to check, e.g. v0.1.0 (default: next milestone)"
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--offline", action="store_true", help="skip the GitHub milestone check"
    )
    arguments = parser.parse_args()

    tag = arguments.tag or next_milestone()
    if not tag:
        print("no tag given and no open milestone to guess from", file=sys.stderr)
        return 2

    version = tag.lstrip("v")
    report = Report(tag=tag, version=version)

    check_versions(report, version)
    check_changelog(report, version)
    check_tree(report)
    if arguments.offline:
        # Never let a skipped check read as a passed one. The milestone is
        # the check most likely to be the failing one, so "ready" without it
        # is confidence this run has not earned.
        report.milestone_checked = False
    else:
        check_milestone(report, tag)

    if arguments.json:
        print(
            json.dumps(
                {
                    "tag": report.tag,
                    "ready": report.ready,
                    "milestone_checked": report.milestone_checked,
                    "problems": report.problems,
                    "notes": report.notes,
                    "versions": report.versions,
                    "open_items": report.open_items,
                },
                indent=2,
            )
        )
        return 0 if report.ready else 1

    if report.ready:
        verdict = "ready to tag"
    elif not report.milestone_checked and not report.problems:
        verdict = "the local checks pass; the milestone was not checked"
    else:
        verdict = "not ready"
    print(f"{tag}: {verdict}\n")
    for name, value in report.versions.items():
        mark = " " if value == report.version else "!"
        print(f"  {mark} {value:<10} {name}")
    if report.open_items:
        print(f"\n  open on the milestone ({len(report.open_items)}):")
        for item in report.open_items:
            print(f"    - {item}")
    for problem in report.problems:
        print(f"\n  BLOCKS: {problem}")
    for note in report.notes:
        print(f"\n  note: {note}")
    return 0 if report.ready else 1


if __name__ == "__main__":
    sys.exit(main())
