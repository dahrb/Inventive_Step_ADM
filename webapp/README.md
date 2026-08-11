# webapp/ — Streamlit explorer (optional)

A self-contained Streamlit app for exploring cases and ADM runs. Independent of the main
analysis pipeline; status: exploratory.

| File | Role |
|------|------|
| `app.py` | Entry point / landing page. |
| `pages/1_Case_Explorer.py` | Per-case document + ADM-trace explorer. |
| `pages/2_Dashboard.py` | Results dashboard. |
| `adm_graph.py`, `adm_viz.py`, `adm_helpers.py`, `data_loader.py` | Rendering + data-loading helpers. |
| `requirements.txt` | App dependencies (kept separate from the root env). |
| `run.sh` | Launch helper. |

## Run

```bash
cd webapp
uv run --with-requirements requirements.txt streamlit run app.py
# or: ./run.sh
```
