"""Run and summarize the uVCO oscillator-core ngspice CV sweep."""

from __future__ import annotations

import argparse
import csv
import math
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


SIMULATION = Path(__file__).resolve().parents[1]
TEMPLATE = SIMULATION / "runs" / "oscillator_core_cv.spice"
BUILD = SIMULATION / "build"
RESULTS = SIMULATION / "results"

MEASURE = re.compile(
    r"^(p[1-4]|period|frequency|startup_time|saw_min|saw_max|out_min|out_max|"
    r"ictrl_avg|ictrl_min|ictrl_max|ref_min|ref_max|servo_min|servo_max)\s*=\s*"
    r"([-+0-9.eE]+)",
    re.MULTILINE,
)


@dataclass(frozen=True)
class Point:
    cv: float
    temperature: float = 25.0
    rtrim: float = 25_570.0
    rptc: float = 10_000.0
    cint: float = 10e-9
    c6comp: float = 100e-12
    vbe_delta: float = 0.0
    comparator_vos: float = 2e-3
    r11: float = 1_000_000.0
    r15: float = 10_000.0
    r16: float = 10_000.0
    r17: float = 536_000.0
    r3: float = 100_000.0
    r4: float = 90_900.0
    label: str = "nominal"


def engineering(value: float) -> str:
    return f"{value:.12g}"


def timing(cv: float) -> tuple[float, float, float]:
    expected = 110.0 * 2.0**cv
    periods = 8.0
    stop = max(80e-6, periods / expected)
    if cv >= 8.0:
        stop = max(stop, 500e-6)
    start = stop * 0.25
    step = min(2e-6, 1.0 / (expected * 1000.0))
    return stop, start, step


def slug(point: Point) -> str:
    cv = f"{point.cv:+.3f}".replace("+", "p").replace("-", "m").replace(".", "p")
    temp = f"{point.temperature:+.1f}".replace("+", "p").replace("-", "m").replace(".", "p")
    return f"{point.label}_cv_{cv}_t_{temp}"


def render(point: Point) -> str:
    stop, start, step = timing(point.cv)
    text = TEMPLATE.read_text(encoding="utf-8")
    replacement = (
        f".param CV={engineering(point.cv)} RTRIM={engineering(point.rtrim)} "
        f"RPTC={engineering(point.rptc)} CINT={engineering(point.cint)} "
        f"C6COMP={engineering(point.c6comp)} "
        f"VBE_DELTA={engineering(point.vbe_delta)} "
        f"COMP_VOS={engineering(point.comparator_vos)}\n"
        f".param R11_VAL={engineering(point.r11)} R15_VAL={engineering(point.r15)} "
        f"R16_VAL={engineering(point.r16)} R17_VAL={engineering(point.r17)} "
        f"R3_VAL={engineering(point.r3)} R4_VAL={engineering(point.r4)}\n"
        f".param TSTOP={engineering(stop)} TSTART={engineering(start)} "
        f"TSTEP={engineering(step)} TEMP_C={engineering(point.temperature)}"
    )
    return re.sub(
        r"\.param CV=.*\n\.param R11_VAL=.*\n\.param TSTOP=.*",
        replacement,
        text,
        count=1,
    )


