#!/usr/bin/env python3
"""Run the full uVCO core-to-sine ngspice signal-chain simulation."""

from __future__ import annotations

import argparse
import csv
import math
import re
import subprocess
from pathlib import Path

import numpy as np

SIM = Path(__file__).resolve().parents[1]
TEMPLATE = SIM / "runs" / "full_signal_chain.spice"
BUILD = SIM / "build" / "full-signal-chain"
RESULTS = SIM / "results"


def load_waveform(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    data = np.genfromtxt(path, names=True)
    names = data.dtype.names or ()
    if len(names) != 4:
        raise RuntimeError(f"unexpected waveform columns: {names}")
    return tuple(np.asarray(data[name], dtype=float) for name in names)  # type: ignore[return-value]


def saw_crossings(time: np.ndarray, waveform: np.ndarray) -> np.ndarray:
    indices = np.flatnonzero((waveform[:-1] < 2.5) & (waveform[1:] >= 2.5))
    crossings = time[indices] + (2.5 - waveform[indices]) * (
        time[indices + 1] - time[indices]
    ) / (waveform[indices + 1] - waveform[indices])
    if len(crossings) < 3:
        raise RuntimeError("fewer than three saw midpoint crossings")
    return crossings


def sine_metrics(time: np.ndarray, waveform: np.ndarray, crossings: np.ndarray) -> dict[str, float]:
    """Use four complete, individually phase-aligned saw cycles for H1–H10."""
    if len(crossings) < 5:
        raise RuntimeError("fewer than four complete settled cycles")
    sample_count = 4096
    cycle_amps = []
    extrema = []
    for start, stop in zip(crossings[-5:-1], crossings[-4:]):
        uniform_time = np.linspace(start, stop, sample_count, endpoint=False)
        output = np.interp(uniform_time, time, waveform)
        spectrum = np.fft.rfft(output)
        cycle_amps.append(2 * np.abs(spectrum[1:11]) / sample_count)
        extrema.append((float(np.min(output)), float(np.max(output))))
    amplitudes = np.sqrt(np.mean(np.square(cycle_amps), axis=0))
    if amplitudes[0] < 0.1:
        raise RuntimeError("sine fundamental is too small for THD")
    thd = float(np.linalg.norm(amplitudes[1:]) / amplitudes[0])
    return {
        "sine_min_v": min(item[0] for item in extrema),
        "sine_max_v": max(item[1] for item in extrema),
        "fundamental_peak_v": float(amplitudes[0]),
        "thd_percent": 100 * thd,
        **{f"h{harmonic}_percent": float(100 * amplitudes[harmonic - 1] / amplitudes[0])
           for harmonic in range(2, 11)},
    }


def render(cv: float) -> str:
    expected_frequency = 110.0 * 2.0**cv
    stop = max(12 / expected_frequency, 1e-3)
    step = min(2e-6, 1 / (expected_frequency * 2000))
    deck = TEMPLATE.read_text(encoding="utf-8")
    deck, cv_count = re.subn(r"(?m)(\.param CV=)([^\s]+)", rf"\g<1>{cv:.12g}", deck, count=1)
    deck, timing_count = re.subn(
        r"(?m)(\.param TSTOP=)([^\s]+)( TSTEP=)([^\s]+)",
        rf"\g<1>{stop:.12g}\g<3>{step:.12g}",
        deck,
        count=1,
    )
    if cv_count != 1 or timing_count != 1:
        raise RuntimeError("full-chain template parameters not found")
    return deck


def run_point(cv: float, reuse: bool = False) -> dict[str, float | str]:
    BUILD.mkdir(parents=True, exist_ok=True)
    work = BUILD / f"cv_{cv:+.5f}".replace("+", "p").replace("-", "m").replace(".", "p")
    work.mkdir(parents=True, exist_ok=True)
    deck = work / "full_signal_chain.spice"
    if not reuse:
        deck.write_text(
            render(cv).replace(
                ".include ../models/uvco_oscillator_models.lib",
                f'.include "{(SIM / "models" / "uvco_oscillator_models.lib").as_posix()}"',
            ),
            encoding="utf-8",
        )
        log = work / "ngspice.log"
        with log.open("w", encoding="utf-8") as stream:
            completed = subprocess.run(["ngspice", "-b", deck.name], cwd=work, stdout=stream, stderr=subprocess.STDOUT, check=False)
        if completed.returncode:
            raise RuntimeError(f"ngspice failed; inspect {log}")
    time, saw, triangle, sine = load_waveform(work / "waveform.dat")
    settled = time >= time[-1] - (time[-1] - time[0]) / 4
    settled_saw_span = float(np.ptp(saw[settled]))
    if settled_saw_span < 4.0:
        return {"cv_v": cv, "status": "no_sustained_oscillation", "saw_span_v": settled_saw_span}
    crossings = saw_crossings(time, saw)
    oscillation_hz = 1 / float(np.mean(np.diff(crossings[-5:])))
    metrics = sine_metrics(time, sine, crossings)
    final_period = 1 / oscillation_hz
    steady = time >= time[-1] - 3 * final_period
    return {
        "cv_v": cv,
        "status": "oscillating",
        "frequency_hz": oscillation_hz,
        "saw_min_v": float(np.min(saw[steady])),
        "saw_max_v": float(np.max(saw[steady])),
        "triangle_min_v": float(np.min(triangle[steady])),
        "triangle_max_v": float(np.max(triangle[steady])),
        **metrics,
    }


def plot_svg(path: Path, rows: list[dict[str, float | str]], columns: list[str], title: str) -> None:
    width, height = 1050, 620
    left, right, top, bottom = 90, 240, 75, 80
    x0, x1 = left, width - right
    y0, y1 = top, height - bottom
    positive = [float(row[key]) for row in rows for key in columns if float(row[key]) > 0]
    ymin = 10 ** math.floor(math.log10(min(positive)))
    ymax = 10 ** math.ceil(math.log10(max(positive)))
    if ymax <= ymin:
        ymax = 10 * ymin
    xmin, xmax = 30.0, 22000.0

    def x(value: float) -> float:
        return x0 + (math.log10(value) - math.log10(xmin)) / (math.log10(xmax) - math.log10(xmin)) * (x1 - x0)

    def y(value: float) -> float:
        return y1 - (math.log10(max(value, ymin)) - math.log10(ymin)) / (math.log10(ymax) - math.log10(ymin)) * (y1 - y0)

    colors = ["#1565c0", "#d84315", "#2e7d32", "#8e24aa", "#00838f", "#ef6c00", "#6d4c41", "#ad1457", "#455a64"]
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<defs><clipPath id="plot"><rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}"/></clipPath></defs>',
        f'<text x="{left}" y="36" font-family="sans-serif" font-size="24" font-weight="bold">{title}</text>',
        f'<text x="{left}" y="58" font-family="sans-serif" font-size="13">Full oscillator → triangle → sine chain; calibrated functional OTA</text>',
    ]
    for tick in (30, 100, 300, 1000, 3000, 10000, 22000):
        xx = x(tick)
        lines.extend((
            f'<line x1="{xx:.1f}" y1="{y0}" x2="{xx:.1f}" y2="{y1}" stroke="#e4e9ef"/>',
            f'<text x="{xx:.1f}" y="{y1+23}" text-anchor="middle" font-family="sans-serif" font-size="12">{tick:g}</text>',
        ))
    decade = ymin
    while decade <= ymax * 1.001:
        yy = y(decade)
        lines.extend((
            f'<line x1="{x0}" y1="{yy:.1f}" x2="{x1}" y2="{yy:.1f}" stroke="#e4e9ef"/>',
            f'<text x="{x0-12}" y="{yy+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="12">{decade:g}</text>',
        ))
        decade *= 10
    lines.extend((
        f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" fill="none" stroke="#4b5563"/>',
        f'<text x="{(x0+x1)/2:.1f}" y="{height-20}" text-anchor="middle" font-family="sans-serif" font-size="15">Measured oscillator frequency (Hz)</text>',
        f'<text x="24" y="{(y0+y1)/2:.1f}" transform="rotate(-90 24 {(y0+y1)/2:.1f})" text-anchor="middle" font-family="sans-serif" font-size="15">Percent of fundamental</text>',
    ))
    for index, key in enumerate(columns):
        color = colors[index]
        points = " ".join(f"{x(float(row['frequency_hz'])):.2f},{y(float(row[key])):.2f}" for row in rows)
        lines.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2.2" clip-path="url(#plot)"/>')
        for row in rows:
            f = float(row["frequency_hz"])
            if xmin <= f <= xmax:
                lines.append(f'<circle cx="{x(f):.2f}" cy="{y(float(row[key])):.2f}" r="2.5" fill="{color}"/>')
        label = "THD (H2–H10)" if key == "thd_percent" else key.replace("_percent", "").upper()
        lines.extend((
            f'<line x1="{x1+20}" y1="{top+index*28}" x2="{x1+48}" y2="{top+index*28}" stroke="{color}" stroke-width="3"/>',
            f'<text x="{x1+56}" y="{top+index*28+5}" font-family="sans-serif" font-size="14">{label}</text>',
        ))
    lines.append("</svg>")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cv", type=float, default=0.0)
    parser.add_argument("--sweep", action="store_true", help="sweep the 30 Hz–22 kHz operating range")
    parser.add_argument("--reuse", action="store_true", help="re-analyze saved waveforms without rerunning ngspice")
    args = parser.parse_args()
    if not args.sweep:
        for key, value in run_point(args.cv, args.reuse).items():
            print(f"{key}={value}")
        return
    cv_points = sorted(set(np.linspace(-2.0, 8.0, 33)) | {-1.8648, -1.86423, 7.8, 7.80541})
    rows = [run_point(float(cv), args.reuse) for cv in cv_points]
    for row in rows:
        print(f"CV={float(row['cv_v']):+.5f} V  status={row['status']}  "
              f"f={row.get('frequency_hz', 'n/a')} Hz  THD={row.get('thd_percent', 'n/a')}%", flush=True)
    valid = [row for row in rows if row["status"] == "oscillating"]
    if len(valid) != len(rows):
        raise RuntimeError("some sweep points failed to oscillate; inspect generated decks and logs")
    RESULTS.mkdir(parents=True, exist_ok=True)
    with (RESULTS / "full_signal_chain_thd.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(valid[0]))
        writer.writeheader()
        writer.writerows(valid)
    plot_svg(RESULTS / "full_signal_chain_thd.svg", valid, ["thd_percent"], "uVCO sine total harmonic distortion")
    plot_svg(RESULTS / "full_signal_chain_harmonics.svg", valid,
             [f"h{index}_percent" for index in range(2, 11)], "uVCO sine harmonic response")
    print(f"results={RESULTS / 'full_signal_chain_thd.csv'}")


if __name__ == "__main__":
    main()
