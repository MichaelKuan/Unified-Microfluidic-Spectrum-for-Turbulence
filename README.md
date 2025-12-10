# Unified Microfluidic Master Spectrum for Turbulence
![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)
![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)
![Status](https://img.shields.io/badge/status-stable-brightgreen.svg)


This repository contains the Python implementation of the **Unified Microfluidic Master Spectrum**, a general turbulence-spectrum model that extends Kolmogorov–Pao theory to microfluidic flows. The model incorporates:

- adjustable inertial-range slopes,
- viscous dissipation cutoffs,
- physics-specific cutoffs (elastic, interfacial, electrokinetic, etc.),
- automated wavenumber-grid construction,
- optional knee detection (amplitude- or slope-based),
- batch parameter input from Excel.

## Output Summary

This repository accompanies the manuscript:

> **Kuan et al., “A Unified Spectrum for Turbulence in Microfluidic Flow,” 202X.**

The version included here corresponds to the **no log-periodic modulation** formulation used to generate all spectra reported in the manuscript.

---

## 1. Installation

Download or clone the repository:

```bash
git clone https://github.com/MichaelKuan/Unified-Microfluidic-Spectrum-for-Turbulence
cd Unified-Microfluidic-Spectrum-for-Turbulence 
```
Install required Python packages:
```bash
pip install numpy pandas matplotlib openpyxl
```

You can then run the model with:
```bash
python master_spectrum_nomod.py
```

## 2. Usage Instruction

### 2.1 Excel Input Specification

The model reads parameters from an Excel file (e.g. `master_spectrum_nomod_test_v1.xlsx`).  
Each **row** defines one spectrum. Column names are case-insensitive.

#### Required columns
| Column | Meaning |
|--------|---------|
| `name` | Label used for output figures and summary table |
| `epsilon` | Dissipation rate \( \varepsilon \) |
| `m` | Inertial–range slope |

#### Viscous cutoff (choose one)
| Column | Meaning |
|--------|---------|
| `nu` | Kinematic viscosity (the script computes \(k_\eta\)) |
| `k_eta` | Kolmogorov wavenumber (used directly) |

Viscous damping parameters (optional):
| Column | Meaning |
|--------|---------|
| `gamma_v`, `alpha_v` | Viscous cutoff prefactor and exponent |

#### Physics-specific cutoff (optional)
If `gamma_p` or `k_star` are blank, this term is ignored.

| Column | Meaning |
|--------|---------|
| `gamma_p`, `alpha_p` | Physics-specific cutoff parameters |
| `k_star` | Physics cutoff wavenumber (elastic, interfacial, electrokinetic, etc.) |

#### Plotting controls (optional)
| Column | Meaning |
|--------|---------|
| `k_min`, `k_max` | Force custom wavenumber range |
| `num_k` | Number of points in log-spaced k-grid |
| `tail_exp_cap` | Controls automatic \(k_{\max}\) estimate |
| `y_span_decades` | Number of orders of magnitude shown vertically |

If omitted, the script selects robust defaults based on \(k_\eta\), dissipation rate, and cutoff parameters.

---

### 2.2 Adjusting the X-axis (k-range)

The script automatically chooses a physically meaningful range:

- \(k_{\min}\) ≈ \(10^{-2} k_\eta\)  
- \(k_{\max}\) based on the viscous tail exponent cap

To override this, specify `k_min` and/or `k_max` in the Excel file.

---

### 2.3 Adjusting the Y-axis (vertical range)

The setting `y_span_decades` controls how many logarithmic decades of \(E(k)\) are displayed.  
For example:

- `6` → show top 6 decades  
- `12` → wide view  
- `20+` → full tail

If omitted, a reasonable default is used.

---

### 2.4 Knee Detection (optional)

The script supports two types of knee detection:

- **Amplitude-based:** identifies where \(E(k)\) drops by a chosen factor  
- **Slope-based:** identifies where the spectrum steepens by a chosen \(\Delta s\)

Enable them in the Python file:

```python
SHOW_KNEES_AMPLITUDE = True
SHOW_KNEES_SLOPE = False
```

## 3. Reproduce Figure from Manuscript
## 4. Trouble-shooting
## 5. Citation, License and Contact Information

## 1. Repository Structure

```text
unified-microfluidic-spectrum/
├── master_spectrum_nomod.py            # Main script: spectrum evaluation and plotting
├── examples/
│   └── master_spectrum_nomod_test.xlsx # Example Excel parameter file
├── figures/                            # Auto-generated plots (optional)
├── outputs/
│   └── master_spectrum_summary.csv     # Auto-generated summary table
├── requirements.txt
├── README.md
└── LICENSE

