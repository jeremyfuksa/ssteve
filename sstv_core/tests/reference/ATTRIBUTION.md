# Reference audio and images — sources and terms

Third-party material vendored into this repository for decoder testing. Each
entry records where it came from and under what terms, so anyone
redistributing SSTeVe knows what they are carrying.

Some material is deliberately **not** vendored and is fetched on demand
instead — see `scripts/fetch_reference_audio.py` and the bottom of this file.

---

## `audio/robot36/` and `images/robot36/` — Robot 36 (10 files)

**Source:** [kevinnz/SSTV-MEL](https://github.com/kevinnz/SSTV-MEL),
`samples/Robot36/` with paired expected decodes from `expected/Robot36/`.
Retrieved 2026-08-07. Filenames normalised to lowercase underscores; content
unmodified.

**Repository licence:** MIT, © 2025 Kevin Alcock (ZL3XA).

**Terms of the recordings — read this before redistributing:**

The MIT licence covers SSTV-MEL's *software*. The recordings are third-party
material within that repository and carry no separate grant. `samples/README.md`
states only:

> Amateur radio SSTV transmissions are public broadcasts on allocated
> frequencies. Recordings are routinely shared within the amateur radio
> community for educational and technical use.

That describes a community norm, not a licence. Specifically:

- **No recordist is named** for the Robot 36 files, and no dates or events are
  given. (The PD120/PD180 files in the same repository *do* carry event names
  and dates; the Robot 36 section does not.) The upstream project does not
  document where these ten recordings came from.
- Copyright in a recording of a transmission can rest with the transmitting
  operator, the recordist, or both. "Publicly broadcast" does not place a
  work in the public domain in most jurisdictions.
- Callsigns appearing in the images (PT7APM, HB100JAM, LX95) identify real
  operators who have not been asked.

**Decision:** vendored deliberately on 2026-08-07, with the above understood
and accepted. If a rights holder objects, remove the files and switch these
tests to the fetch-on-demand mechanism already used for the Wikimedia
material — `tests/decode/test_reference_audio.py` shows the pattern, and the
tests skip cleanly when their fixtures are absent.

**If you are packaging or relicensing SSTeVe**, treat this directory as
material whose provenance is undocumented upstream, and consider removing it.

---

## `audio/ariss/`, `audio/essexham/`, `audio/mmsstv/`

Pre-existing in the repository before 2026-08-07 with no recorded provenance.
Origins not established. The MMSSTV set carries `*_expected.jpg` images that
appear to be MMSSTV's own decoder output, used here as ground truth.

The same caution applies: these were not sourced by this project and their
terms are unknown.

---

## Fetched on demand, not vendored

`scripts/fetch_reference_audio.py` downloads the following into
`audio/_cache/` (gitignored). They are not redistributed by this repository.

| File | Mode | Licence |
|---|---|---|
| Wikimedia "SSTV sunset" + decode | Martin M1 | GFDL 1.2+ / CC-BY-SA 3.0 / CC-BY 2.5 — Mysid |
| Wikimedia French Wikipedia logo | Robot 36 | CC0 1.0 |
| Wikimedia Wikipedia logo | Robot 36 | CC-BY-SA 3.0 — Synthesized Studios |

Those three have explicit, verifiable licences. That is why they are handled
differently from the material above.
