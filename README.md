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

This repository accompanies the manuscript:

> **Kuan et al., “A Unified Spectrum for Turbulence in Microfluidic Flow,” 202X.**

The version included here corresponds to the **no log-periodic modulation** formulation used to generate all spectra reported in the manuscript.

---

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

