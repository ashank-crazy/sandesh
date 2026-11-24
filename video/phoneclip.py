"""Cut the real-phone screen recording into the 'realphone' scene's clip, timed to its narration.

    python3 phoneclip.py "<recording.mp4>"   # after tts.py realphone; needs ffmpeg and Pillow

The recording (Android, airplane mode, PocketPal, tiny-aya-fire-sandesh-v2.1-Q4_K_M.gguf, temperature 0, Pal system
prompt = our benchmark's) stays out of git: it is the user's own phone. Outputs, all under out/ (gitignored) except
phone/clip.js: out/phoneclip.mp4 (the cut), out/phone_first.png / out/phone_last.png (posters shown before and after
it), out/phone_mask.png (rounded screen corners), and phone/clip.js (where and when render.mjs overlays the clip).

Segments are source seconds. Each starts on a narration line; a segment either plays at its own speed and then
holds its last frame until the next one starts, or (speed None) is sped up to fill the gap exactly.
The notification shade (WhatsApp previews) is visible around 2.3 s and 4.3 s, so the first cut keeps 2.45-4.15 only.
"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

SRC = sys.argv[1]
FPS = 30
W, H, R = 432, 960, 40          # screen size on the 1920x1080 frame (576x1280 source, same 0.45 aspect; even for x264)
X, Y = 166, 52                  # screen's top-left on the frame (matches .rphone in scenes.html)
LEAD = .5
T = json.load(open("audio/timing.json"))["realphone"]
at = lambda i: LEAD + T["lines"][i]["start"]  # noqa: E731
END = LEAD + T["duration"]

# (source start, source end, scene-local start, speed or None to fill until the next segment)
SEGS = [
    (2.45, 4.15, at(0) + 3.0, 1.0),    # quick settings: Wi-Fi off, airplane mode on
    (5.2, 6.4, at(0) + 5.6, 1.0),      # the chat: model tiny-aya-fire-sandesh-v2.1-Q4_K_M, Pal: Sandesh
    (129.3, 134.0, at(1), 1.0),        # paste the second inbox (with the real scam) and send
    (134.0, 201.0, None, None),        # 62 s to the first token (model reload + prompt), sped up to fill
    (201.0, 215.0, at(3), 2.0),        # turn 2 reply streams: the warning
    (216.5, 228.5, at(4), 3.0),        # typing "Ok, please take care of whatever is urgent"
    (228.5, 243.0, at(5), 2.0),        # turn 3 reply streams
]

starts, durs = [], []
for i, (a, b, s, sp) in enumerate(SEGS):
    s = s if s is not None else starts[-1] + durs[-1]
    starts.append(s)
    nxt = SEGS[i + 1][2] if i + 1 < len(SEGS) else None
    if sp is None:
        durs.append(nxt - s)
    else:
        natural = (b - a) / sp
        durs.append(natural if nxt is None else nxt - s)
    if i and abs(starts[i] - (starts[i - 1] + durs[i - 1])) > 1e-6:
        raise SystemExit(f"segment {i} overlaps or leaves a gap")

parts = []
for i, ((a, b, _, sp), d) in enumerate(zip(SEGS, durs)):
    speed = (b - a) / d if sp is None else max(sp, (b - a) / d) if i + 1 < len(SEGS) else sp
    play = (b - a) / speed
    parts.append(f"[0:v]trim=start={a}:end={b},setpts=(PTS-STARTPTS)/{speed:.5f},fps={FPS},scale={W}:{H}:flags=lanczos,"
                 f"tpad=stop_mode=clone:stop_duration={max(0, d - play) + .2:.3f},trim=duration={d:.4f},setpts=PTS-STARTPTS[s{i}]")
    print(f"seg {i}: src {a:7.2f}-{b:7.2f}  at {starts[i]:6.2f}  dur {d:5.2f}  x{speed:5.2f}  hold {max(0, d - play):4.2f}")
fc = ";".join(parts) + ";" + "".join(f"[s{i}]" for i in range(len(SEGS))) + f"concat=n={len(SEGS)}:v=1:a=0[v]"
Path("out").mkdir(exist_ok=True)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", SRC, "-filter_complex", fc, "-map", "[v]", "-r", str(FPS),
                "-c:v", "libx264", "-crf", "14", "-preset", "slow", "-pix_fmt", "yuv420p", "out/phoneclip.mp4"], check=True)
total = sum(durs)
# first: frame 0; last: the final frame (-update keeps overwriting; a plain -ss near the end writes nothing)
for name, pre, post in (("first", [], ["-frames:v", "1"]), ("last", ["-sseof", "-0.2"], ["-update", "1"])):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *pre, "-i", "out/phoneclip.mp4", *post, f"out/phone_{name}.png"], check=True)
    if not Path(f"out/phone_{name}.png").exists():
        raise SystemExit(f"poster {name} missing")
mask = Image.new("L", (W, H), 0)
ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, H - 1), radius=R, fill=255)
mask.save("out/phone_mask.png")
meta = {"scene": "realphone", "at": round(starts[0], 4), "dur": round(total, 4), "x": X, "y": Y, "w": W, "h": H,
        "clip": "out/phoneclip.mp4", "mask": "out/phone_mask.png", "first": "out/phone_first.png", "last": "out/phone_last.png",
        "wait": {"from": round(starts[3], 3), "to": round(starts[4], 3), "src_s": SEGS[3][1] - SEGS[3][0]}}
Path("phone").mkdir(exist_ok=True)
Path("phone/clip.js").write_text("window.PHONECLIP = " + json.dumps(meta, indent=1) + "\n")
print(f"clip {total:.2f} s at scene-local {starts[0]:.2f}-{starts[0] + total:.2f} (scene ends {END + 3:.2f})")
