"""Download third-party SSTV reference recordings into a local cache.

These files are NOT vendored into the repository. They are other people's
recordings under their own licences, and redistributing them inside SSTeVe
would mean taking on those obligations and asserting rights we have not
verified. Fetching on demand keeps the repo free of third-party media while
still letting the decode tests run against real off-air signals.

The cache lives in `tests/reference/audio/_cache/`, which is gitignored.
Tests that use it skip when it is absent, so a clean checkout, CI, and
offline work are all unaffected.

Usage:
    uv run python scripts/fetch_reference_audio.py           # fetch all
    uv run python scripts/fetch_reference_audio.py --list    # show sources
    uv run python scripts/fetch_reference_audio.py --clean   # remove cache

Every entry below records its licence and attribution. If you redistribute a
decoded image or use one in documentation, honour the terms recorded here.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent / "tests" / "reference" / "audio" / "_cache"

USER_AGENT = (
    "SSTeVe-test-fixture-fetcher/1.0 "
    "(https://github.com/jeremyfuksa/SSTeVe; amateur radio SSTV decoder tests)"
)


@dataclass(frozen=True)
class Source:
    """One downloadable reference recording."""

    name: str
    mode: str
    url: str
    licence: str
    attribution: str
    notes: str
    expected_image_url: str | None = None

    @property
    def filename(self) -> str:
        return self.name + Path(self.url).suffix

    @property
    def expected_filename(self) -> str | None:
        if self.expected_image_url is None:
            return None
        return self.name + "_expected" + Path(self.expected_image_url).suffix


SOURCES: tuple[Source, ...] = (
    Source(
        name="wikimedia_martin_m1_sunset",
        mode="MartinM1",
        url="https://upload.wikimedia.org/wikipedia/commons/c/ce/SSTV_sunset_audio.ogg",
        expected_image_url=(
            "https://upload.wikimedia.org/wikipedia/commons/c/cf/SSTV_Sunset.png"
        ),
        licence="GFDL 1.2+ / CC-BY-SA 3.0 / CC-BY 2.5 (multi-licensed)",
        attribution="Mysid (audio, via QSSTV); decoded PNG by en:User:Little Professor",
        notes=(
            "The only licence-clean Martin M1 file found with a paired ground-truth "
            "decode. The PNG is a genuine decode of this audio, not the source photo, "
            "and is 320x256 as Martin M1 requires. CAVEAT: lossy Ogg Vorbis at about "
            "23 kbps -- fine for a happy-path regression test, not for tuning sync "
            "thresholds or measuring noise tolerance."
        ),
    ),
    Source(
        name="wikimedia_robot36_fr_logo",
        mode="Robot36",
        url=(
            "https://upload.wikimedia.org/wikipedia/commons/2/29/"
            "French_Wikipedia_logo_in_SSTV.flac"
        ),
        licence="CC0 1.0 (public domain dedication)",
        attribution="Wikimedia Commons; no attribution required",
        notes=(
            "Lossless FLAC and the cleanest licence of anything found -- no "
            "attribution obligation, no restrictions. No published expected image, "
            "so this exercises decode geometry and sync rather than pixel accuracy."
        ),
    ),
    Source(
        name="wikimedia_robot36_wp_logo",
        mode="Robot36",
        url=(
            "https://upload.wikimedia.org/wikipedia/commons/c/cf/"
            "SSTV_Logo_Wikipedia_Robot36.ogg"
        ),
        licence="CC-BY-SA 3.0 Unported",
        attribution="Synthesized Studios (Wikimedia user Santos687), 2013",
        notes="Lossy Ogg Vorbis at about 63 kbps. No published expected image.",
    ),
)


def fetch(url: str, destination: Path, attempts: int = 3) -> bool:
    """Download `url` to `destination`. Returns False on failure.

    Retries with a pause between attempts: Wikimedia rate-limits rapid
    sequential requests and returns a 404 rather than a 429, so a transient
    refusal is indistinguishable from a dead link on the first try.
    """
    # Only https: urlopen would otherwise happily accept file:// or custom
    # schemes from a mistyped SOURCES entry.
    if not url.startswith("https://"):
        raise ValueError(f"refusing non-https URL: {url}")

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
                data = response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == attempts:
                print(f"    FAILED after {attempts} attempts: {exc}", file=sys.stderr)
                return False
            print(f"    attempt {attempt} failed ({exc}); retrying")
            time.sleep(2 * attempt)
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()[:16]
        print(f"    {len(data) / 1024:.0f} KB  sha256:{digest}")
        # Be a good citizen: these are donated servers.
        time.sleep(0.5)
        return True

    return False


def write_manifest() -> None:
    """Record what is in the cache and under what terms.

    The cache is gitignored, so this is the only place the licence of a
    downloaded file is written down where someone can find it later.
    """
    lines = [
        "# Reference audio cache",
        "",
        "Downloaded by `scripts/fetch_reference_audio.py`. NOT part of the",
        "repository -- this directory is gitignored. Each file below belongs to",
        "its author under the licence shown. Honour these terms if you",
        "redistribute a decode or use one in documentation.",
        "",
    ]
    for source in SOURCES:
        lines += [
            f"## {source.name}",
            "",
            f"- Mode: {source.mode}",
            f"- Audio: {source.url}",
            f"- Licence: {source.licence}",
            f"- Attribution: {source.attribution}",
        ]
        if source.expected_image_url:
            lines.append(f"- Expected image: {source.expected_image_url}")
        lines += ["", source.notes, ""]

    (CACHE_DIR / "MANIFEST.md").write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="show sources and exit")
    parser.add_argument("--clean", action="store_true", help="delete the cache and exit")
    parser.add_argument("--force", action="store_true", help="re-download existing files")
    args = parser.parse_args()

    if args.clean:
        if CACHE_DIR.exists():
            shutil.rmtree(CACHE_DIR)
            print(f"removed {CACHE_DIR}")
        else:
            print("cache is already empty")
        return 0

    if args.list:
        for source in SOURCES:
            print(f"{source.name}  [{source.mode}]")
            print(f"  {source.url}")
            print(f"  licence: {source.licence}")
            print(f"  paired image: {'yes' if source.expected_image_url else 'no'}")
            print()
        return 0

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"cache: {CACHE_DIR}")
    print()

    failures = 0
    for source in SOURCES:
        print(f"{source.name}  [{source.mode}]  {source.licence}")

        audio_path = CACHE_DIR / source.filename
        if audio_path.exists() and not args.force:
            print(f"    already present ({audio_path.stat().st_size / 1024:.0f} KB)")
        elif not fetch(source.url, audio_path):
            failures += 1

        expected_name = source.expected_filename
        if expected_name:
            image_path = CACHE_DIR / expected_name
            if image_path.exists() and not args.force:
                print("    expected image already present")
            elif source.expected_image_url and not fetch(
                source.expected_image_url, image_path
            ):
                failures += 1
        print()

    write_manifest()

    if failures:
        print(f"{failures} download(s) failed.", file=sys.stderr)
        return 1

    print("Cache ready. Decode tests that use it will now run instead of skipping.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
