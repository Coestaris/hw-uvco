# uVCO sine harmonic comparison

## Run and method

The current diode/op-amp triangle circuit at `168f58a` and the previous
analog-switch circuit at `ece9f33` were simulated with ngspice 47. Both runs
used the same 37 CV points, transient timing limits, and the current
`simulate_full_signal_chain.py` H1–H10 analyzer: four complete settled cycles,
each aligned to a saw midpoint crossing, with harmonic powers averaged across
cycles. THD is the root-sum-square of H2–H10 divided by H1. The previous
SPICE deck and its `triangle_shaper_models.lib` came directly from `ece9f33`;
the current deck and oscillator model came from this working tree. Both runs
completed with sustained oscillation at every point.

The abbreviated revision IDs above identify the original analysis snapshots.
The imported standalone Git history starts after those snapshots.

The [comparison CSV](full_signal_chain_comparison.csv) contains both measured
frequencies, H1 amplitudes, THD, and H2–H10 at every CV point. The
[comparison plot](full_signal_chain_comparison.svg) overlays full-chain THD.
The freshly generated [current-chain CSV](full_signal_chain_thd.csv),
[THD plot](full_signal_chain_thd.svg), and
[harmonic plot](full_signal_chain_harmonics.svg) describe the current design.

| CV (V) | Current frequency | Current THD | Previous frequency | Previous THD |
|---:|---:|---:|---:|---:|
| −1.86423 | 30.03 Hz | 0.331% | 30.03 Hz | 0.122% |
| −0.125 | 100.68 Hz | 0.244% | 100.76 Hz | 0.139% |
| 3.3125 | 1.085 kHz | 0.776% | 1.086 kHz | 0.576% |
| 4.875 | 3.172 kHz | 2.465% | 3.177 kHz | 1.738% |
| 6.4375 | 9.098 kHz | 6.618% | 9.117 kHz | 5.244% |
| 7.8 | 21.918 kHz | 12.495% | 21.913 kHz | 12.835% |
| 8.0 | 24.798 kHz | 13.552% | 24.796 kHz | 14.548% |

The previous full chain has lower THD at 32 of the 37 matched CV points. It
reaches 1%, 5%, and 10% THD at approximately 1.74, 8.67, and 17.16 kHz;
the current chain reaches those levels at 1.38, 6.65, and 15.85 kHz. These
crossings are linear interpolations between measured points. The current chain
has slightly lower total THD near and above 22 kHz, while its H1 amplitude
falls to 4.65 V peak at 21.9 kHz versus 4.90 V peak previously. At that
point the current H2 and H3 are 7.66% and 5.46%, versus 6.35% and 4.65%
previously; the lower current *total* THD comes from lower upper harmonics.

## Distortion source

The two commits also changed the sine model: the prior full chain used a
calibrated instantaneous transfer, while the current chain includes its
resistor network and TL072 summer. Stage-isolation runs at CV = 7.8 V make
the comparison more specific:

The numeric [control CSV](full_signal_chain_controls.csv) records the same
H1–H10 measurements for every isolation run below.

| Circuit at approximately 22 kHz | Sine THD |
|---|---:|
| Current oscillator, triangle, and sine stages | 12.495% |
| Previous analog-switch triangle with current oscillator and sine stage | 8.594% |
| Ideal instantaneous triangle fold of the current oscillator saw, current sine stage | 10.585% |
| Ideal 0–5 V saw and ideal triangle fold, current sine stage | 0.069% |

At 22 kHz the previous analog-switch **triangle stage** performs better when
both designs drive the same current sine shaper. Most of the current
high-frequency THD is already present in the oscillator's saw waveform; the
diode/op-amp triangle circuit adds distortion. The sine stage alone contributes
little in the ideal-input control. These THD values are not additive because
harmonic phase and filtering change between controls.