def run_point(ngspice: str, point: Point) -> dict[str, float | str]:
    BUILD.mkdir(parents=True, exist_ok=True)
    name = slug(point)
    deck = BUILD / f"{name}.spice"
    log = BUILD / f"{name}.log"
    deck.write_text(render(point), encoding="utf-8")

    # The generated deck is one directory deeper than the committed template.
    model = SIMULATION / "models" / "uvco_oscillator_models.lib"
    deck.write_text(
        deck.read_text(encoding="utf-8").replace(
            ".include ../models/uvco_oscillator_models.lib",
            f'.include "{model.as_posix()}"',
        ),
        encoding="utf-8",
    )
    command = [ngspice, "-b", "-o", str(log), str(deck)]
    completed = subprocess.run(
        command,
        cwd=SIMULATION,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    content = log.read_text(encoding="utf-8", errors="replace")
    if completed.returncode:
        raise RuntimeError(f"ngspice failed for {name}; inspect {log}")
    values = {key: float(value) for key, value in MEASURE.findall(content)}
    ideal = 110.0 * 2.0**point.cv
    common: dict[str, float | str] = {
        "case": point.label,
        "cv_v": point.cv,
        "temperature_c": point.temperature,
        "rtrim_ohm": point.rtrim,
        "rptc_ohm": point.rptc,
        "cint_f": point.cint,
        "c6comp_f": point.c6comp,
        "vbe_delta_v": point.vbe_delta,
        "comparator_vos_v": point.comparator_vos,
        "ideal_hz": ideal,
    }
    if "frequency" not in values:
        return {
            **common,
            "status": "no sustained oscillation",
            **values,
            "period": math.nan,
            "frequency": math.nan,
            "error_vs_ideal_pct": math.nan,
            "octave_error_cents": math.nan,
            "period_spread_pct": math.nan,
            "control_ripple_pct": math.nan,
            "reference_pp_v": (
                values.get("ref_max", math.nan) - values.get("ref_min", math.nan)
            ),
        }
    cycle_periods = [values[f"p{index}"] for index in range(1, 5)]
    current_average = values["ictrl_avg"]
    return {
        **common,
        "status": "oscillating",
        **values,
        "error_vs_ideal_pct": 100.0 * (values["frequency"] / ideal - 1.0),
        "octave_error_cents": 1200.0 * math.log2(values["frequency"] / ideal),
        "period_spread_pct": 100.0 * (max(cycle_periods) - min(cycle_periods)) / values["period"],
        "control_ripple_pct": 100.0 * (values["ictrl_max"] - values["ictrl_min"]) / abs(current_average),
        "reference_pp_v": values["ref_max"] - values["ref_min"],
    }


def write_results(rows: list[dict[str, float | str]]) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    columns = list(rows[0])
    csv_path = RESULTS / "frequency_vs_cv.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    nominal = [row for row in rows if row["case"] == "nominal"]
    lines = [
        "# Nominal oscillator frequency versus CV",
        "",
        "| CV (V) | Frequency (Hz) | Ideal 110 Hz * 2^CV (Hz) | Error (%) | Error (cent) | Raw saw min/max (V) | 0--5 V output min/max (V) |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in nominal:
        if row["status"] == "oscillating":
            lines.append(
                f"| {float(row['cv_v']):.3f} | {float(row['frequency']):.6g} | "
                f"{float(row['ideal_hz']):.6g} | {float(row['error_vs_ideal_pct']):+.4f} | "
                f"{float(row['octave_error_cents']):+.3f} | "
                f"{float(row['saw_min']):.4f}/{float(row['saw_max']):.4f} | "
                f"{float(row['out_min']):.4f}/{float(row['out_max']):.4f} |"
            )
        else:
            lines.append(
                f"| {float(row['cv_v']):.3f} | no sustained oscillation | "
                f"{float(row['ideal_hz']):.6g} | -- | -- | "
                f"{float(row['saw_min']):.4f}/{float(row['saw_max']):.4f} | "
                f"{float(row['out_min']):.4f}/{float(row['out_max']):.4f} |"
            )
    lines.extend(
        [
            "",
            "The 110 Hz law is a readable reference, not a fit.  The simulation includes reset time, comparator hysteresis/delay, op-amp dynamics, and the semiconductor models listed in `../README.md`.",
            "",
        ]
    )
    (RESULTS / "frequency_vs_cv.md").write_text("\n".join(lines), encoding="utf-8")


def sensitivity_points() -> list[Point]:
    points = [Point(cv=cv, label="baseline") for cv in (0, 5, 8)]
    for cv in (0, 8):
        points.extend(
            [
                Point(cv=cv, cint=10.01e-9, label="c3_plus_0p1pct"),
                Point(cv=cv, cint=9.99e-9, label="c3_minus_0p1pct"),
                Point(cv=cv, vbe_delta=2e-3, label="q1a_vbe_plus_2mV"),
                Point(cv=cv, vbe_delta=-2e-3, label="q1a_vbe_minus_2mV"),
            ]
        )
    points.extend(
        [
            Point(
                cv=8,
                r15=10_000 * 1.001,
                r16=10_000 * 0.999,
                r17=536_000 * 0.999,
                label="scale_fast_0p1pct",
            ),
            Point(
                cv=8,
                r15=10_000 * 0.999,
                r16=10_000 * 1.001,
                r17=536_000 * 1.001,
                label="scale_slow_0p1pct",
            ),
            Point(
                cv=0,
                r11=1_000_000 * 0.999,
                r3=100_000 * 1.001,
                r4=90_900 * 0.999,
                label="timing_resistors_fast_0p1pct",
            ),
            Point(
                cv=0,
                r11=1_000_000 * 1.001,
                r3=100_000 * 0.999,
                r4=90_900 * 1.001,
                label="timing_resistors_slow_0p1pct",
            ),
            Point(cv=0, comparator_vos=10e-3, label="comparator_vos_plus_10mV"),
            Point(cv=0, comparator_vos=-10e-3, label="comparator_vos_minus_10mV"),
        ]
    )
    for temperature in (-20.0, 60.0):
        points.extend(
            Point(cv=cv, temperature=temperature, label=f"temperature_{temperature:+.0f}C")
            for cv in (0, 5, 8)
        )
    return points


def write_sensitivity(rows: list[dict[str, float | str]]) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS / "sensitivity.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    baseline = {
        float(row["cv_v"]): float(row["frequency"])
        for row in rows
        if row["case"] == "baseline"
    }
    lines = [
        "# Oscillator sensitivity cases",
        "",
        "| Case | CV (V) | Temperature (C) | Frequency (Hz) | Change from 25 C nominal at same CV (%) |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        cv = float(row["cv_v"])
        change = 100.0 * (float(row["frequency"]) / baseline[cv] - 1.0)
        lines.append(
            f"| {row['case']} | {cv:.1f} | {float(row['temperature_c']):.1f} | "
            f"{float(row['frequency']):.6g} | {change:+.4f} |"
        )
    lines.extend(
        [
            "",
            "The C3 cases apply the newly documented +/-0.1% tolerance. The VBE cases apply the DMMT3904W datasheet's 2 mV matching limit as a differential input error. The resistor cases stack stated 0.1% limits in the frequency-fast or frequency-slow direction.",
            "",
        ]
    )
    (RESULTS / "sensitivity.md").write_text("\n".join(lines), encoding="utf-8")


def stability_points() -> list[Point]:
    return [
        Point(cv=cv, c6comp=c6_pf * 1e-12, label=f"c6_{c6_pf:.0f}pF")
        for c6_pf in (47.0, 100.0, 200.0)
        for cv in (0.0, 5.0, 8.0, 10.0, 11.0, 12.0)
    ]


def write_stability(rows: list[dict[str, float | str]]) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS / "c6_stability.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# C6 compensation comparison",
        "",
        "| C6 | CV (V) | Frequency | Error vs ideal | Cycle spread | Q1B reference ripple | Startup to first midpoint |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        c6_pf = float(row["c6comp_f"]) * 1e12
        cv = float(row["cv_v"])
        if row["status"] == "oscillating":
            lines.append(
                f"| {c6_pf:.0f} pF | {cv:.0f} | {float(row['frequency']):.6g} Hz | "
                f"{float(row['error_vs_ideal_pct']):+.3f}% | "
                f"{float(row['period_spread_pct']):.4f}% | "
                f"{float(row['reference_pp_v']) * 1e3:.4f} mVpp | "
                f"{float(row['startup_time']) * 1e3:.4f} ms |"
            )
        else:
            lines.append(
                f"| {c6_pf:.0f} pF | {cv:.0f} | no sustained oscillation | -- | -- | "
                f"{float(row['reference_pp_v']) * 1e3:.4f} mVpp | -- |"
            )
    lines.extend(
        [
            "",
            "Cycle spread is the peak-to-peak difference of four consecutive periods divided by their mean. Reference ripple is measured at Q1B collector after startup. The local TPA1862 model includes its datasheet 6 MHz GBW, 5 V/us slew rate, and approximately 70 degree unity-gain phase margin condition.",
            "",
        ]
    )
    (RESULTS / "c6_stability.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ngspice", default=shutil.which("ngspice") or "ngspice")
    parser.add_argument(
        "--cv",
        nargs="*",
        type=float,
        default=[-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    )
    parser.add_argument(
        "--sensitivity",
        action="store_true",
        help="run documented tolerance and temperature sensitivity cases instead of the CV sweep",
    )
    parser.add_argument(
        "--stability",
        action="store_true",
        help="compare 47 pF, 100 pF, and 200 pF C6 compensation values",
    )
    args = parser.parse_args()

    if args.sensitivity and args.stability:
        parser.error("--sensitivity and --stability are mutually exclusive")
    if args.stability:
        rows = [run_point(args.ngspice, point) for point in stability_points()]
        write_stability(rows)
    elif args.sensitivity:
        rows = [run_point(args.ngspice, point) for point in sensitivity_points()]
        write_sensitivity(rows)
    else:
        rows = [run_point(args.ngspice, Point(cv=value)) for value in args.cv]
        write_results(rows)
    for row in rows:
        if row["status"] == "oscillating":
            print(
                f"CV={float(row['cv_v']):+6.3f} V  "
                f"f={float(row['frequency']):12.5f} Hz  "
                f"error={float(row['error_vs_ideal_pct']):+8.4f}%"
            )
        else:
            print(f"CV={float(row['cv_v']):+6.3f} V  no sustained oscillation")


if __name__ == "__main__":
    main()
