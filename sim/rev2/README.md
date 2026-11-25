# VCO1 Rev2 simulation

This directory characterizes the circuit drawn on
[`oscillator_core.kicad_sch`](../../hardware/rev2/oscillator_core.kicad_sch). The committed run deck keeps the
same references, values, and connectivity so that the electrical model can be
reviewed against the schematic.  Generated decks, raw waveforms, and logs go
under `build/` and are not source artifacts.

## Explicit component and net table

| Reference | Value/model | Pin-to-net mapping | Simulation role |
|---|---|---|---|
| V12P, V12N | +12 V, -12 V | `V12P:+12V-0`, `V12N:0--12V` | Analog rails |
| V5, V2V5 | 5 V, 2.5 V | `V5:+5V-0`, `V2V5:+2V5-0` | Comparator/reference rails |
| VCV | parameter `CV` | `CV-0` | Swept control voltage |
| U9B, R16, R15, C20 | TPA1862, 10 k, 10 k, 100 p | `+=0`, `-=cv_sum`, `out=cv_inv`; R16 `CV-cv_sum`; R15/C20 `cv_inv-cv_sum` | Inverts CV |
| U9A, R17, R13, TH1, C17, R12 | TPA1862, 536 k, tuned trim, 10 k PTC, 100 p, 1 k | `+=0`, `-=expo_sum`, `out=expo_drive`; R17/R13 `cv_inv-expo_sum`; TH1/C17 `expo_sum-base_a`; R12 `expo_drive-base_a` | Applies the temperature-compensated exponential base voltage |
| Q1A, Q1B | DMMT3904W-7-F | Q1A `C=control_current B=base_a E=emit`; Q1B `C=ref_col B=0 E=emit` | Matched exponential pair |
| R11, U1A, R10, C6 | 1 M, TPA1862, 1 k, 100 p | R11 `+5V-ref_col`; U1A `+=0 -=ref_col out=servo_out`; R10 `servo_out-emit`; C6 `ref_col-servo_out` | Programs and servos the nominal 5 uA reference current |
| U1B, C3 | TPA1862, 10 n C0G/NP0, 0.1% | U1B `+=0 -=control_current out=saw_raw`; C3 `saw_raw-control_current` | Current integrator |
| U2, R4, R3 | TP1961, 90.9 k, 100 k | U2 `+=cmp_plus -=+2V5 out=cmp_out V+=+5V V-=0`; R4 `saw_raw-cmp_plus`; R3 `cmp_out-cmp_plus` | Schmitt threshold and reset command |
| Q2, R7, R6, R5 | 2N7002, 47, 100 k, 47 | Q2 `D=reset_d G=reset_g S=control_current`; R7 `saw_raw-reset_d`; R6 `reset_g-control_current`; R5 `cmp_out-reset_g` | Fast sawtooth reset |
| U4A, U4B, R18, R19, R14 | TL072, 10 k, 100 k, 47 | U4A `+=saw_raw -=level_sum out=level`; U4B `+=0 -=out`; R18 `level-level_sum`; R19 `+2V5-level_sum`; R14 `level-SAW` | Maps the raw approximately 0.23--4.77 V ramp to approximately 0--5 V; parks the unused channel as a grounded follower |
| C7, C33 | 100 p, DNP | Output shunts | Omitted because both schematic instances are marked DNP |

U4 is now powered with pin 8 on +12 V and pin 4 on -12 V in both the hardware
sheet and native simulation.  U4B is wired as a grounded follower instead of
shorting its output.  The redundant `saw_out` label was removed; `saw_in` is
the single timing-node probe name.

## Model fidelity

- Q1 uses Diodes Incorporated's `DI_DMMT3904W` manufacturer model.  The two
  instances are identical in the nominal run; separate tolerance cases cover
  the datasheet's 2 mV VBE and 2% gain-matching limits.
- Q2 uses Diodes Incorporated's `N7002` manufacturer model.  The schematic
  specifies only the generic `2N7002`, so this is a representative vendor
  model rather than a guaranteed model of an assigned ordering code.
- TPA1862 and TP1961 have no published manufacturer SPICE models located for
  this work.  Local macromodels reproduce the relevant published limits:
  TPA1862 6 MHz GBW, 5 V/us typical slew rate, approximately 70 degree phase
  margin at the datasheet's 10 k/100 pF condition, rail-limited output and
  30 uV maximum offset; TP1961 7.5 mV internal hysteresis, 7 ns typical propagation
  delay, 1 ns edges, 25 ohm approximate output resistance, and offset as a
  parameter.
- TL072 uses a local 3 MHz, 13 V/us, rail-headroom-limited behavioral channel.
  It affects the delivered SAW level and the downstream triangle and sine
  stages, but is outside the oscillator timing loop.
- TH1 is 10 k at 25 C with the schematic's +3300 ppm/C linear coefficient.
  No exact thermistor ordering code or nonlinear resistance curve is present.
- PCB trace parasitics, supply impedance, package thermal coupling, capacitor
  voltage coefficient, dielectric absorption, aging, and transistor
  self-heating are not modeled.

## Reproduce

Install `uv` and put `ngspice` on your PATH. Run the analyses from the repository
root with the locked Python environment. These commands use the checked-in
SPICE decks. KiCad's direct oscillator-sheet export emits TP4 and TP5 as
incomplete transmission-line statements, which ngspice rejects.

```text
uv run --locked --project sim/rev2 uvco-sweep
uv run --locked --project sim/rev2 uvco-sweep --sensitivity
uv run --locked --project sim/rev2 uvco-sweep --stability
```

The analyses write the frequency, sensitivity, and C6 stability tables under
`results/`; generated decks and raw/log artifacts remain under the ignored
`build/` directory.

## Full oscillator-to-sine chain

`runs/full_signal_chain.spice` follows the current oscillator, diode/op-amp
triangle shaper, and LM13700 sine-shaper resistor network. The sine OTA is a
functional differential-pair model; its trimmers were calibrated once at low
frequency, then held fixed. Sweep the requested audio range and generate CSV
data plus THD and H2–H10 SVG plots with:

```text
uv run --locked --project sim/rev2 uvco-full-signal-chain --sweep
```

See [the signal-chain comparison](results/full_signal_chain_comparison.md) for
measured results, model limits, and a same-CV comparison with the previous
analog-switch revision.

## Primary model and datasheet sources

- https://www.diodes.com/part/view/DMMT3904W
- https://www.diodes.com/spice/download/3320/DMMT3904W.spice.txt
- https://www.diodes.com/part/view/2N7002
- https://www.diodes.com/spice/download/1941/2N7002.spice.txt
- https://www.3peak.com/precision-op-amps/tpa1862
- https://static.3peak.com/res/doc/ds/Datasheet_TPA1861-TPA1862-TPA1864.pdf
- https://static.3peak.com/res/doc/ds/Datasheet_TP1961-TP1962.pdf
- https://www.ti.com/product/TL072
- https://www.ti.com/lit/ds/symlink/tl072.pdf
