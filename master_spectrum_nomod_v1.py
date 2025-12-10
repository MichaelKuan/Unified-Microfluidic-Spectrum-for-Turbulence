#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Master spectrum plotter (NO log-periodic modulation)

E(k) = ε^(2/3) k^{-m}
       * exp[-γ_v (k/kη)^{α_v}]
       * exp[-γ_p (k/k★)^{α_p}]   (optional)

Reads rows from Excel and plots spectra. Adds:
- Tail exponent cap: k_max = k_eta * (tail_cap / gamma_v)^(1/alpha_v)
- Y-axis cropping: show only the top y_span_decades decades of E(k)
- Knee markers: amplitude-based and/or slope-matched

Optional Excel columns (case-insensitive):
  tail_exp_cap, y_span_decades
"""

# ===== CONFIG =====
EXCEL_PATH  = "master_spectrum_nomod_test copy.xlsx"
SHEET_NAME  = "TestPage"     # or None for first sheet
OUTPUT_DIR  = "."
CREATE_TEMPLATE_IF_MISSING = False
DEBUG_DIAGNOSTICS = True

# New knobs (global defaults; can be overridden per-row in Excel)
TAIL_EXP_CAP     = 25.0   # cap viscous exponent Xv at k_max (typical 20–30)
Y_SPAN_DECADES   = 25.0   # show top N decades of E(k) on the combined plot
HARD_KMAX_CEIL   = 1e9    # absolute safety ceiling on k_max
HARD_KMIN_FLOOR  = 1e-17    # don't plot below ~100 1/m by default
E_FLOOR          = 1e-300 # numerical floor for log-plotting
# ==================

# === Knee markers (enable either or both to compare) ===
SHOW_KNEES_AMPLITUDE = False
SHOW_KNEES_SLOPE     = False

# Amplitude-based: set *either* a factor (e.g., 0.05 = 20× drop) or decades (e.g., 1.3)
KNEE_FACTOR  = 0.367879441     # set to None to use decades
KNEE_DECADES = None     # set to a float (e.g., 1.3) and set KNEE_FACTOR=None

# Slope-matched: target extra steepening Δs of local slope relative to -m
DELTA_SLOPE = 3.0

#======================

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from math import pi
import matplotlib as mpl
mpl.rcParams['legend.fontsize'] = 8


np.seterr(under="ignore")  # exp(-very-large) -> 0 is fine

# ---------- helpers ----------
def nkey(s):
    return "".join(ch for ch in str(s).lower() if ch.isalnum())

def get(row: pd.Series, key: str, default=None, cast=float):
    """Flexible column access: case/space/underscore-insensitive."""
    t = nkey(key)
    for col in row.index:
        if nkey(col) == t:
            v = row[col]
            if pd.isna(v): return default
            try: return cast(v) if cast is not None else v
            except Exception: return default
    return default

def fpos(x, fb, lo=None, hi=None):
    """Finite float in [lo,hi], else fallback fb."""
    try:
        x = float(x)
        if not np.isfinite(x): return fb
        if lo is not None and x < lo: return fb
        if hi is not None and x > hi: return fb
        return x
    except Exception:
        return fb

# ---------- Optional: example template ----------
def write_template_xlsx(path: str):
    df = pd.DataFrame([
        {
            "name":"Example-K41-ish",
            "epsilon":90.0, "m":1.67, "nu":1.0e-6,
            "gamma_v":1.0, "alpha_v":4/3,
            "gamma_p":0.0, "alpha_p":2.0, "k_star":1e6,
            "tail_exp_cap": 25.0, "y_span_decades": 12.0,
            "L":1e-4, "k_min":"", "k_max":"", "num_k":2000
        }
    ])
    with pd.ExcelWriter(path) as xw:
        df.to_excel(xw, sheet_name="params", index=False)
    print(f"[TEMPLATE] Wrote example template to: {path}")

# ---------- log-safe spectrum ----------
def master_spectrum(k, eps, m, gamma_v, alpha_v, k_eta,
                    gamma_p=0.0, alpha_p=2.0, k_star=0.0):
    """
    log E = (2/3)log ε - m log k - [γ_v (k/kη)^α_v + γ_p (k/k★)^α_p]
    """
    Xv = gamma_v * (k / k_eta)**alpha_v if (gamma_v and k_eta > 0 and alpha_v > 0) else 0.0
    Xp = gamma_p * (k / k_star)**alpha_p if (gamma_p and k_star > 0 and alpha_p > 0) else 0.0
    logE = (2.0/3.0)*np.log(eps) - m*np.log(k) - (Xv + Xp)
    logE = np.maximum(logE, np.log(np.finfo(float).tiny))  # avoid -inf
    return np.exp(logE)

# ---------- knee helpers ----------
def knees_amplitude(k_eta, gv, av, k_star, gp, ap, factor=0.05, decades=None):
    """
    Amplitude-based knees: choose X* so exp(-X*) = factor  (or X* = decades*ln 10).
    Returns (k_phys_amp, k_visc_amp); np.nan if a knee is not applicable.
    """
    if decades is not None:
        X = decades * np.log(10.0)
    else:
        if factor is None or factor <= 0 or factor >= 1:
            factor = 0.05
        X = -np.log(factor)

    k_phys = k_star * (X/gp)**(1.0/ap) if (gp and ap>0 and k_star>0) else np.nan
    k_visc = k_eta  * (X/gv)**(1.0/av) if (gv and av>0 and k_eta >0) else np.nan
    return k_phys, k_visc

def knees_slope(k_eta, gv, av, k_star, gp, ap, delta_s=3.0):
    """
    Slope-matched knees: choose X so α*X = Δs (same bend strength for both knees).
    Returns (k_phys_slp, k_visc_slp); np.nan if a knee is not applicable.
    """
    Xp = (delta_s / ap) if (ap and ap>0) else np.nan
    Xv = (delta_s / av) if (av and av>0) else np.nan

    k_phys = k_star * (Xp/gp)**(1.0/ap) if (gp and ap>0 and k_star>0 and np.isfinite(Xp)) else np.nan
    k_visc = k_eta  * (Xv/gv)**(1.0/av) if (gv and av>0 and k_eta >0 and np.isfinite(Xv)) else np.nan
    return k_phys, k_visc

def _inside_window(x, kmin, kmax):
    return (x is not None) and np.isfinite(x) and (kmin < x < kmax)

# ---------- main ----------
def main():
    if not os.path.exists(EXCEL_PATH) and CREATE_TEMPLATE_IF_MISSING:
        write_template_xlsx(EXCEL_PATH)
    if not os.path.exists(EXCEL_PATH):
        raise FileNotFoundError(f"Excel file not found: {EXCEL_PATH}")

    xl = pd.ExcelFile(EXCEL_PATH)
    sheet = SHEET_NAME or xl.sheet_names[0]
    df = xl.parse(sheet)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    combined_png = os.path.join(OUTPUT_DIR, "master_spectrum_combined.png")
    summary_csv  = os.path.join(OUTPUT_DIR, "master_spectrum_summary.csv")
    plt.figure()
    any_plotted = False
    summary_rows = []
    comb_ymins, comb_ymaxs = [], []

    # Legend label guards (avoid duplicate legend entries on combined plot)
    label_flags = {"phys_amp": False, "visc_amp": False, "phys_slp": False, "visc_slp": False}

    for i, row in df.iterrows():
        name   = str(get(row, "name", f"curve_{i+1}", cast=str))

        # Required
        eps    = fpos(get(row, "epsilon", None), None, 1e-30, 1e30)
        m      = fpos(get(row, "m", None), None, -10, 10)
        if None in (eps, m):
            print(f"[SKIP] Row {i+1} ({name}) missing epsilon or m.")
            continue

        # k_eta (direct or from nu, eps)
        k_eta  = fpos(get(row, "k_eta", None), None, 1e-12, 1e18)
        nu     = fpos(get(row, "nu", None), None, 1e-12, 1.0)
        if k_eta is None and (nu is not None and eps is not None):
            eta = (nu**3 / eps)**0.25
            k_eta = 1.0 / eta
        if k_eta is None:
            print(f"[SKIP] Row {i+1} ({name}) missing k_eta and (nu,epsilon) to compute it.")
            continue

        # Damping params
        gv     = fpos(get(row, "gamma_v", 1.0), 1.0, 0, 1e6)
        av     = fpos(get(row, "alpha_v", 4/3), 4/3, 0, 10)

        # Physics knee (optional)
        gp     = fpos(get(row, "gamma_p", 0.0), 0.0, 0, 1e6)
        ap     = fpos(get(row, "alpha_p", 2.0), 2.0, 0, 10)
        ks     = fpos(get(row, "k_star", 0.0), 0.0, 0, 1e18)

        # Optional (compat)
        L      = fpos(get(row, "L", 1.0), 1.0, 1e-12, 1e6)

        # Per-row overrides
        tail_cap       = fpos(get(row, "tail_exp_cap", TAIL_EXP_CAP), TAIL_EXP_CAP, 1e-6, 1e6)
        y_span_decades = fpos(get(row, "y_span_decades", Y_SPAN_DECADES), Y_SPAN_DECADES, 1.0, 60.0)

        # --- k-range (k_eta-relative, viscous-tail exponent cap) ---
        if np.isfinite(k_eta) and k_eta > 0:
            k_min_default = max(1e-2 * k_eta, HARD_KMIN_FLOOR)  # start ~2 decades below k_eta
            if gv > 0 and av > 0:
                k_max_cap = k_eta * (tail_cap / gv)**(1.0 / av)
            else:
                k_max_cap = HARD_KMAX_CEIL
            k_max_default = min(k_max_cap, HARD_KMAX_CEIL)
        else:
            k_min_default = HARD_KMIN_FLOOR
            k_max_default = 1e8

        # Respect user-provided bounds but enforce cap/order
        k_min = fpos(get(row, "k_min", k_min_default), k_min_default, 1e-12, 1e18)
        k_max = fpos(get(row, "k_max", k_max_default), k_max_default, 1e-12, 1e18)
        if not (k_max > k_min):
            k_min, k_max = k_min_default, k_max_default

        if gv > 0 and av > 0 and k_eta and np.isfinite(k_eta):
            kmax_limit = k_eta * (tail_cap / gv)**(1.0 / av)
            if k_max > kmax_limit:
                print(f"[INFO] Row {i+1} ({name}) clamping k_max from {k_max:.3g} to {kmax_limit:.3g} to keep Xv ≤ {tail_cap}")
                k_max = kmax_limit

        # k grid
        raw_n = get(row, "num_k", 2000, cast=int)
        try: num_k = int(raw_n)
        except Exception: num_k = 2000
        if not np.isfinite(num_k): num_k = 2000
        num_k = max(100, min(num_k, 200_000))

        lo = np.log10(max(k_min, 1e-12))
        hi = np.log10(max(k_max, k_min * 10.0))
        if not (np.isfinite(lo) and np.isfinite(hi) and hi > lo):
            print(f"[SKIP] Row {i+1} ({name}) invalid log-range.")
            continue
        k = np.logspace(lo, hi, num_k)

        # Spectrum
        E = master_spectrum(k, eps, m, gv, av, k_eta, gp, ap, ks)

        # ===== Masking for log–log plotting =====
        valid = np.isfinite(k) & np.isfinite(E) & (k > 0) & (E > E_FLOOR)
        if valid.sum() < 2:
            print(f"[SKIP] Row {i+1} ({name}) has too few positive points to plot on log axes.")
            continue
        k_plot = k[valid]
        E_plot = E[valid]

        # ===== Per-curve y-limits: show only the top y_span_decades decades (per-curve files) =====
        Emax = float(np.nanmax(E_plot))
        ymin = max(Emax / (10.0**y_span_decades), E_FLOOR)
        ymax = Emax

        # --- Two-knee markers from both methods ---
        k_phys_amp = k_visc_amp = np.nan
        k_phys_slp = k_visc_slp = np.nan

        if SHOW_KNEES_AMPLITUDE:
            k_phys_amp, k_visc_amp = knees_amplitude(
                k_eta, gv, av, ks, gp, ap,
                factor=KNEE_FACTOR, decades=KNEE_DECADES
            )
        if SHOW_KNEES_SLOPE:
            k_phys_slp, k_visc_slp = knees_slope(
                k_eta, gv, av, ks, gp, ap,
                delta_s=DELTA_SLOPE
            )

        _kmin, _kmax = float(k_plot.min()), float(k_plot.max())
        phys_amp_in = _inside_window(k_phys_amp, _kmin, _kmax)
        visc_amp_in = _inside_window(k_visc_amp, _kmin, _kmax)
        phys_slp_in = _inside_window(k_phys_slp, _kmin, _kmax)
        visc_slp_in = _inside_window(k_visc_slp, _kmin, _kmax)

        # ===== Combined plot =====
        plt.loglog(k_plot, E_plot, label=f"{name} (m={m:.3g})")
        any_plotted = True
        comb_ymins.append(ymin); comb_ymaxs.append(ymax)

        # Amplitude-based knees (dashed)
        if SHOW_KNEES_AMPLITUDE:
            if phys_amp_in:
                lbl = "physics knee (amp)" if not label_flags["phys_amp"] else "_nolegend_"
                plt.axvline(k_phys_amp, ls="--", lw=1.2, alpha=0.8, color="gray", label=lbl)
                label_flags["phys_amp"] = True
            if visc_amp_in:
                lbl = "viscous knee (amp)" if not label_flags["visc_amp"] else "_nolegend_"
                plt.axvline(k_visc_amp, ls="--", lw=1.2, alpha=0.8, color="gray", label=lbl)
                label_flags["visc_amp"] = True

        # Slope-matched knees (dotted)
        if SHOW_KNEES_SLOPE:
            if phys_slp_in:
                lbl = "physics knee (slope)" if not label_flags["phys_slp"] else "_nolegend_"
                plt.axvline(k_phys_slp, ls=":", lw=1.2, alpha=0.8, color="gray", label=lbl)
                label_flags["phys_slp"] = True
            if visc_slp_in:
                lbl = "viscous knee (slope)" if not label_flags["visc_slp"] else "_nolegend_"
                plt.axvline(k_visc_slp, ls=":", lw=1.2, alpha=0.8, color="gray", label=lbl)
                label_flags["visc_slp"] = True

        # ===== Per-curve figure =====
        fig2 = plt.figure()
        ax2 = fig2.add_subplot(111)
        ax2.loglog(k_plot, E_plot)
        ax2.set_xlabel("k [1/m]")
        ax2.set_ylabel("E(k) [m^3/s^2]")
        ax2.set_title(name)
        ax2.set_xlim(k_plot.min(), k_plot.max())
        ax2.set_ylim(ymin, ymax)
        ax2.grid(True, which="both", linestyle=":", linewidth=0.5)

        # Amplitude-based knees (dashed)
        if SHOW_KNEES_AMPLITUDE:
            if phys_amp_in:
                ax2.axvline(k_phys_amp, ls="--", lw=1.2, alpha=0.9, color="gray")
                ax2.text(k_phys_amp, ymax*0.80, r"$k_{\star}$ (amp)", rotation=90,
                         va="center", ha="left", fontsize=9, color="gray")
            if visc_amp_in:
                ax2.axvline(k_visc_amp, ls="--", lw=1.2, alpha=0.9, color="gray")
                ax2.text(k_visc_amp, ymax*0.62, r"$k_{\eta}$ (amp)", rotation=90,
                         va="center", ha="left", fontsize=9, color="gray")

        # Slope-matched knees (dotted)
        if SHOW_KNEES_SLOPE:
            if phys_slp_in:
                ax2.axvline(k_phys_slp, ls=":", lw=1.2, alpha=0.9, color="gray")
                ax2.text(k_phys_slp, ymax*0.74, r"$k_{\star}$ (slope)", rotation=90,
                         va="center", ha="left", fontsize=9, color="gray")
            if visc_slp_in:
                ax2.axvline(k_visc_slp, ls=":", lw=1.2, alpha=0.9, color="gray")
                ax2.text(k_visc_slp, ymax*0.56, r"$k_{\eta}$ (slope)", rotation=90,
                         va="center", ha="left", fontsize=9, color="gray")

        fig2.tight_layout()
        out_png = os.path.join(OUTPUT_DIR, f"master_spectrum_{name.replace(' ','_')}.png")
        fig2.savefig(out_png, dpi=180, bbox_inches="tight")
        plt.close(fig2)

        # Diagnostics
        if DEBUG_DIAGNOSTICS:
            Xv_max = gv * (k_plot.max()/k_eta)**av if (gv and av>0 and k_eta>0) else 0.0
            print(f"\n=== DIAG {i+1}: {name} ===")
            print(f"eps={eps}, m={m}, nu={nu}, k_eta={k_eta}")
            print(f"gv,av={gv},{av}   gp,ap,ks={gp},{ap},{ks}")
            print(f"k range: {float(k_plot.min())} → {float(k_plot.max())}  (1/m)")
            print(f"tail_cap={tail_cap}  -> k_max_cap≈ {k_eta * (tail_cap/max(gv,1e-12))**(1.0/av):.3g}")
            print(f"Tail exponent at k_max: Xv={float(Xv_max):.3g}")
            probes = [k_plot.min(), k_eta/2, k_eta, (ks if gp>0 and ks>0 else k_eta*1.5), k_plot.max()]
            def E_of(x): return master_spectrum(np.array([x]), eps, m, gv, av, k_eta, gp, ap, ks)[0]
            vals = [E_of(x) for x in probes]
            print("log10 E at probes:", [None if v<=0 else float(np.log10(v)) for v in vals])
            print("y-span decades (per-curve):", y_span_decades)
            def _fmt(x): 
                return f"{float(x):.3g}" if (x is not None and np.isfinite(x)) else "nan"
            print("knees (amp):   k_phys≈", _fmt(k_phys_amp), "  k_visc≈", _fmt(k_visc_amp))
            print("knees (slope): k_phys≈", _fmt(k_phys_slp), "  k_visc≈", _fmt(k_visc_slp))
            print("=== END DIAG ===")

        # Peak info
        kE = k_plot * E_plot
        if np.isfinite(kE).any():
            i_peak = int(np.nanargmax(kE))
            k_peak = float(k_plot[i_peak])
            ell_m  = float(pi / k_peak) if k_peak > 0 else np.nan
        else:
            k_peak, ell_m = np.nan, np.nan

        summary_rows.append({
            "name": name,
            "epsilon": eps, "m": m,
            "nu": nu, "k_eta": k_eta,
            "gamma_v": gv, "alpha_v": av,
            "gamma_p": gp, "alpha_p": ap, "k_star": ks,
            "L": L, "k_min": float(k_plot.min()), "k_max": float(k_plot.max()), "num_k": len(k_plot),
            "k_peak": k_peak, "mixing_length_ell_m": ell_m,
            "tail_exp_cap": tail_cap, "y_span_decades": y_span_decades
        })

    # Save combined plot (cropped y-range so curves "hit" the axis)
    if any_plotted:
        global_Emax = max(comb_ymaxs)
        y0 = max(global_Emax / (10.0**Y_SPAN_DECADES), E_FLOOR)
        y1 = global_Emax
        ax = plt.gca()
        ax.set_ylim(y0, y1)
        plt.xlabel("k [1/m]"); plt.ylabel("$E(k) [m^3/s^2]$")
        plt.legend(); plt.tight_layout()
        plt.savefig(combined_png, dpi=180, bbox_inches="tight")
        print(f"[OK] Combined plot -> {combined_png}")
    else:
        print("[WARN] No curves plotted; check values or headers.")

    # Save summary CSV
    if summary_rows:
        pd.DataFrame(summary_rows).to_csv(summary_csv, index=False)
        print(f"[OK] Summary CSV -> {summary_csv}")

if __name__ == "__main__":
    main()

