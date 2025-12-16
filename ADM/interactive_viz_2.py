import json
import os
import sys
import webbrowser
import glob
import re
import threading
import queue
import time
import builtins
import logging
from http.server import HTTPServer, SimpleHTTPRequestHandler

# --- 1. IMPORT ADM LOGIC ---
try:
    from inventive_step_ADM import adm_initial, adm_main, sub_adm_1, sub_adm_2
except ImportError:
    try:
        from ADM_JURIX.ADM.inventive_step_ADM import adm_initial, adm_main, sub_adm_1, sub_adm_2
    except ImportError:
        print("CRITICAL ERROR: Could not import ADM factory functions.")
        sys.exit(1)

# Import CLI for execution
try:
    from UI import CLI
    CLI_AVAILABLE = True
except ImportError:
    CLI_AVAILABLE = False
    print("Warning: 'UI.py' not found. CLI features disabled.")

# --- 2. CONFIGURATION ---
CASES_DIR = "./Eval_Cases"
PORT = 8000

SUB_ADM_CONFIG = {
    "ReliableTechnicalEffect": { "factory": sub_adm_1, "label": "Technical Effect" },
    "sub_adm_1": { "factory": sub_adm_1, "label": "Technical Effect" },
    "OTPObvious": { "factory": sub_adm_2, "label": "Objective Problem" },
    "sub_adm_2": { "factory": sub_adm_2, "label": "Objective Problem" }
}

# --- 3. IO INTERCEPTION (THE BRIDGE) ---
class IOBridge:
    def __init__(self):
        self.output_queue = queue.Queue()
        self.input_queue = queue.Queue()
        self.active = False
        self.original_stdout = sys.stdout # Keep reference to real stdout

    def write(self, text):
        if not text: return
        # FILTER: If it looks like a system log, print to TERMINAL ONLY
        if text.startswith("[INFO]") or text.startswith("[DEBUG]") or text.startswith("> Scanning") or "Scanning case:" in text:
            self.original_stdout.write(text + "\n")
        else:
            # Otherwise, send to WEB UI
            self.output_queue.put(text)
    
    def flush(self): 
        self.original_stdout.flush()

    def get_output(self):
        lines = []
        while not self.output_queue.empty(): lines.append(self.output_queue.get())
        return "".join(lines)

    def send_input(self, text): self.input_queue.put(text)

io_bridge = IOBridge()

def web_input(prompt=""):
    # Send the prompt to the UI before waiting
    if prompt:
        io_bridge.write(prompt)
    return io_bridge.input_queue.get()

