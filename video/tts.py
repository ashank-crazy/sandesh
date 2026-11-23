"""Narration: one wav per scene with Kokoro (voice af_heart, speed 1.0, 0.28 s between lines) + audio/timing.json.

    ../.venv-tts/bin/python tts.py            # all scenes
    ../.venv-tts/bin/python tts.py hook outro # only these (keeps the other scenes' timing)
"""
import json
import os
import sys

import espeakng_loader

os.environ.setdefault("ESPEAK_DATA_PATH", espeakng_loader.get_data_path())
import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from kokoro import KPipeline  # noqa: E402

pipe = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
SR = 24000
gap = np.zeros(int(SR * 0.28), dtype=np.float32)
scenes = json.load(open("script.json"))
only = sys.argv[1:]
timing = json.load(open("audio/timing.json")) if only and os.path.exists("audio/timing.json") else {}
for s in scenes:
    if only and s["id"] not in only:
        continue
    parts, marks, t = [], [], 0.0
    for i, line in enumerate(s["lines"]):
        audio = np.concatenate([np.asarray(r.audio, dtype=np.float32) for r in pipe(line, voice="af_heart", speed=1.0)])
        marks.append({"line": line, "start": round(t, 3), "end": round(t + len(audio) / SR, 3)})
        parts.append(audio)
        t += len(audio) / SR
        if i < len(s["lines"]) - 1:
            parts.append(gap)
            t += len(gap) / SR
    wav = np.concatenate(parts)
    sf.write(f"audio/{s['id']}.wav", wav, SR)
    timing[s["id"]] = {"duration": round(len(wav) / SR, 3), "lines": marks}
    print(s["id"], round(len(wav) / SR, 2), flush=True)
json.dump(timing, open("audio/timing.json", "w"), indent=1, ensure_ascii=False)
print("total", round(sum(v["duration"] for v in timing.values()), 2))
