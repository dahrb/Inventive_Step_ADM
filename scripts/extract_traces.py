"""Extract ADM factor traces from TEST-base + TRAIN oracle/tool archives.
Caches a compact pickle so the error-analysis notebook loads instantly.
Records keep main accepted factors + evaluated nodes + per-sub-ADM factors.
"""
import tarfile, json, re, pickle, time, sys
from pathlib import Path
import pandas as pd

BASE = Path('/users/sgdbareh/scratch/ADM_JURIX')
ARC  = BASE / 'Outputs'
CACHE = BASE / 'Analysis' / '_cache'
CACHE.mkdir(exist_ok=True)

CRIT_YES = ['DistinguishingFeatures', 'TechnicalContribution', 'Contribution',
            'Novelty', 'CandidateOTP', 'ValidOTP', 'ObjectiveTechnicalProblem',
            'OTPNotObvious', 'NonObviousOTP']

def adm_terminate(cf):
    if 'SecondaryIndicator' in cf:       return 'No', 'SecondaryIndicator'
    if 'SufficiencyOfDisclosure' in cf:  return 'No', 'SufficiencyOfDisclosure'
    if 'Novelty' in cf and 'NonObviousOTP' in cf:
        return 'Yes', 'complete_yes'
    missing = [f for f in CRIT_YES if f not in cf]
    return 'No', (missing[0] if missing else 'unknown')

CASE_RE = re.compile(r'^T\d{6}$')
CFG_RE  = re.compile(r'^config_\d$')
RUN_RE  = re.compile(r'^run_\d+$')
EXPCFG_RE = re.compile(r'_cfg(\d)')   # exp_config lives in the TOP folder name

def stream(path, model, mode, want_substr):
    rows = []
    with tarfile.open(path, 'r:gz') as tf:
        for mem in tf:
            nm = mem.name
            if not nm.endswith('adm_summary.json'):    continue
            if want_substr and want_substr not in nm:  continue
            parts = nm.split('/')
            case = next((p for p in parts if CASE_RE.match(p)), None)
            run  = next((p for p in parts if RUN_RE.match(p)), 'run_1')
            m_cfg = EXPCFG_RE.search(nm)                    # exp_config from top folder (_cfgN)
            exp_cfg = int(m_cfg.group(1)) if m_cfg else 3   # train dirs have no _cfg -> exp_config 3
            if case is None:  continue
            try:
                summ = json.loads(tf.extractfile(mem).read().decode())
            except Exception:
                continue
            main = next((s for s in summ if s.get('adm_type') == 'main'), None)
            if main is None:  continue
            cf = list(main.get('case', []))
            verdict, node = adm_terminate(set(cf))
            def _norm(factors):
                return ['WouldModify' if f == 'WouldAdapt' else f for f in factors]
            subs = [dict(parent_fact=s.get('parent_fact'), item_name=s.get('item_name'),
                         id=s.get('id'), case=_norm(list(s.get('case', []))),
                         evaluated=_norm(list(s.get('evaluated_nodes', []))))
                    for s in summ if s.get('adm_type') == 'sub_adm']
            rows.append(dict(model=model, mode=mode, case=case, exp_cfg=exp_cfg, run=run,
                             accepted=cf, evaluated=list(main.get('evaluated_nodes', [])),
                             verdict=verdict, term_node=node, subs=subs))
    return rows

JOBS = [
    ('GPT',   'GPT_TEST_BASE.tar.gz',      'tool',   'tool_both_default'),
    ('Llama', 'LLAMA_TEST_BASE.tar.gz',    'tool',   'tool_both_default'),
    ('Qwen',  'QWEN_TEST_BASE.tar.gz',     'tool',   'tool_both_default'),
    ('GPT',   'GPT_TRAIN_TOOL.tar.gz',     'train_tool',   'tool_both_default'),
    ('Llama', 'LLAMA_TRAIN_TOOL.tar.gz',   'train_tool',   'tool_both_default'),
    ('Qwen',  'QWEN_TRAIN_TOOL.tar.gz',    'train_tool',   'tool_both_default'),
    ('GPT',   'GPT_TRAIN_ORACLE.tar.gz',   'train_oracle', 'both_default'),
    ('Llama', 'LLAMA_TRAIN_ORACLE.tar.gz', 'train_oracle', 'both_default'),
    ('Qwen',  'QWEN_TRAIN_ORACLE.tar.gz',  'train_oracle', 'both_default'),
]

all_rows = []
for model, fn, mode, substr in JOBS:
    p = ARC / fn
    if not p.exists():
        print(f"SKIP missing {fn}", flush=True); continue
    t0 = time.time()
    rows = stream(p, model, mode, substr)
    all_rows += rows
    print(f"{model:<6} {mode:<12} {fn:<26} {len(rows):>5} runs  {time.time()-t0:5.1f}s", flush=True)

df = pd.DataFrame(all_rows)
out = CACHE / 'adm_traces.pkl'
df.to_pickle(out)
print(f"\nWROTE {out}  rows={len(df)}")
print(df.groupby(['mode','model']).size())
print("\nexp_cfg spread (tool):")
print(df[df['mode']=='tool'].groupby(['model','exp_cfg'])['case'].count())

# ── Verdict table: baseline + tool, all exp-configs (TEST set) ─────────────────
# Read the compact results_main_<mode>_config<N>_both_False.json files ({run:{case:verdict}}).
VERDICT_RE = re.compile(r'results_main_(baseline|tool)_config(\d)_both_False\.json$')
TEST_ARCS = [('GPT', 'GPT_TEST_BASE.tar.gz'),
             ('Llama', 'LLAMA_TEST_BASE.tar.gz'),
             ('Qwen', 'QWEN_TEST_BASE.tar.gz')]

vrows = []
for model, fn in TEST_ARCS:
    p = ARC / fn
    if not p.exists():
        print(f"SKIP verdicts missing {fn}", flush=True); continue
    t0 = time.time(); n0 = len(vrows)
    with tarfile.open(p, 'r:gz') as tf:
        for mem in tf:
            m = VERDICT_RE.search(mem.name)
            if not m:  continue
            vmode, vcfg = m.group(1), int(m.group(2))
            try:
                d = json.loads(tf.extractfile(mem).read().decode())
            except Exception:
                continue
            for run, cases in d.items():
                for case, verdict in cases.items():
                    vrows.append(dict(model=model, mode=vmode, exp_cfg=vcfg,
                                      run=run, case=case, verdict=verdict))
    print(f"verdicts {model:<6} {fn:<22} {len(vrows)-n0:>6} rows  {time.time()-t0:5.1f}s", flush=True)

vdf = pd.DataFrame(vrows).drop_duplicates(['model', 'mode', 'exp_cfg', 'run', 'case'])
vout = CACHE / 'verdicts.pkl'
vdf.to_pickle(vout)
print(f"\nWROTE {vout}  rows={len(vdf)}")
print(vdf.groupby(['mode', 'exp_cfg']).size())
