import json
import os
import sys
import webbrowser
import re

# --- 1. IMPORT ADM ---
try:
    from ADM_JURIX.ADM.inventive_step_ADM import adm_initial
except ImportError:
    try:
        from ADM_JURIX.ADM.UI import adm_initial
    except ImportError:
        print("CRITICAL ERROR: Could not import adm_initial.")
        sys.exit(1)

# --- 2. MARKDOWN CONTENT ---
MARKDOWN_CONTENT = """
# ADM Session Log
**Date:** 2025-12-03  
**Case:** Umbrella Lamp with Integrated Portable Lighting System

---

## Step 1 — 11:28:05
**Question:** What is the title of your invention?

<details open>
<summary><strong>Reasoning</strong></summary>
The title should concisely describe the invention while highlighting its novel combination of an umbrella structure and a lighting function. A clear, descriptive title helps the examiner quickly understand the subject matter and distinguishes it from existing umbrella or lamp products.
</details>

**Answer:** `Umbrella Lamp with Integrated Portable Lighting System`

---

## Step 2 — 11:28:10
**Question:** Please provide a brief description of your invention:

<details>
<summary><strong>Reasoning</strong></summary>
The brief description should concisely explain the core features and functionality of the Umbrella Lamp with Integrated Portable Lighting System, highlighting how the lighting elements are incorporated into the umbrella structure, the power source, and the intended use cases.
</details>

**Answer:** The invention is an umbrella that incorporates a compact, battery‑powered lighting system within its ribs or canopy. The lamp elements are discreetly embedded and can be activated by a switch on the handle, providing illumination for outdoor activities such as walking, camping, or events.

---

## Step 3 — 11:28:15
**Question:** What is the technical field of the invention?

**Answer:** The invention relates to the technical field of personal accessories that integrate lighting functions, specifically to umbrellas equipped with an integrated, battery‑powered illumination system.

---

## Step 29 — 11:31:05
**Question:** Session Summary & Final Decision

<details open>
<summary><strong>Final Reasoning</strong></summary>
The evaluation concludes that the Umbrella Lamp lacks novelty and inventive step. The invention is deemed an obvious combination of known devices, merely selecting parameters within a limited range using routine design procedures, with no unexpected technical effect or distinguishing features. Secondary indicators also point to obviousness. Consequently, the invention does not meet the requirements for patentability.
</details>

### Final Decision
<span style="background:#fee2e2; color:#991b1b; padding:4px 8px; border-radius:4px; font-weight:800; border:1px solid #fecaca;">NO (REJECTED)</span>
"""

