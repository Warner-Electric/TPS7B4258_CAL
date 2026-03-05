#!/usr/bin/env python3
# tps7b4258_tool_v2.py — unified CLI + Tkinter GUI for TPS7B4258 design
# Now includes Cff auto-calc with E-series capacitor suggestions.

from __future__ import annotations
import math
import argparse
import sys
from dataclasses import dataclass

# ---------------- E-series helpers (resistors) ----------------
E24 = [
    10.0, 11.0, 12.0, 13.0, 15.0, 16.0, 18.0, 20.0, 22.0, 24.0, 27.0, 30.0,
    33.0, 36.0, 39.0, 43.0, 47.0, 51.0, 56.0, 62.0, 68.0, 75.0, 82.0, 91.0
]
E48 = [
    100, 105, 110, 115, 121, 127, 133, 140, 147, 154, 162, 169,
    178, 187, 196, 205, 215, 226, 237, 249, 261, 274, 287, 301,
    316, 332, 348, 365, 383, 402, 422, 442, 464, 487, 511, 536,
    562, 590, 619, 649, 681, 715, 750, 787, 825, 866, 909, 953
]
E96_BASE = [10 ** (n / 96) for n in range(96)]
E96 = sorted(set(int(round(v * 100)) for v in E96_BASE))

# ---------------- E-series helpers (capacitors) ----------------
# We use decade multiples of E6/E12/E24 mantissas to propose nearby capacitor values.
E6_CAP = [1.0, 1.5, 2.2, 3.3, 4.7, 6.8]
E12_CAP = [1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2]
E24_CAP = [1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
           3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1]


def nearest_standard_res(value_ohms: float, series: str = "E48") -> float:
    if value_ohms <= 0:
        return 0.0
    decade = 10 ** math.floor(math.log10(value_ohms))
    norm = value_ohms / decade
    if series.upper() == "E24":
        base = [v / 10 for v in E24]
    elif series.upper() == "E96":
        base = [v / 100 for v in E96]
    else:  # E48
        base = [v / 100 for v in E48]
    nearest = min(base, key=lambda b: abs(b - norm))
    return nearest * decade


def pretty_res(val_ohm: float) -> str:
    if val_ohm == 0:
        return "0 Ω"
    for scale, unit in [(1e6, 'MΩ'), (1e3, 'kΩ'), (1, 'Ω')]:
        if val_ohm >= scale:
            return f"{val_ohm/scale:.3g} {unit}"
    return f"{val_ohm:.3g} Ω"


def nearest_cap(value_f: float, series: str = "E12"):
    """Return (nearest, lower, upper) standard capacitor values in Farads.
    series: E6, E12, or E24.
    """
    if value_f <= 0:
        return (0.0, 0.0, 0.0)
    mantissas = E12_CAP
    if series.upper() == 'E6':
        mantissas = E6_CAP
    elif series.upper() == 'E24':
        mantissas = E24_CAP
    exp = math.floor(math.log10(value_f))
    norm = value_f / (10 ** exp)
    best = min(mantissas, key=lambda m: abs(m - norm))
    # lower and upper
    lower = max([m for m in mantissas if m <= norm], default=mantissas[0])
    upper = min([m for m in mantissas if m >= norm], default=mantissas[-1])
    return best * (10 ** exp), lower * (10 ** exp), upper * (10 ** exp)


def pretty_cap(val_f: float) -> str:
    # prefer pF/nF/uF units
    if val_f >= 1e-6:
        return f"{val_f*1e6:.3g} µF"
    elif val_f >= 1e-9:
        return f"{val_f*1e9:.3g} nF"
    else:
        return f"{val_f*1e12:.3g} pF"

# ---------------- Core math ----------------

def dropout_requirements(vout: float, vdrop_typ: float, vdrop_max: float):
    return vout + vdrop_typ, vout + vdrop_max


def thermal(pd: float, theta_ja: float, ta: float):
    dt = pd * theta_ja
    tj = ta + dt
    return dt, tj


def cff_for_zero(r_upper: float, f_zero_hz: float) -> float:
    if r_upper <= 0 or f_zero_hz <= 0:
        return 0.0
    return 1.0 / (2 * math.pi * r_upper * f_zero_hz)


def zero_for_cff(r_upper: float, cff: float) -> float:
    if r_upper <= 0 or cff <= 0:
        return 0.0
    return 1.0 / (2 * math.pi * r_upper * cff)


def cout_ok(cout: float) -> bool:
    return (1e-6 <= cout <= 100e-6)


