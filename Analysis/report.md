# ADM–JURIX Inventive-Step Experiments — Evaluation Report

*Generated 2026-08-11. Scope: experiment methodology, coverage/parity audit, headline
results, methodological weaknesses, and codebase streamlining. The `webapp/` is
intentionally excluded per request.*

---

## 1. Methodology (brief)

The project tests whether an **Abstract Domain Model (ADM)** of the EPO
"inventive step" test can guide LLMs to reproduce the outcomes of EPO Board of Appeal
decisions. Ground truth is the appeal outcome: **`Reversed → Yes` (inventive step present),
`Affirmed → No`**.

- **ADM engine** ([ADM/inventive_step_ADM.py](../ADM/inventive_step_ADM.py), built with
  [ADM/ADM_Construction.py](../ADM/ADM_Construction.py)): a main ADM plus two sub-ADMs
  (Sub-ADM 1 = reliable technical character of a feature; Sub-ADM 2 = objective technical
  problem). 75 nodes/questions in [ADM/questions.json](../ADM/questions.json), with `lenient`
  and `strict` reformulations.
- **Batched hybrid runner** ([ADM/batched_hybrid_system.py](../ADM/batched_hybrid_system.py)):
  walks the ADM, asks the LLM each factor question over a served model (vLLM), and records
  per-turn logs + an `adm_summary.json` and a `FINAL_VERDICT`.
- **Models:** `gpt-oss-120b` (mxfp4), `Llama-3.3-70B-Instruct-FP8`,
  `Qwen3-Next-80B-A3B-Instruct(-FP8)`, plus a **QLoRA-fine-tuned Qwen**.

### Independent variables
| Axis | Values |
|------|--------|
| **Mode** | `tool` (case data only), `train` (case data **+** oracle Decision Reasons/Order), `baseline` (single-shot, no ADM) |
| **ADM config** | `both`, `sub_adm_1`, `sub_adm_2`, `none` |
| **Question set** | `default`, `lenient`, `strict` |
| **`adm_initial`** | precondition questions on/off |
| **Data config (test)** | 1 = appeal only · 2 = claims+CPA · 3 = appeal+claims+CPA |

- **Train set:** 95 decisions (53 Yes / 42 No, majority-class acc 55.8%).
- **Test set:** 879 decisions (448 Yes / 431 No, majority-class acc 51.0%).
- **Temperature:** 0.3 default; each config typically run **3×** (tool) for variance.
- **Metrics:** F1 / macro-F1, accuracy, MCC, precision/recall, with bootstrap 95% CIs and
  paired bootstrap significance (in [Analysis/llm_train_results.ipynb](llm_train_results.ipynb)).

### Fine-tuning arm
QLoRA on Qwen3-Next-80B ([ADM/finetune_qwen.py](../ADM/finetune_qwen.py)). Two SFT datasets
are built from GT-correct Qwen train-mode logs:
- **ADM fine-tune** — per-factor Q→A turns from `train_both_default`
  ([Data/build_sft_dataset.py](../Data/build_sft_dataset.py)) → adapter `qwen_lora_adm` → merged `qwen_adm_merged`.
- **Baseline/prompt fine-tune** — single-turn full-case prompts from `baseline_default`
  ([Data/build_sft_baseline_dataset.py](../Data/build_sft_baseline_dataset.py)) → adapter `qwen_lora_baseline` → merged `qwen_baseline_merged`.

---

## 2. Experiments performed

| # | Experiment | Where | Status |
|---|-----------|-------|--------|
| 1 | **Train-set full grid** — 3 models × {tool, oracle} × 4 ADM configs × 3 question sets (+baseline) | `*_TRAIN*.tar.gz`, llm_train_results.ipynb | Grid complete; oracle mode = 1 run (see §3a) |
| 2 | **Test-set data-config sweep** — cfg 1/2/3 × {baseline,tool}, 3 runs | `*_TEST*.tar.gz`, llm_results.ipynb | Complete except holes in §3b |
| 3 | **`adm_initial` ablation** (True vs False) per model | llm_train_results §12, llm_results §5 | Complete |
| 4 | **Qwen N_HISTORY ablation** (1/2/3) | llm_train_results §18 | Complete |
| 5 | **Qwen max_tokens ablation** (500–8000) | §19 | Complete |
| 6 | **Qwen temperature ablation** (0.0–0.3, 3 runs) | §20 | Complete |
| 7 | **Qwen N_HISTORY × trim-level grid** (3×4=12) | §21 | Complete (trim3 = artifact, see §4) |
| 8 | **Qwen history-mode / rolling-summary** (raw vs summarise) | §26 | Complete |
| 9 | **ADM factor / early-termination error analysis** | §25 | Complete |
| 10 | **QLoRA fine-tune Qwen on ADM data → test** ("Qwen-FT") | `QWEN_FINETUNED_TEST_03_05.tar.gz` | Complete |
| 11 | **QLoRA fine-tune Qwen on baseline/prompt data → test** | `qwen_baseline_merged` built | ⚠️ **NOT TESTED** (see §3) |
| 12 | Speed/smoke tests (gpt-oss, llama, qwen) | `run_*_speed_test.sh` | Complete (ancillary) |
| 13 | Diagnostic single-case runs (DIAG_T*) | `run_diagnostic_*.sh` | Ancillary/debug |

