import json
import os
import sys
import webbrowser
import re

# --- 1. IMPORT ADM ---
try:
    from new_inventive_step_ADM import adm_initial
except ImportError:
    try:
        from new_UI import adm_initial
    except ImportError:
        print("CRITICAL ERROR: Could not import adm_initial.")
        sys.exit(1)

# --- 2. HTML TEMPLATE (DAGRE-D3) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>ADM Dashboard</title>
    
    <script src="https://d3js.org/d3.v5.min.js"></script>
    <script src="https://dagrejs.github.io/project/dagre-d3/latest/dagre-d3.min.js"></script>
    
    <style>
        body { margin: 0; overflow: hidden; font-family: 'Segoe UI', sans-serif; background-color: #f8fafc; }
        #graph-container { width: 100vw; height: 100vh; display: flex; justify-content: center; align-items: center; background: radial-gradient(circle at center, #ffffff 0%, #f1f5f9 100%); }
        
        /* HEADER */
        .header {
            position: absolute; top: 20px; left: 30px; background: rgba(255, 255, 255, 0.95);
            padding: 15px 25px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); 
            border: 1px solid #e2e8f0; pointer-events: none; z-index: 999;
        }
        h1 { margin: 0; font-size: 18px; color: #0f172a; }

        /* LEGEND */
        .legend {
            position: absolute; bottom: 30px; right: 30px; background: white; padding: 20px; 
            border-radius: 12px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1); 
            border: 1px solid #e2e8f0; font-size: 12px; font-weight: 600; color: #475569; z-index: 999;
        }
        .legend-item { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
        .dot { width: 12px; height: 12px; border: 1px solid #333; }

        /* GRAPH STYLES */
        g.node rect, g.node ellipse, g.node polygon { stroke: #333; stroke-width: 1.5px; cursor: pointer; transition: all 0.2s; }
        g.node:hover rect, g.node:hover ellipse { stroke: #3b82f6; stroke-width: 3px; }
        g.node text { font-family: 'Arial'; font-size: 14px; pointer-events: none; }
        
        g.edgePath path { stroke: #64748b; stroke-width: 1.5px; fill: none; }
        g.edgeLabel rect { fill: #fff; opacity: 0.8; }
        g.edgeLabel tspan { font-size: 14px; font-weight: bold; }

        /* TOOLTIP */
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
    </style>
</head>
<body>
    <div class="header"><h1>ADM Dashboard</h1><div style="font-size:12px; color:#64748b;">Live Status Visualization</div></div>
    
    <div class="legend">
        <div class="legend-item"><div class="dot" style="background:#90EE90"></div> Accepted (Present in Case)</div>
        <div class="legend-item"><div class="dot" style="background:#FFB6C1"></div> Rejected (Evaluated False)</div>
        <div class="legend-item"><div class="dot" style="background:#E2E8F0"></div> Unknown (Not reached)</div>
        <div style="height:1px; background:#e2e8f0; margin: 8px 0;"></div>
        <div class="legend-item">Ellipse: Issue / Sub-Node</div>
        <div class="legend-item">Rect: Leaf Factor</div>
    </div>

    <svg id="graph-container"><g/></svg>
    <div id="tooltip" class="tooltip"></div>

    <script>
        // --- 1. INITIALIZE VARIABLES FIRST (Fixes JS Errors) ---
        var tooltip = d3.select("#tooltip");
        var graphData = __GRAPH_JSON__;

        function hideTooltip() {
            tooltip.style("opacity", 0);
            setTimeout(() => { if(tooltip.style('opacity')==0) tooltip.style('left', '-9999px')}, 200);
        }

        // --- 2. SETUP GRAPH ---
        var g = new dagreD3.graphlib.Graph().setGraph({
            rankdir: 'TB',
            nodesep: 60,
            ranksep: 80,
            marginx: 40,
            marginy: 40
        });

        // Add Nodes
        graphData.nodes.forEach(function(node) {
            g.setNode(node.id, {
                label: node.label,
                class: node.id,
                shape: node.shape,
                style: `fill: ${node.color}`,
                labelStyle: "font-weight: bold; fill: #000;",
                description: node // Store data for click
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

        // --- 3. RENDER ---
        var render = new dagreD3.render();
        var svg = d3.select("svg");
        var svgGroup = svg.select("g");

        render(svgGroup, g);

        // --- 4. ZOOM ---
        var zoom = d3.zoom().on("zoom", function() {
            svgGroup.attr("transform", d3.event.transform);
            hideTooltip();
        });
        svg.call(zoom);

        // Initial Center
        var initialScale = 0.85;
        svg.call(zoom.transform, d3.zoomIdentity.translate((window.innerWidth - g.graph().width * initialScale) / 2, 40).scale(initialScale));

        // --- 5. INTERACTIVITY ---
        svg.selectAll("g.node").on("click", function(id) {
            d3.event.stopPropagation();
            
            var nodeData = g.node(id).description;
            var mouse = d3.mouse(document.body); // D3 v5 syntax
            var x = mouse[0];
            var y = mouse[1];

            // Badge Logic
            let badgeColor = "#475569"; 
            let badgeBg = "#f1f5f9";
            
            if (nodeData.status === "ACCEPTED") {
                badgeColor = "#166534"; badgeBg = "#dcfce7";
            } else if (nodeData.status === "REJECTED") {
                badgeColor = "#991b1b"; badgeBg = "#fee2e2";
            }

            tooltip.html(`
                <div class="tooltip-header">
                    <span>${nodeData.label_raw}</span>
                    <span style="background:${badgeBg}; color:${badgeColor}; padding:2px 6px; border-radius:4px; font-size:10px;">${nodeData.status}</span>
                </div>
                <div class="tooltip-body">
                    <div style="font-size:10px; font-weight:800; color:#94a3b8; margin-bottom:4px;">STATEMENT</div>
                    <div class="statement-text">${nodeData.statement}</div>
                </div>
            `);

            tooltip.style("left", x + "px")
                   .style("top", y + "px")
                   .style("opacity", 1);
        });

        d3.select("body").on("click", function() {
            hideTooltip();
        });

    </script>
</body>
</html>
"""

# --- 3. PYTHON LOGIC ---

def split_camel_case(name):
    # Splits "ClosestPriorArt" -> "Closest\nPrior\nArt" for display
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

def generate_dashboard(adm, input_case, evaluated_nodes, filename="adm_viz_dashboard.html"):
    print(f"Generating Dashboard: {filename}")

    # --- CRITICAL: RUN ADM EVALUATION FIRST ---
    # This populates adm.case with ALL nodes that are implied True.
    # This guarantees that non-leaf nodes (like RelevantPriorArt) turn Green
    # if their conditions are met.
    adm.evaluateTree(input_case)
    
    # adm.case now contains inputs + inferred nodes
    final_case_set = set(adm.case)
    evaluated_set = set(evaluated_nodes)
    
    # We also update the ADM object's internal state so evaluateNode(3vl) works for Rejections
    adm.evaluated_nodes = evaluated_set

    # Build Data
    graph_data = build_graph_json(adm, final_case_set, evaluated_set)
    json_str = json.dumps(graph_data)
    
    # Inject
    html = HTML_TEMPLATE.replace("__GRAPH_JSON__", json_str)
    
    with open(filename, "w", encoding='utf-8') as f:
        f.write(html)
        
    print("Done. Opening in browser...")
    webbrowser.open(f"file://{os.path.abspath(filename)}")

# --- MAIN ---
if __name__ == "__main__":
    adm = adm_initial()
    
    # TEST DATA
    # Input: 'CommonKnowledge' is True.
    # Logic: CommonKnowledge -> Implies -> RelevantPriorArt -> Implies -> Valid (Root)
    # Result: All three should be GREEN.
    test_inputs = ['SimilarPurpose', 'Contested', 'RelevantPriorArt']
    
    # We pass empty list for evaluated if we just want to see what is Accepted.
    # Or pass explicit list if we want to show Rejections.
    test_evaluated = ['SinglePublication', 'SimilarField', 'SimilarEffect', 'SimilarPurpose', 'Textbook', 'PublicationNewField', 'SameField', 'Contested', 'TechnicalSurvey']
    
    generate_dashboard(adm, test_inputs, test_evaluated)