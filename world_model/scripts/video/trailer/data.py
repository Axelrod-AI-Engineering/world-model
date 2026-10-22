"""The trailer's scene data, built at record time from Emily's bundle (data/work/emily, never committed) and the
voiceover's word timings. Cue times are seconds from each scene's start."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / "data/work/emily/emily_import.json"
SCENES = ROOT / "data/work/emily/trailer_scenes.json"      # the meta and stack scenes' content (client figures)

# where each scene starts in the voiceover (seconds), from the word timings of docs/media/EmilyVideo.m4a
VO = {"open": 0.0, "title": 12.75, "old": 18.65, "import": 32.6, "trans": 43.0, "ask": 83.7, "meta": 90.2,
      "stack": 111.85, "end": 119.75, "total": 124.0}


def headlines():
    items = json.loads(BUNDLE.read_text())["items"]
    items = sorted(items, key=lambda x: x["published_at"])
    return [{"source": x["source"], "date": x["published_at"][:10], "headline": x["headline"]} for x in items]


def scene_data(scene: str) -> dict:
    if scene == "open":
        return {"headlines": headlines(), "dimAt": 8.8, "nextAt": 10.9}
    if scene in ("meta", "stack"):
        # the meta agent's and the stack's content quote Emily's client model and canvas, so it lives with her data
        return {scene: json.loads(SCENES.read_text())[scene]}
    return {}
