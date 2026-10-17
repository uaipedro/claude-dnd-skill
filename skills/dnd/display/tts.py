"""Narrator TTS via Gemini Flash TTS (Google AI Studio API key).

Server-side wrapper called by /tts in dnd-display-app.py. Reads the API key
from DND_TTS_KEY env var → GEMINI_API_KEY env var → ~/.config/claude-dnd/tts.key
(in that order). Returns None on any failure so the caller can silently
degrade to text-only narration.

stdlib only — no requests, no google-cloud-sdk, no dependencies.
Setup walkthrough: docs/SKILL-tts.md.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

# ── Configuration ───────────────────────────────────────────────────────────

# LOCAL PATCH (2026-10-10): routed through OpenRouter's speech endpoint instead
# of Google AI Studio. Original kept at ~/.claude/dnd/patches/tts.py.original-2.4.0.
GEMINI_TTS_MODEL = os.environ.get("DND_TTS_MODEL", "google/gemini-3.8-flash-lite-tts")
GEMINI_TTS_URL = "https://openrouter.ai/api/v1/audio/speech"

KEY_FILE = Path.home() / ".openrouter_api_key"

# Curated 9-voice catalog. The full Gemini API exposes 30 voices; this
# subset keeps the per-block dropdown scannable. Extend VALID_VOICES and
# the matching arrays in display/templates/index.html if you want the
# full catalog.
VALID_VOICES = frozenset({
    # LOCAL PATCH: full Gemini catalog so per-character voices have room.
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
    "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
})
DEFAULT_VOICE = "Enceladus"

# Gemini Flash TTS responses degrade in latency past this point and may
# truncate. Bigger blocks should be chunked by the caller; the narration
# path naturally chunks at block flush.
MAX_TEXT_CHARS = 6000

# Request timeout — Gemini Flash TTS typical latency is 1-3s; we give it
# substantial headroom for cold-start or transient slowness.
DEFAULT_TIMEOUT = 90.0


# ── Key resolution ──────────────────────────────────────────────────────────

def _get_api_key() -> Optional[str]:
    """Resolve the Gemini API key. Env vars take precedence over the key file."""
    for env in ("DND_TTS_KEY", "OPENROUTER_API_KEY"):
        v = os.environ.get(env)
        if v and v.strip():
            return v.strip()
    if KEY_FILE.exists():
        try:
            return KEY_FILE.read_text(encoding="utf-8").strip() or None
        except OSError:
            return None
    return None


def key_source() -> str:
    """Return a human description of where the key came from, for diagnostics.

    Used by the verify path and the /dnd load surface — does not return the key.
    """
    for env in ("DND_TTS_KEY", "OPENROUTER_API_KEY"):
        v = os.environ.get(env)
        if v and v.strip():
            return f"env:{env}"
    if KEY_FILE.exists() and KEY_FILE.read_text(encoding="utf-8").strip():
        return f"file:{KEY_FILE}"
    return "unset"


# ── Synthesis ───────────────────────────────────────────────────────────────

# LOCAL PATCH: disk cache + per-character voices.
# Cache: one PCM file per (model, voice, text) so replaying a block is free.
# Voices: <campaign>/voices.json maps a speaker name to a voice, e.g.
#   {"_narrador": "Enceladus", "Kalli Alran": "Gacrux"}
CACHE_DIR = Path.home() / ".claude" / "dnd" / "tts-cache"


def _cache_path(text: str, voice: str) -> Path:
    import hashlib
    h = hashlib.sha256(f"{GEMINI_TTS_MODEL}|{voice}|{text}".encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{h}.pcm"


def voice_for(speaker, fallback: str = "") -> str:
    """Resolve the voice for a speaker from the active campaign's voices.json."""
    try:
        root = Path(os.environ.get("DND_CAMPAIGN_ROOT") or Path.home() / ".claude" / "dnd")
        camp = json.loads((root / ".runtime" / "active-campaign.json").read_text(encoding="utf-8"))["name"]
        table = json.loads((root / "campaigns" / camp / "voices.json").read_text(encoding="utf-8"))
    except Exception:
        return fallback
    key = (speaker or "").strip() or "_narrador"
    v = table.get(key) or (table.get("_narrador") if key == "_narrador" else table.get("_npc_padrao"))
    return v if v in VALID_VOICES else fallback


class TtsError(Exception):
    """Raised by synthesize_strict; caught by synthesize to fail silently."""


# LOCAL PATCH: long blocks are split into paragraph-sized pieces synthesized in
# parallel — one long request took >30s and timed out into the browser voice.
CHUNK_CHARS = 600
_GAP = b"\x00\x00" * int(24000 * 0.3)


def _split_chunks(text: str) -> list:
    import re
    parts = []
    for para in [x.strip() for x in text.split("\n") if x.strip()]:
        if len(para) <= CHUNK_CHARS:
            parts.append(para)
            continue
        cur = ""
        for sent in re.split(r"(?<=[.!?…])\s+", para):
            if cur and len(cur) + len(sent) + 1 > CHUNK_CHARS:
                parts.append(cur)
                cur = sent
            else:
                cur = (cur + " " + sent).strip()
        if cur:
            parts.append(cur)
    merged = []
    for part in parts:  # glue short neighbours back together
        if merged and len(merged[-1]) + len(part) + 1 <= CHUNK_CHARS:
            merged[-1] += "\n" + part
        else:
            merged.append(part)
    return merged


