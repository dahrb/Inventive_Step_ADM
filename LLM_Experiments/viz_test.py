#!/usr/bin/env python3
"""
Generate an interactive ADM visualization focused on inventive-step nodes.

This script imports `UI.py` (directly) and prefers `inventive_step_ADM` when present.
It extracts the domain (nodes/edges), maps explanations from the markdown log
and writes an HTML where clicking a node reveals the reasoning and answer.

Usage:
  python viz_test.py /path/to/adm_log_3.md /path/to/UI.py

Output: `adm_domain_visual.html` next to the markdown file.
"""
import sys
import re
import json
import importlib
import importlib.util
import ast
from pathlib import Path

MD_DEFAULT = Path("adm_log_3.md")
OUT_DEFAULT = Path("adm_domain_visual.html")


def try_import_module(name):
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def adf_from_known_modules():
    candidates = ["inventive_step_ADM", "academic_research_ADM", "WildAnimals"]
    for modname in candidates:
        mod = try_import_module(modname)
        if not mod:
            continue
        for attr in ("adf", "get_adf", "create_adf"):
            if hasattr(mod, attr):
                try:
                    factory = getattr(mod, attr)
                    adf = factory() if callable(factory) else factory
                    return adf, f"{modname}.{attr}"
                except Exception:
                    pass
        if hasattr(mod, "ADF") and callable(getattr(mod, "ADF")):
            try:
                adf = mod.ADF()
                return adf, f"{modname}.ADF"
            except Exception:
                pass
    return None, None


def normalize_domain_from_adf(adf):
    if adf is None:
        return {"nodes": [], "edges": [], "node_meta": {}}
    nodes = []
    edges = []
    node_meta = {}

    if hasattr(adf, "nodes"):
        try:
            nd = getattr(adf, "nodes")
            if isinstance(nd, dict):
                nodes = [str(k) for k in nd.keys()]
            else:
                try:
                    nodes = [str(getattr(n, "name", n)) for n in nd]
                except Exception:
                    nodes = []
        except Exception:
            nodes = []

    try:
        if hasattr(adf, "nodes") and isinstance(adf.nodes, dict):
            for name, node_obj in adf.nodes.items():
                name_s = str(name)
                if hasattr(node_obj, "children"):
                    try:
                        for c in getattr(node_obj, "children") or []:
                            edges.append([name_s, str(c)])
                    except Exception:
                        pass
                if hasattr(node_obj, "parents"):
                    try:
                        for p in getattr(node_obj, "parents") or []:
                            edges.append([str(p), name_s])
                    except Exception:
                        pass
                for dep_attr in ("dependency_node", "dependencies", "depends_on"):
                    if hasattr(node_obj, dep_attr):
                        try:
                            deps = getattr(node_obj, dep_attr)
                            if isinstance(deps, (list, tuple)):
                                for d in deps:
                                    edges.append([str(d), name_s])
                            elif deps:
                                edges.append([str(deps), name_s])
                        except Exception:
                            pass
                meta = {}
                if hasattr(node_obj, "acceptance"):
                    try:
                        meta["acceptance"] = getattr(node_obj, "acceptance")
                    except Exception:
                        pass
                if meta:
                    node_meta[name_s] = meta
    except Exception:
        pass

    nodes = sorted(set(nodes))
    edges = [list(t) for t in {tuple(e) for e in edges}]
    return {"nodes": nodes, "edges": edges, "node_meta": node_meta}


def parse_domain_from_ui_source(ui_path: Path):
    try:
        src = ui_path.read_text(encoding="utf-8")
    except Exception:
        return {"nodes": [], "edges": [], "node_meta": {}}

    m = re.search(r'(?ms)^(?:\s*)(?:nodes|DOMAIN|domain)\s*[=:]\s*(\[[^\]]+\]|\{[^\}]+\})', src, re.IGNORECASE)
    if m:
        literal = m.group(1)
        try:
            val = ast.literal_eval(literal)
            if isinstance(val, list):
                return {"nodes": [str(x) for x in val], "edges": [], "node_meta": {}}
            if isinstance(val, dict):
                nodes = val.get("nodes") or val.get("vertices") or []
                edges = val.get("edges") or val.get("relations") or []
                return {"nodes": [str(x) for x in nodes], "edges": [[str(a), str(b)] for a,b in edges], "node_meta": {}}
        except Exception:
            pass

    labels = re.findall(r'["\']([A-Za-z0-9_ \-]{2,60})["\']', src)
    if labels:
        cand = sorted(set(labels), key=lambda s: -labels.count(s))
        cand = [c for c in cand if len(c) < 40][:50]
        return {"nodes": cand, "edges": [], "node_meta": {}}

    return {"nodes": [], "edges": [], "node_meta": {}}


