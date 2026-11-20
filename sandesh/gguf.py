"""Final round, P2: the same models as 4-bit GGUF files run by llama.cpp, the engine a phone app would ship.

``convert``  Hugging Face checkpoint -> GGUF bf16 (llama.cpp's own ``convert_hf_to_gguf.py``) -> Q4_K_M
             (``llama-quantize``). Writes ``ckpt/gguf/<name>/<name>-Q4_K_M.gguf`` plus a sidecar ``<file>.json`` that
             names the Hugging Face tokenizer, so prompts are tokenized exactly as in the bf16 runs and reach llama.cpp
             as token ids (no second chat template in the loop).
``fetch``    Cohere's own Q4_K_M of the base model (``CohereLabs/tiny-aya-fire-GGUF``): a check on our conversion.
``bench``    ``llama-bench`` on the GPU and on the CPU alone (all cores; a stand-in for a laptop): prompt and generation
             tokens per second.

Every sandesh script takes a ``.gguf`` path as ``--model``: ``gen.load_model`` starts ``llama-server`` on it and
``gen.generate`` sends greedy requests (temperature 0) to its parallel slots.

    bash scripts/setup_llama.sh                       # llama.cpp into tools/ (once)
    python -m sandesh.gguf convert --model ckpt/sft_v2 --name sft_v2
    python -m sandesh.evaluate --model ckpt/gguf/sft_v2/sft_v2-Q4_K_M.gguf --name sft_v2_q4
    python -m sandesh.gguf bench --gguf ckpt/gguf/sft_v2/sft_v2-Q4_K_M.gguf --name sft_v2_q4
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
TOOLS = Path(os.environ.get("SANDESH_LLAMA_TOOLS", ROOT / "tools"))
QUANT = "Q4_K_M"
COHERE_GGUF = "CohereLabs/tiny-aya-fire-GGUF"


def _bin(name: str) -> str:
    p = TOOLS / "bin" / name
    if not p.exists():
        raise SystemExit(f"{p} is missing: run  bash scripts/setup_llama.sh")
    return str(p)


def _env() -> dict:
    """Environment for the llama.cpp binaries: the release's CUDA runtime libraries sit next to them in tools/bin."""
    lib = str(TOOLS / "bin")
    return dict(os.environ, LD_LIBRARY_PATH=lib + (":" + os.environ["LD_LIBRARY_PATH"]
                                                   if os.environ.get("LD_LIBRARY_PATH") else ""))


def _tool_info() -> dict:
    out = {}
    for key in ("llama_cpp_tag", "backend"):
        f = TOOLS / f"{key}.txt"
        out[key] = f.read_text().strip() if f.exists() else None
    return out


def gguf_path(name: str, root: Path = Path("ckpt/gguf")) -> Path:
    return root / name / f"{name}-{QUANT}.gguf"


def _sidecar(path: Path) -> Path:
    return path.with_name(path.name + ".json")


# --------------------------------------------------------------------------- convert / fetch
def _hf_dir(model: str) -> Path:
    p = Path(model)
    if p.is_dir():
        return p
    from huggingface_hub import snapshot_download

    return Path(snapshot_download(model, allow_patterns=["*.json", "*.safetensors", "*.model", "*.txt", "*.jinja"]))


# Settings worth comparing across files: if our conversion differed from Cohere's own file in any of these, the
# 4-bit results would not be about quantization.
META_KEYS = ("general.architecture", "general.file_type", "cohere2.context_length", "cohere2.embedding_length",
             "cohere2.block_count", "cohere2.feed_forward_length", "cohere2.attention.head_count",
             "cohere2.attention.head_count_kv", "cohere2.attention.sliding_window", "cohere2.rope.freq_base",
             "cohere2.rope.dimension_count", "cohere2.logit_scale", "cohere2.attention.layer_norm_epsilon",
             "tokenizer.ggml.model", "tokenizer.ggml.pre", "tokenizer.ggml.tokens", "tokenizer.ggml.bos_token_id",
             "tokenizer.ggml.eos_token_id", "tokenizer.ggml.eot_token_id", "tokenizer.ggml.padding_token_id",
             "n_tensors")
_META_SCRIPT = r"""
import json, sys
from gguf import GGUFReader
r = GGUFReader(sys.argv[1])
out = {"n_tensors": len(r.tensors)}
for k, f in r.fields.items():
    if k.startswith("tokenizer.ggml.") and k.rsplit(".", 1)[-1] in ("tokens", "scores", "token_type", "merges"):
        out[k] = len(f.data)
        continue
    try:
        v = f.contents()
    except Exception:
        continue
    if isinstance(v, (str, int, float, bool)):
        out[k] = v
print(json.dumps(out))
"""


