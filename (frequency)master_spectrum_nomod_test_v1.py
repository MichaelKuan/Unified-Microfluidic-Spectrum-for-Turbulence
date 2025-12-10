#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Master spectrum plotter (NO log-periodic modulation)

Adds frequency-domain option to match Phys. Rev. E Fig. 2:
- DOMAIN = "f"  -> plots E(f) vs f using Taylor's hypothesis:
                   k = 2*pi*f/U,  E(f) = (1/U)*E(k=2*pi*f/U)
- DOMAIN = "k"  -> original E(k) vs k

Optional per-row Excel column:
  U  (mean advection speed in m/s; default 2.9e-3 m/s)

Other features retained:
- Tail exponent cap on viscous term
- Y-axis cropping by decades
- (Optional) knee markers
"""

# ===== CONFIG =====
EXCEL_PATH  = "master_spectrum_nomod_test copy.xlsx"
SHEET_NAME  = "TestPage"     # or None for first sheet
OUTPUT_DIR  = "."
CREATE_TEMPLATE_IF_MISSING = False
DEBUG_DIAGNOSTICS = True

# Domain switch: "f" for frequency plots like Phys. Rev. E Fig. 2; "k" for wavenumber
DOMAIN = "f"        # "f" or "k"
U_DEFAULT = 2.9e-3  # m/s (≈ 2.9 mm/s at x4 in the paper) original:2.9e-3

# New knobs (global defaults; can be overridden per-row in Excel)
TAIL_EXP_CAP     = 25.0   # cap viscous exponent Xv at k_max (typical 20–30)
Y_SPAN_DECADES   = 12.0   # show top N decades of E on combined plot
HARD_KMAX_CEIL   = 1e9    # absolute safety ceiling on k_max
HARD_KMIN_FLOOR  = 1e2    # don't plot below ~100 1/m by default
E_FLOOR          = 1e-300 # numerical floor for log-plotting
# ==================

# === Knee markers (optional) ===
SHOW_KNEES_AMPLITUDE = False
SHOW_KNEES_SLOPE     = False
KNEE_FACTOR  = 0.367879441     # amplitude-based (or set KNEE_DECADES)
KNEE_DECADES = None
DELTA_SLOPE = 3.0

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from math import pi

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
            "U": 2.9e-3,
            "L":1e-4, "k_min":"", "k_max":"", "num_k":2000
        }
    ])
    with pd.ExcelWriter(path) as xw:
        df.to_excel(xw, sheet_name="params", index=False)
    print(f"[TEMPLATE] Wrote example template to: {path}")

# ---------- base spectrum in k ----------
def master_spectrum_k(k, eps, m, gamma_v, alpha_v, k_eta,
                      gamma_p=0.0, alpha_p=2.0, k_star=0.0):
    """
    E_k(k) with:
    log E = (2/3)log ε - m log k - [γ_v (k/kη)^α_v + γ_p (k/k★)^α_p]
    """
    Xv = gamma_v * (k / k_eta)**alpha_v if (gamma_v and k_eta > 0 and alpha_v > 0) else 0.0
    Xp = gamma_p * (k / k_star)**alpha_p if (gamma_p and k_star > 0 and alpha_p > 0) else 0.0
    logE = (2.0/3.0)*np.log(eps) - m*np.log(k) - (Xv + Xp)
    logE = np.maximum(logE, np.log(np.finfo(float).tiny))  # avoid -inf
    return np.exp(logE)

# ---------- knees ----------
def knees_amplitude(k_eta, gv, av, k_star, gp, ap, factor=0.05, decades=None):
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

    # Legend label guards
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

        # Optional
        L      = fpos(get(row, "L", 1.0), 1.0, 1e-12, 1e6)

        # Per-row overrides
        tail_cap       = fpos(get(row, "tail_exp_cap", TAIL_EXP_CAP), TAIL_EXP_CAP, 1e-6, 1e6)
        y_span_decades = fpos(get(row, "y_span_decades", Y_SPAN_DECADES), Y_SPAN_DECADES, 1.0, 60.0)

        # Mean advection speed (for frequency domain)
        U_row = fpos(get(row, "U", None), None, 1e-6, 10.0)  # accept 1 µm/s to 10 m/s
        U = U_row if U_row is not None else U_DEFAULT

        # --- k-range (then possibly map to f-range) ---
        if np.isfinite(k_eta) and k_eta > 0:
            k_min_default = max(1e-2 * k_eta, HARD_KMIN_FLOOR)  # ~2 decades below k_eta
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

        # Build grid in chosen domain
        raw_n = get(row, "num_k", 2000, cast=int)
        try: num_k = int(raw_n)
        except Exception: num_k = 2000
        if not np.isfinite(num_k): num_k = 2000
        num_k = max(100, min(num_k, 200_000))

        if DOMAIN.lower() == "f":
            # frequency grid derived from k-grid:
            lo_k = np.log10(max(k_min, 1e-12))
            hi_k = np.log10(max(k_max, k_min * 10.0))
            if not (np.isfinite(lo_k) and np.isfinite(hi_k) and hi_k > lo_k):
                print(f"[SKIP] Row {i+1} ({name}) invalid log-range.")
                continue
            k_grid = np.logspace(lo_k, hi_k, num_k)
            f_grid = (U / (2.0 * np.pi)) * k_grid  # f = U*k / (2π)

            # Evaluate E_f(f) = (1/U) * E_k(k=2π f / U)
            k_from_f = (2.0 * np.pi * f_grid) / U
            E_k_vals = master_spectrum_k(k_from_f, eps, m, gv, av, k_eta, gp, ap, ks)
            E_plot = (1.0 / U) * E_k_vals

            x_plot = f_grid
            x_label = "f [Hz]"
            y_label = "E(f) [units of (m^2/s)/Hz]"
            title_sfx = f"{name}  (freq domain; U={U:g} m/s)"
            # Knee markers map: k_knee -> f_knee = (U/2π) * k_knee
            knee_map = lambda k_knee: (U/(2.0*np.pi))*k_knee if np.isfinite(k_knee) else np.nan

        else:
            # original k-domain
            lo = np.log10(max(k_min, 1e-12))
            hi = np.log10(max(k_max, k_min * 10.0))
            if not (np.isfinite(lo) and np.isfinite(hi) and hi > lo):
                print(f"[SKIP] Row {i+1} ({name}) invalid log-range.")
                continue
            x_plot = np.logspace(lo, hi, num_k)
            E_plot = master_spectrum_k(x_plot, eps, m, gv, av, k_eta, gp, ap, ks)
            x_label = "k [1/m]"
            y_label = "E(k) [m^3/s^2]"
            title_sfx = f"{name}  (wavenumber domain)"
            knee_map = lambda k_knee: k_knee

        # ===== Masking for log–log plotting =====
        valid = np.isfinite(x_plot) & np.isfinite(E_plot) & (x_plot > 0) & (E_plot > E_FLOOR)
        if valid.sum() < 2:
            print(f"[SKIP] Row {i+1} ({name}) has too few positive points to plot on log axes.")
            continue
        x_plot = x_plot[valid]
        E_plot = E_plot[valid]

        # ===== Per-curve y-limits: show only the top y_span_decades decades =====
        Emax = float(np.nanmax(E_plot))
        ymin = max(Emax / (10.0**y_span_decades), E_FLOOR)
        ymax = Emax

        # --- Knee markers in chosen domain ---
        k_phys_amp = k_visc_amp = np.nan
        k_phys_slp = k_visc_slp = np.nan
        if SHOW_KNEES_AMPLITUDE:
            k_phys_amp, k_visc_amp = knees_amplitude(k_eta, gv, av, ks, gp, ap,
                                                     factor=KNEE_FACTOR, decades=KNEE_DECADES)
        if SHOW_KNEES_SLOPE:
            k_phys_slp, k_visc_slp = knees_slope(k_eta, gv, av, ks, gp, ap,
                                                 delta_s=DELTA_SLOPE)
        # map knees to active x-axis
        xa_phys_amp = knee_map(k_phys_amp)
        xa_visc_amp = knee_map(k_visc_amp)
        xa_phys_slp = knee_map(k_phys_slp)
        xa_visc_slp = knee_map(k_visc_slp)

        _xmin, _xmax = float(x_plot.min()), float(x_plot.max())
        def _in(xa): return (xa is not None) and np.isfinite(xa) and (_xmin < xa < _xmax)
        phys_amp_in = _in(xa_phys_amp)
        visc_amp_in = _in(xa_visc_amp)
        phys_slp_in = _in(xa_phys_slp)
        visc_slp_in = _in(xa_visc_slp)

        # ===== Combined plot =====
        plt.loglog(x_plot, E_plot, label=f"{name} (m={m:.3g})")
        any_plotted = True
        comb_ymins.append(ymin); comb_ymaxs.append(ymax)

        if SHOW_KNEES_AMPLITUDE:
            if phys_amp_in:
                lbl = "physics knee (amp)" if not label_flags["phys_amp"] else "_nolegend_"
                plt.axvline(xa_phys_amp, ls="--", lw=1.2, alpha=0.8, color="gray", label=lbl)
                label_flags["phys_amp"] = True
            if visc_amp_in:
                lbl = "viscous knee (amp)" if not label_flags["visc_amp"] else "_nolegend_"
                plt.axvline(xa_visc_amp, ls="--", lw=1.2, alpha=0.8, color="gray", label=lbl)
                label_flags["visc_amp"] = True

        if SHOW_KNEES_SLOPE:
            if phys_slp_in:
                lbl = "physics knee (slope)" if not label_flags["phys_slp"] else "_nolegend_"
                plt.axvline(xa_phys_slp, ls=":", lw=1.2, alpha=0.8, color="gray", label=lbl)
                label_flags["phys_slp"] = True
            if visc_slp_in:
                lbl = "viscous knee (slope)" if not label_flags["visc_slp"] else "_nolegend_"
                plt.axvline(xa_visc_slp, ls=":", lw=1.2, alpha=0.8, color="gray", label=lbl)
                label_flags["visc_slp"] = True

        # ===== Per-curve figure =====
        fig2 = plt.figure()
        ax2 = fig2.add_subplot(111)
        ax2.loglog(x_plot, E_plot)
        ax2.set_xlabel(x_label)
        ax2.set_ylabel(y_label)
        ax2.set_title(title_sfx)
        ax2.set_xlim(x_plot.min(), x_plot.max())
        ax2.set_ylim(ymin, ymax)
        ax2.grid(True, which="both", linestyle=":", linewidth=0.5)

        if SHOW_KNEES_AMPLITUDE:
            if phys_amp_in:
                ax2.axvline(xa_phys_amp, ls="--", lw=1.2, alpha=0.9, color="gray")
                ax2.text(xa_phys_amp, ymax*0.80, r"$k_{\star}$ (amp)", rotation=90,
                         va="center", ha="left", fontsize=9, color="gray")
            if visc_amp_in:
                ax2.axvline(xa_visc_amp, ls="--", lw=1.2, alpha=0.9, color="gray")
                ax2.text(xa_visc_amp, ymax*0.62, r"$k_{\eta}$ (amp)", rotation=90,
                         va="center", ha="left", fontsize=9, color="gray")

        if SHOW_KNEES_SLOPE:
            if phys_slp_in:
                ax2.axvline(xa_phys_slp, ls=":", lw=1.2, alpha=0.9, color="gray")
                ax2.text(xa_phys_slp, ymax*0.74, r"$k_{\star}$ (slope)", rotation=90,
                         va="center", ha="left", fontsize=9, color="gray")
            if visc_slp_in:
                ax2.axvline(xa_visc_slp, ls=":", lw=1.2, alpha=0.9, color="gray")
                ax2.text(xa_visc_slp, ymax*0.56, r"$k_{\eta}$ (slope)", rotation=90,
                         va="center", ha="left", fontsize=9, color="gray")

        fig2.tight_layout()
        out_png = os.path.join(OUTPUT_DIR, f"master_spectrum_{name.replace(' ','_')}.png")
        fig2.savefig(out_png, dpi=180, bbox_inches="tight")
        plt.close(fig2)

        # Diagnostics
        if DEBUG_DIAGNOSTICS:
            if DOMAIN.lower() == "k":
                Xv_max = gv * (x_plot.max()/k_eta)**av if (gv and av>0 and k_eta>0) else 0.0
            else:
                # report viscous tail exponent at the equivalent k_max
                k_equiv_max = (2.0*np.pi*x_plot.max())/U
                Xv_max = gv * (k_equiv_max/k_eta)**av if (gv and av>0 and k_eta>0) else 0.0
            print(f"\n=== DIAG {i+1}: {name} ===")
            print(f"eps={eps}, m={m}, nu={nu}, k_eta={k_eta}")
            print(f"gv,av={gv},{av}   gp,ap,ks={gp},{ap},{ks}")
            print(f"DOMAIN={DOMAIN}  U_used={U}")
            if DOMAIN.lower() == "k":
                print(f"k range: {float(x_plot.min())} → {float(x_plot.max())}  (1/m)")
            else:
                print(f"f range: {float(x_plot.min())} → {float(x_plot.max())}  (Hz)")
            print(f"tail_cap={tail_cap}  Tail exponent at top end: Xv≈ {float(Xv_max):.3g}")
            print("=== END DIAG ===")

        # Peak info (still computed in plotted domain)
        xE = x_plot * E_plot
        if np.isfinite(xE).any():
            i_peak = int(np.nanargmax(xE))
            x_peak = float(x_plot[i_peak])
        else:
            x_peak = np.nan

        summary_rows.append({
            "name": name,
            "epsilon": eps, "m": m,
            "nu": nu, "k_eta": k_eta,
            "gamma_v": gv, "alpha_v": av,
            "gamma_p": gp, "alpha_p": ap, "k_star": ks,
            "U_used": U, "domain_used": DOMAIN,
            "L": L,
            "x_min": float(x_plot.min()), "x_max": float(x_plot.max()),
            "num_pts": len(x_plot),
            "x_peak_of_xE": x_peak,
            "tail_exp_cap": tail_cap, "y_span_decades": y_span_decades
        })

    # Save combined plot
    if any_plotted:
        global_Emax = max(comb_ymaxs)
        y0 = max(global_Emax / (10.0**Y_SPAN_DECADES), E_FLOOR)
        y1 = global_Emax
        ax = plt.gca()
        ax.set_ylim(y0, y1)
        ax.set_xlabel("f [Hz]" if DOMAIN.lower()=="f" else "k [1/m]")
        ax.set_ylabel("$E(f) [(m^2/s)/Hz]$" if DOMAIN.lower()=="f" else "E(k) [m^3/s^2]")
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