# --- 3. HTML TEMPLATE (Split Screen + Restore Exact Graph Logic) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>ADM Dashboard</title>
    
    <script src="https://d3js.org/d3.v5.min.js"></script>
    <script src="https://dagrejs.github.io/project/dagre-d3/latest/dagre-d3.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    
    <style>
        /* --- LAYOUT --- */
        body { 
            margin: 0; padding: 0; 
            font-family: 'Segoe UI', -apple-system, sans-serif; 
            background-color: #f8fafc; 
            height: 100vh; overflow: hidden;
            display: flex;
        }

        /* --- LEFT PANEL: REPORT --- */
        #report-panel {
            width: 450px;
            min-width: 350px;
            background: white;
            border-right: 1px solid #e2e8f0;
            overflow-y: auto;
            padding: 40px;
            box-shadow: 4px 0 15px rgba(0,0,0,0.02);
            z-index: 10;
        }

        #report-content { font-size: 14px; color: #334155; line-height: 1.6; }
        #report-content h1 { font-size: 22px; font-weight: 800; color: #0f172a; margin-bottom: 5px; border-bottom: 2px solid #f1f5f9; padding-bottom: 15px; }
        #report-content h2 { font-size: 16px; font-weight: 700; color: #475569; margin-top: 30px; margin-bottom: 10px; display: flex; align-items: center; }
        #report-content h2::before { content: ''; display: inline-block; width: 6px; height: 6px; background: #3b82f6; border-radius: 50%; margin-right: 8px; }
        #report-content strong { color: #0f172a; font-weight: 700; }
        #report-content hr { border: 0; border-top: 1px solid #e2e8f0; margin: 30px 0; }
        details { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; margin: 10px 0; }
        summary { cursor: pointer; font-weight: 600; color: #64748b; font-size: 12px; text-transform: uppercase; outline: none; }
        code { background: #f1f5f9; padding: 2px 5px; border-radius: 4px; font-family: 'Consolas', monospace; font-size: 13px; color: #0f172a; }

        /* --- RIGHT PANEL: GRAPH CONTAINER --- */
        #graph-panel {
            flex-grow: 1;
            position: relative;
            background: radial-gradient(circle at center, #ffffff 0%, #f8fafc 100%);
            display: flex;
            justify-content: center;
            align-items: center;
        }
        
        svg { width: 100%; height: 100%; display: block; }

        /* --- GRAPH STYLES (RESTORED EXACTLY) --- */
        g.node rect, g.node ellipse, g.node polygon { stroke: #333; stroke-width: 1.5px; cursor: pointer; transition: all 0.2s; }
        g.node:hover rect, g.node:hover ellipse { stroke: #3b82f6; stroke-width: 3px; }
        g.node text { font-family: 'Arial'; font-size: 14px; pointer-events: none; }
        
        g.edgePath path { stroke: #64748b; stroke-width: 1.5px; fill: none; }
        g.edgeLabel rect { fill: #fff; opacity: 0.8; }
        g.edgeLabel tspan { font-size: 14px; font-weight: bold; }

        /* --- LEGEND & HEADER --- */
        .header-overlay {
            position: absolute; top: 20px; left: 20px;
            background: rgba(255, 255, 255, 0.9); backdrop-filter: blur(4px);
            padding: 10px 20px; border-radius: 30px;
            border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
            font-size: 13px; font-weight: 600; color: #475569; pointer-events: none;
        }

        .legend {
            position: absolute; bottom: 30px; right: 30px;
            background: white; padding: 20px; border-radius: 12px;
            box-shadow: 0 10px 25px -5px rgba(0,0,0,0.1); border: 1px solid #e2e8f0;
            font-size: 12px; font-weight: 600; color: #475569;
        }
        .legend-item { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
        .dot { width: 12px; height: 12px; border: 1px solid #333; }

        /* --- TOOLTIP (RESTORED EXACTLY) --- */
        .tooltip {
            position: fixed; opacity: 0; pointer-events: none; background: white; border-radius: 8px;
            box-shadow: 0 20px 25px -5px rgba(0,0,0,0.15), 0 8px 10px -6px rgba(0,0,0,0.1); 
            border: 1px solid #e2e8f0; width: 320px; transition: opacity 0.1s; z-index: 1000;
            transform: translate(-50%, -100%); margin-top: -15px; font-family: sans-serif;
        }
        .tooltip-header { 
            padding: 12px 16px; background: #f1f5f9; border-bottom: 1px solid #e2e8f0; 
            font-weight: 700; color: #0f172a; border-radius: 8px 8px 0 0;
            display: flex; justify-content: space-between;
        }
        .tooltip-body { padding: 15px; font-size: 13px; color: #334155; line-height: 1.5; }
        .statement-text { font-style: italic; border-left: 3px solid #cbd5e1; padding-left: 8px; }
        .tooltip::after {
            content: ""; position: absolute; top: 100%; left: 50%; margin-left: -8px; 
            border-width: 8px; border-style: solid; border-color: white transparent transparent transparent;
        }
    </style>
</head>
<body>

    <div id="report-panel">
        <div id="report-content"></div>
    </div>

    <div id="graph-panel">
        <div class="header-overlay">Logic Graph &bull; Selective Reasoning</div>
        
        <div class="legend">
            <div class="legend-item"><div class="dot" style="background:#90EE90"></div> Accepted</div>
            <div class="legend-item"><div class="dot" style="background:#FFB6C1"></div> Rejected</div>
            <div class="legend-item"><div class="dot" style="background:#E2E8F0"></div> Unknown</div>
            <div style="height:1px; background:#e2e8f0; margin: 8px 0;"></div>
            <div class="legend-item">Ellipse: Issue / Sub-Node</div>
            <div class="legend-item">Rect: Leaf Factor</div>
        </div>

        <svg><g/></svg>
        <div id="tooltip" class="tooltip"></div>
    </div>

    <script>
        // 1. INJECT DATA
        const graphData = __GRAPH_JSON__;
        const markdownText = `__MARKDOWN_TEXT__`;

        // 2. RENDER MARKDOWN
        document.getElementById('report-content').innerHTML = marked.parse(markdownText);

        // 3. INITIALIZE VARIABLES (Fix JS Errors)
        var tooltip = d3.select("#tooltip");
        function hideTooltip() {
            tooltip.style("opacity", 0);
            setTimeout(() => { if(tooltip.style('opacity')==0) tooltip.style('left', '-9999px')}, 200);
        }

        // 4. SETUP GRAPH (RESTORED CONFIG)
        var g = new dagreD3.graphlib.Graph().setGraph({
            rankdir: 'TB',
            nodesep: 60,  // Restored
            ranksep: 80,  // Restored
            marginx: 40,  // Restored
            marginy: 40   // Restored
        });

        // Add Nodes
        graphData.nodes.forEach(function(node) {
            g.setNode(node.id, {
                label: node.label,
                class: node.id,
                shape: node.shape,
                style: `fill: ${node.color}`,
                labelStyle: "font-weight: bold; fill: #000;",
                description: node
            });
        });

        // Add Edges
        graphData.links.forEach(function(link) {
            g.setEdge(link.source, link.target, {
                label: link.label,
                curve: d3.curveBasis, 
                style: "stroke: #64748b; fill: none;",
                arrowheadStyle: "fill: #64748b"
            });
        });

        // 5. RENDER
        var render = new dagreD3.render();
        var svg = d3.select("svg");
        var svgGroup = svg.select("g");

        render(svgGroup, g);

        // 6. ZOOM
        var zoom = d3.zoom().on("zoom", function() {
            svgGroup.attr("transform", d3.event.transform);
            hideTooltip();
        });
        svg.call(zoom);
        
        // Initial Center (Restored Scale)
        var panelWidth = document.getElementById('graph-panel').clientWidth;
        var initialScale = 0.85; // Restored
        svg.call(zoom.transform, d3.zoomIdentity.translate((panelWidth - g.graph().width * initialScale) / 2, 40).scale(initialScale));

        // 7. INTERACTIVITY (Restored Exact Click Handler)
        svg.selectAll("g.node").on("click", function(id) {
            d3.event.stopPropagation();
            
            var nodeData = g.node(id).description;
            var mouse = d3.mouse(document.body);
            var x = mouse[0];
            var y = mouse[1];

            let badgeColor = nodeData.status === "ACCEPTED" ? "#166534" : "#991b1b";
            let badgeBg = nodeData.status === "ACCEPTED" ? "#dcfce7" : "#fee2e2";
            
            if (nodeData.status === "UNKNOWN") {
                 badgeColor = "#475569"; badgeBg = "#f1f5f9";
            }

            tooltip.html(`
                <div class="tooltip-header">
                    <span>${nodeData.label_raw}</span>
                    <span style="background:${badgeBg}; color:${badgeColor}; padding:2px 6px; border-radius:4px; font-size:10px;">${nodeData.status}</span>
                </div>
                <div class="tooltip-body">
                    <div style="font-size:10px; font-weight:800; color:#94a3b8; margin-bottom:4px;">REASONING</div>
                    <div style="margin-bottom:10px;">N/A</div>
                    <div style="font-size:10px; font-weight:800; color:#94a3b8; margin-bottom:4px;">STATEMENT</div>
                    <div class="statement-text">${nodeData.statement}</div>
                </div>
            `);

            tooltip.style("left", x + "px")
                   .style("top", y + "px")
                   .style("opacity", 1);
        });

        d3.select("body").on("click", hideTooltip);

    </script>
</body>
</html>
"""

# --- 4. PYTHON LOGIC ---

def split_camel_case(name):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1\n\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1\n\2', s1)

def build_graph_json(adm, case_set, evaluated_set):
    """
    Builds graph data with strict priority coloring:
    1. IN CASE -> GREEN (Accepted)
    2. NOT IN CASE but EVALUATED -> RED (Rejected)
    3. ELSE -> GREY (Unknown)
    """
    nodes = []
    links = []

    # Identify shape types
    issue_nodes = []
    if hasattr(adm, 'root_node') and adm.root_node.children:
        issue_nodes = adm.root_node.children

    for name, node in adm.nodes.items():
        
        # --- ROBUST COLORING LOGIC ---
        # 1. Accepted: Explicitly in the final case list
        if name in case_set:
            color = "#90EE90" # Light Green
            status = "ACCEPTED"
            stmt = node.statement[0] if (node.statement and len(node.statement) > 0) else "Accepted"
            
        # 2. Rejected: Not in case, but definitively False by ADM logic
        else:
            # We run the 3VL check. 
            # If evaluateNode returns False, it is rejected.
            # If evaluateNode returns None, it is Unknown.
            res, _ = adm.evaluateNode(node, mode='3vl')
            
            if res is False:
                color = "#FFB6C1" # Light Red
                status = "REJECTED"
                stmt = node.statement[-1] if (node.statement and len(node.statement) > 0) else "Rejected"
            else:
                color = "#E2E8F0" # Grey
                status = "UNKNOWN"
                stmt = "Not evaluated."

        # Shape Logic
        if hasattr(adm, 'root_node') and name == adm.root_node.name:
            shape = "rect"
        elif name in issue_nodes:
            shape = "ellipse"
        elif node.children:
            shape = "ellipse"
        else:
            shape = "rect"

        nodes.append({
            "id": name,
            "label": split_camel_case(name),
            "label_raw": name,
            "color": color,
            "shape": shape,
            "status": status,
            "statement": stmt
        })

    # Edges
    for name, node in adm.nodes.items():
        if node.children:
            for child in node.children:
                edge_label = "+"
                if node.acceptance:
                    for condition in node.acceptance:
                        tokens = condition.split()
                        if child in tokens:
                            if 'reject' in tokens or 'not' in tokens:
                                edge_label = "-"
                                break
                
                links.append({
                    "source": name,
                    "target": child,
                    "label": edge_label
                })

    return {"nodes": nodes, "links": links}

def generate_dashboard(adm, input_case, evaluated_nodes, filename="adm_split_dashboard.html"):
    print(f"Generating Dashboard: {filename}")

    # 1. Run ADM
    adm.evaluateTree(input_case)
    final_case_set = set(adm.case)
    adm.evaluated_nodes = set(evaluated_nodes)

    # 2. Build Data
    graph_data = build_graph_json(adm, final_case_set, adm.evaluated_nodes)
    
    # 3. Escape for JS injection
    json_str = json.dumps(graph_data)
    markdown_safe = MARKDOWN_CONTENT.replace("`", "\\`") 

    # 4. Inject
    html = HTML_TEMPLATE.replace("__GRAPH_JSON__", json_str)
    html = html.replace("__MARKDOWN_TEXT__", markdown_safe)
    
    with open(filename, "w", encoding='utf-8') as f:
        f.write(html)
        
    print("Done. Opening...")
    webbrowser.open(f"file://{os.path.abspath(filename)}")

# --- MAIN ---
if __name__ == "__main__":
    adm = adm_initial()
    test_inputs = ['CommonKnowledge'] 
    test_evaluated = ['CommonKnowledge', 'SimilarEffect', 'SameField', 'SimilarPurpose', 'SimilarField']
    generate_dashboard(adm, test_inputs, test_evaluated)