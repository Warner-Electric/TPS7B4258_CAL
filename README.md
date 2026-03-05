# TPS7B4258 Design Tool v2 — CLI + Tkinter GUI

**File:** `tps7b4258_tool_v2.py`  
**Purpose:** Quickly synthesize divider networks and sanity‑check operating margins for **TI TPS7B4258** LDO designs. Supports:
- **Modes**: `TRACK`, `BOOST (Vout > Vref)`, and `BUCK_REF (Vout < Vref)`
- **Cff auto‑calc** in BOOST mode with **E‑series** capacitor suggestions (E6/E12/E24)
- **E‑series rounding** for resistors (E24/E48/E96)
- Headroom (dropout) and **thermal** estimates, **Cout/ESR** window checks
- **GUI** with copyable report, or **CLI** for scripted runs

---

## ✨ Features
- **Network synthesis**
  - BOOST: compute `R1 (OUT→FB)` and `R2 (FB→GND)` for target Vout
  - BUCK_REF: compute `RTOP (VREF→ADJ/EN)` and `RBOT (ADJ/EN→GND)` for target Vadj
  - TRACK: FB tied to OUT (Vout ≈ Vref_in)
- **Cff across R1** (BOOST):
  - Given target **zero** `fz` → compute **Cff**
  - Given **Cff** → compute resulting **fz**
  - Suggest nearest **standard capacitor values** (E6/E12/E24)
- **Operating checks**
  - Headroom: `Vin_required = Vout + Vdrop(typ/max)`
  - Thermal: `Pd = (Vin_max - Vout)*Iout + Vin_max*Iq`, `ΔT = Pd*θJA`, `Tj = Ta + ΔT`
  - Output cap guidance: `Cout ∈ [1 µF, 100 µF]` and `ESR ∈ [1 mΩ, 2 Ω]`

---

## 🛠️ Installation
- **Python** 3.9+
- **No third‑party packages required** for CLI/GUI (uses only standard library + Tkinter which ships with most Python installers).  
  > On some Linux distros, install Tkinter via your package manager (e.g., `sudo apt install python3-tk`).

---

## ▶️ Quick Start
### GUI
```bash
python tps7b4258_tool_v2.py --gui
```
- Select **mode** (TRACK/BOOST/BUCK_REF)
- Enter inputs (Vref, Vout, Vin range, Iout, Iq, θJA, Ta, dropout typ/max, divider current)
- (Optional) **Cout** and **ESR** for window checks
- For BOOST **Cff**: choose **By target zero fz** *or* **By Cff value** and select **capacitor series** (E6/E12/E24)
- Click **Calculate** then **Copy** to clipboard

### CLI
```bash
# Show GUI if no mode is provided
python tps7b4258_tool_v2.py

# BOOST example: 12 V from 5 V ref, E48 resistors, divider @ 20 µA, target Cff zero 2 kHz
python tps7b4258_tool_v2.py boost --vref 5 --vout 12 --vin-min 13 --vin-max 40 \
  --iout 0.15 --iq 55e-6 --theta-ja 48 --ta 25 --series E48 --divider-current 20e-6 \
  --target-zero 2000 --cap-series E12

# BOOST example: given Cff=220 pF (2.2e-10 F), report resulting fz
python tps7b4258_tool_v2.py boost --cff 2.2e-10 --series E96 --vref 5 --vout 12

# BUCK_REF example: generate reference divider below Vref
python tps7b4258_tool_v2.py buck_ref --vref 5 --vout 2.5 --divider-current 30e-6 --series E96
```
**Common arguments (CLI):**
- `--vref` (V), `--vout` (V), `--vin-min`/`--vin-max` (V)
- `--iout` (A), `--iq` (A)
- `--theta-ja` (°C/W), `--ta` (°C)
- `--vdo-typ`/`--vdo-max` (V)
- `--series` resistor series: `E24|E48|E96`
- `--divider-current` (A)
- `--cout` (F), `--esr` (Ω)
- **Cff options (BOOST):** `--cap-series E6|E12|E24`, `--target-zero` (Hz) or `--cff` (F)

Exit codes: `0` success, `1/2` on errors (e.g., bad inputs, Tk unavailable).

---

## 📐 Calculations
- **Resistor rounding**: nearest value in chosen **E‑series** (E24/E48/E96) using decade‑normalized comparison.
- **BOOST divider**: `Vout = Vref*(1 + R1/R2)` → solve for ideal R1/R2 at divider current `Idiv` and round.
- **BUCK_REF divider**: `Vadj = Vref * RBOT / (RTOP + RBOT)` for target below Vref.
- **Cff ↔ zero (BOOST):**
  - `Cff = 1 / (2π * R1 * fz)`  (target `fz` → Cff)
  - `fz  = 1 / (2π * R1 * Cff)` (given Cff → zero)
- **Cap suggestions**: nearest/lower/upper from selected capacitor series mantissas (E6/E12/E24) across decades, reported in **pF/nF/µF**.

---

## 🧪 Output & Reporting
The tool prints a structured **Design Report** including:
- **Mode** and key inputs
- **Headroom / Dropout** verdicts at `Vin_min`
- **Ideal efficiency** estimates: `η ≈ Vout/Vin`
- **Thermal** (`Pd`, `ΔT`, `Tj`) with cautions at 125 °C and 150 °C
- **Network Synthesis**
  - Divider values with **pretty units** (Ω, kΩ, MΩ)
  - Achieved voltage and **error (ppm)** vs target
  - **Cff** section (BOOST): computed/suggested values or resulting zero
  - Small **ASCII schematic** for BOOST
- **Output capacitor window** checks for `Cout` / `ESR`
- **Notes** on layout and protection features

---

## 🖥️ GUI Notes
- Clean two‑pane layout: inputs left, report right
- E‑series selectors for **resistors** and **Cff capacitors**
- Copy button copies the entire report to clipboard

---

## ⚠️ Engineering Notes
- This tool provides **first‑order sizing**. Always validate stability (phase margin, load/line transients) with the vendor’s guidance and lab tests.
- Layout matters: place **input/output capacitors** close to the LDO pins with a low‑impedance ground return.

---

## 📜 License
Add your preferred license (e.g., MIT, Apache‑2.0).

---

## ✍️ Changelog
- **v2** — Unified CLI/GUI, Cff auto‑calc with E‑series suggestions, improved reporting
- **v1** — Initial calculation scripts