At 21.9 kHz, one simulated saw cycle is about 45.62 µs and the reset portion
with negative slope lasts about 1.71 µs, or 3.75% of the period. The measured
90%–10% fall takes about 0.96 µs. In a separate control with an ideal saw
and ideal fold, a nearly instantaneous reset gave 0.063% THD; a 1.0 µs linear
reset gave 9.53% THD. This ties the dominant distortion to the finite reset
edge and its increasing share of each cycle. Increasing the modeled U1B slew
rate alone from 5 to 50 V/µs did not improve the full-chain result at 22 kHz
(12.50% THD), so this run does not identify a single op-amp slew limit as the
entire cause.

KiCad's exported oscillator-sheet netlist confirms that its `R7` (47 Ω)
connects `/saw_in` to the Q2 drain and `C3` (10 nF) connects `/saw_in` to
`/control_current`; those are the SPICE deck's reset and integration nodes.
The symbol property references in the current native sheet differ from the
exported netlist references (`R13` maps to exported `R7`, and `C25` maps to
exported `C3`). The connectivity CLI reports both forms through the symbol
UUID. The component values and exported connectivity, rather than the property
reference text, were used for the deck check.

## Reset-path modification trials

Additional nominal runs held the measured frequency near 21.9 kHz by adjusting
CV when the integrator capacitance changed. The reset interval is the portion
of one saw cycle with a falling output. These trials changed the SPICE deck
only; they are not schematic edits.

| Deck reset resistor | Integrator capacitor | Frequency | Falling interval | Full-chain sine THD |
|---:|---:|---:|---:|---:|
| 47 Ω | 10 nF | 21.918 kHz | 1.713 µs | 12.495% |
| 22 Ω | 10 nF | 21.911 kHz | 1.149 µs | 12.312% |
| 10 Ω | 10 nF | 21.917 kHz | 1.164 µs | 13.694% |
| 4.7 Ω | 10 nF | 21.911 kHz | 1.171 µs | 13.923% |
| 47 Ω | 4.7 nF | 21.958 kHz | 1.147 µs | 12.426% |
| 47 Ω | 2.2 nF | 21.950 kHz | 1.156 µs | 13.242% |
| 47 Ω | 1 nF | 21.920 kHz | 1.138 µs | 12.267% |

Reducing the reset resistor or capacitor shortens the falling interval, but
none of these simple changes materially cleans the current full chain. A
zero-volt sensing source in series with the simulated reset resistor measured
approximately 91 mA peak at 47 Ω and 173 mA peak at 22 Ω. The actual Q2 part
and pulse duty rating must be checked before choosing a lower resistor.

An ideal behavioral output blanker held the saw at 5 V while the reset
comparator was asserted, then passed the live saw. It reduced THD at 21.9 kHz
only from 12.495% to 12.238% with the current diode/op-amp triangle circuit.
With an ideal triangle fold in place of that circuit, the same blanker reduced
THD from 10.585% to 2.650%. This identifies a strong interaction between the
reset transition and the current triangle circuit. A real blanker would need
switch timing, settling, and output glitch validation; this ideal control does
not establish a ready-to-build circuit.

## Scope and reproduction

These are nominal functional/macromodel results at 25 °C with ideal rails.
The BAV99, TL072, TPA1862, comparator, OTA, and switch timing/transfer
representations have different levels of model fidelity. The two full-chain
numbers cannot by themselves isolate the triangle redesign because the sine
stage models differ. The same-sine hybrid control addresses that distinction.
Trim positions, tolerances, PCB parasitics, and a physical unit were not
measured. In the current deck, RV1 is centered; R23, R24, and R29 are 3.646
kΩ, 4.991 kΩ, and 5 kΩ. The fixed trim is carried through the sweep.

Run the current sweep from the repository root with:

```text
uv run --locked --project sim/rev2 uvco-full-signal-chain --sweep
```

Generated transient decks, waveforms, and logs are under the ignored
`sim/build/full-signal-chain/` directory. The comparison baseline is recorded
in the CSV above and is recoverable from commit `ece9f33` using that commit's
full-chain deck and triangle model with the current analyzer.
