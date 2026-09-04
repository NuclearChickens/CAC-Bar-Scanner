#!/usr/bin/env python3
"""Render the scan-verdict sounds into sounds/.

Re-run after changing any parameter below; the .wav files are checked
in so a normal build never has to run this. Standard library only (no
numpy, no sound libraries) — the same reason build_guide_pdf.sh avoids
pandoc: this is two short tones, not a signal-processing project.

    python3 make_sounds.py

Design notes — both sounds are deliberately tonal opposites so an
operator can tell them apart across a loud room without looking:

    allowed.wav  high, warm, ringing   (bell struck once)
    denied.wav   low, flat, buzzing    (square-wave buzzer)
"""
import math
import struct
import wave
from pathlib import Path

SR = 44100
OUT_DIR = Path(__file__).resolve().parent / "sounds"


def _write_wav(name: str, samples: list[float], peak: float) -> None:
    """Normalize to ``peak`` (0..1 of full scale) and write 16-bit mono.

    Mono 44.1 kHz keeps the files ~30 KB, which matters because they
    ride inside the onefile exe."""
    loudest = max(abs(s) for s in samples) or 1.0
    scale = peak / loudest
    frames = b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, s * scale)) * 32767))
        for s in samples
    )
    OUT_DIR.mkdir(exist_ok=True)
    path = OUT_DIR / name
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(frames)
    print(f"{path}: {len(samples) / SR * 1000:.0f} ms, {path.stat().st_size} bytes")


def bell(f0: float = 1760.0, dur: float = 0.34) -> list[float]:
    """ALLOWED — a struck bell.

    Additive synthesis: each partial decays faster than the one below
    it, and the 2.76x partial is deliberately inharmonic. That ratio is
    what separates a bell from a plain beep. The 3 ms attack makes the
    onset land the instant the verdict resolves."""
    partials = [  # (frequency ratio, amplitude, decay time constant)
        (1.00, 1.00, 0.130),
        (2.00, 0.38, 0.090),
        (2.76, 0.26, 0.065),
        (5.40, 0.10, 0.035),
    ]
    out = []
    for i in range(int(SR * dur)):
        t = i / SR
        s = sum(
            amp * math.exp(-t / tau) * math.sin(2 * math.pi * f0 * ratio * t)
            for ratio, amp, tau in partials
        )
        if t < 0.003:            # fade in — otherwise the onset clicks
            s *= t / 0.003
        if t > dur - 0.02:       # fade out — same reason
            s *= (dur - t) / 0.02
        out.append(s)
    return out


def buzzer(f_low: float = 146.0, f_high: float = 219.0,
           dur: float = 0.32) -> list[float]:
    """DENIED — a flat game-show buzzer.

    Two detuned square waves. Squares are all odd harmonics, which is
    what makes this read as harsh and mechanical where the bell reads
    as musical. No pitch movement: it sits still and blares."""
    out = []
    for i in range(int(SR * dur)):
        t = i / SR
        s = 1.0 if math.sin(2 * math.pi * f_low * t) >= 0 else -1.0
        s += 0.3 * (1.0 if math.sin(2 * math.pi * f_high * t) >= 0 else -1.0)
        if t < 0.005:
            s *= t / 0.005
        if t > dur - 0.030:
            s *= (dur - t) / 0.030
        out.append(s)
    return out


if __name__ == "__main__":
    # The buzzer is normalized quieter than the bell: square waves carry
    # far more energy per unit of peak amplitude, so matching their peaks
    # would make the denial sound roughly twice as loud as the approval.
    _write_wav("allowed.wav", bell(), peak=0.72)
    _write_wav("denied.wav", buzzer(), peak=0.60)