def gguf_meta(path: Path) -> dict:
    """Header fields of a GGUF file (read with llama.cpp's own gguf-py, in the converter's venv)."""
    env = dict(os.environ, PYTHONPATH=str(TOOLS / "llama.cpp" / "gguf-py"))
    r = subprocess.run([str(TOOLS / "venv-gguf" / "bin" / "python"), "-c", _META_SCRIPT, str(path)],
                       capture_output=True, text=True, env=env)
    if r.returncode:
        return {"error": r.stderr[-500:]}
    allm = json.loads(r.stdout)
    return {k: allm.get(k) for k in META_KEYS}


def _stage(model: str, base: str, dst: Path) -> Path:
    """Folder the converter reads. For a fine-tuned checkpoint: its weights (and their index), with every other
    file (config, tokenizer, chat template) from the base model. The converter pins transformers 4.57, which may not
    read files saved by transformers 5; LoRA fine-tuning (merged) changes neither the architecture nor the tokenizer."""
    if model == base:
        return _hf_dir(base)
    src, ref = _hf_dir(model), _hf_dir(base)
    dst.mkdir(parents=True, exist_ok=True)
    for f in dst.iterdir():
        f.unlink()
    weights = lambda f: f.suffix == ".safetensors" or f.name == "model.safetensors.index.json"
    for f in src.iterdir():
        if weights(f):
            (dst / f.name).symlink_to(f.resolve())
    for f in ref.iterdir():
        if not weights(f) and f.is_file() and not f.name.startswith("."):
            (dst / f.name).symlink_to(f.resolve())
    return dst


def convert(model: str, name: str, root: Path, base: str) -> Path:
    q = gguf_path(name, root)
    if q.exists() and _sidecar(q).exists():
        print(f"skip {q} (exists)")
        return q
    q.parent.mkdir(parents=True, exist_ok=True)
    src = _stage(model, base, q.parent / "hf")
    bf16 = q.with_name(f"{name}-bf16.gguf")
    if not bf16.exists():
        py = TOOLS / "venv-gguf" / "bin" / "python"
        tmp = bf16.with_suffix(".part")
        subprocess.run([str(py), str(TOOLS / "llama.cpp" / "convert_hf_to_gguf.py"), str(src),
                        "--outfile", str(tmp), "--outtype", "bf16"], check=True)
        tmp.rename(bf16)
    tmp = q.with_suffix(".part")
    subprocess.run([_bin("llama-quantize"), str(bf16), str(tmp), QUANT, str(os.cpu_count() or 4)], check=True,
                   env=_env())
    tmp.rename(q)
    meta = {"tokenizer": model, "source": model, "quant": QUANT, "bytes": q.stat().st_size,
            "bf16_gguf_bytes": bf16.stat().st_size, "made_with": "convert_hf_to_gguf.py --outtype bf16, llama-quantize",
            "non_weight_files_from": base, **_tool_info(), "gguf_meta": gguf_meta(q)}
    _sidecar(q).write_text(json.dumps(meta, indent=2))
    print(f"{q}: {meta['bytes'] / 2**30:.2f} GiB (bf16 GGUF {meta['bf16_gguf_bytes'] / 2**30:.2f} GiB)")
    return q


def fetch(name: str, root: Path, base: str) -> Path:
    """Cohere's own Q4_K_M file, linked from the Hugging Face cache (no second copy)."""
    from huggingface_hub import hf_hub_download, list_repo_files

    q = gguf_path(name, root)
    if q.exists() and _sidecar(q).exists():
        print(f"skip {q} (exists)")
        return q
    files = [f for f in list_repo_files(COHERE_GGUF) if f.lower().endswith(".gguf") and "q4_k_m" in f.lower()]
    if not files:
        raise SystemExit(f"no Q4_K_M file in {COHERE_GGUF}")
    src = Path(hf_hub_download(COHERE_GGUF, files[0]))
    q.parent.mkdir(parents=True, exist_ok=True)
    if q.exists() or q.is_symlink():
        q.unlink()
    q.symlink_to(src.resolve())
    meta = {"tokenizer": base, "source": f"{COHERE_GGUF}/{files[0]}", "quant": QUANT, "bytes": src.stat().st_size,
            "made_with": "Cohere (published file)", **_tool_info(), "gguf_meta": gguf_meta(q)}
    _sidecar(q).write_text(json.dumps(meta, indent=2))
    print(f"{q} -> {src} ({meta['bytes'] / 2**30:.2f} GiB)")
    return q


