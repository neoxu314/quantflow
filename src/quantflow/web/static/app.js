import { SETTINGS_FIELD_MAP, getNestedValue, setNestedValue, formatStockCode } from "./utils.js";
const state = {
    watchlists: [],
    selectedWatchlist: null,
    currentWatchlistData: null,
    watchlistDirty: false,
    tasks: [],
    strategies: [],
    taskFiles: [],
    selectedTaskFile: "",
    rawConfig: {},
    // Runs (new)
    runsList: [],
    selectedRunId: null,
    selectedRun: null,
    // Library (new) data
    libraryStrategies: [],
    libraryIndicators: [],
    currentIndicatorConfig: null,
};
async function api(path, options = {}) {
    const resp = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options,
    });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    return resp.json();
}
async function init() {
    setupEventListeners();
    // Load core and library data in parallel
    await Promise.allSettled([loadStrategies(), loadWatchlists(), loadTaskFiles(), loadConfig(), loadLibraryStrategies(), loadLibraryIndicators(), loadRuns()]);
    if (state.taskFiles.length > 0) {
        selectTaskFile(state.taskFiles[0].filename);
    }
    else {
        selectTaskFile("");
    }
    window.addEventListener("beforeunload", (e) => {
        if (state.watchlistDirty) {
            e.preventDefault();
            e.returnValue = "";
        }
    });
}
async function loadStrategies() {
    const res = await api("/api/strategies");
    state.strategies = res.strategies;
}
// Library data fetchers
async function loadLibraryStrategies() {
    const res = await api("/api/library/strategies");
    state.libraryStrategies = res.strategies;
    renderLibraryStrategies();
}
async function loadLibraryIndicators() {
    const res = await api("/api/library/indicators");
    state.libraryIndicators = res.indicators;
    renderLibraryIndicators();
}
async function loadWatchlists() {
    state.watchlists = await api("/api/watchlists");
    renderWatchlistSidebar();
}
// Runs data fetch
let runsPollingTimer = null;
async function loadRuns() {
    try {
        const res = await api("/api/runs/");
        state.runsList = res.runs || [];
        renderRunsList();
        // Refresh detail panel if a run status changed
        if (state.selectedRunId) {
            const updated = state.runsList.find(r => r.id === state.selectedRunId);
            if (updated && updated.status !== state.selectedRun?.status) {
                state.selectedRun = updated;
                renderRunsDetail(updated);
                if (updated.status !== "running" && updated.status !== "queued") {
                    if (sseSource) {
                        sseSource.close();
                        sseSource = null;
                        sseTargetRunId = null;
                    }
                }
                else {
                    connectSSE(updated.id);
                }
            }
        }
    }
    catch (e) {
        console.error('Failed to load runs:', e);
    }
}
function startRunsPolling() {
    if (runsPollingTimer)
        return;
    runsPollingTimer = setInterval(loadRuns, 3000);
}
function stopRunsPolling() {
    if (runsPollingTimer) {
        clearInterval(runsPollingTimer);
        runsPollingTimer = null;
    }
}
function renderRunsList() {
    const list = document.getElementById('runs-list');
    if (!list)
        return;
    if (!state.runsList || state.runsList.length === 0) {
        list.innerHTML = '<li class="text-gray-400 text-sm text-center py-8">No runs yet</li>';
        return;
    }
    list.innerHTML = state.runsList.map(r => {
        const active = state.selectedRunId === r.id ? 'bg-blue-50 border-l-2 border-blue-500' : '';
        const time = new Date(r.created_at).toLocaleString();
        return `<li class="px-3 py-2 rounded cursor-pointer hover:bg-gray-100 ${active}" data-run-id="${r.id}">` +
            `<div class="flex items-center justify-between">` +
            `<div class="flex-1 min-w-0"><div class="font-medium text-sm truncate">${r.name}</div>` +
            `<div class="text-xs text-gray-500">${r.run_type} • ${r.status} • ${time}</div></div>` +
            `<button class="ml-2 text-gray-400 hover:text-red-500 p-1 rounded flex-shrink-0" onclick="event.stopPropagation(); deleteRun('${r.id}')" title="Delete run">✕</button>` +
            `</div></li>`;
    }).join('');
    list.querySelectorAll('[data-run-id]').forEach(el => {
        el.addEventListener('click', () => {
            const id = el.dataset.runId;
            selectRun(id);
        });
    });
}
async function selectRun(runId) {
    state.selectedRunId = runId;
    renderRunsList();
    try {
        const data = await api(`/api/runs/${runId}`);
        state.selectedRun = data.run;
        renderRunsDetail(state.selectedRun);
        if (data.run.status === "running" || data.run.status === "queued") {
            connectSSE(runId);
        }
    }
    catch (e) {
        console.error('Failed to load run details:', e);
    }
}
// ---- Runs detail rendering (4 sub-tabs) ----
function renderRunsDetail(run) {
    const emptyState = document.getElementById("runs-empty-state");
    const detail = document.getElementById("runs-detail");
    if (!run) {
        emptyState.classList.remove("hidden");
        detail.classList.add("hidden");
        return;
    }
    emptyState.classList.add("hidden");
    detail.classList.remove("hidden");
    // Render all 4 sub-tab panels
    renderConfigTab(run);
    renderProgressTab(run);
    renderReportTab(run);
    renderFilesTab(run);
    // Reset to Config tab
    document.querySelectorAll(".run-subtab").forEach(t => {
        t.style.borderColor = "transparent";
        t.style.color = "#6b7280";
    });
    const firstTab = document.querySelector('[data-runtab="config"]');
    if (firstTab) {
        firstTab.style.borderColor = "#3b82f6";
        firstTab.style.color = "#2563eb";
    }
    document.querySelectorAll(".run-tab-content").forEach(p => p.classList.add("hidden"));
    document.getElementById("runtab-config").classList.remove("hidden");
}
function renderConfigTab(run) {
    const panel = document.getElementById("runtab-config");
    let html = `<div class="space-y-2 text-sm">
        <div class="grid grid-cols-2 gap-x-4 gap-y-1">
            <span class="text-gray-500">Type:</span><span class="font-mono">${run.run_type}</span>
            <span class="text-gray-500">Status:</span><span>${run.status}</span>`;
    if (run.started_at)
        html += `<span class="text-gray-500">Started:</span><span>${new Date(run.started_at).toLocaleString()}</span>`;
    if (run.finished_at)
        html += `<span class="text-gray-500">Finished:</span><span>${new Date(run.finished_at).toLocaleString()}</span>`;
    if (run.duration_ms)
        html += `<span class="text-gray-500">Duration:</span><span>${(run.duration_ms / 1000).toFixed(1)}s</span>`;
    if (run.run_type === "stock_scan" && run.config?.indicators) {
        const indNames = run.config.indicators.join(", ");
        html += `<span class="text-gray-500">Indicators:</span><span class="font-mono">${indNames}</span>`;
    }
    if (run.signal_count) {
        const label = run.run_type === "stock_scan" ? "Bars:" : "Signals:";
        html += `<span class="text-gray-500">${label}</span><span>${run.signal_count}</span>`;
    }
    if (run.error)
        html += `<span class="text-gray-500">Error:</span><span class="text-red-600">${run.error}</span>`;
    html += `</div></div>`;
    html += `<details class="mt-3"><summary class="text-sm text-gray-500 cursor-pointer">Raw Config (JSON)</summary>
        <pre class="mt-2 bg-gray-50 p-3 rounded text-xs overflow-x-auto">${JSON.stringify(run.config, null, 2)}</pre></details>`;
    html += `<div class="flex gap-2 mt-4 pt-3 border-t">
        <button onclick="runAgain('${run.id}')" class="text-sm px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600">▶ Run Again</button>
    </div>`;
    panel.innerHTML = html;
}
function renderProgressTab(run) {
    const panel = document.getElementById("runtab-progress");
    if (run.status === "completed") {
        const label = run.run_type === "stock_scan" ? "bar(s)" : "signal(s)";
        panel.innerHTML = `<div class="text-center py-4"><div class="text-2xl mb-2">✅</div>
            <div class="text-lg font-medium">Complete</div>
            ${run.signal_count ? `<div class="text-sm text-gray-500 mt-1">${run.signal_count} ${label}</div>` : ""}</div>`;
    }
    else if (run.status === "failed") {
        panel.innerHTML = `<div class="text-center py-4"><div class="text-2xl mb-2">❌</div>
            <div class="text-lg font-medium text-red-600">Failed</div>
            <div class="text-sm text-red-500 mt-1">${run.error || "unknown"}</div></div>`;
    }
    else if (run.status === "running") {
        panel.innerHTML = `<div class="space-y-3">
            <div class="h-3 bg-gray-200 rounded overflow-hidden">
                <div id="run-progress-bar" class="h-full bg-blue-500 transition-all" style="width:0%"></div>
            </div>
            <div id="run-progress-text" class="text-sm text-gray-600">Starting...</div>
            <div id="run-log-container" class="bg-gray-900 text-green-400 font-mono text-xs p-3 rounded h-64 overflow-y-auto"></div>
        </div>`;
        connectSSE(run.id);
    }
    else {
        panel.innerHTML = `<div class="text-gray-500 text-center py-8">Status: ${run.status}</div>`;
    }
}
function renderReportTab(run) {
    const panel = document.getElementById("runtab-report");
    if (run.status === "running" || run.status === "queued") {
        panel.innerHTML = '<div class="text-gray-500 text-center py-8">Report available after completion</div>';
        return;
    }
    if (run.run_type === "stock_scan") {
        const code = run.config?.code || run.name;
        panel.innerHTML = '<div class="text-sm text-gray-500 text-center">Loading indicator data...</div>';
        api(`/api/runs/${run.id}/indicator-data`)
            .then(data => {
            if (!data.data || data.data.length === 0) {
                panel.innerHTML = `<div class="text-gray-500 text-center py-8">${data.message || "No indicator data"}</div>`;
                return;
            }
            const cols = Object.keys(data.data[0]).filter(k => k !== "index");
            const ohlcvCols = ["date", "open", "high", "low", "close", "volume"];
            const otherCols = cols.filter(c => !ohlcvCols.includes(c));
            const orderedCols = [...ohlcvCols.filter(c => cols.includes(c)), ...otherCols];
            let html = `<div class="mb-2 text-sm text-gray-600">Stock: <span class="font-mono font-semibold">${data.code || code}</span> | Total bars: ${data.bar_count || data.data.length}</div>`;
            html += '<div class="overflow-x-auto"><table class="min-w-full divide-y divide-gray-200 text-xs"><thead class="bg-gray-50"><tr>';
            orderedCols.forEach(c => {
                html += `<th class="px-2 py-1 text-left font-medium text-gray-500 uppercase tracking-wider">${c}</th>`;
            });
            html += '</tr></thead><tbody class="bg-white divide-y divide-gray-100">';
            const rows = data.data.slice(-100).reverse();
            rows.forEach(row => {
                html += '<tr>';
                orderedCols.forEach(c => {
                    const v = row[c] !== null && row[c] !== undefined ? row[c] : '-';
                    const fmt = (typeof v === 'number') ? v.toFixed(4) : v;
                    const fontClass = (c === 'K' || c === 'D' || c === 'J' || c === 'MACD' || c === 'RSI') ? 'font-mono' : '';
                    html += `<td class="px-2 py-1 ${fontClass}">${fmt}</td>`;
                });
                html += '</tr>';
            });
            html += '</tbody></table></div>';
            if (data.data.length > 100) {
                html += `<div class="text-xs text-gray-400 mt-1 text-center">Showing last 100 of ${data.data.length} bars</div>`;
            }
            panel.innerHTML = html;
        }).catch(() => { panel.innerHTML = '<div class="text-red-500 text-center">Failed to load</div>'; });
        return;
    }
    if (!run.report_path) {
        panel.innerHTML = '<div class="text-gray-500 text-center py-8">No report available</div>';
        return;
    }
    panel.innerHTML = '<div class="text-sm text-gray-500 text-center">Loading...</div>';
    api(`/api/runs/${run.id}/report`)
        .then(data => {
        if (data.report) {
            panel.innerHTML = `<div class="prose max-w-none">${mdToHtml(data.report)}</div>`;
        }
        else {
            panel.innerHTML = `<div class="text-gray-500 text-center py-8">${data.message || "No content"}</div>`;
        }
    }).catch(() => { panel.innerHTML = '<div class="text-red-500 text-center">Failed to load</div>'; });
}
function renderFilesTab(run) {
    const panel = document.getElementById("runtab-files");
    if (!run.output_path) {
        panel.innerHTML = '<div class="text-gray-500 text-center py-8">No output files</div>';
        return;
    }
    api(`/api/runs/${run.id}/files`)
        .then(data => {
        if (!data.files.length) {
            panel.innerHTML = '<div class="text-gray-500 text-center py-8">No files</div>';
            return;
        }
        let html = `<table class="min-w-full divide-y divide-gray-200 text-sm">
                <thead class="bg-gray-50"><tr><th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">File</th>
                <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Size</th>
                <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Actions</th></tr></thead><tbody>`;
        data.files.forEach(f => {
            html += `<tr><td class="px-4 py-2 font-mono text-xs">${f.name}</td>
                    <td class="px-4 py-2 text-gray-500">${f.size}</td>
                    <td class="px-4 py-2"><button class="text-blue-500 hover:text-blue-700 text-xs"
                        onclick="copyToClipboard('${f.path}')">📋 Copy Path</button></td></tr>`;
        });
        html += "</tbody></table>";
        panel.innerHTML = html;
    }).catch(() => { panel.innerHTML = '<div class="text-red-500 text-center">Failed</div>'; });
}
// ---- New Run modal wizard ----
let selectedRunType = "";
function resetRunModal() {
    selectedRunType = "";
    document.getElementById("run-step-type").classList.remove("hidden");
    document.getElementById("run-step-config").classList.add("hidden");
    document.getElementById("run-step-preview").classList.add("hidden");
    document.getElementById("btn-back-run").classList.add("hidden");
    document.getElementById("btn-check-run").classList.add("hidden");
    document.getElementById("btn-execute-run").classList.add("hidden");
    ["stock_scan", "watchlist_run", "task_run"].forEach(t => {
        document.getElementById(`run-config-${t}`).classList.add("hidden");
    });
}
function selectRunType(type) {
    selectedRunType = type;
    document.getElementById("run-step-type").classList.add("hidden");
    document.getElementById("run-step-config").classList.remove("hidden");
    document.getElementById("run-step-preview").classList.remove("hidden");
    document.getElementById("btn-back-run").classList.remove("hidden");
    document.getElementById("btn-check-run").classList.remove("hidden");
    document.getElementById("btn-execute-run").classList.remove("hidden");
    // Hide all config sections first, then show the selected one
    ["stock_scan", "watchlist_run", "task_run"].forEach(t => {
        document.getElementById(`run-config-${t}`).classList.add("hidden");
    });
    document.getElementById(`run-config-${type}`).classList.remove("hidden");
    if (type === "stock_scan") {
        const today = new Date().toISOString().split("T")[0];
        document.getElementById("run-start-date").value = today;
        document.getElementById("run-end-date").value = today;
    }
    populateRunFormFields(type);
    updateCliPreview();
}
function populateRunFormFields(type) {
    const today = new Date().toISOString().split("T")[0];
    if (type === "stock_scan") {
        const startDate = document.getElementById("run-start-date");
        const endDate = document.getElementById("run-end-date");
        if (startDate && !startDate.value)
            startDate.value = today;
        if (endDate && !endDate.value)
            endDate.value = today;
    }
    else if (type === "watchlist_run") {
        const sel = document.getElementById("run-watchlist-select");
        sel.innerHTML = state.watchlists.map(w => `<option value="${w.path}">${w.name} (${w.itemCount} stocks)</option>`).join("");
        const stratDiv = document.getElementById("run-strategy-checkboxes");
        stratDiv.innerHTML = state.strategies
            .map((s) => {
            const icon = s.type === "buy" ? "🔵" : "🔴";
            const label = s.name.replace(/(Buy|Sell)$/, "");
            return `<label class="flex items-center gap-2"><input type="checkbox" value="${s.id}" ${s.type === "buy" ? "checked" : ""} class="rounded"> ${icon} ${label}</label>`;
        }).join("");
    }
    else if (type === "task_run") {
        const sel = document.getElementById("run-task-config-select");
        sel.innerHTML = state.taskFiles.map((tf) => `<option value="config/${tf.filename}">${tf.filename} (${tf.taskCount} tasks)</option>`).join("");
    }
}
function updateCliPreview() {
    const preview = document.getElementById("run-cli-preview");
    if (!preview)
        return;
    if (selectedRunType === "stock_scan") {
        const code = document.getElementById("run-stock-code").value || "CODE";
        const inds = Array.from(document.querySelectorAll(".run-indicator:checked"))
            .map((el) => el.value).join(",");
        preview.textContent = `python -m quantflow.cli scan --code ${code} --indicator ${inds || "kdj,dual_line"}`;
    }
    else if (selectedRunType === "watchlist_run") {
        const wl = document.getElementById("run-watchlist-select")?.value || "WATCHLIST";
        preview.textContent = `python -m quantflow.cli monitor --watchlist ${wl}`;
    }
    else if (selectedRunType === "task_run") {
        const tc = document.getElementById("run-task-config-select")?.value || "CONFIG";
        preview.textContent = `python -m quantflow.cli tasks --config ${tc}`;
    }
}
async function executeRun() {
    const body = { run_type: selectedRunType };
    if (selectedRunType === "stock_scan") {
        body.code = document.getElementById("run-stock-code").value;
        const start = document.getElementById("run-start-date").value;
        const end = document.getElementById("run-end-date").value;
        if (start)
            body.start_date = start;
        if (end)
            body.end_date = end;
        body.indicators = Array.from(document.querySelectorAll(".run-indicator:checked"))
            .map((el) => el.value);
    }
    else if (selectedRunType === "watchlist_run") {
        body.watchlist = document.getElementById("run-watchlist-select").value;
        body.strategies = Array.from(document.querySelectorAll("#run-strategy-checkboxes input:checked"))
            .map((el) => el.value);
    }
    else if (selectedRunType === "task_run") {
        body.task_config = document.getElementById("run-task-config-select").value;
        body.daily = document.getElementById("run-daily-mode").checked;
    }
    const output = document.getElementById("run-output-path").value;
    if (output)
        body.output_path = output;
    const errDiv = document.getElementById("run-validation-errors");
    try {
        const result = await api("/api/runs/", {
            method: "POST", body: JSON.stringify(body),
        });
        errDiv.classList.add("hidden");
        if (!result.ok) {
            errDiv.classList.remove("hidden");
            errDiv.innerHTML = result.errors.map((e) => `• ${e}`).join("<br>");
            return;
        }
        closeModal("modal-new-run");
        toast("Run started");
        await loadRuns();
        startRunsPolling();
        if (result.run_id)
            selectRun(result.run_id);
    }
    catch (e) {
        toast(`Error: ${e.message}`);
    }
}
async function preflightCheck() {
    const body = { run_type: selectedRunType, validate_only: true };
    if (selectedRunType === "stock_scan") {
        body.code = document.getElementById("run-stock-code").value;
    }
    else if (selectedRunType === "watchlist_run") {
        body.watchlist = document.getElementById("run-watchlist-select").value;
    }
    else if (selectedRunType === "task_run") {
        body.task_config = document.getElementById("run-task-config-select").value;
    }
    const output = document.getElementById("run-output-path").value;
    if (output)
        body.output_path = output;
    const errDiv = document.getElementById("run-validation-errors");
    try {
        const result = await api("/api/runs/", {
            method: "POST", body: JSON.stringify(body),
        });
        if (!result.ok) {
            errDiv.classList.remove("hidden");
            errDiv.innerHTML = result.errors.map((e) => `• ${e}`).join("<br>");
        }
        else {
            errDiv.classList.add("hidden");
            toast("Checks passed");
        }
    }
    catch (e) {
        toast("Validation request sent");
    }
}
function formatRelativeTime(isoStr) {
    const date = new Date(isoStr);
    const diffMs = Date.now() - date.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1)
        return "just now";
    if (diffMin < 60)
        return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24)
        return `${diffHr}h ago`;
    return date.toLocaleDateString();
}
function mdToHtml(md) {
    let html = md
        .replace(/^### (.+)$/gm, '<h3 class="text-lg font-semibold mt-4">$1</h3>')
        .replace(/^## (.+)$/gm, '<h2 class="text-xl font-semibold mt-6">$1</h2>')
        .replace(/^# (.+)$/gm, '<h1 class="text-2xl font-bold mt-8">$1</h1>')
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/\*(.+?)\*/g, "<em>$1</em>")
        .replace(/`([^`]+)`/g, '<code class="bg-gray-100 px-1 rounded text-xs">$1</code>')
        .replace(/\*\s+(.+?)(?=\n|$)/gm, '<li class="ml-4 list-disc">$1</li>')
        .replace(/^[-•]\s+(.+?)(?=\n|$)/gm, '<li class="ml-4 list-disc">$1</li>');
    html = html.replace(/((?:\|.+\|\n?)+)/g, (match) => {
        const rows = match.trim().split("\n").filter(r => !r.match(/^\|-+[-| ]+$/));
        if (rows.length < 2)
            return match;
        let t = '<table class="min-w-full divide-y divide-gray-200 text-sm mt-2 mb-4"><tbody>';
        rows.forEach(row => {
            const cells = row.split("|").filter(c => c.trim()).map(c => c.trim());
            t += '<tr class="bg-white">';
            cells.forEach(cell => { t += `<td class="px-4 py-2 border border-gray-200">${cell}</td>`; });
            t += "</tr>";
        });
        return t + "</tbody></table>";
    });
    html = html.replace(/^(?!<\/?[a-zA-Z\/\d])((?!$).+)$/gm, '<p class="text-sm text-gray-700 mb-1">$1</p>');
    return html;
}
let sseSource = null;
let sseTargetRunId = null;
function connectSSE(runId) {
    if (sseTargetRunId === runId && sseSource)
        return;
    if (sseSource)
        sseSource.close();
    sseTargetRunId = runId;
    try {
        sseSource = new EventSource(`/api/runs/${runId}/logs:sse`);
        sseSource.addEventListener("log", (ev) => {
            const data = JSON.parse(ev.data);
            const logContainer = document.getElementById("run-log-container");
            if (logContainer)
                appendLog(logContainer, data.message, data.level || "info");
        });
        sseSource.addEventListener("progress", (ev) => {
            const data = JSON.parse(ev.data);
            const bar = document.getElementById("run-progress-bar");
            const txt = document.getElementById("run-progress-text");
            if (bar)
                bar.style.width = `${data.percentage}%`;
            if (txt)
                txt.textContent = `${data.percentage}% (${data.current}/${data.total})`;
        });
        sseSource.addEventListener("status", async (ev) => {
            const data = JSON.parse(ev.data);
            if (data.status !== "running") {
                if (sseSource)
                    sseSource.close();
                sseSource = null;
                sseTargetRunId = null;
                if (state.selectedRunId)
                    await selectRun(state.selectedRunId);
                await loadRuns();
            }
        });
    }
    catch (_e) {
        /* SSE unavailable — queued or deleted */
    }
}
function appendLog(container, message, level) {
    const time = new Date().toLocaleTimeString();
    const color = level === "error" ? "text-red-400" : level === "warning" ? "text-yellow-400" : "text-green-400";
    const entry = document.createElement("div");
    entry.className = `${color} break-all`;
    entry.textContent = `${time}  ${message}`;
    container.appendChild(entry);
    container.scrollTop = container.scrollHeight;
}
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => toast("Path copied"));
}
function runAgain(runId) {
    const orig = state.runsList.find(r => r.id === runId);
    if (!orig)
        return;
    openModal("modal-new-run");
    resetRunModal();
    selectRunType(orig.run_type);
    if (orig.run_type === "stock_scan" && orig.config?.code) {
        document.getElementById("run-stock-code").value = orig.config.code;
        if (orig.config?.start_date) {
            document.getElementById("run-start-date").value = orig.config.start_date;
        }
        if (orig.config?.end_date) {
            document.getElementById("run-end-date").value = orig.config.end_date;
        }
        updateCliPreview();
    }
    toast("Pre-filled from previous run");
}
async function deleteRun(runId) {
    const run = state.runsList.find(r => r.id === runId);
    if (!run)
        return;
    const statusMsg = run.status === "running" ? "This will stop the running task." :
        run.status === "queued" ? "This will remove it from the queue." : "";
    if (!confirm(`Delete run "${run.name}"?\n${statusMsg}\nAssociated report file will also be deleted.\n\nThis action cannot be undone.`))
        return;
    try {
        await api(`/api/runs/${runId}`, { method: "DELETE" });
        state.runsList = state.runsList.filter(r => r.id !== runId);
        if (state.selectedRunId === runId) {
            state.selectedRunId = null;
            state.selectedRun = null;
            document.getElementById("runs-empty-state").classList.remove("hidden");
            document.getElementById("runs-detail").classList.add("hidden");
        }
        renderRunsList();
        toast("Run deleted");
    }
    catch (e) {
        toast(`Delete failed: ${e.message}`);
    }
}
// ---- End of Runs functions ----
async function loadTasks(filename) {
    const url = filename ? `/api/tasks?filename=${encodeURIComponent(filename)}` : "/api/tasks";
    state.tasks = await api(url);
    renderTaskTable();
    loadTaskFiles();
}
async function loadTaskFiles() {
    state.taskFiles = await api("/api/task-files");
    renderTaskFileSidebar();
}
function renderTaskFileSidebar() {
    const list = document.getElementById("task-file-list");
    list.innerHTML = "";
    for (const tf of state.taskFiles) {
        const li = document.createElement("li");
        const isSelected = state.selectedTaskFile === tf.filename;
        li.innerHTML = `
            <div class="flex items-center justify-between">
              <button data-filename="${tf.filename}" class="task-file-item flex-1 text-left px-3 py-2 rounded text-sm transition-colors
                  ${isSelected ? "bg-blue-100 text-blue-700 font-medium" : "hover:bg-gray-100 text-gray-700"}">
                <div class="truncate">${tf.filename}</div>
                <div class="text-xs text-gray-400">${tf.taskCount} tasks</div>
              </button>
              <button class="tf-delete-btn text-red-500 hover:text-red-700 px-2 opacity-50 hover:opacity-100" data-filename="${tf.filename}">×</button>
            </div>`;
        list.appendChild(li);
    }
}
function selectTaskFile(filename) {
    state.selectedTaskFile = filename;
    renderTaskFileSidebar();
    const emptyMsg = document.getElementById("task-file-empty");
    const listArea = document.getElementById("task-list-area");
    const header = document.getElementById("task-file-header");
    if (!filename) {
        emptyMsg.classList.remove("hidden");
        emptyMsg.textContent = "Select a task file";
        listArea.classList.add("hidden");
        return;
    }
    emptyMsg.classList.add("hidden");
    listArea.classList.remove("hidden");
    header.textContent = filename;
    loadTasks(filename);
}
async function loadConfig() {
    const config = await api("/api/config");
    state.rawConfig = (config.raw ?? {});
    populateSettingsForm(state.rawConfig);
}
function switchTab(tab) {
    for (const t of ["watchlists", "tasks", "settings", "library", "runs"]) {
        const tabBtn = document.getElementById(`tab-${t}`);
        const panel = document.getElementById(`panel-${t}`);
        if (t === tab) {
            tabBtn.className = "tab-active px-6 py-3 border-b-2 font-medium text-sm";
            panel.classList.remove("hidden");
        }
        else {
            tabBtn.className = "tab-inactive px-6 py-3 border-b-2 font-medium text-sm";
            panel.classList.add("hidden");
        }
    }
    if (tab === "runs") {
        startRunsPolling();
    }
    else {
        stopRunsPolling();
    }
}
// Library sub-tab switching (strategies / indicators)
function switchLibrarySubTab(subtab) {
    for (const s of ["strategies", "indicators"]) {
        const btn = document.getElementById(`subtab-${s}`);
        const panel = document.getElementById(`library-${s}-panel`);
        if (s === subtab) {
            btn.className = "subtab-active px-4 py-2 border-b-2 text-sm font-medium";
            btn.style.borderColor = "#3b82f6";
            btn.style.color = "#2563eb";
            panel.classList.remove("hidden");
        }
        else {
            btn.className = "subtab-inactive px-4 py-2 border-b-2 text-sm font-medium border-transparent text-gray-500 hover:text-gray-700";
            btn.style.borderColor = "transparent";
            btn.style.color = "";
            panel.classList.add("hidden");
        }
    }
}
// Render library data lists
function renderLibraryStrategies() {
    const list = document.getElementById("library-strategies-list");
    const loading = document.getElementById("library-strategies-loading");
    loading.classList.add("hidden");
    list.innerHTML = "";
    if (state.libraryStrategies.length === 0) {
        list.innerHTML = '<p class="text-gray-500 text-center py-8">No strategies available</p>';
        return;
    }
    for (const strat of state.libraryStrategies) {
        const icon = strat.type === "buy" ? "\uD83D\uDD35" : "\uD83D\uDD34";
        const div = document.createElement("div");
        div.className = "border rounded-lg p-4 hover:shadow-md transition-shadow";
        div.innerHTML = `
            <div class="flex items-start gap-3">
                <span class="text-lg">${icon}</span>
                <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2">
                        <h4 class="font-semibold text-gray-900">${strat.name}</h4>
                        <span class="text-xs px-2 py-0.5 rounded-full font-medium ${strat.type === "buy" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}">${strat.type}</span>
                    </div>
                    ${strat.description ? `<p class="mt-1.5 text-sm text-gray-600 whitespace-pre-line">${strat.description}</p>` : ""}
                    <div class="mt-2 flex flex-wrap gap-3 text-xs">
                        <span class="text-gray-500">Lookback: <span class="font-medium text-gray-700">${strat.min_lookback_days} days</span></span>
                        ${strat.required_indicators.length > 0 ? `<span class="text-gray-500">Indicators: <span class="font-medium text-gray-700">${strat.required_indicators.join(", ")}</span></span>` : ""}
                    </div>
                </div>
            </div>`;
        list.appendChild(div);
    }
}
function renderLibraryIndicators() {
    const tbody = document.getElementById("library-indicators-table");
    const loading = document.getElementById("library-indicators-loading");
    if (loading)
        loading.classList.add("hidden");
    tbody.innerHTML = "";
    if (state.libraryIndicators.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="px-4 py-4 text-center text-gray-500">No indicators available</td></tr>';
        return;
    }
    for (const ind of state.libraryIndicators) {
        const paramsStr = Object.entries(ind.params).map(([k, v]) => `${k}=${v}`).join(", ");
        const catLabel = ind.category === "standard" ? '\uD83D\uDC99' : '\uD83D\uDD27';
        const tr = document.createElement("tr");
        tr.className = "hover:bg-gray-50";
        tr.innerHTML = `
            <td class="px-4 py-2 text-sm font-medium text-gray-900">${ind.name}</td>
            <td class="px-4 py-2 text-sm text-gray-600">${catLabel} ${ind.category}</td>
            <td class="px-4 py-2 text-sm text-gray-600 font-mono text-xs" title="${paramsStr}">${paramsStr}</td>
            <td class="px-4 py-2 text-sm text-gray-600 text-xs">${ind.required_fields.join(", ") || "-"}</td>
            <td class="px-4 py-2 text-sm text-gray-600 text-xs">${ind.output_fields.join(", ") || "-"}</td>
            <td class="px-4 py-2 text-sm text-gray-600">${ind.lookback_bars || "-"}</td>
            <td class="px-4 py-2 text-sm">
                <button class="text-blue-600 hover:text-blue-800 text-xs indicator-config-btn" data-indicator="${ind.name}">Edit Params</button>
            </td>`;
        tbody.appendChild(tr);
    }
    // Wire up edit buttons
    tbody.querySelectorAll(".indicator-config-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const name = btn.dataset.indicator;
            openIndicatorParamsModal(name);
        });
    });
}
function openIndicatorParamsModal(indicatorName) {
    if (!state.libraryIndicators)
        return;
    const ind = state.libraryIndicators.find(i => i.name === indicatorName);
    if (!ind)
        return;
    state.currentIndicatorConfig = indicatorName;
    document.getElementById("indicator-params-title").textContent = `Configure ${ind.name}`;
    document.getElementById("indicator-params-desc").textContent = `Category: ${ind.category} | Inputs: ${ind.required_fields.join(", ")} | Outputs: ${ind.output_fields.join(", ")}`;
    const form = document.getElementById("indicator-params-form");
    form.innerHTML = "";
    for (const [key, value] of Object.entries(ind.params)) {
        const row = document.createElement("div");
        row.className = "grid grid-cols-3 gap-2 items-center text-sm";
        row.innerHTML = `
            <label class="text-gray-700 font-medium">${key}</label>
            <input type="number" step="any" value="${value}" data-param-key="${key}" class="indicator-param-input col-span-2 border rounded px-2 py-1" />
        `;
        form.appendChild(row);
    }
    openModal("modal-indicator-params");
}
async function saveIndicatorParams() {
    if (!state.currentIndicatorConfig)
        return;
    const form = document.getElementById("indicator-params-form");
    const inputs = form.querySelectorAll(".indicator-param-input");
    const params = {};
    for (const input of inputs) {
        const key = input.dataset.paramKey;
        const val = input.value;
        const numVal = Number(val);
        params[key] = isNaN(numVal) ? val : numVal;
    }
    try {
        await api("/api/library/indicators/params", {
            method: "PUT",
            body: JSON.stringify({ name: state.currentIndicatorConfig, params }),
        });
        toast("Indicator parameters saved");
        closeModal("modal-indicator-params");
        // Refresh library indicators to reflect changes
        await loadLibraryIndicators();
    }
    catch (e) {
        alert(`Failed to save: ${e.message}`);
    }
}
function renderWatchlistSidebar() {
    const list = document.getElementById("watchlist-list");
    list.innerHTML = "";
    for (const wl of state.watchlists) {
        const li = document.createElement("li");
        const isSelected = state.selectedWatchlist === wl.filename;
        li.innerHTML = `
            <div class="flex items-center justify-between">
              <button data-filename="${wl.filename}" class="watchlist-item flex-1 text-left px-3 py-2 rounded text-sm transition-colors
                  ${isSelected ? "bg-blue-100 text-blue-700 font-medium" : "hover:bg-gray-100 text-gray-700"}">
                <div class="truncate">${wl.name}</div>
                <div class="text-xs text-gray-400">${wl.itemCount} stocks</div>
              </button>
              <button class="wl-delete-btn text-red-500 hover:text-red-700 px-2 opacity-50 hover:opacity-100" data-filename="${wl.filename}">×</button>
            </div>`;
        list.appendChild(li);
    }
}
async function selectWatchlist(filename) {
    if (state.watchlistDirty && state.selectedWatchlist !== filename) {
        if (!confirm("Unsaved changes. Discard?"))
            return;
        state.currentWatchlistData = null;
        state.watchlistDirty = false;
        updateModifiedUI();
    }
    state.selectedWatchlist = filename;
    renderWatchlistSidebar();
    state.currentWatchlistData = await api(`/api/watchlists/${filename}`);
    state.watchlistDirty = false;
    renderStockTable();
    document.getElementById("watchlist-empty").classList.add("hidden");
    document.getElementById("watchlist-content").classList.remove("hidden");
    document.getElementById("watchlist-title").textContent = `${state.currentWatchlistData.name} (${state.currentWatchlistData.items.length} stocks)`;
}
function renderStockTable() {
    if (!state.currentWatchlistData)
        return;
    const tbody = document.getElementById("stock-table");
    tbody.innerHTML = "";
    const items = state.currentWatchlistData.items;
    if (items.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="px-4 py-4 text-center text-gray-500">No stocks</td></tr>';
        return;
    }
    for (let i = 0; i < items.length; i++) {
        const item = items[i];
        const tr = document.createElement("tr");
        tr.className = "hover:bg-gray-50";
        const tags = (item.tags || []).map(t => `<span class="bg-gray-100 px-1.5 py-0.5 rounded text-xs">${t}</span>`).join(" ");
        tr.innerHTML = `
            <td class="px-4 py-2 text-sm text-gray-900">${item.code}</td>
            <td class="px-4 py-2 text-sm text-gray-600">${item.name || "-"}</td>
            <td class="px-4 py-2 text-sm text-gray-600">${tags || "-"}</td>
            <td class="px-4 py-2 text-sm"><button data-idx="${i}" class="text-red-600 hover:text-red-800 delete-stock-btn">Delete</button></td>`;
        tbody.appendChild(tr);
    }
    tbody.querySelectorAll(".delete-stock-btn").forEach(btn => {
        btn.addEventListener("click", (e) => {
            const idx = parseInt(e.target.dataset.idx || "0");
            state.currentWatchlistData.items.splice(idx, 1);
            markWatchlistDirty();
            renderStockTable();
        });
    });
}
function markWatchlistDirty() {
    state.watchlistDirty = true;
    updateModifiedUI();
}
function updateModifiedUI() {
    const indicator = document.getElementById("save-indicator");
    const saveBtn = document.getElementById("btn-save-watchlist");
    if (state.watchlistDirty) {
        indicator.classList.remove("hidden");
        saveBtn.classList.remove("hidden");
    }
    else {
        indicator.classList.add("hidden");
        saveBtn.classList.add("hidden");
    }
}
async function saveWatchlist() {
    if (!state.currentWatchlistData || !state.selectedWatchlist)
        return;
    const cleanItems = state.currentWatchlistData.items.map(item => ({
        code: item.code, name: item.name || undefined, tags: item.tags || [],
    }));
    await api(`/api/watchlists/${state.selectedWatchlist}`, {
        method: "PUT",
        body: JSON.stringify({
            name: state.currentWatchlistData.name,
            description: state.currentWatchlistData.description || "",
            items: cleanItems,
        }),
    });
    state.watchlistDirty = false;
    updateModifiedUI();
    loadWatchlists();
    toast("Watchlist saved");
}
async function openNewWatchlist() {
    const name = prompt("Watchlist name:");
    if (!name)
        return;
    const filename = name.replace(/[^a-zA-Z0-9_-\s]/g, "").trim().replace(/\s+/g, "_") + ".yaml";
    await api(`/api/watchlists/${filename}`, {
        method: "PUT",
        body: JSON.stringify({ name: name.replace(/\s+/g, "_"), description: "", items: [] }),
    });
    toast(`Created ${filename}`);
    loadWatchlists();
}
function updateAddStockPreview() {
    const market = document.getElementById("add-stock-market").value;
    const code = document.getElementById("add-stock-code").value.trim();
    const preview = document.getElementById("add-stock-preview");
    const previewCode = document.getElementById("add-stock-preview-code");
    if (market && code) {
        previewCode.textContent = formatStockCode(code, market);
        preview.classList.remove("hidden");
    }
    else {
        preview.classList.add("hidden");
    }
}
function openModal(id) { document.getElementById(id).classList.remove("hidden"); }
function closeModal(id) { document.getElementById(id).classList.add("hidden"); }
function openAddStockModal() {
    document.getElementById("add-stock-market").value = "";
    document.getElementById("add-stock-code").value = "";
    document.getElementById("add-stock-name").value = "";
    document.getElementById("add-stock-tags").value = "";
    document.getElementById("add-stock-warning").classList.add("hidden");
    document.getElementById("add-stock-preview").classList.add("hidden");
    openModal("modal-add-stock");
}
async function confirmAddStock() {
    const market = document.getElementById("add-stock-market").value;
    const rawCode = document.getElementById("add-stock-code").value.trim();
    if (!market && !rawCode.includes(".")) {
        alert("Please select a market");
        return;
    }
    if (!rawCode) {
        alert("Code is required");
        return;
    }
    const code = formatStockCode(rawCode, market);
    const name = document.getElementById("add-stock-name").value.trim();
    const tagsStr = document.getElementById("add-stock-tags").value.trim();
    try {
        const res = await api("/api/watchlists/search", { method: "POST", body: JSON.stringify({ code }) });
        if (res.found) {
            const warning = document.getElementById("add-stock-warning");
            warning.textContent = `Already in: ${res.inLists.join(", ")}`;
            warning.classList.remove("hidden");
        }
    }
    catch (e) { }
    if (!state.currentWatchlistData) {
        state.currentWatchlistData = { filename: "", name: "", description: "", items: [] };
    }
    state.currentWatchlistData.items.push({
        code, name: name || undefined, tags: tagsStr ? tagsStr.split(",").map(s => s.trim()).filter(Boolean) : [],
    });
    markWatchlistDirty();
    renderStockTable();
    closeModal("modal-add-stock");
}
function openBatchModal() {
    document.getElementById("batch-input").value = "";
    openModal("modal-batch");
}
function confirmBatchImport() {
    const text = document.getElementById("batch-input").value.trim();
    if (!text) {
        alert("No data");
        return;
    }
    let added = 0;
    for (const line of text.split("\n").filter(l => l.trim())) {
        const parts = line.trim().split(/\s+/);
        if (parts[0]) {
            state.currentWatchlistData.items.push({ code: parts[0], name: parts.slice(1).join(" ") || undefined, tags: ["Personal"] });
            added++;
        }
    }
    markWatchlistDirty();
    renderStockTable();
    closeModal("modal-batch");
    toast(`Imported ${added} stocks`);
}
function renderTaskTable() {
    const tbody = document.getElementById("task-table");
    tbody.innerHTML = "";
    const listArea = document.getElementById("task-list-area");
    const emptyMsg = document.getElementById("task-file-empty");
    // Always show the list area if a file is selected, even if empty
    listArea.classList.remove("hidden");
    emptyMsg.classList.add("hidden");
    if (state.tasks.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="px-4 py-4 text-center text-sm text-gray-400">No tasks yet. Click "+ New Task" to add.</td></tr>`;
        return;
    }
    for (const task of state.tasks) {
        const tr = document.createElement("tr");
        tr.className = "hover:bg-gray-50";
        tr.innerHTML = `
            <td class="px-4 py-2 text-sm font-medium text-gray-900 break-words">${task.name}</td>
            <td class="px-4 py-2 text-sm text-gray-600 break-words">${task.watchlist}</td>
            <td class="px-4 py-2 text-sm text-gray-600 break-words">${task.strategies.join(", ")}</td>
            <td class="px-4 py-2 text-sm text-gray-600 font-mono text-xs truncate">${task.output}</td>
            <td class="px-4 py-2 text-sm text-right whitespace-nowrap">
                <button data-id="${task.id}" class="text-blue-600 hover:text-blue-800 mr-2 edit-task-btn">Edit</button>
                <button data-id="${task.id}" class="text-red-600 hover:text-red-800 delete-task-btn">Delete</button>
            </td>`;
        tbody.appendChild(tr);
    }
    tbody.querySelectorAll(".edit-task-btn").forEach(btn => {
        btn.addEventListener("click", (e) => openTaskModal(e.target.dataset.id || ""));
    });
    tbody.querySelectorAll(".delete-task-btn").forEach(btn => {
        btn.addEventListener("click", async (e) => {
            const id = e.target.dataset.id || "";
            const name = state.tasks.find(t => t.id === id)?.name || id;
            if (confirm(`Delete "${name}"?`)) {
                await api(`/api/tasks/${id}`, { method: "DELETE" });
                toast(`Task "${name}" deleted`);
                loadTasks(state.selectedTaskFile);
                loadTaskFiles();
            }
        });
    });
}
async function openTaskModal(taskId) {
    const isEdit = !!taskId;
    document.getElementById("task-modal-title").textContent = isEdit ? "Edit Task" : "New Task";
    if (!state.selectedTaskFile) {
        toast("Please select a task file first.");
        return;
    }
    const wlSelect = document.getElementById("task-watchlist");
    wlSelect.innerHTML = "";
    for (const wl of state.watchlists) {
        const opt = document.createElement("option");
        opt.value = `watchlists/${wl.filename}`;
        opt.textContent = wl.name;
        wlSelect.appendChild(opt);
    }
    const stratContainer = document.getElementById("task-strategies");
    stratContainer.innerHTML = "";
    for (const s of state.strategies) {
        const label = document.createElement("label");
        label.className = "flex items-center gap-2";
        label.innerHTML = `<input type="checkbox" value="${s.id}" class="task-strategy-cb"><span class="text-sm">${s.name} (${s.type})</span>`;
        stratContainer.appendChild(label);
    }
    if (isEdit) {
        const task = state.tasks.find(t => t.id === taskId);
        if (!task)
            return;
        document.getElementById("task-name").value = task.name;
        document.getElementById("task-output").value = task.output;
        wlSelect.value = task.watchlist;
        stratContainer.querySelectorAll(".task-strategy-cb").forEach((cb) => {
            cb.checked = task.strategies.includes(cb.value);
        });
    }
    else {
        document.getElementById("task-name").value = "";
        document.getElementById("task-output").value = "./output";
    }
    document.getElementById("btn-save-task").onclick = null;
    document.getElementById("btn-save-task").addEventListener("click", async () => {
        if (!state.selectedTaskFile) {
            toast("Please select a task file first.");
            return;
        }
        const taskName = document.getElementById("task-name").value.trim();
        if (!taskName) {
            alert("Name required");
            return;
        }
        if (!wlSelect.value) {
            alert("Watchlist required");
            return;
        }
        const strategies = [...stratContainer.querySelectorAll(".task-strategy-cb:checked")].map(cb => cb.value);
        const output = document.getElementById("task-output").value.trim() || "./output";
        const payload = { name: taskName, watchlist: wlSelect.value, strategies, output };
        try {
            if (isEdit) {
                await api(`/api/tasks/${taskId}`, { method: "PUT", body: JSON.stringify(payload) });
                toast("Task updated");
            }
            else {
                await api(`/api/tasks?filename=${encodeURIComponent(state.selectedTaskFile)}`, { method: "POST", body: JSON.stringify(payload) });
                toast("Task created");
            }
            closeModal("modal-task");
            loadTasks(state.selectedTaskFile);
            loadTaskFiles();
        }
        catch (e) {
            alert(`Failed: ${e.message}`);
        }
    });
    openModal("modal-task");
}
function populateSettingsForm(raw) {
    for (const [fieldId, dataPath] of Object.entries(SETTINGS_FIELD_MAP)) {
        const el = document.getElementById(fieldId);
        if (!el)
            continue;
        const val = getNestedValue(raw, dataPath);
        if (val !== undefined) {
            el.value = String(val);
        }
    }
}
function collectFormValues() {
    const result = { ...state.rawConfig };
    for (const [, dataPath] of Object.entries(SETTINGS_FIELD_MAP)) {
        const els = document.querySelectorAll(`[data-path="${dataPath}"]`);
        if (els.length === 0)
            continue;
        const rawVal = els[0].value;
        let parsed = rawVal;
        if (dataPath.includes("_size") || dataPath.includes("_min") || dataPath.includes("_max") || dataPath.includes("port") || dataPath.includes("multiplier") || dataPath.includes("buffer")) {
            const num = Number(rawVal);
            if (!isNaN(num))
                parsed = num;
        }
        setNestedValue(result, dataPath, parsed);
    }
    return result;
}
async function saveSettings() {
    try {
        await api("/api/config", {
            method: "PUT",
            body: JSON.stringify({ raw: collectFormValues() }),
        });
        state.rawConfig = collectFormValues();
        const status = document.getElementById("settings-save-status");
        status.textContent = "✅ Saved successfully";
        status.className = "text-sm text-green-600";
        setTimeout(() => {
            status.textContent = "";
            hideSaveSettings();
        }, 3000);
    }
    catch (e) {
        const status = document.getElementById("settings-save-status");
        status.textContent = `❌ Failed: ${e.message}`;
        status.className = "text-sm text-red-600";
    }
}
function markSettingsDirty() {
    document.getElementById("settings-save-area").classList.remove("hidden");
    document.getElementById("btn-save-settings").classList.remove("hidden");
}
function hideSaveSettings() {
    document.getElementById("settings-save-area").classList.add("hidden");
    document.getElementById("btn-save-settings").classList.add("hidden");
}
let searchTimeout = null;
async function handleSearch() {
    const input = document.getElementById("search-input").value.trim();
    const resultsDiv = document.getElementById("search-results");
    const statusDiv = document.getElementById("search-status");
    if (input.length < 2) {
        resultsDiv.classList.add("hidden");
        statusDiv.classList.add("hidden");
        return;
    }
    const res = await api("/api/watchlists/search", { method: "POST", body: JSON.stringify({ code: input }) });
    resultsDiv.classList.remove("hidden");
    if (res.found) {
        statusDiv.classList.remove("hidden");
        statusDiv.innerHTML = `<span class="text-green-600">Found in:</span> ${res.inLists.join(", ")}`;
        resultsDiv.innerHTML = res.inLists.map(l => `<div class="px-3 py-2 text-sm text-gray-600 hover:bg-gray-50">In: ${l}</div>`).join("");
    }
    else if (res.fuzzyMatches?.length) {
        statusDiv.classList.add("hidden");
        resultsDiv.innerHTML = res.fuzzyMatches.map((m) => `<div class="px-3 py-2 text-sm hover:bg-gray-50"><span class="text-gray-900">${m.code}</span> <span class="text-gray-500 ml-2">${m.name || ""}</span></div>`).join("");
    }
    else {
        statusDiv.classList.remove("hidden");
        statusDiv.innerHTML = '<span class="text-red-500">Not found</span>';
        resultsDiv.innerHTML = '<div class="px-3 py-2 text-sm text-gray-400">No matches</div>';
    }
}
// ---- Browse Directory Modal ----
let browseTargetInputId = "run-output-path";
let browseCurrentPath = "/";
function openBrowseDir(targetInputId, startPath) {
    browseTargetInputId = targetInputId;
    browseCurrentPath = startPath || "/";
    document.getElementById("browse-new-folder").classList.add("hidden");
    document.getElementById("modal-browse-dir").classList.remove("hidden");
    loadBrowseDir(browseCurrentPath);
}
async function loadBrowseDir(path) {
    const list = document.getElementById("browse-list");
    list.innerHTML = '<div class="text-gray-400 text-sm text-center py-8">Loading...</div>';
    try {
        const data = await api(`/api/browse/?path=${encodeURIComponent(path)}`);
        browseCurrentPath = data.current_path;
        document.getElementById("browse-breadcrumb").textContent = data.relative_path || data.current_path;
        document.getElementById("browse-current-path").textContent = data.relative_path || data.current_path;
        // Parent button
        const upBtn = document.getElementById("btn-browse-up");
        upBtn.disabled = !data.has_parent;
        upBtn.style.opacity = data.has_parent ? "1" : "0.4";
        const items = data.directories;
        if (items.length === 0) {
            list.innerHTML = '<div class="text-gray-400 text-sm text-center py-8">No subdirectories</div>';
            return;
        }
        list.innerHTML = items.map(d => `<div class="browse-item flex items-center gap-2 px-3 py-1.5 rounded cursor-pointer hover:bg-blue-50" data-name="${d}">
                <span class="text-base">📁</span>
                <span class="text-sm text-gray-800">${d}</span>
            </div>`).join("");
        list.querySelectorAll(".browse-item").forEach(el => {
            el.addEventListener("dblclick", () => {
                const name = el.dataset.name;
                const parent = browseCurrentPath === "/" ? "" : browseCurrentPath;
                loadBrowseDir(parent ? `${parent}/${name}` : name);
            });
        });
    }
    catch (e) {
        list.innerHTML = `<div class="text-red-400 text-sm text-center py-8">Error: ${e.message}</div>`;
    }
}
function handleBrowseSelect() {
    const target = document.getElementById(browseTargetInputId);
    if (target) {
        const rel = document.getElementById("browse-current-path").textContent;
        target.value = rel || browseCurrentPath;
    }
    closeModal("modal-browse-dir");
}
function handleBrowseMkdir() {
    const nameInput = document.getElementById("browse-new-folder-name");
    const name = nameInput.value.trim();
    if (!name)
        return;
    api("/api/browse/mkdir", {
        method: "POST",
        body: JSON.stringify({ path: browseCurrentPath, name }),
    }).then(() => {
        nameInput.value = "";
        document.getElementById("browse-new-folder").classList.add("hidden");
        loadBrowseDir(browseCurrentPath);
        toast("Folder created");
    }).catch((e) => toast(`Failed: ${e.message}`));
}
// ---- End of Browse functions ----
function toast(msg) {
    const el = document.getElementById("toast");
    document.getElementById("toast-message").textContent = msg;
    el.classList.remove("hidden");
    setTimeout(() => el.classList.add("hidden"), 3000);
}
function setupEventListeners() {
    document.querySelectorAll('[data-tab]').forEach(btn => {
        btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    });
    document.getElementById("btn-new-watchlist").addEventListener("click", openNewWatchlist);
    document.getElementById("btn-add-stock").addEventListener("click", openAddStockModal);
    document.getElementById("btn-batch-import").addEventListener("click", openBatchModal);
    document.getElementById("btn-save-watchlist").addEventListener("click", saveWatchlist);
    document.getElementById("btn-cancel-add").addEventListener("click", () => closeModal("modal-add-stock"));
    document.getElementById("btn-confirm-add").addEventListener("click", confirmAddStock);
    document.getElementById("add-stock-market").addEventListener("change", updateAddStockPreview);
    document.getElementById("add-stock-code").addEventListener("input", updateAddStockPreview);
    document.getElementById("btn-cancel-batch").addEventListener("click", () => closeModal("modal-batch"));
    document.getElementById("btn-confirm-batch").addEventListener("click", confirmBatchImport);
    document.getElementById("btn-cancel-task").addEventListener("click", () => closeModal("modal-task"));
    document.getElementById("btn-new-task").addEventListener("click", () => openTaskModal());
    document.getElementById("task-file-list").addEventListener("click", async (e) => {
        const target = e.target;
        const delBtn = target.closest(".tf-delete-btn");
        if (delBtn) {
            e.stopPropagation();
            const filename = delBtn.dataset.filename;
            if (!filename)
                return;
            if (!confirm(`Delete "${filename}" and all tasks within?`))
                return;
            try {
                await api(`/api/task-files/${encodeURIComponent(filename)}`, { method: "DELETE" });
                toast(`Deleted ${filename}`);
                if (state.selectedTaskFile === filename) {
                    state.selectedTaskFile = "";
                    renderTaskFileSidebar();
                    const emptyMsg = document.getElementById("task-file-empty");
                    const listArea = document.getElementById("task-list-area");
                    emptyMsg.classList.remove("hidden");
                    emptyMsg.textContent = "Select a task file";
                    listArea.classList.add("hidden");
                }
                loadTaskFiles();
            }
            catch (err) {
                alert("Failed to delete task file");
            }
            return;
        }
        const btn = target.closest(".task-file-item");
        if (btn) {
            const filename = btn.dataset.filename;
            if (filename)
                selectTaskFile(filename);
        }
    });
    document.getElementById("btn-new-task-file").addEventListener("click", async () => {
        const name = prompt("New task file name (without extension):");
        if (!name)
            return;
        const filename = name.startsWith("tasks") ? name + ".yaml" : "tasks_" + name.replace(/\s+/g, "_") + ".yaml";
        try {
            await api("/api/task-files", { method: "POST", body: JSON.stringify({ filename }) });
            toast(`Created ${filename}`);
            await loadTaskFiles();
            selectTaskFile(filename);
        }
        catch (e) {
            alert(`Failed: ${e.message}`);
        }
    });
    document.getElementById("search-input").addEventListener("input", () => {
        if (searchTimeout)
            clearTimeout(searchTimeout);
        searchTimeout = setTimeout(handleSearch, 300);
    });
    document.addEventListener("click", (e) => {
        const sr = document.getElementById("search-results");
        const si = document.getElementById("search-input");
        if (!sr.contains(e.target) && e.target !== si)
            sr.classList.add("hidden");
    });
    // Event delegation for watchlist actions: delete and select
    const watchlistList = document.getElementById("watchlist-list");
    if (watchlistList) {
        watchlistList.addEventListener("click", async (e) => {
            const target = e.target;
            // Delete button pressed?
            const delBtn = target.closest(".wl-delete-btn");
            if (delBtn) {
                e.stopPropagation();
                const filename = delBtn.dataset.filename;
                if (!filename)
                    return;
                const wl = state.watchlists.find(w => w.filename === filename);
                const name = wl?.name ?? filename;
                if (!confirm(`Delete watchlist '${name}'? This cannot be undone.`))
                    return;
                try {
                    await api(`/api/watchlists/${filename}`, { method: "DELETE" });
                    toast(`Deleted ${name}`);
                    await loadWatchlists();
                    if (state.selectedWatchlist === filename) {
                        state.selectedWatchlist = null;
                        const content = document.getElementById("watchlist-content");
                        const empty = document.getElementById("watchlist-empty");
                        if (content)
                            content.classList.add("hidden");
                        if (empty)
                            empty.classList.remove("hidden");
                    }
                }
                catch (err) {
                    alert("Failed to delete watchlist");
                }
                return;
            }
            // Selection: clicking anywhere on the watchlist item (button area)
            const btn = target.closest('[data-filename]');
            if (btn) {
                const filename = btn.dataset.filename;
                if (filename) {
                    selectWatchlist(filename);
                }
            }
        });
    }
    const saveBtn = document.getElementById("btn-save-settings");
    if (saveBtn)
        saveBtn.addEventListener("click", saveSettings);
    const resetBtn = document.getElementById("btn-reset-settings");
    if (resetBtn)
        resetBtn.addEventListener("click", () => {
            populateSettingsForm(state.rawConfig);
            hideSaveSettings();
        });
    document.querySelectorAll("#settings-form input, #settings-form select").forEach(el => {
        el.addEventListener("input", markSettingsDirty);
        el.addEventListener("change", markSettingsDirty);
    });
    const toggleBtn = document.getElementById("btn-toggle-token");
    if (toggleBtn)
        toggleBtn.addEventListener("click", () => {
            const input = document.getElementById("cfg-tushare-token");
            const isPassword = input.type === "password";
            input.type = isPassword ? "text" : "password";
            toggleBtn.textContent = isPassword ? "🙈" : "👁️";
        });
    const copyBtn = document.getElementById("btn-copy-token");
    if (copyBtn)
        copyBtn.addEventListener("click", () => {
            const token = document.getElementById("cfg-tushare-token").value;
            if (!token) {
                toast("Token is empty");
                return;
            }
            navigator.clipboard.writeText(token).then(() => toast("Token copied to clipboard"));
        });
    // Library sub-tab switching
    document.querySelectorAll('[data-subtab]').forEach(btn => {
        btn.addEventListener("click", () => switchLibrarySubTab(btn.dataset.subtab));
    });
    document.getElementById("btn-save-params").addEventListener("click", saveIndicatorParams);
    document.getElementById("btn-cancel-params").addEventListener("click", () => closeModal("modal-indicator-params"));
    // RUNS: tab and modal wiring
    const runsTab = document.getElementById("tab-runs");
    if (runsTab)
        runsTab.addEventListener("click", () => switchTab("runs"));
    const newRunBtn = document.getElementById("btn-new-run");
    if (newRunBtn)
        newRunBtn.addEventListener("click", () => {
            resetRunModal();
            openModal("modal-new-run");
        });
    // Runs modal: cancel/back/check/execute
    document.getElementById("btn-cancel-run")?.addEventListener("click", () => {
        resetRunModal();
        closeModal("modal-new-run");
    });
    document.getElementById("btn-back-run")?.addEventListener("click", () => {
        document.getElementById("run-step-type").classList.remove("hidden");
        document.getElementById("run-step-config").classList.add("hidden");
        document.getElementById("run-step-preview").classList.add("hidden");
        document.getElementById("btn-back-run").classList.add("hidden");
        document.getElementById("btn-check-run").classList.add("hidden");
        document.getElementById("btn-execute-run").classList.add("hidden");
        selectedRunType = "";
    });
    document.getElementById("btn-check-run")?.addEventListener("click", preflightCheck);
    document.getElementById("btn-execute-run")?.addEventListener("click", executeRun);
    // Run type select cards
    document.querySelectorAll('[data-type]').forEach(btn => {
        btn.addEventListener("click", () => selectRunType(btn.dataset.type));
    });
    // CLI preview on form changes
    document.getElementById("run-stock-code")?.addEventListener("input", updateCliPreview);
    document.querySelectorAll(".run-indicator").forEach(el => {
        el.addEventListener("change", () => updateCliPreview());
    });
    // Run sub-tab switching
    document.querySelectorAll('[data-runtab]').forEach(btn => {
        btn.addEventListener("click", () => {
            const tab = btn.dataset.runtab;
            document.querySelectorAll(".run-subtab").forEach(t => {
                t.style.borderColor = "transparent";
                t.style.color = "#6b7280";
            });
            btn.style.borderColor = "#3b82f6";
            btn.style.color = "#2563eb";
            document.querySelectorAll(".run-tab-content").forEach(p => p.classList.add("hidden"));
            document.getElementById(`runtab-${tab}`)?.classList.remove("hidden");
        });
    });
    // Global helpers for onclick handlers
    window.copyToClipboard = copyToClipboard;
    window.runAgain = runAgain;
    window.deleteRun = deleteRun;
    // Browse directory buttons
    document.getElementById("btn-browse-dir")?.addEventListener("click", () => {
        const input = document.getElementById("run-output-path");
        openBrowseDir("run-output-path", input?.value || "");
    });
    document.getElementById("btn-browse-close")?.addEventListener("click", () => closeModal("modal-browse-dir"));
    document.getElementById("btn-browse-cancel")?.addEventListener("click", () => closeModal("modal-browse-dir"));
    document.getElementById("btn-browse-select")?.addEventListener("click", handleBrowseSelect);
    document.getElementById("btn-browse-up")?.addEventListener("click", () => {
        // Navigate parent
        const slashIdx = browseCurrentPath.lastIndexOf("/");
        const parent = slashIdx > 0 ? browseCurrentPath.slice(0, slashIdx) : "/";
        loadBrowseDir(parent);
    });
    document.getElementById("btn-browse-new")?.addEventListener("click", () => {
        document.getElementById("browse-new-folder").classList.toggle("hidden");
        document.getElementById("browse-new-folder-name").focus();
    });
    document.getElementById("btn-browse-new-ok")?.addEventListener("click", handleBrowseMkdir);
    document.getElementById("browse-new-folder-name")?.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            handleBrowseMkdir();
        }
    });
}
init();
