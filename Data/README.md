# Data/ — Datasets & ground truth

## Ground truth (used by the analysis notebooks)

| File | Rows | Purpose |
|------|------|---------|
| `train_data_Inv_Step.pkl` | 95 | TRAIN ground truth (`Reference`, `Outcome ∈ {Reversed, Affirmed}`). |
| `test_data_Inv_Step.pkl` | 879 | TEST ground truth (held out). |

`Outcome` maps to the label as `Reversed → Yes` (inventive step present), `Affirmed → No`.

## Other corpora / intermediates

- `Inv_Step_Test.pkl`, `Inv_Step_Filtered_Test_Data.pkl`, `Inv_Step_Sampled_Valid.pkl`,
  `train_good_reasons.pkl` — intermediate corpora from data prep (kept for provenance;
  not the canonical GT above).
- `case_annotation.xlsx` — manual case annotations.
- `CPC_SCHEMA/`, `CPCSchemeXML202601.zip` — CPC classification schema.
- `data_prep.ipynb` — builds the corpora/GT from raw decisions.
- Case folders (`TRAIN/`, `TEST/`, `VALIDATION/`, `COMVIK/`, `Manual_Cases/`, …) hold the
  per-case source documents (`appeal.txt`, `claims.txt`, `CPA.txt`, …) that the runner feeds
  the LLM. These are **git-ignored** (large).

## SFT datasets (fine-tuning)

Built from GT-correct Qwen logs; **git-ignored** (regenerable, large):

| Builder | Output | Format |
|---------|--------|--------|
| `build_sft_dataset.py` | `sft_train.jsonl` / `sft_val.jsonl` | per-factor Q→A turns from `train_both_default` (ADM-style). |
| `build_sft_baseline_dataset.py` | `sft_baseline_train.jsonl` / `sft_baseline_val.jsonl` | single-turn full-case prompts from `baseline_default`. |

Regenerate, e.g.: `python Data/build_sft_dataset.py`. Splits are made at the **case** level to
avoid train/val leakage.