# --------------------------------------------------------------------------- bench
def bench(gguf: Path, name: str, runs: Path) -> dict:
    """Prompt (512 tokens) and generation (64 tokens) speed, GPU and CPU alone. ``-dev none`` keeps llama.cpp from
    handing big CPU matrix multiplies to the GPU; older builds without it fall back to ``-ngl 0``."""
    keep = ("n_prompt", "n_gen", "avg_ts", "stddev_ts", "backends", "gpu_info", "cpu_info", "n_threads",
            "n_gpu_layers", "model_size", "model_type", "build_commit")
    base = [_bin("llama-bench"), "-m", str(gguf), "-p", "512", "-n", "64", "-r", "3", "-o", "json"]
    threads = ["-t", str(os.cpu_count() or 4)]
    res = {"gguf": str(gguf), **_tool_info()}
    for dev, variants in (("gpu", [["-ngl", "99"]]), ("cpu", [["-ngl", "0", "-dev", "none"] + threads,
                                                             ["-ngl", "0"] + threads])):
        for extra in variants:
            r = subprocess.run(base + extra, capture_output=True, text=True, env=_env())
            if r.returncode == 0:
                rows = json.loads(r.stdout)
                res[dev] = {"args": extra, "rows": [{k: row.get(k) for k in keep} for row in rows]}
                break
            res[f"{dev}_error"] = r.stderr[-2000:]
    out = runs / name / "gguf_bench.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2))
    for dev in ("gpu", "cpu"):
        for row in (res.get(dev) or {}).get("rows", []):
            what = f"prompt {row['n_prompt']}" if row.get("n_prompt") else f"generate {row['n_gen']}"
            print(f"{name} {dev}: {what}: {row['avg_ts']:.1f} tokens/s")
    return res