# --- 4. HTML TEMPLATE ---
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
        body { margin: 0; padding: 0; font-family: 'Segoe UI', system-ui, sans-serif; background-color: #f8fafc; height: 100vh; display: flex; overflow: hidden; }
        
        #report-panel { 
            width: 450px; min-width: 350px; background: white; border-right: 1px solid #e2e8f0; 
            overflow-y: auto; padding: 40px; z-index: 10; display: flex; flex-direction: column;
            transition: all 0.3s ease; 
            white-space: normal;
        }
        #report-panel.collapsed { width: 0 !important; min-width: 0 !important; padding: 0 !important; border: none; opacity: 0; overflow: hidden; }
        #report-content { font-size: 14px; color: #334155; line-height: 1.6; flex-grow: 1; min-width: 300px; }
        #report-content img { max-width: 100%; border-radius: 6px; border: 1px solid #e2e8f0; margin: 10px 0; }
        
        #graph-panel { flex-grow: 1; position: relative; background: radial-gradient(circle at center, #ffffff 0%, #f8fafc 100%); display: flex; flex-direction: column; }
        
        #wizard-panel { 
            display: none; position: absolute; top: 0; left: 0; width: 100%; height: 100%; 
            background: #f1f5f9; z-index: 50; flex-direction: column;
        }
        .close-wiz-btn {
            position: absolute; top: 20px; right: 20px; width: 40px; height: 40px; 
            border-radius: 50%; background: white; border: 1px solid #cbd5e1; 
            color: #64748b; font-size: 24px; line-height: 40px; text-align: center;
            cursor: pointer; z-index: 60; transition: all 0.2s;
        }
        .close-wiz-btn:hover { background: #fee2e2; color: #991b1b; border-color: #fecaca; }
        
        #wiz-output {
            flex-grow: 1; padding: 40px; overflow-y: auto; display: flex; flex-direction: column; gap: 15px;
            scroll-behavior: smooth; padding-bottom: 20px;
        }

        .chat-bubble {
            background: white; border-radius: 12px; padding: 20px; 
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
            max-width: 800px; margin: 0 auto; width: 100%;
            animation: slideIn 0.3s ease-out; border-left: 4px solid #3b82f6;
        }
        @keyframes slideIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

        .context-header {
            font-size: 12px; font-weight: bold; color: #3b82f6; text-transform: uppercase; letter-spacing: 0.5px;
            margin-bottom: 8px; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px;
        }

        .reasoning-box { background: #f8fafc; border: 1px solid #e2e8f0; padding: 15px; border-radius: 8px; margin-top: 10px; }
        .reasoning-header { font-weight: bold; color: #475569; margin-bottom: 8px; text-transform: uppercase; font-size: 12px; letter-spacing: 0.5px; }
        .reasoning-desc { font-style: italic; color: #64748b; margin-bottom: 10px; font-size: 14px; display: block; }
        .reasoning-list { list-style: none; padding: 0; margin: 0; }
        .reasoning-list li { padding-left: 20px; position: relative; margin-bottom: 6px; color: #334155; font-size: 14px; }
        .reasoning-list li::before { content: "•"; position: absolute; left: 0; color: #cbd5e1; font-weight: bold; }
        
        .outcome-badge { 
            display: inline-block; padding: 4px 12px; border-radius: 20px; 
            font-weight: bold; font-size: 14px; margin-bottom: 10px; margin-right: 5px;
        }
        .outcome-rejected { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
        .outcome-accepted { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
        
        .stage-divider { text-align: center; margin: 20px 0; }
        .stage-divider span { background: #e2e8f0; color: #475569; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: bold; }

        .interview-question { font-size: 16px; font-weight: 700; color: #1e293b; margin-bottom: 8px; }
        .interview-answer { font-size: 15px; color: #475569; line-height: 1.5; }
        
        #wiz-input-container {
            padding: 20px; background: white; border-top: 1px solid #e2e8f0;
            display: flex; justify-content: center; align-items: center; min-height: 100px;
            flex-shrink: 0; 
        }

        .yes-no-group { display: flex; gap: 20px; }
        .yn-btn { width: 100px; padding: 12px; text-align: center; border-radius: 8px; cursor: pointer; font-weight: bold; transition: all 0.2s; border: 2px solid transparent; }
        .yn-yes { background: #dcfce7; color: #166534; border-color: #bbf7d0; }
        .yn-yes:hover { background: #166534; color: white; }
        .yn-no { background: #fee2e2; color: #991b1b; border-color: #fecaca; }
        .yn-no:hover { background: #991b1b; color: white; }

        .btn-group { display: flex; flex-direction: column; gap: 8px; width: 100%; max-width: 600px; }
        .option-btn { background: white; border: 1px solid #e2e8f0; padding: 12px 16px; border-radius: 8px; cursor: pointer; display: flex; gap: 12px; align-items: center; transition: all 0.2s; }
        .option-btn:hover { border-color: #3b82f6; background: #eff6ff; }
        .option-number { background: #e2e8f0; color: #475569; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; border-radius: 50%; font-size: 12px; font-weight: bold; }

        .text-input-group { display: flex; gap: 10px; width: 100%; max-width: 600px; }
        .wizard-text-input { flex-grow: 1; padding: 12px; border: 1px solid #cbd5e1; border-radius: 8px; outline: none; font-size: 15px; }
        .wizard-text-input:focus { border-color: #3b82f6; box-shadow: 0 0 0 2px rgba(59,130,246,0.1); }
        .finish-btn { background: #1e293b; color: white; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-weight: bold; border: none; margin-top: 10px; }
        .finish-btn:hover { background: #334155; }

        .top-bar { display: flex; justify-content: space-between; align-items: center; padding: 15px 25px; background: rgba(255,255,255,0.95); border-bottom: 1px solid #e2e8f0; z-index: 20; }
        .tabs { display: flex; gap: 10px; }
        .btn { padding: 8px 16px; border: 1px solid #e2e8f0; background: white; border-radius: 20px; font-size: 13px; font-weight: 600; color: #64748b; cursor: pointer; transition: all 0.2s; }
        .btn:hover { background: #f1f5f9; color: #0f172a; }
        .btn.active { background: #0f172a; color: white; border-color: #0f172a; }
        .btn.create { background: #16a34a; color: white; border-color: #15803d; }
        
        #svg-wrapper { flex-grow: 1; overflow: hidden; position: relative; }
        svg { width: 100%; height: 100%; display: block; }
        g.node rect, g.node ellipse { stroke: #333; stroke-width: 1.5px; cursor: pointer; transition: all 0.2s; }
        .tooltip { position: fixed; opacity: 0; pointer-events: none; background: white; border-radius: 8px; box-shadow: 0 20px 25px rgba(0,0,0,0.15); width: 340px; z-index: 1000; font-family: sans-serif; }
        .tooltip-header { padding: 12px 16px; background: #f1f5f9; font-weight: 700; color: #0f172a; display: flex; justify-content: space-between; border-radius: 8px 8px 0 0; }
        .tooltip-body { padding: 16px; font-size: 13px; color: #334155; }
        .condition-item { padding: 6px 8px; margin-bottom: 4px; background: #f8fafc; border: 1px solid #e2e8f0; font-family: monospace; }
        .condition-item.active { background: #ecfdf5; border-color: #10b981; color: #065f46; font-weight: bold; }
        .dropdown { position: relative; display: inline-block; }
        .dropdown-content { display: none; position: absolute; top: 100%; left: 0; background: white; min-width: 180px; box-shadow: 0 10px 25px rgba(0,0,0,0.15); border-radius: 12px; z-index: 50; padding: 5px; }
        .dropdown:hover .dropdown-content { display: block; }
        .dropdown-item { padding: 8px 12px; cursor: pointer; font-size: 13px; color: #475569; }
        .dropdown-item:hover { background: #f8fafc; color: #0f172a; }
        .case-selector { position: relative; }
        .case-list { display: none; position: absolute; top: 100%; right: 0; background: white; border: 1px solid #e2e8f0; border-radius: 8px; width: 200px; padding: 5px; z-index: 100; box-shadow: 0 10px 25px rgba(0,0,0,0.1); }
        .case-selector:hover .case-list { display: block; }
    </style>
</head>
<body>
    <div id="report-panel"><div id="report-content">Select a case...</div></div>
    <div id="graph-panel">
        <div class="top-bar">
            <button class="btn" onclick="toggleReport()" title="Toggle Report Panel" style="margin-right:15px; padding: 8px 12px;">☰</button>
            <div class="tabs" id="tab-bar"></div>
            <div style="display:flex; gap:10px;">
                <button class="btn create" onclick="startNewCase()">+ New Case</button>
                <div class="case-selector"><button class="btn" id="current-case-btn">Select Case ▼</button><div class="case-list" id="case-list"></div></div>
            </div>
        </div>
        <div id="svg-wrapper"><svg><g/></svg></div>
        <div id="wizard-panel"><div class="close-wiz-btn" onclick="quitWizard()">×</div><div id="wiz-output"></div><div id="wiz-input-container"></div></div>
        <div id="tooltip" class="tooltip"></div>
    </div>
    <script>
        const allCases = __ALL_CASES_JSON__;
        let wizInterval = null;
        const wizOutput = document.getElementById('wiz-output');
        const wizInputContainer = document.getElementById('wiz-input-container');
        const wizPanel = document.getElementById('wizard-panel');
        let currentFeatureContext = ""; 

        function toggleReport() { document.getElementById('report-panel').classList.toggle('collapsed'); }
        function startNewCase() {
            wizPanel.style.display = 'flex';
            document.getElementById('svg-wrapper').style.display = 'none';
            document.getElementById('report-panel').classList.add('collapsed');
            wizOutput.innerHTML = '<div class="chat-bubble">Starting ADM Wizard...</div>';
            currentFeatureContext = "";
            fetch('/start_cli', { method: 'POST' });
            if (wizInterval) clearInterval(wizInterval);
            wizInterval = setInterval(pollWizard, 200);
        }
        function quitWizard() {
             wizPanel.style.display = 'none';
             document.getElementById('svg-wrapper').style.display = 'block';
             if (wizInterval) clearInterval(wizInterval);
             location.reload(); 
        }

        async function pollWizard() {
            try {
                const res = await fetch('/poll_output');
                const text = await res.text();
                if (text && text.trim().length > 0) processWizardText(text);
            } catch (e) { console.error(e); }
        }
        
        function createBubble(htmlContent) {
            if (!htmlContent) return;
            const bubble = document.createElement('div');
            bubble.className = 'chat-bubble';
            bubble.innerHTML = htmlContent;
            wizOutput.appendChild(bubble);
            requestAnimationFrame(() => wizOutput.scrollTop = wizOutput.scrollHeight);
        }

        function processWizardText(text) {
            const isFinished = text.includes("CASE COMPLETE") || text.includes("Goodbye");
            const isYesNo = text.toLowerCase().includes("(y/n)");
            const hasOptions = /(\\d+)\\.\\s+(.*)/.test(text);
            const rawLines = text.split(/\\r?\\n/);
            
            let displayHtml = "";
            let inReasoning = false;
            let reasoningBuffer = { desc: "", items: [] };
            let outcomeShown = false; 

            // Strict Block list for System Noise
            const IGNORE_PATTERNS = [
                "===", "---", "[Early Stop]", 
                "Completed asking questions", 
                "Answer (y/n):", "ADM summary saved",
                // Specific internal status logs we want to hide entirely
                "Total items:", "Accepted:", "Rejected:", 
                "is ACCEPTED", "is REJECTED", 
                "IN sub-ADM cases", "found in any sub-ADM cases", 
                "found 1 accepted item", "found 0 accepted item"
            ];

            const flushReasoning = () => {
                if (!inReasoning) return;
                let html = `<div class="reasoning-box"><div class="reasoning-header">Reasoning Trace</div>`;
                
                // Clean up description noise
                let cleanDesc = reasoningBuffer.desc.replace(/Completed asking questions.*?$/i, "").trim();
                if(cleanDesc && cleanDesc.length > 5) {
                    html += `<div class="reasoning-desc">${cleanDesc}</div>`;
                }
                
                if(reasoningBuffer.items.length > 0) {
                    html += `<ul class="reasoning-list">`;
                    reasoningBuffer.items.forEach(i => html += `<li>${i}</li>`);
                    html += `</ul>`;
                }
                html += `</div>`;
                displayHtml += html;
                inReasoning = false;
                reasoningBuffer = { desc: "", items: [] };
            };

            rawLines.forEach(line => {
                line = line.trim();
                if (!line) return;

                // --- 1. CAPTURE FEATURE CONTEXT ---
                if (line.includes("Evaluating sub-ADM for")) {
                    const match = line.match(/Evaluating sub-ADM for\s+(.*?)(\.\.\.|\[|$)/);
                    if (match) {
                        currentFeatureContext = match[1].replace(/['"]/g, "").trim();
                    }
                    return; 
                }

                // --- 2. DETECT & CLEAN STATUS LINE (The Fix for Wrong Badge) ---
                // Matches lines like: "The feature is... - b REJECTED (Reason...)"
                const statusMatch = line.match(/^(.*?) - .*? (ACCEPTED|REJECTED) \(.*?\)$/);
                if (statusMatch) {
                    // It's the root reasoning line
                    const cleanText = statusMatch[1].trim();
                    const status = statusMatch[2]; // ACCEPTED or REJECTED
                    
                    if (!outcomeShown) {
                        if (status === 'REJECTED') {
                            displayHtml += `<div class="outcome-badge outcome-rejected">🛑 REJECTED</div>`;
                        } else {
                            displayHtml += `<div class="outcome-badge outcome-accepted">✅ ACCEPTED</div>`;
                        }
                        outcomeShown = true;
                    }
                    
                    // Add the cleaned text to reasoning buffer if we are in reasoning mode
                    // Or start reasoning mode if not started
                    if (!inReasoning) inReasoning = true;
                    reasoningBuffer.desc += cleanText + " ";
                    
                    return; // Skip standard processing for this line
                }
                
                // --- 3. NOISE FILTER ---
                if (IGNORE_PATTERNS.some(p => line.includes(p))) return;

                // --- 4. DETECT QUESTION (Force Bubble Break) ---
                const qMatch = line.match(/^\\[Q\\d*\\]\\s*(.*)/);
                const isPlainQuestion = line.endsWith("?") && line.length < 150 && !inReasoning;
                
                if (qMatch || isPlainQuestion) {
                    flushReasoning();
                    if (displayHtml) { createBubble(displayHtml); displayHtml = ""; outcomeShown = false; }
                    
                    if (currentFeatureContext) {
                        displayHtml += `<div class="context-header">Evaluating: ${currentFeatureContext}</div>`;
                    }
                    
                    const qText = qMatch ? qMatch[1] : line;
                    displayHtml += `<div class="interview-question">${qText}</div>`;
                    return;
                }

                // --- STAGE TRANSITION ---
                if (line.includes("Preconditions met") || line.includes("Proceeding to Main")) {
                    flushReasoning();
                    displayHtml += `<div class="stage-divider"><span>✔ INITIAL ADM PASSED — PROCEEDING TO MAIN</span></div>`;
                    createBubble(displayHtml);
                    displayHtml = "";
                    currentFeatureContext = ""; 
                    return; 
                }

                // --- FALLBACK OUTCOME (Explicit "Valid is REJECTED") ---
                if (line.includes("Valid is REJECTED") && !outcomeShown) {
                    displayHtml += `<div class="outcome-badge outcome-rejected">🛑 REJECTED</div>`;
                    outcomeShown = true; 
                    return;
                }

                if (line.includes("Case Outcome:")) {
                    flushReasoning();
                    displayHtml += `<h2>${line}</h2>`;
                    return;
                }

                // --- REASONING BLOCK START ---
                if (line.startsWith("Reasoning") || line.startsWith("Reasoning Trace")) {
                    flushReasoning();
                    inReasoning = true;
                    outcomeShown = false; 
                    return;
                }

                if (inReasoning) {
                    if (line.startsWith("└─")) {
                         reasoningBuffer.items.push(line.substring(2).trim());
                    } else { 
                         reasoningBuffer.desc += line + " ";
                    }
                } else {
                    displayHtml += `<div class="interview-answer">${line}</div>`;
                }
            });
            
            flushReasoning();
            createBubble(displayHtml);
            wizInputContainer.innerHTML = '';

            if (isFinished) {
                const finishDiv = document.createElement('div');
                finishDiv.className = 'chat-bubble';
                finishDiv.style.textAlign = 'center';
                finishDiv.innerHTML = `<h3>Case Closed</h3><p>The reasoning process is complete.</p><button class="finish-btn" onclick="quitWizard()">Return to Dashboard</button>`;
                wizOutput.appendChild(finishDiv);
                wizOutput.scrollTop = wizOutput.scrollHeight;
                return;
            }

            if (isYesNo) {
                wizInputContainer.innerHTML = `<div class="yes-no-group"><div class="yn-btn yn-yes" onclick="sendWizardAnswer('y')">Yes</div><div class="yn-btn yn-no" onclick="sendWizardAnswer('n')">No</div></div>`;
            } else if (hasOptions) {
                const matches = [...text.matchAll(/(\\d+)\\.\\s+(.*)/g)];
                let btnHtml = '<div class="btn-group">';
                matches.forEach(m => {
                    btnHtml += `<div class="option-btn" onclick="sendWizardAnswer('${m[1]}')"><span class="option-number">${m[1]}</span><span>${m[2]}</span></div>`;
                });
                btnHtml += '</div>';
                wizInputContainer.innerHTML = btnHtml;
            } else {
                wizInputContainer.innerHTML = `<div class="text-input-group"><input type="text" class="wizard-text-input" id="wiz-text-in" placeholder="Type answer..." autocomplete="off"><button class="btn active" onclick="submitWizardText()">Send</button></div>`;
                setTimeout(() => {
                    const inp = document.getElementById('wiz-text-in');
                    if(inp) { inp.focus(); inp.onkeypress = (e) => { if(e.key==='Enter') submitWizardText(); }; }
                }, 100);
            }
        }

        async function sendWizardAnswer(val) {
            createBubble(`<div style="text-align:right; font-weight:bold;">${val}</div>`);
            wizInputContainer.innerHTML = '<div style="color:#94a3b8; font-style:italic;">Processing...</div>';
            await fetch('/send_input', { method: 'POST', body: val });
        }
        async function submitWizardText() {
            const inp = document.getElementById('wiz-text-in');
            if(!inp) return;
            const val = inp.value;
            createBubble(`<div style="text-align:right;">${val}</div>`);
            wizInputContainer.innerHTML = '<div style="color:#94a3b8; font-style:italic;">Processing...</div>';
            await fetch('/send_input', { method: 'POST', body: val });
        }

        // --- GRAPH & D3 ---
        var tooltip = d3.select("#tooltip"), svg = d3.select("svg"), inner = svg.select("g");
        var zoom = d3.zoom().on("zoom", () => { inner.attr("transform", d3.event.transform); tooltip.style("opacity", 0).style("left", "-9999px"); });
        svg.call(zoom);
        var render = new dagreD3.render();

        function loadCase(caseName) {
            wizPanel.style.display = 'none';
            document.getElementById('svg-wrapper').style.display = 'block';
            document.getElementById('report-panel').classList.remove('collapsed');
            if(wizInterval) clearInterval(wizInterval);

            const caseData = allCases[caseName];
            if (!caseData) return;
            let mdText = caseData.markdown || "";
            if (mdText) mdText = mdText.replace(/!\[(.*?)\]\((?!http|\/)(.*?)\)/g, (match, alt, url) => `![${alt}](/Eval_Cases/${caseName}/${url})`);
            
            document.getElementById('report-content').innerHTML = marked.parse(mdText);
            const tabBar = document.getElementById("tab-bar");
            tabBar.innerHTML = "";
            document.getElementById("current-case-btn").innerText = caseName;

            const orderedConfig = [];
            const singleItems = caseData.config.filter(i => i.type === 'single');
            const groupItems = caseData.config.filter(i => i.type === 'group');

            singleItems.forEach(i => orderedConfig.push(i));
            const techEff = groupItems.find(i => i.name === 'Technical Effect');
            if(techEff) orderedConfig.push(techEff);
            const objProb = groupItems.find(i => i.name === 'Objective Problem');
            if(objProb) orderedConfig.push(objProb);
            groupItems.forEach(i => {
                if (i.name !== 'Technical Effect' && i.name !== 'Objective Problem') orderedConfig.push(i);
            });

            orderedConfig.forEach((item, index) => {
                if (item.type === 'single') {
                    const btn = document.createElement("div");
                    btn.className = "btn"; btn.innerText = item.name;
                    btn.onclick = () => { clearActive(); btn.classList.add("active"); drawGraph(item.data); };
                    if (index === 0) btn.click();
                    tabBar.appendChild(btn);
                } else {
                    const drop = document.createElement("div"); drop.className = "dropdown";
                    const btn = document.createElement("div"); btn.className = "btn"; btn.innerText = item.name + " ▼";
                    drop.appendChild(btn);
                    const content = document.createElement("div"); content.className = "dropdown-content";
                    item.options.forEach(opt => {
                        const link = document.createElement("div"); link.className = "dropdown-item"; link.innerText = opt.name;
                        link.onclick = () => { clearActive(); btn.classList.add("active"); drawGraph(opt.data); };
                        content.appendChild(link);
                    });
                    drop.appendChild(content); tabBar.appendChild(drop);
                }
            });
        }
        function clearActive() { document.querySelectorAll('.btn').forEach(el => { if (!el.classList.contains('create')) el.classList.remove('active'); }); }
        function drawGraph(graphData) {
            inner.selectAll("*").remove();
            var g = new dagreD3.graphlib.Graph().setGraph({ rankdir: 'TB', nodesep: 60, ranksep: 80, marginx: 40, marginy: 40 });
            graphData.nodes.forEach(n => { g.setNode(n.id, { label: n.label, class: n.id, shape: n.shape, style: `fill: ${n.color}`, labelStyle: "font-weight: bold; fill: #000;", description: n }); });
            graphData.links.forEach(l => { g.setEdge(l.source, l.target, { label: l.label, curve: d3.curveBasis, style: "stroke: #64748b; fill: none;", arrowheadStyle: "fill: #64748b" }); });
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
                let conditionsHtml = d.conditions.length > 0 ? d.conditions.map((c,i) => `<div class="condition-item${(d.status==="ACCEPTED"&&i===d.active_index)?" active":""}">${c}</div>`).join('') : "<i>No conditions.</i>";
                tooltip.html(`<div class="tooltip-header"><span>${d.label_raw}</span><span style="background:${bBg}; color:${bCol}; padding:2px 6px; border-radius:4px; font-size:10px;">${d.status}</span></div><div class="tooltip-body"><div style="margin-bottom:10px;">${d.statement}</div><div style="font-weight:700; color:#94a3b8; font-size:10px; margin-bottom:5px;">CONDITIONS</div>${conditionsHtml}</div>`);
                tooltip.style("left", m[0]+"px").style("top", m[1]+"px").style("opacity", 1);
            });
        }
        const caseList = document.getElementById("case-list");
        Object.keys(allCases).forEach(name => {
            const div = document.createElement("div"); div.className = "dropdown-item"; div.innerText = name;
            div.onclick = () => loadCase(name); caseList.appendChild(div);
        });
        d3.select("body").on("click", () => tooltip.style("opacity", 0).style("left", "-9999px"));
        const keys = Object.keys(allCases);
        if (keys.length > 0) loadCase(keys[0]);
    </script>
</body>
</html>
"""

# --- 5. DATA BUILDER (VIZ) ---
def split_camel_case(name):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1\n\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1\n\2', s1)

def evaluate_condition_flat(condition_str, case_set):
    """Simple check if a condition string is satisfied by case_set."""
    if ' ' not in condition_str: return condition_str in case_set
    tokens = condition_str.replace('(', ' ').replace(')', ' ').split()
    # Simplified boolean logic approximation for highlighting
    # If any non-keyword token is missing, consider condition false
    for t in tokens:
        if t not in ['and', 'or', 'not', 'accept', 'reject'] and t not in case_set:
            return False
    return True

def build_graph_data(adm_factory, json_path, item_name=None):
    if not os.path.exists(json_path): return None
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    case_set = set(data.get('case', [])) if isinstance(data, dict) else set()
    
    adm = adm_factory(item_name) if item_name else adm_factory()
    adm.case = list(case_set)

    nodes = []
    links = []
    issue_nodes = getattr(adm.root_node, 'children', []) if hasattr(adm, 'root_node') else []

    for name, node in adm.nodes.items():
        status = "ACCEPTED" if name in case_set else "REJECTED"
        color = "#90EE90" if status == "ACCEPTED" else "#FFB6C1"
        stmt = node.statement[0] if status == "ACCEPTED" and node.statement else (node.statement[-1] if node.statement else status)
        
        active_index = -1
        if status == "ACCEPTED" and node.acceptance:
            for i, cond in enumerate(node.acceptance):
                if evaluate_condition_flat(cond, case_set):
                    active_index = i; break
        
        shape = "rect"
        if hasattr(adm, 'root_node') and name == adm.root_node.name: shape = "rect"
        elif name in issue_nodes or node.children: shape = "ellipse"

        nodes.append({
            "id": name, "label": split_camel_case(name), "label_raw": name,
            "color": color, "shape": shape, "status": status, "statement": stmt,
            "conditions": getattr(node, 'acceptanceOriginal', node.acceptance) or [],
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

def scan_cases():
    all_cases = {}
    if not os.path.exists(CASES_DIR): os.makedirs(CASES_DIR)
    
    print("\n[INFO] Scanning for cases...")
    case_folders = [f for f in os.listdir(CASES_DIR) if os.path.isdir(os.path.join(CASES_DIR, f))]
    
    for case_name in case_folders:
        case_path = os.path.join(CASES_DIR, case_name)
        print(f"  > Scanning case: {case_name}")
        
        # --- ROBUST LOG FINDER ---
        md_text = "# No Report Found"
        # 1. Prioritize strict names
        possible_logs = ["adm_log.md", "log.md", "ADM_LOG.md"]
        found_log = None
        
        for pl in possible_logs:
            p = os.path.join(case_path, pl)
            if os.path.exists(p):
                found_log = p
                break
        
        # 2. Fallback to any markdown
        if not found_log:
            md_files = glob.glob(os.path.join(case_path, "*.md"))
            if md_files: found_log = md_files[0]
            
        if found_log:
            print(f"    [DEBUG] Found report: {found_log}")
            try:
                with open(found_log, 'r', encoding='utf-8') as f: 
                    md_text = f.read().replace('`', '\\`')
            except Exception as e:
                print(f"    [ERROR] Reading log: {e}")
        else:
            print("    [DEBUG] No markdown log found.")

        # --- DATA CONFIG ---
        config = []
        
        init_data = build_graph_data(adm_initial, os.path.join(case_path, "adm_initial_summary.json"))
        if init_data: config.append({"name": "Preconditions", "type": "single", "data": init_data})
        
        main_data = build_graph_data(adm_main, os.path.join(case_path, "adm_main_summary.json"))
        if main_data: config.append({"name": "Inventive Step", "type": "single", "data": main_data})
        
        sub_groups = {}
        for sd in [d for d in os.listdir(case_path) if os.path.isdir(os.path.join(case_path, d))]:
            matched = None
            for p, m in SUB_ADM_CONFIG.items():
                if p in sd: matched = m; break
            
            if matched:
                lbl = matched['label']
                if lbl not in sub_groups: sub_groups[lbl] = []
                for jf in glob.glob(os.path.join(case_path, sd, "*_summary.json")):
                    item = os.path.basename(jf).replace("_summary.json", "")
                    d = build_graph_data(matched['factory'], jf, item)
                    if d: sub_groups[lbl].append({"name": item, "data": d})
        
        for lbl, opts in sub_groups.items():
            config.append({"name": lbl, "type": "group", "options": opts})
            
        all_cases[case_name] = {"markdown": md_text, "config": config}
    
    return all_cases

# --- 6. SERVER CLASS ---
class RequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            data = scan_cases()
            json_str = json.dumps(data)
            html = HTML_TEMPLATE.replace("__ALL_CASES_JSON__", json_str)
            self.wfile.write(html.encode('utf-8'))
        elif self.path == '/poll_output':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            out = io_bridge.get_output()
            self.wfile.write(out.encode('utf-8'))
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == '/start_cli':
            if not io_bridge.active:
                io_bridge.active = True
                t = threading.Thread(target=run_cli_session)
                t.daemon = True
                t.start()
            self.send_response(200); self.end_headers()
        elif self.path == '/send_input':
            length = int(self.headers['Content-Length'])
            val = self.rfile.read(length).decode('utf-8')
            io_bridge.send_input(val)
            self.send_response(200); self.end_headers()

def run_cli_session():
    original_stdout = sys.stdout
    original_input = builtins.input
    sys.stdout = io_bridge
    builtins.input = web_input 
    try:
        print("\n=== STARTING NEW CASE ===\n")
        cli = CLI(adm=adm_initial())
        res = cli.query_domain()
        cli.save_adm(name='initial')
        if res:
            print("\n>> Preconditions met. Proceeding to Main ADM...")
            cli_2 = CLI(adm=adm_main())
            cli_2.caseName = cli.caseName
            cli_2.adm.facts = cli.adm.facts
            _ = cli_2.query_domain()
            cli_2.save_adm(name='main')
        
        case_dir = os.path.join(CASES_DIR, cli.caseName)
        md_path = os.path.join(case_dir, "adm_log.md")
        if not os.path.exists(md_path):
            with open(md_path, 'w') as f: f.write(f"# Case: {cli.caseName}\n\n**Status:** Created via Web CLI.")
        print("\n=== CASE COMPLETE ===\nReloading dashboard...")
    except Exception as e: print(f"\nError: {e}")
    finally:
        sys.stdout = original_stdout
        builtins.input = original_input
        io_bridge.active = False

# --- 7. MAIN ---
if __name__ == "__main__":
    if not os.path.exists(CASES_DIR): os.makedirs(CASES_DIR)
    print(f"Starting server at http://localhost:{PORT}")
    def open_browser():
        time.sleep(1)
        webbrowser.open(f"http://localhost:{PORT}")
    t = threading.Thread(target=open_browser)
    t.start()
    server = HTTPServer(('localhost', PORT), RequestHandler)
    try: server.serve_forever()
    except KeyboardInterrupt: server.server_close()