def esr_ok(esr: float) -> bool:
    return (1e-3 <= esr <= 2.0)

# ---------------- Designs ----------------
@dataclass
class BoostResult:
    R1: float
    R2: float
    vout_ach: float
    err_ppm: float


def design_boost(vref: float, vout: float, i_div: float, series: str) -> BoostResult:
    if vout <= vref:
        raise ValueError("BOOST requires Vout > Vref.")
    r2_ideal = vref / i_div
    r1_ideal = r2_ideal * (vout / vref - 1.0)
    R2 = nearest_standard_res(r2_ideal, series)
    R1 = nearest_standard_res(r1_ideal, series)
    vout_ach = vref * (1.0 + R1 / R2)
    err_ppm = (vout_ach / vout - 1.0) * 1e6
    return BoostResult(R1=R1, R2=R2, vout_ach=vout_ach, err_ppm=err_ppm)

@dataclass
class BuckRefResult:
    RTOP: float
    RBOT: float
    vadj_ach: float
    err_ppm: float


def design_buck_ref(vref: float, vout: float, i_div: float, series: str) -> BuckRefResult:
    if not (0 < vout < vref):
        raise ValueError("BUCK_REF requires 0 < Vout < Vref.")
    r_total_ideal = vref / i_div
    ratio = vout / vref  # RBOT / (RTOP + RBOT)
    rbot_ideal = r_total_ideal * ratio
    rtop_ideal = r_total_ideal - rbot_ideal
    RTOP = nearest_standard_res(rtop_ideal, series)
    RBOT = nearest_standard_res(rbot_ideal, series)
    vadj_ach = vref * (RBOT / (RTOP + RBOT))
    err_ppm = (vadj_ach / vout - 1.0) * 1e6
    return BuckRefResult(RTOP=RTOP, RBOT=RBOT, vadj_ach=vadj_ach, err_ppm=err_ppm)

# ---------------- CLI ----------------

