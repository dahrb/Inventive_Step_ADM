# Figs/ — Generated figures

All code that produces figures writes here. The ADM visualisation methods
(`ADM_Construction.visualiseNetwork` / `visualiseMinimalist` / `visualiseSubADMs`) route bare
filenames into this directory via the `FIGS_DIR` constant; override with the `FIGS_DIR`
environment variable.

Figure files (`*.png`, `*.svg`) are **git-ignored** — regenerate them from the ADM code and the
`Analysis/` notebooks. Only this README is tracked.