---

## 3. Coverage & parity checklist (what has / hasn't been run)

> **Terminology (this resolves the earlier confusion).** Two independent axes share the word
> "train":
> - **Dataset** = which cases: **TRAIN set** (95 cases) or **TEST set** (879 cases).
> - **Mode** = what's in the prompt: **`tool`** (case data only), **`train` = oracle mode**
>   (case data **+** decision reasoning), **`baseline`** (single-shot, no ADM).
>
> So "GPT `tool` mode has 3 runs" and "every `train`(oracle) mode config has only 1 run" are
> both true and not contradictory — they are different *modes*. The counts below are read
> **directly from the `.tar.gz` archives** (authoritative), not from the notebook printouts.

### ⚠️ Correction to the archives-vs-notebook discrepancy
The gaps printed by [llm_train_results.ipynb](llm_train_results.ipynb) ("GPT tool = 5 configs",
"Llama train = 9 configs", "GPT train not found") are **an artifact of stale/partial local
extraction**, *not* missing experiments. Re-counting the archives directly shows **all three
models have the full 12-config grid in both tool and oracle mode**. Fix the notebook to read
the tars (as [llm_results.ipynb](llm_results.ipynb) already does) and those "gaps" disappear.
Grid = 4 ADM configs (`both`/`none`/`sub1`/`sub2`) × 3 question sets (`default`/`lenient`/`strict`) = **12 core configs**, + 1 `baseline`.

### 3a. TRAIN set (95 cases) — verified from archives
`✅` = present · number = **runs per config** · target for full parity = **3 runs**.

| Model | `tool` core (12 cfg) | `tool` baseline | `train`/oracle core (12 cfg) | `train` baseline | `adm_initial=True` (4 cfg, tool) |
|-------|:---:|:---:|:---:|:---:|:---:|
| **GPT**   | ✅ 12/12 × **3** | ✅ 3 | ✅ 12/12 × **1** | ✅ 1 | ✅ 4/4 × 1–3 |
| **Llama** | ✅ 12/12 × **3** | ✅ 3 | ✅ 12/12 × **1** | ✅ 1 | ✅ 4/4 × 1 |
| **Qwen**  | ✅ 12/12 × **3** | ✅ 3 | ✅ 12/12 × **1** | ✅ 1 | ✅ 4/4 × 1 |

**TRAIN-set parity gap:** the only systematic hole is **oracle (`train`) mode = 1 run for every
model** (vs 3 for `tool`). Its F1 (up to 0.98) therefore has **no variance estimate**. Its
value is diagnostic (an upper bound), so 1 run may be acceptable — but if you quote its numbers,
add ≥2 more runs on at least the headline configs (`train_both_default` per model).

### 3b. TEST set (879 cases) — verified from archives
Axes here are **data config 1/2/3** (context provided) × **mode**. Target = 3 runs.

| Variant | Model / weights | `baseline` cfg1 | cfg2 | cfg3 | `tool` cfg1 | cfg2 | cfg3 |
|---------|-----------------|:---:|:---:|:---:|:---:|:---:|:---:|
| **GPT**       | gpt-oss-120b            | ✅ 3 | ✅ 3 | ✅ 3 | ✅ 3 | ✅ 3 | ⚠️ **2** |
| **Llama**     | Llama-3.3-70B           | ❌ | ❌ | ✅ 3 | ✅ 3 | ✅ 3 | ✅ 3 |
| **Qwen**      | Qwen-3-80B (base)       | ✅ 3 | ✅ 3 | ✅ 3 | ✅ 3 | ✅ 3 | ✅ 3 |
| **Qwen-init** | base, `adm_initial=True`| ➖ | ➖ | ➖ | ✅ 3 | ✅ 3 | ✅ 3 |
| **Qwen-FT**   | `qwen_adm_merged` (ADM-data SFT) | ✅ 3 | ✅ 3 | ✅ 3 | ✅ 3 | ✅ 3 | ⚠️ **1** |
| **Qwen-FT-baseline** | `qwen_baseline_merged` (prompt SFT) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

