import json
import os
import sys
import webbrowser
import glob
import re
from pythonds import Stack
import traceback

# --- 1. IMPORT ADM FACTORIES ---
try:
    from inventive_step_ADM import adm_initial, adm_main, sub_adm_1, sub_adm_2, question_mapping
except ImportError:
    try:
        from inventive_step_ADM import adm_initial, adm_main, sub_adm_1, sub_adm_2, question_mapping
    except ImportError:
        print("CRITICAL ERROR: Could not import ADM factory functions.")
        sys.exit(1)

# --- 2. CONFIGURATION ---
CASES_DIR = "./Eval_Cases"
OUTPUT_FILE = "adm_case_manager.html"

SUB_ADM_CONFIG = {
    "ReliableTechnicalEffect": { "factory": sub_adm_1, "label": "Technical Effect" },
    "sub_adm_1": { "factory": sub_adm_1, "label": "Technical Effect" },
    "OTPObvious": { "factory": sub_adm_2, "label": "Objective Problem" },
    "sub_adm_2": { "factory": sub_adm_2, "label": "Objective Problem" }
}

# --- 3. HTML TEMPLATE ---
        
# Default absolute tool directory (used by the dashboard generator)
TOOL_DIR = '/users/sgdbareh/scratch/ADM_JURIX/Outputs/Prior/config_3/tool'
LOG_REASONING = {}
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>ADM Case Manager</title>
    
    <script src="https://d3js.org/d3.v5.min.js"></script>
    <script src="https://dagrejs.github.io/project/dagre-d3/latest/dagre-d3.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    
    <style>
        /* LAYOUT */
        body { margin: 0; padding: 0; font-family: 'Segoe UI', system-ui, sans-serif; background-color: #f8fafc; height: 100vh; display: flex; overflow: hidden; }
        
        /* LEFT PANEL: REPORT */
        #report-panel { 
            width: 450px; min-width: 350px; background: white; border-right: 1px solid #e2e8f0; 
            overflow-y: auto; padding: 40px; box-shadow: 4px 0 15px rgba(0,0,0,0.02); z-index: 10; 
            display: flex; flex-direction: column; 
        }
        #report-content { font-size: 14px; color: #334155; line-height: 1.6; flex-grow: 1; }
        #report-content h1 { font-size: 22px; font-weight: 800; color: #0f172a; margin-bottom: 10px; border-bottom: 2px solid #f1f5f9; padding-bottom: 15px; }
        #report-content h2 { font-size: 16px; font-weight: 700; color: #475569; margin-top: 30px; margin-bottom: 10px; }
        details { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; margin: 10px 0; }
        summary { cursor: pointer; font-weight: 600; color: #64748b; font-size: 12px; text-transform: uppercase; outline: none; }
        code { background: #f1f5f9; padding: 2px 5px; border-radius: 4px; font-family: 'Consolas', monospace; font-size: 13px; color: #0f172a; }

        /* RIGHT PANEL: GRAPH */
        #graph-panel { flex-grow: 1; position: relative; background: radial-gradient(circle at center, #ffffff 0%, #f8fafc 100%); display: flex; flex-direction: column; }

        /* HEADER */
        .top-bar {
            display: flex; justify-content: space-between; align-items: center;
            padding: 15px 25px; background: rgba(255,255,255,0.95); 
            border-bottom: 1px solid #e2e8f0; backdrop-filter: blur(5px); z-index: 20;
        }
        .tabs { display: flex; gap: 10px; flex-wrap: wrap; }
        
        /* CASE SELECTOR */
        .case-selector { position: relative; display: inline-block; }
        .case-btn {
            padding: 8px 16px; background: #0f172a; color: white; border-radius: 6px;
            font-size: 13px; font-weight: 600; cursor: pointer; border: none;
            display: flex; align-items: center; gap: 8px; box-shadow: 0 2px 5px rgba(15,23,42,0.2);
        }
        .case-btn:after { content: '▼'; font-size: 8px; opacity: 0.8; }
        .case-content {
            visibility: hidden; opacity: 0; position: absolute; top: 110%; right: 0;
            background: white; min-width: 220px; border-radius: 8px;
            box-shadow: 0 10px 25px -5px rgba(0,0,0,0.2); border: 1px solid #e2e8f0;
            z-index: 100; padding: 5px; transform: translateY(-5px); transition: all 0.2s;
        }
        .case-selector:hover .case-content { visibility: visible; opacity: 1; transform: translateY(0); }
        .case-item { padding: 10px 12px; font-size: 13px; color: #475569; font-weight: 500; border-radius: 6px; cursor: pointer; transition: all 0.1s; }
        .case-item:hover { background: #f1f5f9; color: #0f172a; }

        /* TABS & DROPDOWNS */
        .tab-btn { padding: 8px 16px; border: 1px solid #e2e8f0; background: white; border-radius: 20px; font-size: 13px; font-weight: 600; color: #64748b; cursor: pointer; transition: all 0.2s; }
        .tab-btn:hover { background: #f1f5f9; color: #0f172a; }
        .tab-btn.active { background: white; color: #0f172a; border-color: #0f172a; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }

        .dropdown { position: relative; display: inline-block; }
        .dropdown::after { content: ''; position: absolute; top: 100%; left: 0; right: 0; height: 15px; }
        .drop-trigger { padding: 8px 16px; border: 1px solid #e2e8f0; background: white; border-radius: 20px; font-size: 13px; font-weight: 600; color: #64748b; cursor: pointer; display: flex; align-items: center; gap: 6px; transition: all 0.2s; }
        .drop-trigger:after { content: '▼'; font-size: 9px; opacity: 0.6; }
        .drop-trigger:hover { background: #f1f5f9; color: #0f172a; }
        .dropdown.active .drop-trigger { background: white; color: #0f172a; border-color: #0f172a; }
        
        .dropdown-content {
            visibility: hidden; opacity: 0; position: absolute; top: 100%; left: 0;
            background: white; min-width: 200px; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.15);
            border: 1px solid #e2e8f0; border-radius: 12px; z-index: 50; padding: 6px; margin-top: 8px;
            transform: translateY(-10px); transition: all 0.2s ease, visibility 0s linear 0.2s;
        }
        .dropdown:hover .dropdown-content { visibility: visible; opacity: 1; transform: translateY(0); transition-delay: 0s; }
        .dropdown-item { padding: 10px 14px; color: #475569; font-size: 13px; font-weight: 500; border-radius: 8px; cursor: pointer; }
        .dropdown-item:hover { background-color: #f8fafc; color: #0f172a; }
        .dropdown-item.selected { background-color: #f1f5f9; color: #0f172a; font-weight: 600; }

        /* GRAPH */
        /* Do not reserve space for the detail panel - it should overlay when visible */
        #svg-wrapper { flex-grow: 1; overflow: hidden; position: relative; margin-right: 0; }
        svg { width: 100%; height: 100%; display: block; }
        g.node rect, g.node ellipse { stroke: #333; stroke-width: 1.5px; cursor: pointer; transition: all 0.2s; }
        g.node:hover rect, g.node:hover ellipse { stroke: #3b82f6; stroke-width: 3px; }
        g.node text { font-family: 'Arial'; font-size: 14px; pointer-events: none; }
        g.edgePath path { stroke: #64748b; stroke-width: 1.5px; fill: none; }
        g.edgeLabel rect { fill: #fff; opacity: 0.8; }
        
        /* DETAILS PANEL (right side) */
        /* Position the panel below the top bar so it does not overlap menu controls */
        #detail-panel { display: none; position: absolute; top: 64px; right: 0; width: 360px; bottom: 0; background: white; border-left: 1px solid #e2e8f0; padding: 18px; overflow-y: auto; z-index: 15; }
        .detail-header { padding-bottom: 8px; border-bottom: 1px solid #f1f5f9; margin-bottom: 10px; font-weight: 800; color: #0f172a; }
        .detail-body { font-size: 13px; color: #334155; line-height: 1.5; }
        .detail-section { margin-top: 14px; }
        .detail-section .section-label { font-size: 11px; font-weight: 800; color: #94a3b8; margin-bottom: 6px; text-transform: uppercase; }
        .detail-statement { font-style: italic; border-left: 3px solid #cbd5e1; padding-left: 8px; margin-bottom: 12px; }
        .node-selected rect, .node-selected ellipse { stroke: #f59e0b; stroke-width: 4px; filter: drop-shadow(0 0 12px rgba(245,158,11,0.6)); }
        
        /* Conditions List Styling */
        .condition-list { list-style: none; padding: 0; margin: 0; }
        .condition-item { padding: 6px 8px; margin-bottom: 4px; background: #f8fafc; border-radius: 4px; border: 1px solid #e2e8f0; font-family: 'Consolas', monospace; font-size: 11px; color: #475569; }
        /* Active (True) Condition Styling */
        .condition-item.active {
            background: #ecfdf5; border-color: #10b981; color: #065f46;
            box-shadow: 0 0 8px rgba(16, 185, 129, 0.25); font-weight: 600;
            position: relative; overflow: hidden;
        }
        .condition-item.active::before {
            content: "✔"; position: absolute; right: 6px; top: 50%; transform: translateY(-50%);
            color: #10b981; font-size: 12px;
        }

        .legend { position: absolute; bottom: 30px; right: 30px; background: white; padding: 20px; border-radius: 12px; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.1); border: 1px solid #e2e8f0; font-size: 12px; font-weight: 600; color: #475569; pointer-events: none; }
        .legend-item { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
        .dot { width: 12px; height: 12px; border: 1px solid #333; }
        .view-label { position: absolute; top: 80px; right: 20px; background: rgba(255, 255, 255, 0.9); padding: 8px 16px; border-radius: 20px; border: 1px solid #e2e8f0; font-size: 12px; font-weight: 700; color: #94a3b8; pointer-events: none; }
    </style>
</head>
<body>

    <!-- Left report panel removed per request; main graph will occupy full width -->

    <div id="graph-panel">
        <div class="top-bar">
            <div class="tabs" id="tab-bar"></div>
            <div class="case-selector">
                <button class="case-btn" id="current-case-btn">Select Case</button>
                <div class="case-content" id="case-list"></div>
            </div>
        </div>

        <div class="view-label" id="view-label">Main View</div>
        <div id="svg-wrapper"><svg><g/></svg></div>

        <div class="legend">
            <div class="legend-item"><div class="dot" style="background:#90EE90"></div> Accepted</div>
            <div class="legend-item"><div class="dot" style="background:#FFB6C1"></div> Rejected</div>
            <div style="height:1px; background:#e2e8f0; margin: 8px 0;"></div>
            <div class="legend-item">Ellipse: Issue / Sub-Node</div>
            <div class="legend-item">Rect: Leaf Factor</div>
        </div>

            <div id="detail-panel"><div class="detail-header">Node details</div><div class="detail-body">Click a node to see details here.</div></div>
    </div>

    <script>
        const allCases = __ALL_CASES_JSON__;
        
        var svg = d3.select("svg");
        var inner = svg.select("g");
        var zoom = d3.zoom().on("zoom", () => {
            inner.attr("transform", d3.event.transform);
            // clear any transient interactions
        });
        svg.call(zoom);
        var render = new dagreD3.render();

        // Helper to hide/reset the detail panel (defined here so it is in scope)
        function hideDetailPanel(){
            try{
                inner.selectAll('g.node').classed('node-selected', false);
                var panel = document.getElementById('detail-panel');
                if(panel){
                    panel.style.display = 'none';
                    // restore default content: header + placeholder body
                    panel.innerHTML = '<div class="detail-header">Node details</div><div class="detail-body">Click a node to see details here.</div>';
                }
            }catch(e){ /* ignore until inner exists */ }
        }

        // Clear node selection when clicking outside nodes. Use a single handler so it cannot be
        // accidentally overwritten; ensure clicks inside the panel don't propagate.
        d3.select("body").on("click", () => { hideDetailPanel(); });
        // prevent clicks inside the detail panel from bubbling to body (which would hide it)
        document.getElementById('detail-panel').addEventListener('click', function(e){ e.stopPropagation(); });

        function loadCase(caseName) {
            const caseData = allCases[caseName];
            if (!caseData) return;

            var reportEl = document.getElementById('report-content');
            if(reportEl) reportEl.innerHTML = marked.parse(caseData.markdown);
            const tabBar = document.getElementById("tab-bar");
            tabBar.innerHTML = ""; 
            document.getElementById("current-case-btn").innerText = caseName;

            caseData.config.forEach((item, index) => {
                if (item.type === 'single') {
                    const btn = document.createElement("div");
                    btn.className = "tab-btn";
                    btn.innerText = item.name;
                    btn.onclick = () => {
                        clearActive();
                        hideDetailPanel();
                        btn.classList.add("active");
                        drawGraph(item.data, item.name);
                    };
                    if (index === 0) btn.click();
                    tabBar.appendChild(btn);
                } else {
                    const drop = document.createElement("div");
                    drop.className = "dropdown";
                    const trigger = document.createElement("div");
                    trigger.className = "drop-trigger";
                    trigger.innerText = item.name;
                    const content = document.createElement("div");
                    content.className = "dropdown-content";
                    
                    item.options.forEach(opt => {
                        const link = document.createElement("div");
                        link.className = "dropdown-item";
                        link.innerText = opt.name;
                        link.onclick = (e) => {
                            e.stopPropagation();
                            clearActive();
                            hideDetailPanel();
                            drop.classList.add("active");
                            link.classList.add("selected");
                            drawGraph(opt.data, `${item.name} > ${opt.name}`);
                        };
                        content.appendChild(link);
                    });
                    
                    drop.appendChild(trigger);
                    drop.appendChild(content);
                    tabBar.appendChild(drop);
                }
            });
        }

        function clearActive() {
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.dropdown').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.dropdown-item').forEach(el => el.classList.remove('selected'));
        }

        function drawGraph(graphData, label) {
            document.getElementById('view-label').innerText = label;
            inner.selectAll("*").remove();

            var g = new dagreD3.graphlib.Graph().setGraph({
                rankdir: 'TB', nodesep: 60, ranksep: 80, marginx: 40, marginy: 40
            });

            graphData.nodes.forEach(n => {
                g.setNode(n.id, {
                    label: n.label, class: n.id, shape: n.shape,
                    style: `fill: ${n.color}`, labelStyle: "fill: #000;", description: n
                });
            });

            graphData.links.forEach(l => {
                g.setEdge(l.source, l.target, {
                    label: l.label, curve: d3.curveBasis,
                    style: "stroke: #64748b; fill: none;", arrowheadStyle: "fill: #64748b"
                });
            });

            render(inner, g);

            var wrapper = document.getElementById('svg-wrapper');
            var initialScale = 0.85;
            svg.call(zoom.transform, d3.zoomIdentity.translate((wrapper.clientWidth - g.graph().width * initialScale) / 2, 40).scale(initialScale));

            inner.selectAll("g.node").on("click", function(id) {
                d3.event.stopPropagation();
                var d = g.node(id).description;

                // Toggle selection: hide panel if clicking the same node again
                var already = d3.select(this).classed('node-selected');
                if(already){
                    hideDetailPanel();
                    return;
                }
                inner.selectAll('g.node').classed('node-selected', false);
                d3.select(this).classed('node-selected', true);

                // Generate Conditions List HTML
                let conditionsHtml = "";
                if (d.conditions && d.conditions.length > 0) {
                    conditionsHtml = '<ul class="condition-list">';
                    d.conditions.forEach((cond, idx) => {
                        let activeClass = (d.status === "ACCEPTED" && idx === d.active_index) ? " active" : "";
                        conditionsHtml += `<li class="condition-item${activeClass}">${cond}</li>`;
                    });
                    conditionsHtml += '</ul>';
                } else {
                    conditionsHtml = '<div style="font-style:italic; color:#94a3b8; font-size:11px;">No specific conditions.</div>';
                }

                // Populate right-hand detail panel
                const panel = document.getElementById('detail-panel');
                let html = `<div class="detail-header">${d.label_raw} <span style="float:right; font-weight:600; color:${d.status==='ACCEPTED'?'#166534':'#991b1b'}">${d.status}</span></div>`;
                html += `<div class="detail-body">`;
                html += `<div class="detail-section"><div class="section-label">Statement</div><div class="detail-statement">${d.statement}</div></div>`;
                html += `<div class="detail-section"><div class="section-label">Acceptance Conditions</div>${conditionsHtml}</div>`;
                html += `<div class="detail-section"><div class="section-label">Reasoning</div>`;
                if(d.reasoning){
                    if(Array.isArray(d.reasoning)) html += d.reasoning.map(r=> `<div style="margin-bottom:8px;">${r}</div>`).join('');
                    else html += `<div>${d.reasoning}</div>`;
                } else {
                    html += '<div style="font-style:italic; color:#94a3b8;">No reasoning available.</div>';
                }
                html += `</div></div>`;
                if(panel){ panel.innerHTML = html; panel.style.display = 'block'; }
            });
        }

        const caseList = document.getElementById("case-list");
        const caseNames = Object.keys(allCases);
        caseNames.forEach(name => {
            const item = document.createElement("div");
            item.className = "case-item";
            item.innerText = name;
            item.onclick = () => loadCase(name);
            caseList.appendChild(item);
        });

        // Note: the click handler above already hides the panel and clears selection.

        if (caseNames.length > 0) loadCase(caseNames[0]);

    </script>
</body>
</html>
"""

# --- 4. PYTHON LOGIC (FLAT EVALUATOR) ---

def split_camel_case(name):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1\n\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1\n\2', s1)

def evaluate_condition_flat(condition_str, case_set):
    """
    Evaluates a postfix or infix-like condition string against the case set WITHOUT recursion.
    It treats every token as a leaf.
    Returns: Boolean result of condition
    """
    # Quick Check: If simple token (no spaces/ops), just check existence
    if ' ' not in condition_str:
        return condition_str in case_set

    # Simple Postfix Evaluator that doesn't recurse
    stack = Stack()
    tokens = condition_str.split()
    
    for token in tokens:
        if token == 'accept':
            stack.push(True)
        elif token == 'reject':
            val = stack.pop()
            if val is True: stack.push(False) # Reject creates False outcome if trigger is True
            else: stack.push(True) # Wait, 'reject X' means if X is true, FAIL. If X is false, PASS? 
            # In ADM logic: 'reject X' -> if X True, then FAIL node.
            # Simplified: We treat 'reject' as NOT? Or special fail flag?
            # Standard ADM: if reject token triggered, node is rejected.
            # Let's try simple boolean mapping: reject X -> NOT X
            pass
        elif token == 'not':
            val = stack.pop()
            stack.push(not val)
        elif token == 'and':
            v2 = stack.pop()
            v1 = stack.pop()
            stack.push(v1 and v2)
        elif token == 'or':
            v2 = stack.pop()
            v1 = stack.pop()
            stack.push(v1 or v2)
        else:
            # It's a node name -> Check if in case
            stack.push(token in case_set)
            
    if stack.isEmpty(): return False
    return stack.pop()

def get_active_index_flat(adm, node):
    """
    Finds which acceptance condition is True based purely on adm.case list.
    """
    if not node.acceptance:
        return -1
        
    for i, condition in enumerate(node.acceptance):
        # We need the postfix version which `node.acceptance` usually is
        # But we need to handle the 'reject' logic carefully. 
        # Standard ADM logic: 'reject A' -> if A is True, then Condition is FALSE (and node Rejected).
        # Normal condition: 'A and B' -> if A & B True, Condition True (Node Accepted).
        
        # We try to evaluate the condition string using our flat evaluator
        if evaluate_condition_flat(condition, adm.case):
            # If the condition evaluates to True...
            # Check for 'reject' keyword in the string itself
            tokens = condition.split()
            if 'reject' in tokens:
                # If a reject condition evaluates to True, it means REJECTION happened.
                # So this is the 'active' condition for Rejection? 
                # But we only highlight active for Accepted nodes usually.
                pass 
            else:
                return i
    return -1

def build_graph_data_from_json(adm_factory, json_path, item_name=None):
    if not os.path.exists(json_path):
        return None

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if isinstance(data, dict):
        case_set = set(data.get('case', []))
    else:
        case_set = set()

    if item_name: adm = adm_factory(item_name)
    else: adm = adm_factory()

    adm.case = list(case_set)

    nodes = []
    links = []
    issue_nodes = getattr(adm.root_node, 'children', []) if hasattr(adm, 'root_node') else []

    for name, node in adm.nodes.items():
        # VISUAL STATUS: PURELY DATA DRIVEN
        if name in case_set:
            color = "#90EE90"
            status = "ACCEPTED"
            stmt = node.statement[0] if node.statement else "Accepted"
            
            # HIGHLIGHT LOGIC: FLAT EVALUATION
            # We only care to highlight which condition made it True
            active_index = get_active_index_flat(adm, node)
            
        else:
            color = "#FFB6C1"
            status = "REJECTED"
            stmt = node.statement[-1] if node.statement else "Rejected"
            active_index = -1

        # Use readable acceptance if available (postfix otherwise)
        conditions = getattr(node, 'acceptanceOriginal', node.acceptance) or []

        shape = "rect"
        if hasattr(adm, 'root_node') and name == adm.root_node.name: shape = "rect"
        elif name in issue_nodes or node.children: shape = "ellipse"
        else: shape = "rect"

        # Attach reasoning from LOG_REASONING if available via question_mapping
        reasoning_text = None
        try:
            if 'question_mapping' in globals() and name in question_mapping:
                qnum = question_mapping.get(name)
                tag = f"[Q{qnum}]"

                # Build a normalized node label to match feature text in logs
                raw_label = split_camel_case(name)
                node_norm = re.sub(r"[^0-9a-z ]+", "", raw_label.replace('\n', ' ').lower()).strip()
                node_norm = re.sub(r"\s+", ' ', node_norm)

                # If an item_name (sub-adm instance) is provided, normalize that too
                item_norm = None
                if item_name:
                    item_norm = re.sub(r"[^0-9a-z ]+", "", item_name.replace('_', ' ').lower()).strip()
                    item_norm = re.sub(r"\s+", ' ', item_norm)

                # Prefer feature-specific reasoning stored as '[Qn]::feature text'
                key_specific = f"{tag}::{node_norm}"
                key_item = f"{tag}::{item_norm}" if item_norm else None

                if key_specific in LOG_REASONING:
                    reasoning_text = LOG_REASONING.get(key_specific)
                elif key_item and key_item in LOG_REASONING:
                    reasoning_text = LOG_REASONING.get(key_item)
                else:
                    # Fallback to generic tag mapping
                    reasoning_text = LOG_REASONING.get(tag)
        except Exception:
            reasoning_text = None

        nodes.append({
            "id": name,
            "label": split_camel_case(name),
            "label_raw": name,
            "color": color,
            "shape": shape,
            "status": status,
            "statement": stmt,
            "conditions": conditions,
            "active_index": active_index,
            "reasoning": reasoning_text
        })

    for name, node in adm.nodes.items():
        if node.children:
            for child in node.children:
                edge_label = "+"
                if node.acceptance:
                    for c in node.acceptance:
                        if child in c.split() and ('reject' in c.split() or 'not' in c.split()):
                            edge_label = "-"
                links.append({"source": name, "target": child, "label": edge_label})

    return {"nodes": nodes, "links": links}

# --- 5. MANAGER LOGIC ---

def scan_and_build():
    all_cases_data = {}
    # Prefer scanning the TOOL_DIR (absolute path) if it exists and contains summary JSONs.
    case_paths = []
    if os.path.exists(TOOL_DIR):
        # If the tool dir contains top-level summary JSONs, treat it as a single case
        top_level_summaries = glob.glob(os.path.join(TOOL_DIR, "*_summary.json"))
        if top_level_summaries or os.path.exists(os.path.join(TOOL_DIR, "adm_initial_summary.json")) or os.path.exists(os.path.join(TOOL_DIR, "adm_main_summary.json")):
            case_paths = [TOOL_DIR]
        else:
            # Otherwise, look for subfolders that contain summary jsons and treat each as a case
            for d in os.listdir(TOOL_DIR):
                full = os.path.join(TOOL_DIR, d)
                if os.path.isdir(full) and glob.glob(os.path.join(full, "*_summary.json")):
                    case_paths.append(full)

    # Fallback to CASES_DIR structure if nothing found under TOOL_DIR
    if not case_paths:
        if not os.path.exists(CASES_DIR):
            print(f"Directory {CASES_DIR} not found. Creating empty one.")
            os.makedirs(CASES_DIR)
            return {}
        case_paths = [os.path.join(CASES_DIR, f) for f in os.listdir(CASES_DIR) if os.path.isdir(os.path.join(CASES_DIR, f))]

    for case_path in case_paths:
        case_name = os.path.basename(case_path.rstrip(os.sep))
        print(f"Processing Case: {case_name}")
        # Load reasoning log if present (single log.json at TOOL_DIR)
        try:
            log_path = os.path.join(TOOL_DIR, 'log.json')
            if os.path.exists(log_path):
                with open(log_path, 'r', encoding='utf-8') as lf:
                    entries = json.load(lf)
                    for e in entries:
                        q = e.get('question', '')
                        reasoning = e.get('reasoning') or e.get('raw_content') or e.get('answer')
                        if not q or not reasoning:
                            continue
                        # Extract the bracketed question tag (e.g. [Q17])
                        m = re.match(r"\s*(\[[^\]]+\])", q)
                        if not m:
                            continue
                        tag = m.group(1)

                        # Try to extract a feature or subject that the question refers to
                        # Many sub-ADM questions include a line like: "Feature: insertion tube with distal tip..."
                        fmatch = re.search(r"Feature:\s*(.+?)(?:\\n|$)", q, flags=re.I)
                        if fmatch:
                            feature = fmatch.group(1).strip()
                            # normalize the feature text to a simple key
                            norm = re.sub(r"[^0-9a-z ]+","", feature.lower())
                            norm = re.sub(r"\s+"," ", norm).strip()
                            key = f"{tag}::{norm}"
                            LOG_REASONING[key] = reasoning

                        # Also store a generic tag fallback (only set if not present to avoid overwriting more specific entries)
                        if tag not in LOG_REASONING:
                            LOG_REASONING[tag] = reasoning
        except Exception:
            print('Warning: failed to load log.json for reasoning.', traceback.format_exc())
        
        md_path = os.path.join(case_path, "adm_log.md")
        if not os.path.exists(md_path):
            md_files = glob.glob(os.path.join(case_path, "*.md"))
            if md_files: md_path = md_files[0]
            
        markdown_text = "# No Report Found"
        if os.path.exists(md_path):
            with open(md_path, 'r', encoding='utf-8') as f:
                markdown_text = f.read().replace('`', '\\`')

        config = []

        init_json = os.path.join(case_path, "adm_initial_summary.json")
        if os.path.exists(init_json):
            data = build_graph_data_from_json(adm_initial, init_json)
            if data: config.append({"name": "Preconditions", "type": "single", "data": data})

        main_json = os.path.join(case_path, "adm_main_summary.json")
        if os.path.exists(main_json):
            data = build_graph_data_from_json(adm_main, main_json)
            if data: config.append({"name": "Inventive Step", "type": "single", "data": data})

        sub_adm_groups = {}
        sub_dirs = [d for d in os.listdir(case_path) if os.path.isdir(os.path.join(case_path, d))]
        
        for sd in sub_dirs:
            matched_mapping = None
            for prefix, mapping in SUB_ADM_CONFIG.items():
                if prefix in sd:
                    matched_mapping = mapping
                    break
            
            if matched_mapping:
                group_label = matched_mapping['label']
                factory = matched_mapping['factory']
                
                if group_label not in sub_adm_groups:
                    sub_adm_groups[group_label] = []

                json_files = glob.glob(os.path.join(case_path, sd, "*_summary.json"))
                for jf in json_files:
                    fname = os.path.basename(jf)
                    item_name = fname.replace("_summary.json", "")
                    data = build_graph_data_from_json(factory, jf, item_name)
                    if data:
                        sub_adm_groups[group_label].append({ "name": item_name, "data": data })

        for label, options in sub_adm_groups.items():
            if options:
                config.append({ "name": label, "type": "group", "options": options })

        all_cases_data[case_name] = { "markdown": markdown_text, "config": config }

    return all_cases_data

if __name__ == "__main__":
    print("Scanning...")
    data = scan_and_build()
    
    if not data:
        print("No cases found in ./Eval_Cases")
    else:
        json_str = json.dumps(data)
        html = HTML_TEMPLATE.replace("__ALL_CASES_JSON__", json_str)
        
        with open(OUTPUT_FILE, "w", encoding='utf-8') as f:
            f.write(html)
            
        print(f"Done! Open: {OUTPUT_FILE}")
        webbrowser.open(f"file://{os.path.abspath(OUTPUT_FILE)}")