def extract_entries_from_md(md_path: Path):
    text = md_path.read_text(encoding="utf-8")
    parts = re.split(r'(?m)^##\s+', text)
    entries = []
    for part in parts:
        p = part.strip()
        if not p:
            continue
        heading, _, body = p.partition("\n")
        question = None
        m = re.search(r'\*\*Question:\*\*\s*(.+)', body)
        if m:
            question = m.group(1).strip()
        reasoning = None
        m = re.search(r'\*\*Reasoning \(extracted\):\*\*[\s\S]*?```text\n([\s\S]*?)\n```', body)
        if m:
            reasoning = m.group(1).strip()
        hidden = None
        m = re.search(r'<details>[\s\S]*?<summary>.*?</summary>[\s\S]*?```text\n([\s\S]*?)\n```', body)
        if m:
            hidden = m.group(1).strip()
        answer = None
        m = re.search(r'\*\*Answer:\*\*\s*(.+)', body)
        if m:
            answer = re.sub(r'<[^>]+>', '', m.group(1).strip())
        meta = None
        m = re.search(r'<!--\s*JSON:\s*(\{[\s\S]*?\})\s*-->', body)
        if m:
            try:
                meta = json.loads(m.group(1))
            except Exception:
                meta = None
        images = re.findall(r'!\[.*?\]\((.+?)\)', body)
        entries.append({
            "heading": heading.strip(),
            "question": question,
            "reasoning": reasoning,
            "hidden": hidden,
            "answer": answer,
            "meta": meta,
            "images": [str(Path(i).name) for i in images],
            "raw": body
        })
    return entries


def map_nodes_to_entries(nodes, entries):
    mapping = {}
    texts = []
    for e in entries:
        texts.append(" ".join(filter(None, [e.get("question") or "", e.get("reasoning") or "", e.get("hidden") or ""])) .lower())
    for node in nodes:
        nl = str(node).lower()
        match = None
        for idx, t in enumerate(texts):
            if nl and nl in t:
                match = entries[idx]
                break
        mapping[str(node)] = match
    return mapping


HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>ADM Domain Visualization (Inventive Step)</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:Arial,Helvetica,sans-serif;margin:0;display:flex;height:100vh}
#graph{width:60%;border-right:1px solid #ddd;overflow:hidden;position:relative}
#info{width:40%;padding:12px;overflow:auto}
.node{cursor:pointer}
pre{white-space:pre-wrap;background:#111827;color:#e6e6e6;padding:10px;border-radius:6px;display:none}
img.attach{max-width:100%;border-radius:6px;margin-top:8px;border:1px solid #ccc;display:block}
.badge-yes{background:#e6ffed;color:#065f46;padding:2px 6px;border-radius:4px;font-weight:600}
.badge-no{background:#ffecec;color:#7b1414;padding:2px 6px;border-radius:4px;font-weight:600}
.badge-other{font-family:monospace;background:#fff0;padding:2px 6px;border-radius:4px}
.list-node{padding:10px;border-bottom:1px solid #eee;cursor:pointer}
#detail {min-height: 40px;}
.hidden { display: none; }
</style>
</head>
<body>
<div id="graph"><svg id="svg" width="100%" height="100%"></svg></div>
<div id="info"><h3>Select a node</h3><div id="detail"><p>Click a node to load explanation.</p></div></div>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script>const PAYLOAD = __PAYLOAD__;</script>
<script>
function escapeHtml(s){ if(s==null) return ''; return String(s).replace(/[&<>"']/g, ch=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[ch])); }

if(!(PAYLOAD.nodes && PAYLOAD.nodes.length)){
  const graph = document.getElementById('graph');
  graph.innerHTML = '<div style="padding:12px;overflow:auto;height:100%"><h3>Steps</h3><div id="list"></div></div>';
  const list = document.getElementById('list');
  PAYLOAD.entries.forEach((e,i)=>{
    const item = document.createElement('div'); item.className='list-node';
    item.textContent = (e.heading && e.heading.length? e.heading : 'Step ' + (i+1));
    item.addEventListener('click', ()=> showDetail(e));
    list.appendChild(item);
  });
} else {
  const nodes = (PAYLOAD.nodes||[]).map(n=>({id:n}));
  const links = (PAYLOAD.edges||[]).map(e=>({source:e[0], target:e[1]}));
  const svg = d3.select("#svg");
  const width = svg.node().clientWidth;
  const height = svg.node().clientHeight;
  const sim = d3.forceSimulation(nodes).force("link", d3.forceLink(links).id(d=>d.id).distance(120)).force("charge", d3.forceManyBody().strength(-300)).force("center", d3.forceCenter(width/2, height/2)).on("tick", ticked);
  const link = svg.append("g").selectAll("line").data(links).enter().append("line").attr("stroke","#999").attr("stroke-width",1.5);
  const nodeg = svg.append("g").selectAll("g").data(nodes).enter().append("g").call(d3.drag().on("start", (event,d)=>{ if(!event.active) sim.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y }).on("drag",(event,d)=>{ d.fx=event.x; d.fy=event.y }).on("end",(event,d)=>{ if(!event.active) sim.alphaTarget(0); d.fx=null; d.fy=null }));
  nodeg.append("circle").attr("r",16).attr("fill","#69b3a2").attr("stroke","#2c7a63").on("click",(event,d)=> showDetailForId(d.id));
  nodeg.append("text").attr("text-anchor","middle").attr("dy",4).attr("font-size",10).text(d=>d.id);
  function ticked(){ link.attr("x1",d=>d.source.x).attr("y1",d=>d.source.y).attr("x2",d=>d.target.x).attr("y2",d=>d.target.y); nodeg.attr("transform",d=>`translate(${d.x},${d.y})`) }
  function showDetailForId(id){ const e = PAYLOAD.mapping && PAYLOAD.mapping[id]; showDetail(e, id) }
}

function showDetail(e, id){
  const detail = document.getElementById('detail');
  detail.innerHTML = '';
  const h = document.createElement('h3'); h.textContent = id || (e && e.heading) || 'Node'; detail.appendChild(h);
  if(e && e.question){ const p = document.createElement('p'); p.innerHTML = '<strong>Question:</strong> ' + escapeHtml(e.question); detail.appendChild(p) }
  if(e && e.answer){ const p = document.createElement('p'); let ans = (e.answer||'').toString(); if(ans.toLowerCase()==='yes') p.innerHTML = '<strong>Answer:</strong> <span class="badge-yes">YES</span>'; else if(ans.toLowerCase()==='no') p.innerHTML = '<strong>Answer:</strong> <span class="badge-no">NO</span>'; else p.innerHTML = '<strong>Answer:</strong> <span class="badge-other">'+escapeHtml(ans)+'</span>'; detail.appendChild(p) }
  if(e && e.reasoning){ const rdiv = document.createElement('div'); rdiv.innerHTML = '<h4>Extracted reasoning</h4>'; const pre = document.createElement('pre'); pre.textContent = e.reasoning; pre.style.display = 'block'; rdiv.appendChild(pre); detail.appendChild(rdiv) }
  if(e && e.hidden){ const det = document.createElement('details'); const sum = document.createElement('summary'); sum.textContent='Show hidden/raw reasoning'; det.appendChild(sum); const pre = document.createElement('pre'); pre.textContent = e.hidden; det.appendChild(pre); detail.appendChild(det) }
  if(e && e.images && e.images.length){ e.images.forEach(src=>{ const img = document.createElement('img'); img.className='attach'; img.src = src; detail.appendChild(img) }) }
}
</script>
</body>
</html>"""


def build_payload_and_write(md_path: Path, ui_path: Path, out_path: Path):
    if not md_path.exists():
        print("[ERROR] Markdown not found:", md_path)
        return

    adf_obj, adf_source = adf_from_known_modules()
    domain = None
    if adf_obj:
        print(f"[INFO] obtained adf from {adf_source}")
        domain = normalize_domain_from_adf(adf_obj)
    else:
        print("[INFO] inventive_step_ADM not available; trying UI.py import")

    if domain is None or not domain.get("nodes"):
        if ui_path.exists():
            try:
                spec = importlib.util.spec_from_file_location("ui_module", str(ui_path))
                ui_mod = importlib.util.module_from_spec(spec)
                # provide minimal stub for MainClasses to avoid import error in UI.py
                if "MainClasses" not in sys.modules:
                    sys.modules["MainClasses"] = importlib.util.module_from_spec(importlib.util.spec_from_loader("MainClasses", loader=None))
                spec.loader.exec_module(ui_mod)
                if hasattr(ui_mod, "CLI"):
                    try:
                        cli = ui_mod.CLI()
                        if hasattr(cli, "adf"):
                            domain = normalize_domain_from_adf(cli.adf)
                            print("[INFO] extracted domain via UI.CLI.adf()")
                    except Exception as e:
                        print("[WARN] failed to instantiate CLI:", e)
                if (not domain or not domain.get("nodes")):
                    for name in ("get_domain", "get_domain_data", "export_domain", "domain", "DOMAIN"):
                        if hasattr(ui_mod, name):
                            try:
                                val = getattr(ui_mod, name)
                                val = val() if callable(val) else val
                                if hasattr(val, "nodes"):
                                    domain = normalize_domain_from_adf(val)
                                else:
                                    if isinstance(val, (dict, list)):
                                        if isinstance(val, dict) and ("nodes" in val or "edges" in val):
                                            nodes = val.get("nodes") or []
                                            edges = val.get("edges") or []
                                            domain = {"nodes": [str(n) for n in nodes], "edges": [[str(a), str(b)] for a,b in edges], "node_meta": {}}
                                        else:
                                            domain = {"nodes": [str(x) for x in (val if isinstance(val, list) else [])], "edges": [], "node_meta": {}}
                                break
                            except Exception:
                                pass
            except Exception as e:
                print("[WARN] importing UI.py failed:", e)
        else:
            print("[INFO] UI.py not found at", ui_path)

    if (not domain) or (not domain.get("nodes")):
        domain = parse_domain_from_ui_source(ui_path) if ui_path.exists() else {"nodes": [], "edges": [], "node_meta": {}}
        print("[INFO] domain extracted via static source parse")

    filtered_nodes = []
    for n in domain.get("nodes", []):
        nl = str(n).lower()
        if "invent" in nl or "step" in nl or "novel" in nl:
            filtered_nodes.append(n)
    if not filtered_nodes:
        filtered_nodes = domain.get("nodes", [])

    node_set = set(filtered_nodes)
    filtered_edges = [[a,b] for a,b in domain.get("edges", []) if a in node_set and b in node_set]

    domain = {"nodes": filtered_nodes, "edges": filtered_edges, "node_meta": domain.get("node_meta", {})}

    entries = extract_entries_from_md(md_path)
    mapping = map_nodes_to_entries(domain.get("nodes", []), entries) if domain.get("nodes") else {}
    for k,v in list(mapping.items()):
        if v:
            mapping[k] = {"heading": v.get("heading"), "question": v.get("question"), "reasoning": v.get("reasoning"), "hidden": v.get("hidden"), "answer": v.get("answer"), "images": v.get("images", [])}
        else:
            mapping[k] = None

    payload = {"nodes": domain.get("nodes", []), "edges": domain.get("edges", []), "entries": [], "mapping": mapping}

    print(f"[INFO] nodes={len(payload['nodes'])}, edges={len(payload['edges'])}, entries={len(entries)}")

    json_payload = json.dumps(payload, ensure_ascii=False)
    final = HTML.replace("__PAYLOAD__", json_payload)
    out_path.write_text(final, encoding="utf-8")
    print("[OK] wrote:", out_path)


def main(argv):
    md_path = Path(argv[1]) if len(argv) > 1 else MD_DEFAULT
    ui_path = Path(argv[2]) if len(argv) > 2 else Path("UI.py")
    out_path = Path(argv[3]) if len(argv) > 3 else OUT_DEFAULT
    build_payload_and_write(md_path, ui_path, out_path)


if __name__ == "__main__":
    main(sys.argv)
#!/usr/bin/env python3
"""
Generate an interactive ADM visualization by extracting the domain directly
from the project's ADM modules (e.g. inventive_step_ADM) instead of importing UI.py
which may require heavy dependencies.

This version:
- tries to import common ADM modules (inventive_step_ADM, academic_research_ADM, WildAnimals)
  and call their adf() factory to get the ADF object.
- extracts nodes from adf.nodes (dict) and edges from node.children / node.parents / node.dependencies
- falls back to static parsing of UI.py source if imports fail
- builds and writes an interactive HTML with force graph and click-to-inspect details
"""
import sys
import re
import json
from pathlib import Path
import importlib
import importlib.util
import ast

MD_DEFAULT = Path("/users/sgdbareh/scratch/ADM_JURIX/LLM_Experiments/adm_log_3.md")
OUT_DEFAULT = Path("adm_domain_visual.html")

def try_import_module(name):
    try:
        return importlib.import_module(name)
    except Exception:
        return None

def adf_from_known_modules():
    """
    Try to find an adf() factory in known modules used by UI.py.
    Return (adf_obj, module_name) or (None, None).
    """
    candidates = ["inventive_step_ADM", "academic_research_ADM", "WildAnimals", "domain_ADM", "adm_data"]
    for modname in candidates:
        mod = try_import_module(modname)
        if not mod:
            continue
        for attr in ("adf", "get_adf", "create_adf"):
            if hasattr(mod, attr):
                try:
                    factory = getattr(mod, attr)
                    adf = factory()
                    return adf, f"{modname}.{attr}"
                except Exception:
                    # try next attr
                    pass
        # sometimes module exposes a class name matching adf
        if hasattr(mod, "ADF") and callable(getattr(mod, "ADF")):
            try:
                adf = mod.ADF()
                return adf, f"{modname}.ADF"
            except Exception:
                pass
    return None, None

def normalize_domain_from_adf(adf):
    """
    Normalize an adf object into {'nodes': [...], 'edges': [[a,b], ...], 'node_meta': {}}
    Works by inspecting common attributes used in UI.py (adf.nodes, node.children, node.acceptance, adf.name).
    """
    if adf is None:
        return {"nodes": [], "edges": [], "node_meta": {}}
    nodes = []
    edges = []
    node_meta = {}

    # nodes as dict keys
    if hasattr(adf, "nodes"):
        try:
            nd = getattr(adf, "nodes")
            if isinstance(nd, dict):
                nodes = [str(k) for k in nd.keys()]
            else:
                # if it's iterable of objects with 'name'
                try:
                    nodes = [str(getattr(n, "name", n)) for n in nd]
                except Exception:
                    nodes = []
        except Exception:
            nodes = []

    # try to discover edges from node children / parents / dependencies
    try:
        if hasattr(adf, "nodes") and isinstance(adf.nodes, dict):
            for name, node_obj in adf.nodes.items():
                name_s = str(name)
                # children attribute
                if hasattr(node_obj, "children"):
                    try:
                        for c in getattr(node_obj, "children") or []:
                            edges.append([name_s, str(c)])
                    except Exception:
                        pass
                # parents attribute (reverse)
                if hasattr(node_obj, "parents"):
                    try:
                        for p in getattr(node_obj, "parents") or []:
                            edges.append([str(p), name_s])
                    except Exception:
                        pass
                # dependency list / dependency_node
                for dep_attr in ("dependency_node", "dependencies", "depends_on"):
                    if hasattr(node_obj, dep_attr):
                        try:
                            deps = getattr(node_obj, dep_attr)
                            if isinstance(deps, (list, tuple)):
                                for d in deps:
                                    edges.append([str(d), name_s])
                            elif deps:
                                edges.append([str(deps), name_s])
                        except Exception:
                            pass
                # acceptance metadata
                meta = {}
                if hasattr(node_obj, "acceptance"):
                    try:
                        meta["acceptance"] = getattr(node_obj, "acceptance")
                    except Exception:
                        pass
                if meta:
                    node_meta[name_s] = meta
    except Exception:
        pass

    # dedupe
    nodes = sorted(set(nodes))
    edges = [list(t) for t in {tuple(e) for e in edges}]
    return {"nodes": nodes, "edges": edges, "node_meta": node_meta}

def parse_domain_from_ui_source(ui_path: Path):
    """
    Fallback: attempt to statically parse UI.py to find literal domain assignments or lists.
    Keeps simple regex/ast searches.
    """
    try:
        src = ui_path.read_text(encoding="utf-8")
    except Exception:
        return {"nodes": [], "edges": [], "node_meta": {}}

    # look for simple 'nodes = [...]' or 'DOMAIN = {...}' patterns
    m = re.search(r'(?ms)^\s*(?:nodes|DOMAIN|domain)\s*=\s*(\[[^\]]+\]|\{[^\}]+\})', src, re.IGNORECASE)
    if m:
        literal = m.group(1)
        try:
            val = ast.literal_eval(literal)
            if isinstance(val, list):
                return {"nodes": [str(x) for x in val], "edges": [], "node_meta": {}}
            if isinstance(val, dict):
                # if dict has 'nodes' or 'edges'
                nodes = val.get("nodes") or val.get("vertices") or []
                edges = val.get("edges") or val.get("relations") or []
                return {"nodes": [str(x) for x in nodes], "edges": [[str(a), str(b)] for a,b in edges], "node_meta": {}}
        except Exception:
            pass

    # regex find quoted labels in file as naive node list
    labels = re.findall(r'["\']([A-Za-z0-9_ \-]{2,60})["\']', src)
    # pick most frequent short tokens as nodes (heuristic)
    if labels:
        cand = sorted(set(labels), key=lambda s: -labels.count(s))
        cand = [c for c in cand if len(c) < 40][:50]
        return {"nodes": cand, "edges": [], "node_meta": {}}

    return {"nodes": [], "edges": [], "node_meta": {}}

def extract_entries_from_md(md_path: Path):
    text = md_path.read_text(encoding="utf-8")
    parts = re.split(r'(?m)^##\s+', text)
    entries = []
    for part in parts:
        p = part.strip()
        if not p:
            continue
        heading, _, body = p.partition("\n")
        question = None
        m = re.search(r'\*\*Question:\*\*\s*(.+)', body)
        if m: question = m.group(1).strip()
        reasoning = None
        m = re.search(r'\*\*Reasoning \(extracted\):\*\*[\s\S]*?```text\n([\s\S]*?)\n```', body)
        if m: reasoning = m.group(1).strip()
        hidden = None
        m = re.search(r'<details>[\s\S]*?<summary>.*?</summary>[\s\S]*?```text\n([\s\S]*?)\n```', body)
        if m: hidden = m.group(1).strip()
        answer = None
        m = re.search(r'\*\*Answer:\*\*\s*(.+)', body)
        if m: answer = re.sub(r'<[^>]+>', '', m.group(1).strip())
        meta = None
        m = re.search(r'<!--\s*JSON:\s*(\{[\s\S]*?\})\s*-->', body)
        if m:
            try: meta = json.loads(m.group(1))
            except Exception: meta = None
        images = re.findall(r'!\[.*?\]\((.+?)\)', body)
        entries.append({
            "heading": heading.strip(),
            "question": question,
            "reasoning": reasoning,
            "hidden": hidden,
            "answer": answer,
            "meta": meta,
            "images": [str(Path(i).name) for i in images],
            "raw": body
        })
    return entries

def map_nodes_to_entries(nodes, entries):
    mapping = {}
    texts = []
    for e in entries:
        texts.append(" ".join(filter(None, [e.get("question") or "", e.get("reasoning") or "", e.get("hidden") or ""])).lower())
    for node in nodes:
        nl = str(node).lower()
        match = None
        for idx, t in enumerate(texts):
            if nl and nl in t:
                match = entries[idx]
                break
        mapping[str(node)] = match
    return mapping

HTML = """<!doctype html>
<html>
<head><meta charset="utf-8"><title>ADM Domain Visualization</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:Arial,Helvetica,sans-serif;margin:0;display:flex;height:100vh}
#graph{width:60%;border-right:1px solid #ddd;overflow:hidden;position:relative}
#info{width:40%;padding:12px;overflow:auto}
.node{cursor:pointer}
pre{white-space:pre-wrap;background:#111827;color:#e6e6e6;padding:10px;border-radius:6px}
img.attach{max-width:100%;border-radius:6px;margin-top:8px;border:1px solid #ccc}
.badge-yes{background:#e6ffed;color:#065f46;padding:2px 6px;border-radius:4px;font-weight:600}
.badge-no{background:#ffecec;color:#7b1414;padding:2px 6px;border-radius:4px;font-weight:600}
.badge-other{font-family:monospace;background:#fff0;padding:2px 6px;border-radius:4px}
.list-node{padding:10px;border-bottom:1px solid #eee;cursor:pointer}
</style></head>
<body>
<div id="graph"><svg id="svg" width="100%" height="100%"></svg></div>
<div id="info"><h3>Select a node</h3><div id="detail"><p>Click a node to see explanation.</p></div></div>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script>const PAYLOAD = __PAYLOAD__;</script>
<script>
if(!(PAYLOAD.nodes && PAYLOAD.nodes.length)){
  const graph = document.getElementById('graph');
  graph.innerHTML = '<div style="padding:12px;overflow:auto;height:100%"><h3>Steps</h3><div id="list"></div></div>';
  const list = document.getElementById('list');
  PAYLOAD.entries.forEach((e,i)=>{
    const item = document.createElement('div'); item.className='list-node';
    item.textContent = (e.heading && e.heading.length? e.heading : 'Step ' + (i+1)) + (e.question ? ' — ' + e.question : '');
    item.addEventListener('click', ()=> showDetail(e));
    list.appendChild(item);
  });
  function showDetail(e){
    const detail = document.getElementById('detail'); detail.innerHTML = '';
    const h = document.createElement('h3'); h.textContent = e.heading || 'Step'; detail.appendChild(h);
    if(e.question){ const p = document.createElement('p'); p.innerHTML = '<strong>Question:</strong> '+escapeHtml(e.question); detail.appendChild(p) }
    if(e.answer){ const p = document.createElement('p'); let ans=escapeHtml(e.answer||''); if(ans.toLowerCase()==='yes') p.innerHTML = '<strong>Answer:</strong> <span class="badge-yes">YES</span>'; else if(ans.toLowerCase()==='no') p.innerHTML = '<strong>Answer:</strong> <span class="badge-no">NO</span>'; else p.innerHTML = '<strong>Answer:</strong> <span class="badge-other">'+ans+'</span>'; detail.appendChild(p) }
    if(e.reasoning){ const d=document.createElement('div'); d.innerHTML='<h4>Extracted reasoning</h4>'; const pre=document.createElement('pre'); pre.textContent=e.reasoning; d.appendChild(pre); detail.appendChild(d) }
    if(e.hidden){ const det=document.createElement('details'); const sum=document.createElement('summary'); sum.textContent='Show hidden/raw reasoning'; det.appendChild(sum); const pre=document.createElement('pre'); pre.textContent=e.hidden; det.appendChild(pre); detail.appendChild(det) }
    if(e.images && e.images.length){ e.images.forEach(src=>{ const img=document.createElement('img'); img.className='attach'; img.src=src; detail.appendChild(img) }) }
  }
} else {
  const nodes = (PAYLOAD.nodes||[]).map(n=>({id:n}));
  const links = (PAYLOAD.edges||[]).map(e=>({source:e[0], target:e[1]}));
  const svg = d3.select("#svg");
  const width = svg.node().clientWidth;
  const height = svg.node().clientHeight;
  const sim = d3.forceSimulation(nodes).force("link", d3.forceLink(links).id(d=>d.id).distance(120)).force("charge", d3.forceManyBody().strength(-300)).force("center", d3.forceCenter(width/2, height/2)).on("tick", ticked);
  const link = svg.append("g").selectAll("line").data(links).enter().append("line").attr("stroke","#999").attr("stroke-width",1.5);
  const nodeg = svg.append("g").selectAll("g").data(nodes).enter().append("g").call(d3.drag().on("start", (event,d)=>{ if(!event.active) sim.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y }).on("drag",(event,d)=>{ d.fx=event.x; d.fy=event.y }).on("end",(event,d)=>{ if(!event.active) sim.alphaTarget(0); d.fx=null; d.fy=null }));
  nodeg.append("circle").attr("r",16).attr("fill","#69b3a2").attr("stroke","#2c7a63").on("click",(event,d)=> showDetailForId(d.id));
  nodeg.append("text").attr("text-anchor","middle").attr("dy",4).attr("font-size",10).text(d=>d.id);
  function ticked(){ link.attr("x1",d=>d.source.x).attr("y1",d=>d.source.y).attr("x2",d=>d.target.x).attr("y2",d=>d.target.y); nodeg.attr("transform",d=>`translate(${d.x},${d.y})`) }
  function showDetailForId(id){ const e = PAYLOAD.mapping && PAYLOAD.mapping[id]; showDetail(e, id) }
  function showDetail(e, id){
    const detail = document.getElementById('detail'); detail.innerHTML = '';
    const h = document.createElement('h3'); h.textContent = id || (e && e.heading) || 'Node'; detail.appendChild(h);
    if(e && e.question){ const p=document.createElement('p'); p.innerHTML = '<strong>Question:</strong> '+escapeHtml(e.question); detail.appendChild(p) }
    if(e && e.answer){ const p=document.createElement('p'); let ans=(e.answer||''); if(ans.toLowerCase()==='yes') p.innerHTML = '<strong>Answer:</strong> <span class="badge-yes">YES</span>'; else if(ans.toLowerCase()==='no') p.innerHTML = '<strong>Answer:</strong> <span class="badge-no">NO</span>'; else p.innerHTML = '<strong>Answer:</strong> <span class="badge-other">'+escapeHtml(ans)+'</span>'; detail.appendChild(p) }
    if(e && e.reasoning){ const d=document.createElement('div'); d.innerHTML='<h4>Extracted reasoning</h4>'; const pre=document.createElement('pre'); pre.textContent=e.reasoning; d.appendChild(pre); detail.appendChild(d) }
    if(e && e.hidden){ const det=document.createElement('details'); const sum=document.createElement('summary'); sum.textContent='Show hidden/raw reasoning'; det.appendChild(sum); const pre=document.createElement('pre'); pre.textContent=e.hidden; det.appendChild(pre); detail.appendChild(det) }
    if(e && e.images){ e.images.forEach(src=>{ const img=document.createElement('img'); img.className='attach'; img.src=src; detail.appendChild(img) }) }
  }
}
function escapeHtml(s){ if(!s) return ''; return String(s).replace(/[&<>"']/g, ch=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[ch])); }
</script></body></html>
"""

def main(argv):
    md_path = Path(argv[1]) if len(argv) > 1 else MD_DEFAULT
    ui_path = Path(argv[2]) if len(argv) > 2 else Path("/users/sgdbareh/scratch/ADM_JURIX/UI.py")
    out_path = Path(argv[3]) if len(argv) > 3 else OUT_DEFAULT

    if not md_path.exists():
        print("[ERROR] Markdown not found:", md_path); return

    # 1) Try to get adf by importing known ADM modules
    adf_obj, adf_source = adf_from_known_modules()
    domain = None
    if adf_obj:
        print(f"[INFO] obtained adf from {adf_source}")
        domain = normalize_domain_from_adf(adf_obj)
    else:
        print("[INFO] could not get adf from known modules, trying UI.py static parse")

    # 2) If failed, try to import UI.py and instantiate CLI.adf (guard missing deps)
    if domain is None or (not domain.get("nodes")):
        if ui_path.exists():
            try:
                # attempt safe import of UI.py, but prevent it from executing main()
                spec = importlib.util.spec_from_file_location("ui_module", str(ui_path))
                ui_mod = importlib.util.module_from_spec(spec)
                # do not execute top-level code that runs CLI.main by checking for __name__ == '__main__' in UI.py;
                # spec.loader.exec_module will execute file; to avoid side-effects, provide a stub for MainClasses if missing
                # Inject minimal stub module names that UI.py expects if they are missing
                needed = ("MainClasses",)
                for n in needed:
                    if n not in sys.modules:
                        sys.modules[n] = importlib.util.module_from_spec(importlib.util.spec_from_loader(n, loader=None))
                spec.loader.exec_module(ui_mod)
                # try to create CLI and access its adf
                if hasattr(ui_mod, "CLI"):
                    try:
                        cli = ui_mod.CLI()
                        if hasattr(cli, "adf"):
                            domain = normalize_domain_from_adf(cli.adf)
                            print("[INFO] extracted adf via UI.CLI.adf()")
                    except Exception as e:
                        print("[WARN] failed to instantiate CLI:", e)
                else:
                    print("[WARN] UI.py has no CLI class")
            except Exception as e:
                print("[WARN] importing UI.py failed:", e)
        else:
            print("[INFO] UI.py not found at", ui_path)

    # 3) fallback: static parse of UI.py
    if (domain is None) or (not domain.get("nodes")):
        if ui_path.exists():
            domain = parse_domain_from_ui_source(ui_path)
            print("[INFO] domain extracted via static source parse")
        else:
            domain = {"nodes": [], "edges": [], "node_meta": {}}

    # 4) build entries and mapping
    entries = extract_entries_from_md(md_path)
    mapping = map_nodes_to_entries(domain.get("nodes", []), entries) if domain.get("nodes") else {}
    # ensure mapping values are serializable; keep only relevant keys
    for k,v in list(mapping.items()):
        if v:
            mapping[k] = { "heading": v.get("heading"), "question": v.get("question"), "reasoning": v.get("reasoning"), "hidden": v.get("hidden"), "answer": v.get("answer"), "images": v.get("images",[]) }
        else:
            mapping[k] = None

    payload = {
        "nodes": domain.get("nodes", []),
        "edges": domain.get("edges", []),
        "entries": entries,
        "mapping": mapping
    }

    print(f"[INFO] nodes={len(payload['nodes'])}, edges={len(payload['edges'])}, entries={len(entries)}")

    json_payload = json.dumps(payload, ensure_ascii=False)
    final = HTML.replace("__PAYLOAD__", json_payload)
    out_path.write_text(final, encoding="utf-8")
    print("[OK] wrote:", out_path)

if __name__ == "__main__":
    main(sys.argv)