`✅`=complete (3 runs) · `⚠️`=partial (fewer runs) · `➖`=not part of that variant's design · `❌`=**never run**.

### 3c. Outstanding runs, ranked (the actual to-do list)

1. **🔴 `Qwen-FT-baseline` — the entire row is missing.** `qwen_baseline_merged` finished
   merging **13 May 20:37** but has **no test archive**. Without it the headline
   *"ADM-trace SFT vs plain-prompt SFT"* comparison is one-sided. → Serve it
   ([LLM_Models/start_baseline_server.sh](../LLM_Models/start_baseline_server.sh), now fixed)
   and run the full test grid **cfg 1/2/3 × {baseline, tool} × 3 runs = 18 runs**, then add a
   `Qwen-FT-baseline` variant to [llm_results.ipynb](llm_results.ipynb).

2. **🟠 Oracle (`train`) mode = 1 run everywhere (TRAIN set).** 3 models × 12 configs currently
   single-run. Minimum fix: **+2 runs × 3 models on `train_both_default`** (6 runs) for a
   variance estimate on the headline oracle number.

3. **🟠 Llama `baseline` on TEST is missing cfg1 & cfg2** (only cfg3 exists, 3 runs). = **2 cfgs
   × 3 runs = 6 runs**. → Llama server queued (SLURM `10194254`); run the baseline harness at
   cfg1 and cfg2 once it's up. **Note: GPT baseline is NOT missing** — cfg1/cfg2/cfg3 all exist
   (3 runs, 879 cases) in `Outputs/GPT_TEST/baseline_default_cfg{1,2,3}/`; `llm_results.ipynb`
   just doesn't load cfg1/cfg2 (it maps GPT baseline to the single `baseline_default`≡cfg3 dir).
   Fix the loader, no re-run needed.

4. **🟡 Two single-/short-run holes on TEST:** GPT `tool` cfg3 = 2 runs (**+1**); Qwen-FT `tool`
   cfg3 = 1 run (**+2**).

5. **🟡 Fine-tuning is Qwen-only** (no GPT/Llama SFT). Not a missing *run* so much as a scope
   limit — frame FT results as a Qwen case study, or add one more model to generalise.

**Bottom line for parity:** run #1 (18 runs) is compulsory for the finetuning story; #2 (6
runs) is strongly advised before quoting any oracle-mode F1; #3–#4 (≤15 runs) close the
remaining cosmetic asymmetries.

---

## 4. Headline results (with backing data)

### H1 — The ADM tool barely moves the needle over a majority baseline on held-out data
On the 879-case **test set** (majority-class acc ≈ 0.510), best tool-mode runs:

| Variant | cfg | F1 | Acc | MCC |
|--------|-----|----|-----|-----|
| GPT tool | 1 | 0.574 | 0.575 | 0.149 |
| Llama tool | 1 | 0.568 | 0.569 | 0.138 |
| Qwen tool | 2 | 0.538 | 0.542 | 0.081 |

MCC ≈ 0.06–0.15 → **only weakly better than chance**. This is the single most important
sober finding: the ADM-guided tool generalises poorly, and much of its apparent accuracy is
class prior, not discrimination.

### H2 — Oracle guidance ("train mode") is a ceiling, not a result
On the train set, adding the decision reasoning to the prompt lifts F1 enormously — but this
**leaks the answer**:

| Model | Tool F1 | Train F1 | ΔF1 | Train Acc |
|-------|--------|---------|-----|-----------|
| Qwen | 0.375 | **0.906** | +0.532 | 91.1% |
| GPT | 0.303 | 0.635 | +0.332 | 72.0% |

Best `train_both_default` reaches F1 = 0.98 (Qwen). Frame this strictly as an **upper bound**
on "if the ADM asked perfectly, could the LLM read the reasoning correctly."

### H3 — Fine-tuning on ADM traces helps most in **baseline** prompting, less in tool mode
Qwen-FT − Qwen (test), ΔF1:

| cfg | baseline ΔF1 | tool ΔF1 |
|-----|-------------|----------|
| 1 | **+0.195** | +0.068 |
| 2 | **+0.192** | −0.007 |
| 3 | **+0.265** | +0.050 |

