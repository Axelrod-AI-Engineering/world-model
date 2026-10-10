# Demo video scripts

These record the videos in `docs/media/` from the small demo with Playwright, then cut them with ffmpeg. The numbered files are successive versions, kept for reference; only the latest of each is current.

## The two-minute devlog (current)

| Step | File | What it does |
|---|---|---|
| 1. Overlay | `annotate2.js` → `build_ann3.py` (with `engine.js`, `bubble.js`) → `build_ann4.py` → `build_ann5.py` | Builds `annotate5.js`, the injected overlay: callouts, arrows, rings, highlighters, the five-stage diagram, and a check that every arrow lands on its target |
| 2. Footage | `record7.py <slow> qc\|final <tag>` | Drives the demo on port 8766 in four takes timed to the voiceover's words, in slow motion (`4` for the real recording, `1` for a fast check). `qc` also saves snapshots and arrow measurements, which leak into the footage, so record the final cut with `final`. |
| 3. Edit | `edit4.py <tag> <out.mp4>` | Syncs and trims the takes, restores real speed, fades to black, and mixes the voice over a ducked music bed |
| Check | `vet.py <video> <name> <seconds…>` | Tiles frames at the given times into one image, to look over |
| Music | `music.py <out.wav> <seconds>` | Synthesizes the original ambient bed |

`final7.sh` runs steps 2 and 3 against a fresh demo server.

**Not yet portable.** `build_ann3.py` and `final7.sh` hard-code the scratch directory they were written in. `edit4.py` expects the cleaned voiceover (`vo2_clean.wav`, made from `docs/media/AxelrodDemo.m4a`) and the music (`music120.wav`) next to it, and `record7.py`'s cue times come from a word-level transcript of the voiceover. None of these three inputs is committed.

## The one-minute learning video

`record.py`, `edit.py`, and `annotate.js` made `docs/media/axelrod-learning-60s.mp4`, wordless with music. `record3.py`–`record6.py` and `edit3.py` are intermediate versions of the devlog.