def run_cli(argv=None):
    p = argparse.ArgumentParser(description="TPS7B4258 design tool v2 (CLI + GUI)")
    p.add_argument("mode", choices=["track","boost","buck_ref"], nargs='?', help="Operating mode")
    p.add_argument("--gui", action="store_true", help="Launch Tkinter GUI instead of CLI")

    # Common defaults tailored for 12 V from 5 V ref, Vin 13–40 V
    p.add_argument("--vref", type=float, default=5.0)
    p.add_argument("--vout", type=float, default=12.0)
    p.add_argument("--vin-min", type=float, default=13.0)
    p.add_argument("--vin-max", type=float, default=40.0)
    p.add_argument("--iout", type=float, default=0.15)
    p.add_argument("--iq", type=float, default=55e-6)
    p.add_argument("--theta-ja", type=float, default=48.0)
    p.add_argument("--ta", type=float, default=25.0)

    p.add_argument("--vdo-typ", type=float, default=0.25)
    p.add_argument("--vdo-max", type=float, default=0.45)

    p.add_argument("--series", type=str, default="E48", choices=["E24","E48","E96"], help="Resistor rounding series")
    p.add_argument("--divider-current", type=float, default=20e-6)

    p.add_argument("--cout", type=float, default=None)
    p.add_argument("--esr", type=float, default=None)

    # Cff auto-calc options
    p.add_argument("--cap-series", type=str, default="E12", choices=["E6","E12","E24"], help="Capacitor series for Cff suggestion")
    p.add_argument("--target-zero", type=float, default=None, help="If set (Hz), compute Cff across R1 to place zero at this fz (BOOST only)")
    p.add_argument("--cff", type=float, default=None, help="If set (F), compute resulting zero fz (BOOST only)")

    args = p.parse_args(argv)

    if args.gui or args.mode is None:
        return launch_gui_with_defaults()

    # Header
    print("\n=== TPS7B4258 Design Report (v2) ===")
    print(f"Mode: {args.mode.upper()}")
    print(f"Vref_in: {args.vref:.6g} V   Vout target: {args.vout:.6g} V   Vin: {args.vin_min:.6g}–{args.vin_max:.6g} V   Iout: {args.iout:.6g} A")

    # Headroom
    vin_req_typ, vin_req_max = dropout_requirements(args.vout, args.vdo_typ, args.vdo_max)
    ok_typ = args.vin_min >= vin_req_typ
    ok_max = args.vin_min >= vin_req_max
    print("\n-- Headroom / Dropout --")
    print(f"Vin required (typ) ≥ {vin_req_typ:.3f} V  → at Vin_min: {'OK' if ok_typ else 'MARGINAL/FAIL'}")
    print(f"Vin required (max) ≥ {vin_req_max:.3f} V  → at Vin_min: {'OK' if ok_max else 'MARGINAL/FAIL'}")

    # Efficiency
    eta_min = (args.vout / args.vin_min) * 100 if args.vin_min > 0 else float('nan')
    eta_max = (args.vout / args.vin_max) * 100 if args.vin_max > 0 else float('nan')
    print("\n-- Ideal Efficiency (LDO ≈ Vout/Vin) --")
    print(f"η @ Vin_min ≈ {eta_min:.1f}%   |   η @ Vin_max ≈ {eta_max:.1f}%")

    # Thermals worst case at Vin_max
    pd = (args.vin_max - args.vout) * args.iout + args.vin_max * args.iq
    dt, tj = thermal(pd, args.theta_ja, args.ta)
    print("\n-- Thermal Estimate (worst case, continuous load) --")
    print(f"Pd ≈ {pd*1e3:.1f} mW,  ΔT ≈ {dt:.1f} °C  (θJA={args.theta_ja} °C/W)")
    print(f"Tj ≈ {tj:.1f} °C (Ta={args.ta} °C)")
    if tj >= 150:
        print("WARNING: Exceeds 150 °C junction (absolute). Use a pre-regulator or reduce Pd.")
    elif tj >= 125:
        print("CAUTION: Exceeds ~125 °C typical operating limit. Verify duty cycle and derate.")

    # Network synthesis
    print("\n-- Network Synthesis --")
    try:
        if args.mode == 'track':
            print("TRACK: Tie FB → OUT. Vout ≈ Vref_in ± 6 mV (no divider).")
        elif args.mode == 'boost':
            res = design_boost(args.vref, args.vout, args.divider_current, args.series)
            print("Place divider OUT→R1→FB→R2→GND")
            print(f"R1 (OUT→FB): {pretty_res(res.R1)}    R2 (FB→GND): {pretty_res(res.R2)}")
            print(f"Achieved Vout ≈ {res.vout_ach:.6g} V  (error {res.err_ppm:.0f} ppm)")

            # Cff auto-calc / report
            if args.target_zero:
                cff = cff_for_zero(res.R1, args.target_zero)
                cff_n, cff_lo, cff_hi = nearest_cap(cff, args.cap_series)
                print(f"Cff for fz={args.target_zero:.0f} Hz → {pretty_cap(cff)}")
                print(f"Suggested ({args.cap_series}): nearest {pretty_cap(cff_n)}  |  lower {pretty_cap(cff_lo)}  |  upper {pretty_cap(cff_hi)}")
            if args.cff:
                fz = zero_for_cff(res.R1, args.cff)
                print(f"Given Cff={pretty_cap(args.cff)} → zero fz ≈ {fz:.0f} Hz")

            # ASCII schematic
            print("\nSchematic:\nOUT ── R1 ──┐\n            │\n           FB\n            │\n           R2\n            │\n           GND\nCff across R1: OUT ↔ FB")
        elif args.mode == 'buck_ref':
            res = design_buck_ref(args.vref, args.vout, args.divider_current, args.series)
            print("Tie FB → OUT. Divider VREF→RTOP→ADJ/EN→RBOT→GND")
            print(f"RTOP (VREF→ADJ/EN): {pretty_res(res.RTOP)}    RBOT (ADJ/EN→GND): {pretty_res(res.RBOT)}")
            print(f"Achieved Vadj≈Vout ≈ {res.vadj_ach:.6g} V  (error {res.err_ppm:.0f} ppm)")
            print("Cff note: feed-forward cap is generally applied across the UPPER FB resistor in BOOST mode; not used here.")
        else:
            print("Unknown mode.")
    except Exception as ex:
        print(f"Network synthesis error: {ex}")

    # Output capacitor checks
    print("\n-- Output Capacitor (stability window) --")
    print("Allowed: 1 µF to 100 µF (ceramic), ESR 1 mΩ to 2 Ω")
    if args.cout is not None:
        print(f"Cout = {args.cout*1e6:.3g} µF → {'OK' if cout_ok(args.cout) else 'OUT OF RANGE'}")
    if args.esr is not None:
        print(f"ESR  = {args.esr*1e3:.3g} mΩ → {'OK' if esr_ok(args.esr) else 'OUT OF RANGE'}")

    print("\n-- Notes --")
    print("• TPS7B4258 integrates reverse-current and reverse-polarity protection; external series diode usually not required.")
    print("• Place input/output capacitors close to pins with a low-impedance ground return.")