# --------------------------------------------------------------------------- llama-server backend for gen.py
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LlamaServer:
    """A llama-server process on one GGUF file, used by ``gen.generate`` in place of a transformers model.

    Requests carry token ids from the Hugging Face tokenizer, ask for greedy decoding (temperature 0) and stop at the
    model's end-of-turn token, as the bf16 runs do. Slots run in parallel, so outputs can differ from a one-at-a-time
    run in rare near-ties (llama.cpp's batched kernels are not batch-invariant)."""

    is_llama_server = True

    def __init__(self, gguf: str, parallel: int = 16, ctx_per_slot: int = 4096, url: Optional[str] = None,
                 log: Optional[Path] = None, timeout: float = 900):
        self.gguf, self.parallel, self.proc = gguf, parallel, None
        if url:
            self.url = url.rstrip("/")
            return
        port = _free_port()
        self.url = f"http://127.0.0.1:{port}"
        cmd = [_bin("llama-server"), "-m", gguf, "--host", "127.0.0.1", "--port", str(port),
               "-ngl", os.environ.get("SANDESH_LLAMA_NGL", "99"), "-np", str(parallel),
               "-c", str(parallel * ctx_per_slot)]
        self.log_path = log or Path(gguf).with_suffix(".server.log")
        self._log = open(self.log_path, "a")
        self._log.write(f"\n# {time.strftime('%F %T')} {' '.join(cmd)}\n")
        self._log.flush()
        self.proc = subprocess.Popen(cmd, stdout=self._log, stderr=subprocess.STDOUT, env=_env())
        atexit.register(self.close)
        t0 = time.time()
        while True:
            if self.proc.poll() is not None:
                tail = Path(self.log_path).read_text(errors="replace")[-3000:]
                raise RuntimeError(f"llama-server exited ({self.proc.returncode}):\n{tail}")
            try:
                with urllib.request.urlopen(self.url + "/health", timeout=5) as r:
                    if r.status == 200:
                        break
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                pass
            if time.time() - t0 > timeout:
                self.close()
                raise RuntimeError(f"llama-server not ready after {timeout:.0f} s; see {self.log_path}")
            time.sleep(2)

    def close(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def _post(self, path: str, body: dict, timeout: float = 900) -> dict:
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())

    def generate(self, tok, prompts: list[str], max_new_tokens: int = 256, batch_size: int = 16,
                 desc: str = "gen") -> tuple[list[str], dict]:
        from tqdm.auto import tqdm

        if not prompts:
            return [], {"n": 0}
        add_special = not (tok.bos_token and prompts[0].startswith(tok.bos_token))
        ids = [tok(p, add_special_tokens=add_special)["input_ids"] for p in prompts]
        outs: list[Optional[str]] = [None] * len(prompts)
        new_tokens = prompt_tokens = errors = 0
        t0 = time.time()

        def one(i):
            body = {"prompt": ids[i], "n_predict": max_new_tokens, "temperature": 0.0, "top_k": 1, "seed": 0,
                    "cache_prompt": False}
            try:
                return i, self._post("/completion", body), None
            except (urllib.error.URLError, OSError, ValueError) as e:
                return i, None, e

        with ThreadPoolExecutor(max_workers=self.parallel) as ex, \
                tqdm(total=len(prompts), desc=desc, unit="prompt") as bar:
            for fut in as_completed([ex.submit(one, i) for i in range(len(prompts))]):
                i, r, err = fut.result()
                if r is None:
                    errors += 1
                    outs[i] = ""
                    tqdm.write(f"[{desc}] request {i} failed: {err}")
                else:
                    outs[i] = (r.get("content") or "").strip()
                    new_tokens += int(r.get("tokens_predicted") or 0)
                    prompt_tokens += int(r.get("tokens_evaluated") or len(ids[i]))
                bar.update(1)
        if errors > max(3, len(prompts) // 50):
            raise RuntimeError(f"[{desc}] {errors} of {len(prompts)} llama-server requests failed")
        secs = time.time() - t0
        info = _tool_info()
        stats = {"n": len(prompts), "seconds": round(secs, 2), "new_tokens": new_tokens, "prompt_tokens": prompt_tokens,
                 "tok_per_s": round(new_tokens / max(secs, 1e-9), 1),
                 "prompts_per_s": round(len(prompts) / max(secs, 1e-9), 3), "batch_size": self.parallel,
                 "device": f"llama.cpp {info.get('llama_cpp_tag') or '?'} ({info.get('backend') or '?'})",
                 "gguf": self.gguf, "failed_requests": errors}
        return outs, stats


def load_gguf(path: str):
    """(server, Hugging Face tokenizer) for a .gguf file; the tokenizer comes from the sidecar written by convert."""
    from transformers import AutoTokenizer

    side = _sidecar(Path(path))
    meta = json.loads(side.read_text()) if side.exists() else {}
    tok = AutoTokenizer.from_pretrained(meta.get("tokenizer") or os.environ.get("SANDESH_BASE",
                                                                                "CohereLabs/tiny-aya-fire"))
    tok.padding_side = "left"
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    server = LlamaServer(path, parallel=int(os.environ.get("SANDESH_LLAMA_PARALLEL", "16")))
    return server, tok


def compare(names: list[str], ref: str, root: Path) -> int:
    """Header fields of our files against Cohere's (file type aside). Returns the number of differences."""
    meta = {}
    for n in [ref] + names:
        side = _sidecar(gguf_path(n, root))
        if side.exists():
            meta[n] = json.loads(side.read_text()).get("gguf_meta") or {}
    if ref not in meta:
        print(f"no {ref} file to compare against")
        return 0
    diffs = 0
    for n in names:
        if n not in meta:
            continue
        d = {k: (meta[ref].get(k), meta[n].get(k)) for k in META_KEYS
             if k != "general.file_type" and meta[ref].get(k) != meta[n].get(k)}
        diffs += len(d)
        print(f"{n} vs {ref}: " + ("same settings" if not d else
                                   "; ".join(f"{k}: {a} vs {b}" for k, (a, b) in d.items())))
    return diffs


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["convert", "fetch", "bench", "compare"])
    ap.add_argument("--model", help="convert: Hugging Face checkpoint dir or repo id")
    ap.add_argument("--name", help="convert/fetch/bench: output name; compare: the reference (default base_cohere)")
    ap.add_argument("--names", nargs="*", default=["base", "sft_sandesh", "sft_v2"], help="compare: files to check")
    ap.add_argument("--gguf", help="bench: the .gguf file")
    ap.add_argument("--root", default="ckpt/gguf")
    ap.add_argument("--runs", default="runs")
    a = ap.parse_args(argv)
    base = os.environ.get("SANDESH_BASE", "CohereLabs/tiny-aya-fire")
    if a.cmd == "compare":
        compare(a.names, a.name or "base_cohere", Path(a.root))
        return
    if not a.name:
        ap.error(f"{a.cmd} needs --name")
    if a.cmd == "convert":
        convert(a.model or base, a.name, Path(a.root), base)
    elif a.cmd == "fetch":
        fetch(a.name, Path(a.root), base)
    else:
        bench(Path(a.gguf or gguf_path(a.name.removesuffix("_q4"), Path(a.root))), a.name, Path(a.runs))


if __name__ == "__main__":
    main()