E.g. Qwen baseline cfg3 F1 0.457 → Qwen-FT 0.722; recall +0.59. Fine-tuning fixes Qwen's
severe **No-bias** (base Qwen baseline recall 0.13). **The prompt-data-finetuned counterpart
(gap #1) is needed to know whether ADM-trace SFT is doing anything special vs generic SFT.**

### H4 — The tool's errors are overwhelmingly *conservative* (false negatives)
Where train succeeds but tool fails: **GPT 80% / Qwen 82% of the gap are FN** (tool says "No",
truth "Yes"). Root cause localises to **Sub-ADM 2**: `OTPNotObvious` = 42% of primary errors,
`complete_yes` (false positives) 31%, `CandidateOTP` 21%. In 100% of `CandidateOTP` errors,
`Contribution` is present but `ReliableTechnicalEffect` is absent → Q32/Q39 wording is the
prime suspect. Actionable node fixes are enumerated in llm_train_results §25.

### H5 — Ablation takeaways
- **Question set:** `default` wins 4/5 model×mode groups; `lenient` is consistently worst.
- **ADM config:** `sub_adm_1` is the best single config to standardise on (init=False):
  cross-model F1m 0.565, worst-model 0.553.
- **max_tokens:** 2000 optimal (F1 0.624); 500 collapses to F1 0.230 (JSON truncation → No-bias).
- **History:** more history does **not** help (hist1 55.8% ≥ hist2 49.1%); rolling summary hurts.
- **`trim3` "improvement" is an ARTIFACT** — it strips ADM context from the final verdict, so
  Tool↔LLM agreement drops 95%→61% and the LLM just defaults to "Yes", accidentally matching
  the base rate. **Drop trim3 from all future runs.**

---

## 5. Methodological weaknesses (ranked by crucialness)

**None are fatal, but #1–#3 must be addressed or explicitly caveated before publication.**

1. **🔴 LLM/vLLM nondeterminism undermines the 3-run design.** At `temp=0.0, seed=42`, **56%
   of cases give a different answer on the very first, byte-identical prompt**
   (llm_train_results §26 Investigation 1). Two "identical" configs differ by ΔF1 ≈ 0.38.
   The 3-run averaging therefore mixes real signal with irreducible sampling noise, and any
   single-run result (all train-mode, several test cells) is fragile. → Increase runs on
   headline configs, report run-level variance everywhere, and add a nondeterminism caveat.

2. **🔴 Ground-truth proxy validity.** `Reversed=Yes / Affirmed=No` equates *appeal outcome*
   with *inventive step*. Appeals reverse/affirm for many reasons (added matter, clarity,
   procedure), so labels carry noise. Quantify what fraction of the 879 decisions actually
   turn on Art. 56, or restrict to those.

3. **🟠 Weak external validity of the tool (H1).** Test-set MCC ≈ 0.06–0.15 means the core
   system is barely above chance out-of-sample. This must be stated plainly; the strong
   numbers are train-mode (oracle) or in-distribution.

4. **🟠 SFT selection bias + single model.** SFT data uses **only GT-correct** logs (92–93
   cases), biasing toward easy cases, and only Qwen is fine-tuned. Report the correct-only
   filter and treat FT as a Qwen case study.

5. **🟡 Cascading + nondeterminism confound the ADM.** Because each node's answer feeds the
   next, early nondeterministic flips cascade; "history/trim" effects are partly downstream of
   this, not genuine prompt effects (author already diagnosed this in §26).

6. **🟡 Small train set (95) for many ablations** → wide CIs; most train-vs-tool ΔMCC values
   are already reported as non-significant. Keep the CIs prominent.

7. **🟡 Known label/bugs already corrected in analysis but present in raw runs:** `n_history=0`
   sent *full* history (Python `-0` bug); `trim1/2` are no-ops for most cases. Fine as long as
   the writeup uses the corrected labels.

---

## 6. Codebase evaluation & streamlining

### Delete / archive (safe)
- **`ADM/old/`** — 9 stale backups (`batched_hybrid_system_backup.py`, `... copy.py`,
  `..._old_backup.py`, `batched_old.py`, `inventive_step_alt.py`, `hybrid_patent_system.py`,
  `calc_f1.py`, …). Remove; git history preserves them.
- **`Outputs_old/`** (`results.ipynb`, `new_results.ipynb`) — superseded by the two Analysis
  notebooks.
- **`Analysis/llm_test_results.ipynb`** — 255-byte empty stub; delete or merge into
  `llm_results.ipynb`.
- **`main.py`** — "Hello from adm-jurix" stub.
- Root scratch artifacts: `g1.png … g8.png`, `output.png`, `slurm-3873478.out` (gitignored but
  clutter the tree).
- **`tesseract-5.5.1-x86_64.AppImage` (34 MB) is committed to git** (not covered by
  `.gitignore`). Remove from the repo and download in setup instead — this is the biggest
  avoidable bloat.
- **Duplicate merged 155 GB models** (`qwen_adm_merged`, `qwen_baseline_merged`): keep the
  small LoRA adapters + `merge_lora*.py` and regenerate merges on demand rather than storing both.

### Consolidate (the big one)
- **68 `run_*.sh` scripts in `ADM/`** — dozens are near-duplicate resume/`_resume2`/`_resume3`/
  `_missing`/`_only` variants (e.g. `run_train_gpt_run3_resume{,2,3}.sh`). Replace with **one
  parametrised launcher** driven by a config file (model, mode, adm_config, questions, runs,
  resume-flag). This alone removes ~50 files and makes runs reproducible.
- **Dependency management:** `requirements.txt` **and** `pyproject.toml` **and** `uv.lock`
  coexist. Pick **uv/pyproject** as canonical and delete `requirements.txt` (or generate it).
- **Two venvs** (`.venv`, `.venv_11_2`) — document why (CUDA 11.2 vs default) or drop one.
- **`Data/` pkl sprawl:** `Inv_Step_Test.pkl`, `test_data_Inv_Step.pkl`,
  `Inv_Step_Filtered_Test_Data.pkl`, `train_data_Inv_Step.pkl`, … — mark the canonical
  train/test files and move the rest to `Data/backup/`.
- Scratch single-case dirs `Data/DIAG_T*`, `Data/TRAIN_T*` → fold into one `Data/_scratch/`.

### Clarify
- **`UI.py`, `ADM_Construction.py`, `batched_hybrid_system.py`** (0.7k–1.7k lines each) — add
  module docstrings + a one-paragraph architecture note explaining the ADM→runner→server flow.
- **`reconstruct_gpt_train_results.py`** is a good utility but its need (jobs hanging before
  writing results) hints the runner should write results incrementally/atomically.

### Documentation to add (for reproducibility)
1. **`README.md`** (currently empty): project overview, the ADM design (link the two
   `Docs/*.pdf`), env setup (uv + vLLM server via `LLM_Models/start_*_server.sh`), and the
   end-to-end run recipe.
2. **Experiment registry** — a table mapping `run_*.sh` → output archive → notebook section →
   figure. Half the parity gaps in §3 are just "which archive is canonical" ambiguity.
3. **Data provenance** — how TRAIN/TEST/VALIDATION and the `.pkl`s were generated from the raw
   EPO decisions; the GT mapping and any Art. 56 filtering (ties to weakness #2).
4. **Fine-tuning card** — datasets, filters (GT-correct only), hyperparams, and merge steps for
   both `qwen_lora_adm` and `qwen_lora_baseline`.
5. **Secrets:** `api_key.key` is present in the working tree (gitignored — verify it never
   entered history; rotate if unsure).

### Reproducibility quick wins
- Fill `Analysis/report.md` (this file) and `README.md`; pin seeds and record the
  nondeterminism caveat next to results; drop `trim3` configs; standardise on
  `sub_adm_1 / default / max_tokens=2000` as the canonical inference config.

---

## 7. Immediate to-do (priority order)
1. **Run `Qwen-FT-baseline` on the full test grid** (18 runs) and add it to `llm_results.ipynb`
   — completes the ADM-data vs prompt-data finetuning comparison (§3c gap #1). *Compulsory.*
2. **Add ≥2 repeat runs to oracle (`train`) mode** on `train_both_default` per model (§3c gap #2)
   before quoting any oracle-mode F1.
3. **Fix `llm_train_results.ipynb` to read the `.tar.gz` archives** (not the stale extracted
   dirs) — this removes the phantom "GPT tool = 5 configs / Llama train = 9" gaps (§3 correction).
4. **Top up TEST holes:** Llama `baseline` cfg1+cfg2 (server queued), GPT `tool` cfg3 (+1),
   Qwen-FT `tool` cfg3 (+2) (§3c gaps #3–#4). Fix the notebook loader so GPT baseline cfg1/cfg2
   (already on disk) are picked up.
5. Write **README + experiment registry**, purge `ADM/old/` + the AppImage, collapse the
   68 run scripts into one parametrised launcher.