# ---------------- GUI ----------------

def launch_gui_with_defaults():
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
        from tkinter.scrolledtext import ScrolledText
    except Exception:
        print("Tkinter not available in this environment.")
        return 1

    class App(ttk.Frame):
        def __init__(self, master):
            super().__init__(master)
            self.master.title("TPS7B4258 Design Tool v2 (GUI)")
            self.master.geometry("1000x740")
            self._build()

        def _build(self):
            pan = ttk.Panedwindow(self.master, orient=tk.HORIZONTAL)
            pan.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
            left = ttk.Frame(pan, padding=8)
            right = ttk.Frame(pan, padding=8)
            pan.add(left, weight=1)
            pan.add(right, weight=2)

            row = 0
            ttk.Label(left, text="Mode").grid(row=row, column=0, sticky='w')
            self.mode = tk.StringVar(value='boost')
            ttk.Radiobutton(left, text="TRACK", value='track', variable=self.mode).grid(row=row, column=1, sticky='w')
            ttk.Radiobutton(left, text="BOOST (Vout>Vref)", value='boost', variable=self.mode).grid(row=row, column=2, sticky='w')
            ttk.Radiobutton(left, text="BUCK_REF (Vout<Vref)", value='buck_ref', variable=self.mode).grid(row=row, column=3, sticky='w')
            row += 1

            def add(label, var, default, helptext=None):
                nonlocal row
                ttk.Label(left, text=label).grid(row=row, column=0, sticky='w', pady=2)
                e = ttk.Entry(left, textvariable=var, width=16)
                e.grid(row=row, column=1, sticky='w')
                var.set(str(default))
                if helptext:
                    ttk.Label(left, text=helptext, foreground='#555').grid(row=row, column=2, columnspan=2, sticky='w')
                row += 1
                return e

            self.vref = tk.StringVar();      add("Vref_in [V]", self.vref, 5.0, "Reference before divider")
            self.vout = tk.StringVar();      add("Vout target [V]", self.vout, 12.0)
            self.vin_min = tk.StringVar();   add("Vin_min [V]", self.vin_min, 13.0)
            self.vin_max = tk.StringVar();   add("Vin_max [V]", self.vin_max, 40.0)
            self.iout = tk.StringVar();      add("Iout_max [A]", self.iout, 0.15)
            self.iq = tk.StringVar();        add("Iq_typ [A]", self.iq, 55e-6, "≈55 µA")
            self.theta_ja = tk.StringVar();  add("θJA [°C/W]", self.theta_ja, 48.0, "HSOIC-8")
            self.ta = tk.StringVar();        add("Ambient Ta [°C]", self.ta, 25.0)
            self.vdo_typ = tk.StringVar();   add("Dropout typ [V]", self.vdo_typ, 0.25)
            self.vdo_max = tk.StringVar();   add("Dropout max [V]", self.vdo_max, 0.45)
            self.div_i = tk.StringVar();     add("Divider current [A]", self.div_i, 20e-6, ">=~20 µA")
            self.cout = tk.StringVar();      add("Cout [F] (opt)", self.cout, "", "Check 1–100 µF")
            self.esr = tk.StringVar();       add("ESR [Ω] (opt)", self.esr, "", "Check 1 mΩ–2 Ω")

            # Cff section
            ttk.Separator(left, orient='horizontal').grid(row=row, column=0, columnspan=4, sticky='ew', pady=6)
            row += 1
            ttk.Label(left, text="Cff Auto-calc (BOOST mode)").grid(row=row, column=0, sticky='w')
            row += 1
            self.cff_mode = tk.StringVar(value='by_zero')
            ttk.Radiobutton(left, text="By target zero fz [Hz]", value='by_zero', variable=self.cff_mode).grid(row=row, column=0, sticky='w')
            self.fz = tk.StringVar();  add("Target zero [Hz]", self.fz, 2000, "Example: 2000 Hz")
            ttk.Radiobutton(left, text="By Cff value [F]", value='by_cff', variable=self.cff_mode).grid(row=row, column=0, sticky='w')
            self.cff = tk.StringVar(); add("Cff [F]", self.cff, "", "Example: 2.2e-10 (≈220 pF)")

            ttk.Label(left, text="Capacitor series").grid(row=row, column=0, sticky='w')
            self.cap_series = tk.StringVar(value='E12')
            cb = ttk.Combobox(left, textvariable=self.cap_series, values=['E6','E12','E24'], width=8, state='readonly')
            cb.grid(row=row, column=1, sticky='w')
            row += 1

            # Resistor series
            ttk.Label(left, text="Resistor series").grid(row=row, column=0, sticky='w')
            self.series = tk.StringVar(value='E48')
            cb2 = ttk.Combobox(left, textvariable=self.series, values=['E24','E48','E96'], width=8, state='readonly')
            cb2.grid(row=row, column=1, sticky='w')
            row += 1

            btns = ttk.Frame(left)
            btns.grid(row=row, column=0, columnspan=4, sticky='w', pady=8)
            ttk.Button(btns, text="Calculate", command=self.calculate).pack(side=tk.LEFT, padx=4)
            ttk.Button(btns, text="Copy", command=self.copy).pack(side=tk.LEFT, padx=4)
            row += 1

            self.text = ScrolledText(right, wrap='word', height=38)
            self.text.pack(fill=tk.BOTH, expand=True)
            self.text.insert('end', 'TPS7B4258 Design Tool v2 — ready.\n\n')

        def f(self, var, name, allow_empty=False):
            v = var.get().strip()
            if v == '' and allow_empty:
                return None
            try:
                return float(v)
            except Exception:
                raise ValueError(f"Invalid number for {name}: '{v}'")

        def copy(self):
            self.master.clipboard_clear()
            self.master.clipboard_append(self.text.get('1.0','end'))
            messagebox.showinfo("Copied","Report copied to clipboard")

        def calculate(self):
            try:
                mode = self.mode.get()
                vref = self.f(self.vref, 'Vref_in')
                vout = self.f(self.vout, 'Vout')
                vin_min = self.f(self.vin_min, 'Vin_min')
                vin_max = self.f(self.vin_max, 'Vin_max')
                iout = self.f(self.iout, 'Iout_max')
                iq = self.f(self.iq, 'Iq_typ')
                theta_ja = self.f(self.theta_ja, 'θJA')
                ta = self.f(self.ta, 'Ambient Ta')
                vdo_typ = self.f(self.vdo_typ, 'Dropout typ')
                vdo_max = self.f(self.vdo_max, 'Dropout max')
                div_i = self.f(self.div_i, 'Divider current')
                cout = self.f(self.cout, 'Cout', allow_empty=True)
                esr = self.f(self.esr, 'ESR', allow_empty=True)
                fz = self.f(self.fz, 'Target zero', allow_empty=True)
                cff = self.f(self.cff, 'Cff', allow_empty=True)
                cap_series = self.cap_series.get()
                series = self.series.get()
            except ValueError as e:
                messagebox.showerror("Input error", str(e)); return

            lines = []
            lines.append("=== TPS7B4258 Design Report (GUI v2) ===")
            lines.append(f"Mode: {mode.upper()}")
            lines.append(f"Vref_in: {vref:.6g} V   Vout target: {vout:.6g} V   Vin: {vin_min:.6g}–{vin_max:.6g} V   Iout: {iout:.6g} A")

            vin_req_typ, vin_req_max = dropout_requirements(vout, vdo_typ, vdo_max)
            ok_typ = vin_min >= vin_req_typ
            ok_max = vin_min >= vin_req_max
            lines.append("")
            lines.append("-- Headroom / Dropout --")
            lines.append(f"Vin required (typ) ≥ {vin_req_typ:.3f} V  → at Vin_min: {'OK' if ok_typ else 'MARGINAL/FAIL'}")
            lines.append(f"Vin required (max) ≥ {vin_req_max:.3f} V  → at Vin_min: {'OK' if ok_max else 'MARGINAL/FAIL'}")

            eta_min = (vout/vin_min)*100 if vin_min>0 else float('nan')
            eta_max = (vout/vin_max)*100 if vin_max>0 else float('nan')
            lines.append("")
            lines.append("-- Ideal Efficiency (LDO ≈ Vout/Vin) --")
            lines.append(f"η @ Vin_min ≈ {eta_min:.1f}%   |   η @ Vin_max ≈ {eta_max:.1f}%")

            pd = (vin_max - vout)*iout + vin_max*iq
            dt = pd*theta_ja
            tj = ta + dt
            lines.append("")
            lines.append("-- Thermal Estimate (worst case, continuous load) --")
            lines.append(f"Pd ≈ {pd*1e3:.1f} mW,  ΔT ≈ {dt:.1f} °C  (θJA={theta_ja} °C/W)")
            lines.append(f"Tj ≈ {tj:.1f} °C (Ta={ta} °C)")
            if tj >= 150:
                lines.append("WARNING: Exceeds 150 °C junction (absolute). Use a pre-regulator or reduce Pd.")
            elif tj >= 125:
                lines.append("CAUTION: Exceeds ~125 °C typical operating limit. Verify duty cycle and derate.")

            lines.append("")
            lines.append("-- Network Synthesis --")
            try:
                if mode == 'track':
                    lines.append("TRACK: Tie FB → OUT. Vout ≈ Vref_in ± 6 mV (no divider).")
                elif mode == 'boost':
                    res = design_boost(vref, vout, div_i, series)
                    lines.append("Place divider OUT→R1→FB→R2→GND")
                    lines.append(f"R1 (OUT→FB): {pretty_res(res.R1)}    R2 (FB→GND): {pretty_res(res.R2)}")
                    lines.append(f"Achieved Vout ≈ {res.vout_ach:.6g} V  (error {res.err_ppm:.0f} ppm)")

                    # Cff auto-calc panel
                    if self.cff_mode.get() == 'by_zero' and fz:
                        cff_calc = cff_for_zero(res.R1, fz)
                        cff_n, cff_lo, cff_hi = nearest_cap(cff_calc, cap_series)
                        lines.append("")
                        lines.append("Cff (feed-forward across R1)")
                        lines.append(f"Target zero fz = {fz:.0f} Hz → Cff ≈ {pretty_cap(cff_calc)}")
                        lines.append(f"Suggested {cap_series}: nearest {pretty_cap(cff_n)} | lower {pretty_cap(cff_lo)} | upper {pretty_cap(cff_hi)}")
                    elif self.cff_mode.get() == 'by_cff' and cff:
                        fz_calc = zero_for_cff(res.R1, cff)
                        cff_n, cff_lo, cff_hi = nearest_cap(cff, cap_series)
                        lines.append("")
                        lines.append("Cff (feed-forward across R1)")
                        lines.append(f"Entered Cff = {pretty_cap(cff)} → zero fz ≈ {fz_calc:.0f} Hz")
                        lines.append(f"Nearest standard ({cap_series}) suggestions: {pretty_cap(cff_n)} (nearest), {pretty_cap(cff_lo)} (lower), {pretty_cap(cff_hi)} (upper)")

                    lines.append("\nSchematic:\nOUT ── R1 ──┐\n            │\n           FB\n            │\n           R2\n            │\n           GND\nCff across R1: OUT ↔ FB")
                elif mode == 'buck_ref':
                    res = design_buck_ref(vref, vout, div_i, series)
                    lines.append("Tie FB → OUT. Divider VREF→RTOP→ADJ/EN→RBOT→GND")
                    lines.append(f"RTOP (VREF→ADJ/EN): {pretty_res(res.RTOP)}    RBOT (ADJ/EN→GND): {pretty_res(res.RBOT)}")
                    lines.append(f"Achieved Vadj≈Vout ≈ {res.vadj_ach:.6g} V  (error {res.err_ppm:.0f} ppm)")
                    lines.append("Cff note: feed-forward cap is generally applied across the UPPER FB resistor in BOOST mode; not used here.")
                else:
                    lines.append("Unknown mode.")
            except Exception as ex:
                lines.append(f"Network synthesis error: {ex}")

            lines.append("")
            lines.append("-- Output Capacitor (stability window) --")
            lines.append("Allowed: 1 µF to 100 µF (ceramic), ESR 1 mΩ to 2 Ω")
            if cout is not None:
                lines.append(f"Cout = {cout*1e6:.3g} µF → {'OK' if cout_ok(cout) else 'OUT OF RANGE'}")
            if esr is not None:
                lines.append(f"ESR  = {esr*1e3:.3g} mΩ → {'OK' if esr_ok(esr) else 'OUT OF RANGE'}")

            lines.append("")
            lines.append("-- Notes --")
            lines.append("• Reverse-current & reverse-polarity protection integrated; no external series diode typically needed.")
            lines.append("• Place input/output capacitors close to pins; use a solid ground return.")

            self.text.delete('1.0','end')
            self.text.insert('end', "\n".join(lines))

    root = tk.Tk()
    try:
        style = ttk.Style(root)
        style.theme_use('clam')
    except Exception:
        pass
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(run_cli())
