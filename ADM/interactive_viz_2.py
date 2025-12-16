import json
import os
import sys
import webbrowser
import glob
import re
from pythonds import Stack

# --- 1. IMPORT ADM FACTORIES ---
try:
    from inventive_step_ADM import adm_initial, adm_main, sub_adm_1, sub_adm_2
except ImportError:
    try:
        from ADM_JURIX.ADM.inventive_step_ADM import adm_initial, adm_main, sub_adm_1, sub_adm_2
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
        #svg-wrapper { flex-grow: 1; overflow: hidden; position: relative; }
        svg { width: 100%; height: 100%; display: block; }
        g.node rect, g.node ellipse { stroke: #333; stroke-width: 1.5px; cursor: pointer; transition: all 0.2s; }
        g.node:hover rect, g.node:hover ellipse { stroke: #3b82f6; stroke-width: 3px; }
        g.node text { font-family: 'Arial'; font-size: 14px; pointer-events: none; }
        g.edgePath path { stroke: #64748b; stroke-width: 1.5px; fill: none; }
        g.edgeLabel rect { fill: #fff; opacity: 0.8; }
        
        /* TOOLTIP */
        .tooltip { 
            position: fixed; opacity: 0; pointer-events: none; background: white; border-radius: 8px; 
            box-shadow: 0 20px 25px -5px rgba(0,0,0,0.15), 0 8px 10px -6px rgba(0,0,0,0.1); 
            border: 1px solid #e2e8f0; width: 340px; transition: opacity 0.1s; 
            z-index: 1000; transform: translate(-50%, -100%); margin-top: -15px; font-family: sans-serif; 
        }
        .tooltip-header { 
            padding: 12px 16px; background: #f1f5f9; border-bottom: 1px solid #e2e8f0; 
            font-weight: 700; color: #0f172a; display: flex; justify-content: space-between; align-items: center;
            border-radius: 8px 8px 0 0; 
        }
        .tooltip-body { padding: 16px; font-size: 13px; color: #334155; line-height: 1.5; max-height: 400px; overflow-y: auto; }
        .statement-text { font-style: italic; border-left: 3px solid #cbd5e1; padding-left: 8px; margin-bottom: 12px; }
        .section-label { font-size: 10px; font-weight: 800; color: #94a3b8; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
        
        /* Conditions List Styling */
        .condition-list { list-style: none; padding: 0; margin: 0; }
        .condition-item { 
            padding: 6px 8px; margin-bottom: 4px; background: #f8fafc; border-radius: 4px; 
            border: 1px solid #e2e8f0; font-family: 'Consolas', monospace; font-size: 11px; color: #475569;
        }
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

    <div id="report-panel"><div id="report-content">Select a case to begin.</div></div>

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

        <div id="tooltip" class="tooltip"></div>
    </div>

    <script>
        const allCases = __ALL_CASES_JSON__;
        
        var tooltip = d3.select("#tooltip");
        var svg = d3.select("svg");
        var inner = svg.select("g");
        var zoom = d3.zoom().on("zoom", () => {
            inner.attr("transform", d3.event.transform);
            tooltip.style("opacity", 0).style("left", "-9999px");
        });
        svg.call(zoom);
        var render = new dagreD3.render();

        function loadCase(caseName) {
            const caseData = allCases[caseName];
            if (!caseData) return;

            document.getElementById('report-content').innerHTML = marked.parse(caseData.markdown);
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
                var m = d3.mouse(document.body);
                
                let bCol = d.status==="ACCEPTED" ? "#166534" : "#991b1b";
                let bBg = d.status==="ACCEPTED" ? "#dcfce7" : "#fee2e2";

                // Generate Conditions List HTML
                let conditionsHtml = "";
                if (d.conditions && d.conditions.length > 0) {
                    conditionsHtml = '<ul class="condition-list">';
                    d.conditions.forEach((cond, idx) => {
                        // Highlight if node is accepted AND this is the triggering condition
                        let activeClass = (d.status === "ACCEPTED" && idx === d.active_index) ? " active" : "";
                        conditionsHtml += `<li class="condition-item${activeClass}">${cond}</li>`;
                    });
                    conditionsHtml += '</ul>';
                } else {
                    conditionsHtml = '<div style="font-style:italic; color:#94a3b8; font-size:11px;">No specific conditions.</div>';
                }

                tooltip.html(`
                    <div class="tooltip-header">
                        <span>${d.label_raw}</span>
                        <span style="background:${bBg}; color:${bCol}; padding:2px 6px; border-radius:4px; font-size:10px;">${d.status}</span>
                    </div>
                    <div class="tooltip-body">
                        <div class="section-label">Statement</div>
                        <div class="statement-text">${d.statement}</div>
                        
                        <div class="section-label">Acceptance Conditions</div>
                        ${conditionsHtml}
                    </div>
                `);
                tooltip.style("left", m[0]+"px").style("top", m[1]+"px").style("opacity", 1);
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

        d3.select("body").on("click", () => tooltip.style("opacity", 0).style("left", "-9999px"));

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

        nodes.append({
            "id": name,
            "label": split_camel_case(name),
            "label_raw": name,
            "color": color,
            "shape": shape,
            "status": status,
            "statement": stmt,
            "conditions": conditions,
            "active_index": active_index
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

    if not os.path.exists(CASES_DIR):
        print(f"Directory {CASES_DIR} not found. Creating empty one.")
        os.makedirs(CASES_DIR)
        return {}

    case_folders = [f for f in os.listdir(CASES_DIR) if os.path.isdir(os.path.join(CASES_DIR, f))]
    
    for case_name in case_folders:
        print(f"Processing Case: {case_name}")
        case_path = os.path.join(CASES_DIR, case_name)
        
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