def synthesize_strict(
    text: str,
    voice: str = DEFAULT_VOICE,
    timeout: float = DEFAULT_TIMEOUT,
) -> bytes:
    text = (text or "").strip()[:MAX_TEXT_CHARS]
    if voice not in VALID_VOICES:
        voice = DEFAULT_VOICE
    if len(text) <= CHUNK_CHARS:
        return _synthesize_one(text, voice, timeout)
    whole = _cache_path(text, voice)
    try:
        if whole.exists() and whole.stat().st_size > 0:
            return whole.read_bytes()
    except OSError:
        pass
    from concurrent.futures import ThreadPoolExecutor
    chunks = _split_chunks(text)
    with ThreadPoolExecutor(max_workers=4) as ex:
        pieces = list(ex.map(lambda c: _synthesize_one(c, voice, timeout), chunks))
    pcm = _GAP.join(pieces)
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        whole.write_bytes(pcm)
    except OSError:
        pass
    return pcm


def _synthesize_one(
    text: str,
    voice: str = DEFAULT_VOICE,
    timeout: float = DEFAULT_TIMEOUT,
) -> bytes:
    """Call Gemini Flash TTS and return raw L16 PCM bytes (24 kHz mono).

    Raises TtsError for any failure. Use synthesize() for the silent-fail path.
    """
    key = _get_api_key()
    if not key:
        raise TtsError("no api key configured")

    text = (text or "").strip()
    if not text:
        raise TtsError("empty text")
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]

    if voice not in VALID_VOICES:
        voice = DEFAULT_VOICE

    cached = _cache_path(text, voice)
    try:
        if cached.exists() and cached.stat().st_size > 0:
            return cached.read_bytes()
    except OSError:
        pass

    body = {
        "model": GEMINI_TTS_MODEL,
        "input": text,
        "voice": voice,
        "response_format": "pcm",
    }
    body_bytes = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(
        GEMINI_TTS_URL,
        data=body_bytes,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                raise TtsError(f"http {resp.status}")
            raw = resp.read()
    except urllib.error.HTTPError as e:
        snippet = ""
        try:
            snippet = e.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        raise TtsError(f"http {e.code}: {snippet}") from e
    except urllib.error.URLError as e:
        raise TtsError(f"network: {e.reason}") from e
    except Exception as e:
        raise TtsError(f"unexpected: {e}") from e

    # OpenRouter returns raw 24 kHz mono 16-bit PCM directly.
    pcm = raw

    if not pcm:
        raise TtsError("empty pcm payload")
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(pcm)
    except OSError:
        pass
    return pcm


def synthesize(text: str, voice: str = DEFAULT_VOICE) -> Optional[bytes]:
    """Silent-fail wrapper. Returns L16 PCM bytes or None on any failure."""
    try:
        return synthesize_strict(text, voice)
    except TtsError:
        return None


# ── CLI for verification ────────────────────────────────────────────────────

def _cli() -> int:
    import argparse
    import sys

    p = argparse.ArgumentParser(
        description="Verify Gemini Flash TTS setup for the DnD display companion.",
    )
    p.add_argument(
        "--test", action="store_true",
        help="Check key source + run a synthesis call. Writes nothing.",
    )
    p.add_argument(
        "--speak", action="store_true",
        help="Also play the synthesized audio via afplay (macOS).",
    )
    p.add_argument(
        "--text", default="Hello, narrator voice test. The torchlit hall awaits.",
        help="Override the default test phrase.",
    )
    p.add_argument(
        "--voice", default=DEFAULT_VOICE,
        help=f"Voice name (default: {DEFAULT_VOICE}). Valid: {sorted(VALID_VOICES)}",
    )
    args = p.parse_args()

    if not args.test:
        p.print_help()
        return 0

    src = key_source()
    print(f"API key source: {src}")
    if src == "unset":
        print("  → no key found. See docs/SKILL-tts.md to configure one.")
        return 2

    print(f"Model: {GEMINI_TTS_MODEL}")
    print(f"Voice: {args.voice}")
    print(f"Text:  {args.text!r}")
    print("Calling Gemini Flash TTS…")
    try:
        pcm = synthesize_strict(args.text, args.voice)
    except TtsError as e:
        print(f"  FAIL: {e}")
        return 1

    print(f"  OK — received {len(pcm)} bytes of L16 PCM (24 kHz mono).")

    if args.speak:
        import struct
        import subprocess
        import tempfile

        sample_rate = 24000
        n_samples = len(pcm) // 2
        byte_rate = sample_rate * 2
        wav_header = (
            b"RIFF"
            + struct.pack("<I", 36 + len(pcm))
            + b"WAVE"
            + b"fmt "
            + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, byte_rate, 2, 16)
            + b"data"
            + struct.pack("<I", len(pcm))
        )
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_header + pcm)
            wav_path = f.name
        print(f"  Playing via afplay: {wav_path}")
        try:
            subprocess.run(["afplay", wav_path], check=False)
        except FileNotFoundError:
            print("  (afplay not found — non-macOS? PCM file kept at the path above.)")
            return 0
        os.unlink(wav_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
