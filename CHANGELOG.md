# Changelog

What changed, for someone using SSTeVe. Internal refactors, test scaffolding
and CI plumbing do not appear here — if no operator would notice it, it
belongs in the git log instead.

**Write the entry in the pull request that makes the change.** Reconstructing
a changelog at release time is how five user-visible fixes went missing from
Bearpaw 1.1: by then nobody could tell which commits had a user on the other
end of them. The tag gate (`.github/workflows/release-gate.yml`) refuses to
build a tag whose version has no section here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Sections are Added / Changed / Fixed / Removed, in that order, and only the
ones with entries.

## [Unreleased]

## [0.1.0] — unreleased

The first release: a desktop window that listens to a SpyServer and paints
the picture as it arrives. Receive only — transmit is v0.2.

### Added

- **A desktop window.** One window: the canvas, a waterfall presence strip,
  always-visible gain and squelch, and a log of what arrived. It starts the
  engine itself, so there is no server to run first.
- **Receive from a SpyServer.** Point SSTeVe at a network SDR and decode from
  it; the engine tunes, demodulates and decodes without a sound card in the
  path. Auto squelch stays off for SpyServer and file sources, where it has
  nothing useful to measure.
- **Receive from an Airspy HF+ over USB**, not only over the network.
- **A propagation verdict.** Whether the band should be carrying anything at
  all, so a quiet afternoon is not mistaken for a broken receiver. A failure
  to reach the propagation source reads louder than good news, never as a
  blank panel.
- **Every record says where it was heard** — the receiver, the frequency and
  the mode are kept with the picture, so a decode from six months ago can
  still be placed.
- **Decode a recording through the live pipeline**, the same path a live
  signal takes, so replaying a capture proves something about live decoding.
- **The FSKID callsign in a scanned file's name**, when the transmission
  carried one.

### Changed

- **A listen that hears nothing says which kind of nothing.** A quiet band
  and a deaf receiver produce the same empty screen and call for opposite
  responses; the measured input level is what separates them, and it is now
  quoted rather than summarised.
- **A half-duplex conflict reads plainly** and no longer leads with a session
  UUID the operator sees nowhere else. The id is still in the response for a
  client that wants to offer "stop that one and retry".
- **A session ends when its stream dies**, rather than listening to a frozen
  buffer until the timeout. A dead network link no longer reads as a weak
  signal.

### Fixed

- **Martin M2 decodes live.** The mode was in the regression corpus but the
  live receive path had no decoder for it, so a real M2 transmission was
  heard and dropped.
- **VIS detection no longer depends on the caller's block size.** At 48 kHz
  the header was found or missed according to how the audio happened to be
  chunked.
- **FSKID is found on real air**, not only in a clip trimmed to the burst.
- **Forcing a mode over the API works.** Asking for Scottie S2 explicitly was
  refused.
- **The file watcher fills gaps rather than erasing them.** Importing no
  longer overwrites what a decode recorded, and a picture's timestamp no
  longer shifts by the UTC offset the first time the watcher sees it.
- **A decode with no scanlines is reported as a failure**, not saved as a
  black picture.
- **The waterfall keeps running while a picture decodes.**
- **Saved squelch and AFC settings reach the decode** instead of being
  read and discarded.
- **Every decode logs one picture**, not a second empty one for its thumbnail.
- **Input gain reaches the samples**, not only the SDR's analog stage.

[Unreleased]: https://github.com/jeremyfuksa/ssteve/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/jeremyfuksa/ssteve/releases/tag/v0.1.0
