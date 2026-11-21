import { 
    MARKET_SUFFIX, 
    SETTINGS_FIELD_MAP, 
    getNestedValue, 
    setNestedValue,
    formatStockCode,
    isActiveRunStatus,
    escapeHtml,
    mdToHtml
} from "./utils.js";

interface WatchlistItem {
    code: string;
    name?: string;
    tags: string[];
}

interface WatchlistData {
    filename: string;
    name: string;
    description: string;
    items: WatchlistItem[];
}

interface WatchlistSummary {
    filename: string;
    name: string;
    itemCount: number;
    path: string;
}

interface TaskData {
    id: string;
    filename: string;
    name: string;
    watchlist: string;
    strategies: string[];
    days_back?: number | null;
}

interface StrategyInfo {
    id: string;
    name: string;
    type: string;
}

interface LibraryStrategyInfo {
    id: string;
    name: string;
    type: string;
    description: string;
    min_lookback_days: number;
    required_indicators: string[];
}

interface LibraryIndicatorInfo {
    name: string;
    category: string;
    params: Record<string, any>;
    required_fields: string[];
    output_fields: string[];
    lookback_bars: number;
}

// Run record type for Runs feature
interface RunRecord {
    id: string;
    name: string;
    run_type: string;
    config: Record<string, any>;
    status: string;
    created_at: string;
    started_at: string | null;
    finished_at: string | null;
    duration_ms: number | null;
    error: string | null;
    output_path: string | null;
    report_path: string | null;
    signal_count: number;
    preset_id: string | null;
    log_path: string | null;
    progress?: RunProgress | null;
}

interface RunProgress {
    current: number;
    total: number;
    percentage: number;
    phase?: "download" | "analysis";
    task?: string | null;
    sequence?: number;
}

interface TaskFileInfo {
    filename: string;
    taskCount: number;
}

const state = {
    watchlists: [] as WatchlistSummary[],
    selectedWatchlist: null as string | null,
    currentWatchlistData: null as WatchlistData | null,
    watchlistDirty: false,
    tasks: [] as TaskData[],
    strategies: [] as StrategyInfo[],
    taskFiles: [] as TaskFileInfo[],
    selectedTaskFile: "" as string,
    rawConfig: {} as Record<string, unknown>,
    // Runs (new)
    runsList: [] as RunRecord[],
    selectedRunId: null as string | null,
    selectedRun: null as RunRecord | null,
    // Library (new) data
    libraryStrategies: [] as LibraryStrategyInfo[],
    libraryIndicators: [] as LibraryIndicatorInfo[],
    currentIndicatorConfig: null as string | null,
};

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
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
    } else {
        selectTaskFile("");
    }
    window.addEventListener("beforeunload", (e) => {
        if (state.watchlistDirty) {
            e.preventDefault();
            (e as BeforeUnloadEvent).returnValue = "";
        }
    });
}

async function loadStrategies() {
    const res = await api<{ strategies: StrategyInfo[] }>("/api/strategies");
    state.strategies = res.strategies;
}

// Library data fetchers
async function loadLibraryStrategies() {
    const res = await api<{ strategies: LibraryStrategyInfo[] }>("/api/library/strategies");
    state.libraryStrategies = res.strategies;
    renderLibraryStrategies();
}

async function loadLibraryIndicators() {
    const res = await api<{ indicators: LibraryIndicatorInfo[] }>("/api/library/indicators");
    state.libraryIndicators = res.indicators;
    renderLibraryIndicators();
}

async function loadWatchlists() {
    state.watchlists = await api<WatchlistSummary[]>("/api/watchlists");
    renderWatchlistSidebar();
}

// Runs data fetch
let runsPollingTimer: ReturnType<typeof setInterval> | null = null;
let activeRunTab = "config";

async function loadRuns() {
    try {
        const res = await api<{ runs: RunRecord[] }>("/api/runs/");
        state.runsList = res.runs || [];
        renderRunsList();
        // Refresh detail panel if a run status changed
        if (state.selectedRunId) {
            const updated = state.runsList.find(r => r.id === state.selectedRunId);
            if (updated && updated.status !== state.selectedRun?.status) {
                state.selectedRun = updated;
                renderRunsDetail(updated);
                if (!isActiveRunStatus(updated.status)) {
                    if (sseSource) { sseSource.close(); sseSource = null; sseTargetRunId = null; }
                } else {
                    connectSSE(updated.id);
                }
            } else if (updated?.progress) {
                applyRunProgress(updated.id, updated.progress);
            }
        }
    } catch (e) {
        console.error('Failed to load runs:', e);
    }
}

function startRunsPolling() {
    if (runsPollingTimer) return;
    runsPollingTimer = setInterval(loadRuns, 3000);
}

function stopRunsPolling() {
    if (runsPollingTimer) {
        clearInterval(runsPollingTimer);
        runsPollingTimer = null;
    }
}

function renderRunsList() {
    const list = document.getElementById('runs-list')!;
    if (!list) return;
    if (!state.runsList || state.runsList.length === 0) {
        list.innerHTML = '<li class="text-gray-400 text-sm text-center py-8">No runs yet</li>';
        return;
    }
    list.innerHTML = state.runsList.map(r => {
        const active = state.selectedRunId === r.id ? 'bg-blue-50 border-l-2 border-blue-500' : '';
        const time = new Date(r.created_at).toLocaleString();
        return `<li class="px-3 py-2 rounded cursor-pointer hover:bg-gray-100 ${active}" data-run-id="${r.id}">` +
            `<div class="flex items-center justify-between">` +
            `<div class="flex-1 min-w-0"><div class="font-medium text-sm truncate">${escapeHtml(r.name)}</div>` +
            `<div class="text-xs text-gray-500">${r.run_type} • ${r.status} • ${time}</div></div>` +
            `<button class="ml-2 text-gray-400 hover:text-red-500 p-1 rounded flex-shrink-0" onclick="event.stopPropagation(); deleteRun('${r.id}')" title="Delete run">✕</button>` +
            `</div></li>`;
    }).join('');
    list.querySelectorAll('[data-run-id]').forEach(el => {
        el.addEventListener('click', () => {
            const id = (el as HTMLElement).dataset.runId!;
            selectRun(id);
        });
    });
}

async function selectRun(runId: string) {
    if (state.selectedRunId !== runId) {
        activeRunTab = "config";
        sseSource?.close();
        sseSource = null;
        sseTargetRunId = null;
    }
    state.selectedRunId = runId;
    renderRunsList();
    try {
        const data = await api<{ run: RunRecord }>(`/api/runs/${runId}`);
        if (state.selectedRunId !== runId) return;
        state.selectedRun = data.run;
        renderRunsDetail(state.selectedRun);
        if (isActiveRunStatus(data.run.status)) {
            connectSSE(runId);
        }
    } catch (e) {
        console.error('Failed to load run details:', e);
    }
}

// ---- Runs detail rendering (4 sub-tabs) ----

function renderRunsDetail(run: RunRecord | null) {
    const emptyState = document.getElementById("runs-empty-state")!;
    const detail = document.getElementById("runs-detail")!;
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

    showRunTab(activeRunTab);
}

function showRunTab(tab: string) {
    activeRunTab = tab;
    document.querySelectorAll<HTMLElement>(".run-subtab").forEach(button => {
        const active = button.dataset.runtab === tab;
        button.style.borderColor = active ? "#3b82f6" : "transparent";
        button.style.color = active ? "#2563eb" : "#6b7280";
    });
    document.querySelectorAll(".run-tab-content").forEach(panel => {
        panel.classList.toggle("hidden", panel.id !== `runtab-${tab}`);
    });
}

function renderConfigTab(run: RunRecord) {
    const panel = document.getElementById("runtab-config")!;
    let html = `<div class="space-y-2 text-sm">
        <div class="grid grid-cols-2 gap-x-4 gap-y-1">
            <span class="text-gray-500">Type:</span><span class="font-mono">${run.run_type}</span>
            <span class="text-gray-500">Status:</span><span>${run.status}</span>`;
    if (run.started_at) html += `<span class="text-gray-500">Started:</span><span>${new Date(run.started_at).toLocaleString()}</span>`;
    if (run.finished_at) html += `<span class="text-gray-500">Finished:</span><span>${new Date(run.finished_at).toLocaleString()}</span>`;
    if (run.duration_ms) html += `<span class="text-gray-500">Duration:</span><span>${(run.duration_ms / 1000).toFixed(1)}s</span>`;
    if (run.run_type === "stock_scan") {
        if (run.config?.code) html += `<span class="text-gray-500">Code:</span><span class="font-mono">${escapeHtml(run.config.code)}</span>`;
        if (run.config?.start_date) html += `<span class="text-gray-500">Start:</span><span class="font-mono">${escapeHtml(run.config.start_date)}</span>`;
        if (run.config?.end_date) html += `<span class="text-gray-500">End:</span><span class="font-mono">${escapeHtml(run.config.end_date)}</span>`;
        if (run.config?.indicators) {
            const indNames = (run.config.indicators as string[]).join(", ");
            html += `<span class="text-gray-500">Indicators:</span><span class="font-mono">${escapeHtml(indNames)}</span>`;
        }
        if (run.config?.output_path) html += `<span class="text-gray-500">Output:</span><span class="font-mono text-xs">${escapeHtml(run.output_path || run.config.output_path)}</span>`;
    }
    if (run.signal_count) {
        const label = run.run_type === "stock_scan" ? "Bars:" : "Signals:";
        html += `<span class="text-gray-500">${label}</span><span>${run.signal_count}</span>`;
    }
    if (run.error) html += `<span class="text-gray-500">Error:</span><span class="text-red-600">${escapeHtml(run.error)}</span>`;
    html += `</div></div>`;
    html += `<details class="mt-3"><summary class="text-sm text-gray-500 cursor-pointer">Raw Config (JSON)</summary>
        <pre class="mt-2 bg-gray-50 p-3 rounded text-xs overflow-x-auto">${escapeHtml(JSON.stringify(run.config, null, 2))}</pre></details>`;
    const checkResume = (run.status === "failed" || run.status === "partial" ||
                         run.status === "cancelled" || run.status === "interrupted") &&
                        (run.run_type === "task_run" || run.run_type === "watchlist_run");
    html += `<div class="flex gap-2 mt-4 pt-3 border-t">
        <button onclick="runAgain('${run.id}')" class="text-sm px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600">▶ Run Again</button>
        ${checkResume ? '<span id="resume-action"></span>' : ""}
    </div>`;
    panel.innerHTML = html;
    const resumeAction = panel.querySelector("#resume-action");
    if (resumeAction) {
        api<{ can_resume: boolean; reason?: string }>(`/api/runs/${run.id}/checkpoint`)
            .then(checkpoint => {
                if (!resumeAction.isConnected) return;
                if (!checkpoint.can_resume) {
                    if (checkpoint.reason && checkpoint.reason !== "no_checkpoint") {
                        resumeAction.textContent = checkpoint.reason;
                    }
                    return;
                }
                const button = document.createElement("button");
                button.textContent = "⏵ Resume";
                button.className = "text-sm px-3 py-1 bg-amber-500 text-white rounded hover:bg-amber-600";
                button.onclick = () => resumeRun(run.id);
                resumeAction.append(button);
            }).catch(() => {
                if (resumeAction.isConnected) resumeAction.textContent = "Cannot check checkpoint";
            });
    }
}

function renderProgressTab(run: RunRecord) {
    stopLogPolling();
    const panel = document.getElementById("runtab-progress")!;
    let statusHtml = "";
    if (run.status === "completed") {
        const label = run.run_type === "stock_scan" ? "bar(s)" : "signal(s)";
        statusHtml = `<div class="text-center py-2"><div class="text-2xl mb-1">✅</div>
            <div class="text-lg font-medium">Complete</div>
            ${run.signal_count ? `<div class="text-sm text-gray-500 mt-1">${run.signal_count} ${label}</div>` : ""}</div>`;
    } else if (run.status === "partial") {
        statusHtml = `<div class="text-center py-2 text-amber-600">Partially complete — review data coverage in the report.
            ${run.error ? escapeHtml(run.error) : ""}</div>`;
    } else if (run.status === "failed") {
        statusHtml = `<div class="text-center py-2"><div class="text-2xl mb-1">❌</div>
            <div class="text-lg font-medium text-red-600">Failed</div>
            <div class="text-sm text-red-500 mt-1">${escapeHtml(run.error || "unknown")}</div></div>`;
    } else if (run.status === "interrupted") {
        statusHtml = `<div class="text-center py-2"><div class="text-2xl mb-1">⚠️</div>
            <div class="text-lg font-medium text-yellow-600">Interrupted</div>
            <div class="text-sm text-gray-500 mt-1">${escapeHtml(run.error || "Server restarted while run was active")}</div></div>`;
    } else if (["running", "cancelling"].includes(run.status)) {
        statusHtml = `<div class="space-y-1">
            <div class="h-3 bg-gray-200 rounded overflow-hidden">
                <div id="run-progress-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" class="h-full bg-blue-500 transition-all" style="width:0%"></div>
            </div>
            <div id="run-progress-text" class="text-sm text-gray-600">${run.status === "cancelling" ? "Stopping — waiting for the current request..." : "Starting..."}</div>
        </div>`;
    } else {
        statusHtml = `<div class="text-gray-500 text-center py-4">Status: ${run.status}</div>`;
    }

    // Read the latest lines from the run's log file, including after completion.
    // SSE progress events use a separate update path.
    const logBox = `<div class="mt-3">
        <div class="flex items-center justify-between mb-1">
            <span class="text-xs font-medium text-gray-500">Log file</span>
            <span id="run-log-path" class="text-xs text-gray-400 font-mono truncate max-w-[70%]" title="${run.log_path || ''}">${run.log_path || '—'}</span>
        </div>
        <div id="run-log-container" class="bg-gray-900 text-green-400 font-mono text-xs p-3 rounded h-64 overflow-y-auto whitespace-pre-wrap"></div>
    </div>`;
    panel.innerHTML = statusHtml + logBox;
    if (run.progress) applyRunProgress(run.id, run.progress);

    loadRealLog(run.id, false);
    if (["running", "cancelling"].includes(run.status)) {
        connectSSE(run.id);
        startLogPolling(run.id);
    }
}

let logPollTimer: number | null = null;

function stopLogPolling() {
    if (logPollTimer !== null) {
        window.clearInterval(logPollTimer);
        logPollTimer = null;
    }
}

function startLogPolling(runId: string) {
    stopLogPolling();
    logPollTimer = window.setInterval(() => loadRealLog(runId, true), 2000);
}

async function loadRealLog(runId: string, appendOnly: boolean) {
    try {
        const res = await api<{ content: string; exists: boolean; path: string | null; message?: string }>(
            `/api/runs/${runId}/logs?tail=500`);
        const container = document.getElementById("run-log-container");
        if (!container || state.selectedRunId !== runId) return;
        if (!res.exists) {
            if (!appendOnly) {
                container.textContent = res.message || "Log not available yet";
            }
            return;
        }
        // Replace the displayed tail with the current file tail on each poll.
        container.textContent = res.content || "(log file is empty)";
        container.scrollTop = container.scrollHeight;
    } catch (_e) {
        // transient — keep whatever is rendered
    }
}

function renderReportTab(run: RunRecord) {
    const panel = document.getElementById("runtab-report")!;
    if (isActiveRunStatus(run.status)) {
        panel.innerHTML = '<div class="text-gray-500 text-center py-8">Report available after completion</div>';
        return;
    }

    if (run.run_type === "stock_scan") {
        const code = run.config?.code || run.name;
        panel.innerHTML = '<div class="text-sm text-gray-500 text-center">Loading indicator data...</div>';
        api<{ data: Record<string, any>[] | null; code?: string; bar_count?: number; message?: string; legacy_warning?: string }>(`/api/runs/${run.id}/indicator-data`)
            .then(data => {
                if (!data.data || data.data.length === 0) {
                    panel.innerHTML = `<div class="text-gray-500 text-center py-8">${escapeHtml(data.message || "No indicator data")}</div>`;
                    return;
                }
                const cols = Object.keys(data.data[0]).filter(k => k !== "index");
                const ohlcvCols = ["date","open","high","low","close","volume"];
                const otherCols = cols.filter(c => !ohlcvCols.includes(c));
                const orderedCols = [...ohlcvCols.filter(c => cols.includes(c)), ...otherCols];

                let html = data.legacy_warning ? '<div class="text-amber-700 mb-2">This older report may have been replaced by a later run.</div>' : '';
                html += `<div class="mb-2 text-sm text-gray-600">Stock: <span class="font-mono font-semibold">${data.code || code}</span>`;
                if ((run.config as any)?.start_date) {
                    html += ` | Range: <span class="font-mono">${(run.config as any).start_date} → ${(run.config as any).end_date || (run.config as any).start_date}</span>`;
                }
                html += ` | Total bars: ${data.bar_count || data.data.length}</div>`;
                html += '<div style="overflow-x:auto"><table class="min-w-full divide-y divide-gray-200 text-xs"><thead class="bg-gray-50"><tr>';
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
                        const fontClass = (c === 'K'|| c === 'D' || c === 'J' || c === 'MACD' || c === 'RSI') ? 'font-mono' : '';
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

    panel.innerHTML = '<div class="text-sm text-gray-500 text-center">Loading...</div>';
    api<{ report: string | null; message?: string; legacy_warning?: string; partial?: boolean }>(`/api/runs/${run.id}/report`)
        .then(data => {
            if (data.report) {
                const warning = data.legacy_warning ? '<div class="text-amber-700 mb-2">This older report may have been replaced by a later run.</div>' : '';
                const download = data.partial ? `<a class="text-blue-600 underline" href="/api/runs/${encodeURIComponent(run.id)}/report?download=true" download>Download partial report</a>` : '';
                panel.innerHTML = warning + download + `<div class="prose max-w-none">${mdToHtml(data.report)}</div>`;
            } else {
                panel.innerHTML = `<div class="text-gray-500 text-center py-8">${escapeHtml(data.message || "No content")}</div>`;
            }
        }).catch(() => { panel.innerHTML = '<div class="text-red-500 text-center">Failed to load</div>'; });
}

function renderFilesTab(run: RunRecord) {
    const panel = document.getElementById("runtab-files")!;
    if (!run.output_path) {
        panel.innerHTML = '<div class="text-gray-500 text-center py-8">No output files</div>';
        return;
    }
    api<{ files: { name: string; relative_path?: string; path: string; size: string; type: string }[] }>(`/api/runs/${run.id}/files`)
        .then(data => {
            if (!data.files.length) { panel.innerHTML = '<div class="text-gray-500 text-center py-8">No files</div>'; return; }
            let html = `<div class="mb-3 flex justify-between items-center">
                <span class="text-sm text-gray-500 font-mono">${run.output_path}</span>
                <button onclick="openFolder('${run.id}')" class="text-sm px-3 py-1 bg-gray-100 hover:bg-gray-200 rounded text-gray-700">📁 Open Folder</button>
            </div>`;
            html += `<table class="min-w-full divide-y divide-gray-200 text-sm">
                <thead class="bg-gray-50"><tr><th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">File</th>
                <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Size</th>
                <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Actions</th></tr></thead><tbody>`;
            data.files.forEach(f => {
                html += `<tr><td class="px-4 py-2 font-mono text-xs">${escapeHtml(f.relative_path || f.name)}</td>
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
    document.getElementById("run-step-type")!.classList.remove("hidden");
    document.getElementById("run-step-config")!.classList.add("hidden");
    document.getElementById("run-step-preview")!.classList.add("hidden");
    document.getElementById("btn-back-run")!.classList.add("hidden");
    document.getElementById("btn-check-run")!.classList.add("hidden");
    document.getElementById("btn-execute-run")!.classList.add("hidden");
    ["stock_scan", "watchlist_run", "task_run"].forEach(t => {
        document.getElementById(`run-config-${t}`)!.classList.add("hidden");
    });
}

function selectRunType(type: string) {
    selectedRunType = type;
    document.getElementById("run-step-type")!.classList.add("hidden");
    document.getElementById("run-step-config")!.classList.remove("hidden");
    document.getElementById("run-step-preview")!.classList.remove("hidden");
    document.getElementById("btn-back-run")!.classList.remove("hidden");
    document.getElementById("btn-check-run")!.classList.remove("hidden");
    document.getElementById("btn-execute-run")!.classList.remove("hidden");
    // Hide all config sections first, then show the selected one
    ["stock_scan", "watchlist_run", "task_run"].forEach(t => {
        document.getElementById(`run-config-${t}`)!.classList.add("hidden");
    });
    document.getElementById(`run-config-${type}`)!.classList.remove("hidden");
    if (type === "stock_scan") {
        const today = new Date().toISOString().split("T")[0];
        (document.getElementById("run-start-date") as HTMLInputElement).value = today;
        (document.getElementById("run-end-date") as HTMLInputElement).value = today;
    }
    populateRunFormFields(type);
    updateCliPreview();
}

function populateRunFormFields(type: string) {
    const today = new Date().toISOString().split("T")[0];
    if (type === "stock_scan") {
        const startDate = (document.getElementById("run-start-date") as HTMLInputElement);
        const endDate = (document.getElementById("run-end-date") as HTMLInputElement);
        if (startDate && !startDate.value) startDate.value = today;
        if (endDate && !endDate.value) endDate.value = today;
    } else if (type === "watchlist_run") {
        const sel = document.getElementById("run-watchlist-select") as HTMLSelectElement;
        sel.innerHTML = state.watchlists.map(w =>
            `<option value="${w.path}">${w.name} (${w.itemCount} stocks)</option>`
        ).join("");
        const stratDiv = document.getElementById("run-strategy-checkboxes")!;
        stratDiv.innerHTML = (state.strategies as any[])
            .map((s: any) => {
                const icon = s.type === "buy" ? "🔵" : "🔴";
                const label = s.name.replace(/(Buy|Sell)$/, "");
                return `<label class="flex items-center gap-2"><input type="checkbox" value="${s.id}" ${s.type === "buy" ? "checked" : ""} class="rounded"> ${icon} ${label}</label>`;
            }).join("");
    } else if (type === "task_run") {
        const sel = document.getElementById("run-task-config-select") as HTMLSelectElement;
        sel.innerHTML = (state as any).taskFiles.map((tf: any) =>
            `<option value="config/${tf.filename}">${tf.filename} (${tf.taskCount} tasks)</option>`
        ).join("");
    }
}

function updateCliPreview() {
    const preview = document.getElementById("run-cli-preview")!;
    if (!preview) return;
    if (selectedRunType === "stock_scan") {
        const code = (document.getElementById("run-stock-code") as HTMLInputElement).value || "CODE";
        const start = (document.getElementById("run-start-date") as HTMLInputElement).value;
        const end = (document.getElementById("run-end-date") as HTMLInputElement).value;
        const inds = Array.from(document.querySelectorAll(".run-indicator:checked"))
            .map((el: Element) => (el as HTMLInputElement).value).join(",");
        const output = (document.getElementById("run-output-path") as HTMLInputElement).value;
        let cmd = `python -m quantflow.cli scan --code ${code} --indicator ${inds || "kdj,dual_line"}`;
        if (start) cmd += ` --start ${start}`;
        if (end) cmd += ` --end ${end}`;
        if (output) cmd += ` --output ${output}`;
        preview.textContent = cmd;
    } else if (selectedRunType === "watchlist_run") {
        const wl = (document.getElementById("run-watchlist-select") as HTMLSelectElement)?.value || "WATCHLIST";
        const strategies = Array.from(document.querySelectorAll("#run-strategy-checkboxes input:checked"))
            .map((el: Element) => (el as HTMLInputElement).value).join(",");
        const output = (document.getElementById("run-output-path") as HTMLInputElement).value;
        let cmd = `python -m quantflow.cli monitor --watchlist ${wl}`;
        if (strategies) cmd += ` --strategies ${strategies}`;
        if (output) cmd += ` --output ${output}`;
        preview.textContent = cmd;
    } else if (selectedRunType === "task_run") {
        const tc = (document.getElementById("run-task-config-select") as HTMLSelectElement)?.value || "CONFIG";
        const daily = (document.getElementById("run-daily-mode") as HTMLInputElement).checked;
        const output = (document.getElementById("run-output-path") as HTMLInputElement).value;
        let cmd = `python -m quantflow.cli tasks --config ${tc}`;
        if (daily) cmd += ` --daily`;
        if (output) cmd += ` --output ${output}`;
        preview.textContent = cmd;
    }
}

async function executeRun() {
    const body: Record<string, any> = { run_type: selectedRunType };
    if (selectedRunType === "stock_scan") {
        body.code = (document.getElementById("run-stock-code") as HTMLInputElement).value;
        const start = (document.getElementById("run-start-date") as HTMLInputElement).value;
        const end = (document.getElementById("run-end-date") as HTMLInputElement).value;
        if (start) body.start_date = start;
        if (end) body.end_date = end;
        body.indicators = Array.from(document.querySelectorAll(".run-indicator:checked"))
            .map((el: Element) => (el as HTMLInputElement).value);
    } else if (selectedRunType === "watchlist_run") {
        body.watchlist = (document.getElementById("run-watchlist-select") as HTMLSelectElement).value;
        body.strategies = Array.from(document.querySelectorAll("#run-strategy-checkboxes input:checked"))
            .map((el: Element) => (el as HTMLInputElement).value);
    } else if (selectedRunType === "task_run") {
        body.task_config = (document.getElementById("run-task-config-select") as HTMLSelectElement).value;
        body.daily = (document.getElementById("run-daily-mode") as HTMLInputElement).checked;
    }
    const output = (document.getElementById("run-output-path") as HTMLInputElement).value;
    if (output) body.output_path = output;

    const errDiv = document.getElementById("run-validation-errors")!;
    try {
        const result = await api<{ ok: boolean; run_id?: string; errors?: string[] }>("/api/runs/", {
            method: "POST", body: JSON.stringify(body),
        });
        errDiv.classList.add("hidden");
        if (!result.ok) {
            errDiv.classList.remove("hidden");
            errDiv.innerHTML = result.errors!.map((e: string) => `• ${escapeHtml(e)}`).join("<br>");
            return;
        }
        closeModal("modal-new-run");
        toast("Run started");
        await loadRuns();
        startRunsPolling();
        if (result.run_id) selectRun(result.run_id);
    } catch (e: any) {
        toast(`Error: ${e.message}`);
    }
}

async function preflightCheck() {
    const body: Record<string, any> = { run_type: selectedRunType, validate_only: true };
    if (selectedRunType === "stock_scan") {
        body.code = (document.getElementById("run-stock-code") as HTMLInputElement).value;
    } else if (selectedRunType === "watchlist_run") {
        body.watchlist = (document.getElementById("run-watchlist-select") as HTMLSelectElement).value;
    } else if (selectedRunType === "task_run") {
        body.task_config = (document.getElementById("run-task-config-select") as HTMLSelectElement).value;
    }
    const output = (document.getElementById("run-output-path") as HTMLInputElement).value;
    if (output) body.output_path = output;
    const errDiv = document.getElementById("run-validation-errors")!;
    try {
        const result = await api<{ ok: boolean; errors?: string[] }>("/api/runs/", {
            method: "POST", body: JSON.stringify(body),
        });
        if (!result.ok) {
            errDiv.classList.remove("hidden");
            errDiv.innerHTML = result.errors!.map((e: string) => `• ${escapeHtml(e)}`).join("<br>");
        } else {
            errDiv.classList.add("hidden");
            toast("Checks passed");
        }
    } catch (e: any) {
        toast("Validation request sent");
    }
}

function formatRelativeTime(isoStr: string): string {
    const date = new Date(isoStr);
    const diffMs = Date.now() - date.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return "just now";
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    return date.toLocaleDateString();
}

let sseSource: EventSource | null = null;
let sseTargetRunId: string | null = null;

function applyRunProgress(runId: string, progress: RunProgress) {
    const run = state.selectedRun;
    if (state.selectedRunId !== runId || run?.id !== runId || run.status !== "running") return;
    if ((progress.sequence ?? 0) < (run.progress?.sequence ?? 0)) return;
    run.progress = progress;
    const bar = document.getElementById("run-progress-bar");
    const text = document.getElementById("run-progress-text");
    const phase = progress.phase === "download" ? "Downloading "
        : progress.phase === "analysis" ? "Analyzing " : "";
    if (bar) {
        bar.style.width = `${progress.percentage}%`;
        bar.setAttribute("aria-valuenow", String(progress.percentage));
    }
    if (text) text.textContent = `${phase}${progress.percentage}% (${progress.current}/${progress.total})`;
}

function connectSSE(runId: string) {
    if (sseTargetRunId === runId && sseSource) return;
    if (sseSource) sseSource.close();
    sseTargetRunId = runId;
    try {
        const stream = new EventSource(`/api/runs/${runId}/logs:sse`);
        sseSource = stream;
        // NOTE: "log" summary events are intentionally NOT rendered here.
        // The black box is populated from the real on-disk log file via
        // loadRealLog(); mixing SSE summaries would duplicate/mismatch it.
        stream.addEventListener("progress", (ev: Event) => {
            if (sseSource !== stream) return;
            applyRunProgress(runId, JSON.parse((ev as MessageEvent).data));
        });
        stream.addEventListener("status", async (ev: Event) => {
            if (sseSource !== stream || state.selectedRunId !== runId) return;
            const data = JSON.parse((ev as MessageEvent).data);
            if (!isActiveRunStatus(data.status)) {
                if (sseSource) sseSource.close();
                sseSource = null;
                sseTargetRunId = null;
                stopLogPolling();
                // Final refresh of the file log before freezing the view.
                await loadRealLog(runId, false);
                if (state.selectedRunId) await selectRun(state.selectedRunId);
                await loadRuns();
            }
        });
    } catch (_e) {
        /* SSE unavailable — queued or deleted */
    }
}

function appendLog(container: HTMLElement, message: string, level: string) {
    const time = new Date().toLocaleTimeString();
    const color = level === "error" ? "text-red-400" : level === "warning" ? "text-yellow-400" : "text-green-400";
    const entry = document.createElement("div");
    entry.className = `${color} break-all`;
    entry.textContent = `${time}  ${message}`;
    container.appendChild(entry);
    container.scrollTop = container.scrollHeight;
}

function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text).then(() => toast("Path copied"));
}

async function openFolder(runId: string) {
    try {
        const res = await api<{ ok: boolean; path?: string; message?: string }>(`/api/runs/${runId}/open-folder`, { method: "POST" });
        if (res.ok) {
            toast("Folder opened");
        } else {
            toast(res.message || "Failed to open folder");
        }
    } catch (e: any) {
        toast(`Error: ${e.message}`);
    }
}

function runAgain(runId: string) {
    const orig = state.runsList.find(r => r.id === runId);
    if (!orig) return;
    openModal("modal-new-run");
    resetRunModal();
    selectRunType(orig.run_type);
    const config = orig.config;
    if (orig.run_type === "stock_scan") {
        (document.getElementById("run-stock-code") as HTMLInputElement).value = config.code || "";
        if (config.start_date) {
            (document.getElementById("run-start-date") as HTMLInputElement).value = config.start_date;
        }
        if (config.end_date) {
            (document.getElementById("run-end-date") as HTMLInputElement).value = config.end_date;
        }
        if (Array.isArray(config.indicators)) {
            document.querySelectorAll<HTMLInputElement>(".run-indicator").forEach(input => {
                input.checked = config.indicators.includes(input.value);
            });
        }
    } else if (orig.run_type === "watchlist_run") {
        (document.getElementById("run-watchlist-select") as HTMLSelectElement).value = config.watchlist || "";
        if (Array.isArray(config.strategies) && config.strategies.length) {
            document.querySelectorAll<HTMLInputElement>("#run-strategy-checkboxes input").forEach(input => {
                input.checked = config.strategies.includes(input.value);
            });
        }
    } else if (orig.run_type === "task_run") {
        (document.getElementById("run-task-config-select") as HTMLSelectElement).value = config.task_config || "";
        (document.getElementById("run-daily-mode") as HTMLInputElement).checked = !!config.daily;
    }
    (document.getElementById("run-output-path") as HTMLInputElement).value = config.output_path || "";
    updateCliPreview();
    toast("Pre-filled from previous run");
}

async function resumeRun(runId: string) {
    try {
        const res = await api<{ ok: boolean; run_id: string; resumed_from: string; message?: string }>(
            `/api/runs/${runId}/resume`, { method: "POST" });
        if (!res.ok) throw new Error(res.message || "Resume failed");
        toast("Resumed — continuing from checkpoint");
        await loadRuns();
        await selectRun(res.run_id);
    } catch (e: any) {
        toast(`Resume failed: ${e.message}`);
    }
}

async function deleteRun(runId: string) {
    const run = state.runsList.find(r => r.id === runId);
    if (!run) return;
    if (run.status === "running" || run.status === "cancelling") {
        toast("Cancel the run and wait for it to stop before deleting.");
        return;
    }
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
            document.getElementById("runs-empty-state")!.classList.remove("hidden");
            document.getElementById("runs-detail")!.classList.add("hidden");
        }
        renderRunsList();
        toast("Run deleted");
    } catch (e: any) {
        toast(`Delete failed: ${e.message}`);
    }
}

// ---- End of Runs functions ----

async function loadTasks(filename?: string) {
    const url = filename ? `/api/tasks?filename=${encodeURIComponent(filename)}` : "/api/tasks";
    state.tasks = await api<TaskData[]>(url);
    renderTaskTable();
    loadTaskFiles();
}

async function loadTaskFiles() {
    state.taskFiles = await api<TaskFileInfo[]>("/api/task-files");
    renderTaskFileSidebar();
}

function renderTaskFileSidebar() {
    const list = document.getElementById("task-file-list")!;
    list.innerHTML = "";
    for (const tf of state.taskFiles) {
        const li = document.createElement("li");
        const isSelected = state.selectedTaskFile === tf.filename;
        li.innerHTML = `
            <div class="flex items-center justify-between">
              <button data-filename="${escapeHtml(tf.filename)}" class="task-file-item flex-1 text-left px-3 py-2 rounded text-sm transition-colors
                  ${isSelected ? "bg-blue-100 text-blue-700 font-medium" : "hover:bg-gray-100 text-gray-700"}">
                <div class="truncate">${escapeHtml(tf.filename)}</div>
                <div class="text-xs text-gray-400">${tf.taskCount} tasks</div>
              </button>
              <button class="tf-delete-btn text-red-500 hover:text-red-700 px-2 opacity-50 hover:opacity-100" data-filename="${escapeHtml(tf.filename)}">×</button>
            </div>`;
        list.appendChild(li);
    }
}

function selectTaskFile(filename: string) {
    state.selectedTaskFile = filename;
    renderTaskFileSidebar();
    const emptyMsg = document.getElementById("task-file-empty")!;
    const listArea = document.getElementById("task-list-area")!;
    const header = document.getElementById("task-file-header")!;
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

async function loadConfig(): Promise<void> {
    const config = await api<Record<string, unknown>>("/api/config");
    state.rawConfig = (config.raw ?? {}) as Record<string, unknown>;
    populateSettingsForm(state.rawConfig);
}

function switchTab(tab: string) {
    for (const t of ["watchlists", "tasks", "settings", "library", "runs"]) {
        const tabBtn = document.getElementById(`tab-${t}`)!;
        const panel = document.getElementById(`panel-${t}`)!;
        if (t === tab) {
            tabBtn.className = "tab-active px-6 py-3 border-b-2 font-medium text-sm";
            panel.classList.remove("hidden");
        } else {
            tabBtn.className = "tab-inactive px-6 py-3 border-b-2 font-medium text-sm";
            panel.classList.add("hidden");
        }
    }
    if (tab === "runs") {
        startRunsPolling();
    } else {
        stopRunsPolling();
    }
}

// Library sub-tab switching (strategies / indicators)
function switchLibrarySubTab(subtab: string) {
    for (const s of ["strategies", "indicators"]) {
        const btn = document.getElementById(`subtab-${s}`)!;
        const panel = document.getElementById(`library-${s}-panel`)!;
        if (s === subtab) {
            btn.className = "subtab-active px-4 py-2 border-b-2 text-sm font-medium";
            btn.style.borderColor = "#3b82f6";
            btn.style.color = "#2563eb";
            panel.classList.remove("hidden");
        } else {
            btn.className = "subtab-inactive px-4 py-2 border-b-2 text-sm font-medium border-transparent text-gray-500 hover:text-gray-700";
            btn.style.borderColor = "transparent";
            btn.style.color = "";
            panel.classList.add("hidden");
        }
    }
}

// Render library data lists
function renderLibraryStrategies() {
    const list = document.getElementById("library-strategies-list")!;
    const loading = document.getElementById("library-strategies-loading")!;
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
    const tbody = document.getElementById("library-indicators-table")!;
    const loading = document.getElementById("library-indicators-loading")!;
    if (loading) loading.classList.add("hidden");
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
            const name = (btn as HTMLElement).dataset.indicator!;
            openIndicatorParamsModal(name);
        });
    });
}

function openIndicatorParamsModal(indicatorName: string) {
    if (!state.libraryIndicators) return;
    const ind = state.libraryIndicators.find(i => i.name === indicatorName);
    if (!ind) return;
    state.currentIndicatorConfig = indicatorName;
    document.getElementById("indicator-params-title")!.textContent = `Configure ${ind.name}`;
    document.getElementById("indicator-params-desc")!.textContent = `Category: ${ind.category} | Inputs: ${ind.required_fields.join(", ")} | Outputs: ${ind.output_fields.join(", ")}`;
    const form = document.getElementById("indicator-params-form")!;
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
    if (!state.currentIndicatorConfig) return;
    const form = document.getElementById("indicator-params-form")!;
    const inputs = form.querySelectorAll(".indicator-param-input");
    const params: Record<string, any> = {};
    for (const input of inputs) {
        const key = (input as HTMLInputElement).dataset.paramKey!;
        const val = (input as HTMLInputElement).value;
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
    } catch (e: unknown) {
        alert(`Failed to save: ${(e as Error).message}`);
    }
}

function renderWatchlistSidebar() {
    const list = document.getElementById("watchlist-list")!;
    list.innerHTML = "";
    for (const wl of state.watchlists) {
        const li = document.createElement("li");
        const isSelected = state.selectedWatchlist === wl.filename;
        li.innerHTML = `
            <div class="flex items-center justify-between">
              <button data-filename="${escapeHtml(wl.filename)}" class="watchlist-item flex-1 text-left px-3 py-2 rounded text-sm transition-colors
                  ${isSelected ? "bg-blue-100 text-blue-700 font-medium" : "hover:bg-gray-100 text-gray-700"}">
                <div class="truncate">${escapeHtml(wl.name)}</div>
                <div class="text-xs text-gray-400">${wl.itemCount} stocks</div>
              </button>
              <button class="wl-delete-btn text-red-500 hover:text-red-700 px-2 opacity-50 hover:opacity-100" data-filename="${escapeHtml(wl.filename)}">×</button>
            </div>`;
        list.appendChild(li);
    }
}

async function selectWatchlist(filename: string) {
    if (state.watchlistDirty && state.selectedWatchlist !== filename) {
        if (!confirm("Unsaved changes. Discard?")) return;
        state.currentWatchlistData = null;
        state.watchlistDirty = false;
        updateModifiedUI();
    }
    state.selectedWatchlist = filename;
    renderWatchlistSidebar();
    state.currentWatchlistData = await api<WatchlistData>(`/api/watchlists/${filename}`);
    state.watchlistDirty = false;
    renderStockTable();
    document.getElementById("watchlist-empty")!.classList.add("hidden");
    document.getElementById("watchlist-content")!.classList.remove("hidden");
    document.getElementById("watchlist-title")!.textContent = `${state.currentWatchlistData.name} (${state.currentWatchlistData.items.length} stocks)`;
}

function renderStockTable() {
    if (!state.currentWatchlistData) return;
    const tbody = document.getElementById("stock-table")!;
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
        const tags = (item.tags || []).map(t => `<span class="bg-gray-100 px-1.5 py-0.5 rounded text-xs">${escapeHtml(t)}</span>`).join(" ");
        tr.innerHTML = `
            <td class="px-4 py-2 text-sm text-gray-900">${item.code}</td>
            <td class="px-4 py-2 text-sm text-gray-600"><span class="editable-name cursor-pointer hover:bg-gray-100 px-1 rounded" data-idx="${i}" title="Click to edit">${escapeHtml(item.name || "-")}</span></td>
            <td class="px-4 py-2 text-sm text-gray-600"><div class="editable-tags cursor-pointer hover:bg-gray-100 px-1 rounded min-h-[20px]" data-idx="${i}" title="Click to edit tags">${tags || "-"}</div></td>
            <td class="px-4 py-2 text-sm"><button data-idx="${i}" class="text-red-600 hover:text-red-800 delete-stock-btn">Delete</button></td>`;
        tbody.appendChild(tr);
    }
    tbody.querySelectorAll(".delete-stock-btn").forEach(btn => {
        btn.addEventListener("click", (e) => {
            const idx = parseInt((e.target as HTMLElement).dataset.idx || "0");
            state.currentWatchlistData!.items.splice(idx, 1);
            markWatchlistDirty();
            renderStockTable();
        });
    });
    tbody.querySelectorAll(".editable-name").forEach(span => {
        span.addEventListener("click", (e) => {
            const idx = parseInt((e.currentTarget as HTMLElement).dataset.idx || "0");
            startEditName(idx);
        });
    });
    tbody.querySelectorAll(".editable-tags").forEach(div => {
        div.addEventListener("click", (e) => {
            const idx = parseInt((e.currentTarget as HTMLElement).dataset.idx || "0");
            startEditTags(idx);
        });
    });
}

function startEditName(idx: number) {
    if (!state.currentWatchlistData) return;
    const item = state.currentWatchlistData.items[idx];
    const span = document.querySelector(`.editable-name[data-idx="${idx}"]`) as HTMLElement;
    if (!span) return;
    const input = document.createElement("input");
    input.type = "text";
    input.value = item.name || "";
    input.className = "border border-blue-400 rounded px-1 py-0.5 text-sm w-full";
    input.dataset.idx = String(idx);
    const finish = () => {
        const newName = input.value.trim();
        if (newName !== (item.name || "")) {
            item.name = newName || undefined;
            markWatchlistDirty();
        }
        renderStockTable();
    };
    input.addEventListener("blur", finish);
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { input.blur(); }
        if (e.key === "Escape") {
            input.removeEventListener("blur", finish);
            renderStockTable();
        }
    });
    span.replaceWith(input);
    input.focus();
    input.select();
}

function startEditTags(idx: number) {
    if (!state.currentWatchlistData) return;
    const item = state.currentWatchlistData.items[idx];
    const container = document.querySelector(`.editable-tags[data-idx="${idx}"]`) as HTMLElement;
    if (!container) return;

    container.classList.remove("cursor-pointer", "hover:bg-gray-100");
    container.innerHTML = "";

    const pillsDiv = document.createElement("div");
    pillsDiv.className = "flex flex-wrap gap-1 mb-1";

    const renderPills = () => {
        pillsDiv.innerHTML = "";
        for (let t = 0; t < (item.tags || []).length; t++) {
            const pill = document.createElement("span");
            pill.className = "bg-blue-100 text-blue-800 px-1.5 py-0.5 rounded text-xs inline-flex items-center gap-0.5";
            pill.innerHTML = `${escapeHtml(item.tags[t])}<span class="tag-remove-btn cursor-pointer font-bold ml-0.5" data-tag-idx="${t}">&times;</span>`;
            pillsDiv.appendChild(pill);
        }
    };
    renderPills();

    const input = document.createElement("input");
    input.type = "text";
    input.placeholder = "Add tag, Enter to confirm";
    input.className = "border border-blue-400 rounded px-1 py-0.5 text-xs w-full";

    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            const val = input.value.trim();
            if (val) {
                const newTags = val.split(",").map(s => s.trim()).filter(Boolean);
                for (const nt of newTags) {
                    if (!(item.tags || []).includes(nt)) {
                        if (!item.tags) item.tags = [];
                        item.tags.push(nt);
                    }
                }
                input.value = "";
                markWatchlistDirty();
                renderPills();
            }
        }
        if (e.key === "Escape") {
            renderStockTable();
        }
    });

    pillsDiv.addEventListener("click", (e) => {
        const target = (e as MouseEvent).target as HTMLElement;
        if (target.classList.contains("tag-remove-btn")) {
            const tagIdx = parseInt(target.dataset.tagIdx || "0");
            item.tags.splice(tagIdx, 1);
            markWatchlistDirty();
            renderPills();
            input.focus();
        }
    });

    container.appendChild(pillsDiv);
    container.appendChild(input);
    input.focus();

    const finishEdit = (e: MouseEvent) => {
        if (container.contains(e.target as Node)) return;
        document.removeEventListener("click", finishEdit);
        renderStockTable();
    };
    setTimeout(() => document.addEventListener("click", finishEdit), 0);
}

function markWatchlistDirty() {
    state.watchlistDirty = true;
    updateModifiedUI();
}

function updateModifiedUI() {
    const indicator = document.getElementById("save-indicator")!;
    const saveBtn = document.getElementById("btn-save-watchlist")!;
    if (state.watchlistDirty) {
        indicator.classList.remove("hidden");
        saveBtn.classList.remove("hidden");
    } else {
        indicator.classList.add("hidden");
        saveBtn.classList.add("hidden");
    }
}

async function saveWatchlist() {
    if (!state.currentWatchlistData || !state.selectedWatchlist) return;
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
    if (!name) return;
    const filename = name.replace(/[^a-zA-Z0-9_-\s]/g, "").trim().replace(/\s+/g, "_") + ".yaml";
    await api(`/api/watchlists/${filename}`, {
        method: "PUT",
        body: JSON.stringify({ name: name.replace(/\s+/g, "_"), description: "", items: [] }),
    });
    toast(`Created ${filename}`);
    loadWatchlists();
}

function updateAddStockPreview() {
    const market = (document.getElementById("add-stock-market") as HTMLSelectElement).value;
    const code = (document.getElementById("add-stock-code") as HTMLInputElement).value.trim();
    const preview = document.getElementById("add-stock-preview")!;
    const previewCode = document.getElementById("add-stock-preview-code")!;

    if (market && code) {
        previewCode.textContent = formatStockCode(code, market);
        preview.classList.remove("hidden");
    } else {
        preview.classList.add("hidden");
    }
}

function openModal(id: string) { document.getElementById(id)!.classList.remove("hidden"); }
function closeModal(id: string) { document.getElementById(id)!.classList.add("hidden"); }

function openAddStockModal() {
    (document.getElementById("add-stock-market") as HTMLSelectElement).value = "";
    (document.getElementById("add-stock-code") as HTMLInputElement).value = "";
    (document.getElementById("add-stock-name") as HTMLInputElement).value = "";
    (document.getElementById("add-stock-tags") as HTMLInputElement).value = "";
    document.getElementById("add-stock-warning")!.classList.add("hidden");
    document.getElementById("add-stock-preview")!.classList.add("hidden");
    openModal("modal-add-stock");
}

async function confirmAddStock() {
    const market = (document.getElementById("add-stock-market") as HTMLSelectElement).value;
    const rawCode = (document.getElementById("add-stock-code") as HTMLInputElement).value.trim();
    if (!market && !rawCode.includes(".")) { alert("Please select a market"); return; }
    if (!rawCode) { alert("Code is required"); return; }

    const code = formatStockCode(rawCode, market);
    const name = (document.getElementById("add-stock-name") as HTMLInputElement).value.trim();
    const tagsStr = (document.getElementById("add-stock-tags") as HTMLInputElement).value.trim();

    try {
        const res = await api<{ found: boolean; inLists?: string[] }>("/api/watchlists/search", { method: "POST", body: JSON.stringify({ code }) });
        if (res.found) {
            const warning = document.getElementById("add-stock-warning")!;
            warning.textContent = `Already in: ${res.inLists.join(", ")}`;
            warning.classList.remove("hidden");
        }
    } catch (e) { }
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
    (document.getElementById("batch-input") as HTMLTextAreaElement).value = "";
    openModal("modal-batch");
}

function confirmBatchImport() {
    const text = (document.getElementById("batch-input") as HTMLTextAreaElement).value.trim();
    if (!text) { alert("No data"); return; }
    let added = 0;
    for (const line of text.split("\n").filter(l => l.trim())) {
        const parts = line.trim().split(/\s+/);
        if (parts[0]) {
            state.currentWatchlistData!.items.push({ code: parts[0], name: parts.slice(1).join(" ") || undefined, tags: ["Personal"] });
            added++;
        }
    }
    markWatchlistDirty();
    renderStockTable();
    closeModal("modal-batch");
    toast(`Imported ${added} stocks`);
}

function renderTaskTable() {
    const tbody = document.getElementById("task-table")!;
    tbody.innerHTML = "";
    const listArea = document.getElementById("task-list-area")!;
    const emptyMsg = document.getElementById("task-file-empty")!;
    
    // Always show the list area if a file is selected, even if empty
    listArea.classList.remove("hidden");
    emptyMsg.classList.add("hidden");

    if (state.tasks.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="px-4 py-4 text-center text-sm text-gray-400">No tasks yet. Click "+ New Task" to add.</td></tr>`;
        return;
    }

    for (const task of state.tasks) {
        const tr = document.createElement("tr");
        tr.className = "hover:bg-gray-50";
        tr.innerHTML = `
            <td class="px-4 py-2 text-sm font-medium text-gray-900 break-words">${task.name}</td>
            <td class="px-4 py-2 text-sm text-gray-600 break-words">${task.watchlist}</td>
            <td class="px-4 py-2 text-sm text-gray-600 break-words">${task.strategies.join(", ")}</td>
            <td class="px-4 py-2 text-sm text-right whitespace-nowrap">
                <button data-id="${task.id}" class="text-blue-600 hover:text-blue-800 mr-2 edit-task-btn">Edit</button>
                <button data-id="${task.id}" class="text-red-600 hover:text-red-800 delete-task-btn">Delete</button>
            </td>`;
        tbody.appendChild(tr);
    }
    tbody.querySelectorAll(".edit-task-btn").forEach(btn => {
        btn.addEventListener("click", (e) => openTaskModal((e.target as HTMLElement).dataset.id || ""));
    });
    tbody.querySelectorAll(".delete-task-btn").forEach(btn => {
        btn.addEventListener("click", async (e) => {
            const id = (e.target as HTMLElement).dataset.id || "";
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

async function openTaskModal(taskId?: string) {
    const isEdit = !!taskId;
    document.getElementById("task-modal-title")!.textContent = isEdit ? "Edit Task" : "New Task";
    if (!state.selectedTaskFile) { toast("Please select a task file first."); return; }
    const wlSelect = document.getElementById("task-watchlist") as HTMLSelectElement;
    wlSelect.innerHTML = "";
    for (const wl of state.watchlists) {
        const opt = document.createElement("option");
        opt.value = `watchlists/${wl.filename}`;
        opt.textContent = wl.name;
        wlSelect.appendChild(opt);
    }
    const stratContainer = document.getElementById("task-strategies")!;
    stratContainer.innerHTML = "";
    for (const s of state.strategies) {
        const label = document.createElement("label");
        label.className = "flex items-center gap-2";
        label.innerHTML = `<input type="checkbox" value="${s.id}" class="task-strategy-cb"><span class="text-sm">${s.name} (${s.type})</span>`;
        stratContainer.appendChild(label);
    }
    if (isEdit) {
        const task = state.tasks.find(t => t.id === taskId);
        if (!task) return;
        (document.getElementById("task-name") as HTMLInputElement).value = task.name;
        wlSelect.value = task.watchlist;
        stratContainer.querySelectorAll(".task-strategy-cb").forEach((cb: HTMLInputElement) => {
            cb.checked = task.strategies.includes(cb.value);
        });
    } else {
        (document.getElementById("task-name") as HTMLInputElement).value = "";
    }
    
    const saveBtn = document.getElementById("btn-save-task")!;
    saveBtn.onclick = async () => {
        if (!state.selectedTaskFile) { toast("Please select a task file first."); return; }
        const taskName = (document.getElementById("task-name") as HTMLInputElement).value.trim();
        if (!taskName) { alert("Name required"); return; }
        if (!wlSelect.value) { alert("Watchlist required"); return; }
        const strategies = [...stratContainer.querySelectorAll(".task-strategy-cb:checked")].map(cb => (cb as HTMLInputElement).value);
        const payload = { name: taskName, watchlist: wlSelect.value, strategies };
        try {
            if (isEdit) {
                await api(`/api/tasks/${taskId}`, { method: "PUT", body: JSON.stringify(payload) });
                toast("Task updated");
            } else {
                await api(`/api/tasks?filename=${encodeURIComponent(state.selectedTaskFile)}`, { method: "POST", body: JSON.stringify(payload) });
                toast("Task created");
            }
            closeModal("modal-task");
            loadTasks(state.selectedTaskFile);
            loadTaskFiles();
        } catch (e: any) {
            alert(`Failed: ${e.message}`);
        }
    };
    openModal("modal-task");
}



function populateSettingsForm(raw: Record<string, unknown>): void {
    for (const [fieldId, dataPath] of Object.entries(SETTINGS_FIELD_MAP)) {
        const el = document.getElementById(fieldId) as HTMLInputElement | HTMLSelectElement;
        if (!el) continue;
        const val = getNestedValue(raw, dataPath);
        if (val !== undefined) {
            if (el.type === "checkbox") {
                (el as HTMLInputElement).checked = val === true || val === "true";
            } else {
                el.value = String(val);
            }
        }
    }
}

function collectFormValues(): Record<string, unknown> {
    const result = { ...state.rawConfig };
    for (const [, dataPath] of Object.entries(SETTINGS_FIELD_MAP)) {
        const els = document.querySelectorAll(`[data-path="${dataPath}"]`);
        if (els.length === 0) continue;
        const rawVal = (els[0] as HTMLInputElement | HTMLSelectElement).value;
        let parsed: unknown = rawVal;
        if (dataPath.includes("_size") || dataPath.includes("_min") || dataPath.includes("_max") || dataPath.includes("port") || dataPath.includes("multiplier") || dataPath.includes("buffer") || dataPath.includes("workers")) {
            const num = Number(rawVal);
            if (!isNaN(num)) parsed = num;
        }
        if ((els[0] as HTMLInputElement).type === "checkbox") {
            parsed = (els[0] as HTMLInputElement).checked;
        }
        setNestedValue(result, dataPath, parsed);
    }
    return result;
}

async function saveSettings(): Promise<void> {
    try {
        await api<{ success: boolean }>("/api/config", {
            method: "PUT",
            body: JSON.stringify({ raw: collectFormValues() }),
        });
        await loadConfig();
        const status = document.getElementById("settings-save-status")!;
        status.textContent = "✅ Saved successfully";
        status.className = "text-sm text-green-600";
        setTimeout(() => {
            status.textContent = "";
            hideSaveSettings();
        }, 3000);
    } catch (e: unknown) {
        const status = document.getElementById("settings-save-status")!;
        status.textContent = `❌ Failed: ${(e as Error).message}`;
        status.className = "text-sm text-red-600";
    }
}

function markSettingsDirty(): void {
    document.getElementById("settings-save-area")!.classList.remove("hidden");
    document.getElementById("btn-save-settings")!.classList.remove("hidden");
}

function hideSaveSettings(): void {
    document.getElementById("settings-save-area")!.classList.add("hidden");
    document.getElementById("btn-save-settings")!.classList.add("hidden");
}

let searchTimeout: ReturnType<typeof setTimeout> | null = null;

async function handleSearch() {
    const input = (document.getElementById("search-input") as HTMLInputElement).value.trim();
    const resultsDiv = document.getElementById("search-results")!;
    const statusDiv = document.getElementById("search-status")!;
    if (input.length < 2) { resultsDiv.classList.add("hidden"); statusDiv.classList.add("hidden"); return; }
    const res = await api<{ found: boolean; inLists?: string[]; fuzzyMatches?: { code: string; name?: string; watchlist?: string }[] }>("/api/watchlists/search", { method: "POST", body: JSON.stringify({ code: input }) });
    resultsDiv.classList.remove("hidden");
    if (res.found) {
        statusDiv.classList.remove("hidden");
        statusDiv.innerHTML = `<span class="text-green-600">Found in:</span> ${res.inLists.join(", ")}`;
        if (res.fuzzyMatches?.length) {
            renderFuzzyMatches(res.fuzzyMatches, resultsDiv);
        } else {
            resultsDiv.innerHTML = res.inLists.map(l => `<div class="px-3 py-2 text-sm text-gray-600 hover:bg-gray-50">In: ${l}</div>`).join("");
        }
    } else if (res.fuzzyMatches?.length) {
        statusDiv.classList.add("hidden");
        renderFuzzyMatches(res.fuzzyMatches, resultsDiv);
    } else {
        statusDiv.classList.remove("hidden");
        statusDiv.innerHTML = '<span class="text-red-500">Not found</span>';
        resultsDiv.innerHTML = '<div class="px-3 py-2 text-sm text-gray-400">No matches</div>';
    }
}

function renderFuzzyMatches(matches: { code: string; name?: string; watchlist?: string }[], container: HTMLElement) {
    const byWatchlist: Record<string, { code: string; name?: string }[]> = {};
    for (const m of matches) {
        const wl = m.watchlist || "Unknown";
        if (!byWatchlist[wl]) byWatchlist[wl] = [];
        byWatchlist[wl].push({ code: m.code, name: m.name });
    }
    let html = "";
    for (const [wl, stocks] of Object.entries(byWatchlist)) {
        html += `<div class="px-3 py-1 text-xs text-gray-500 bg-gray-50 font-medium">${wl} (${stocks.length})</div>`;
        for (const s of stocks) {
            html += `<div class="px-3 py-2 text-sm hover:bg-blue-50 cursor-pointer search-stock-item" data-code="${s.code}" data-watchlist="${wl}">
                <span class="font-mono text-gray-900">${s.code}</span>
                <span class="text-gray-500 ml-2">${s.name || ""}</span>
            </div>`;
        }
    }
    container.innerHTML = html;
    container.querySelectorAll(".search-stock-item").forEach(el => {
        el.addEventListener("click", async () => {
            const code = (el as HTMLElement).dataset.code!;
            const wl = (el as HTMLElement).dataset.watchlist!;
            container.classList.add("hidden");
            document.getElementById("search-status")!.classList.add("hidden");
            (document.getElementById("search-input") as HTMLInputElement).value = "";
            await selectWatchlist(wl);
            highlightStockRow(code);
        });
    });
}

function highlightStockRow(code: string) {
    const tbody = document.getElementById("stock-table")!;
    const rows = tbody.querySelectorAll("tr");
    for (const row of rows) {
        const codeCell = row.querySelector("td:first-child");
        if (codeCell && codeCell.textContent?.trim() === code) {
            row.classList.add("bg-yellow-100");
            row.scrollIntoView({ behavior: "smooth", block: "center" });
            setTimeout(() => row.classList.remove("bg-yellow-100"), 3000);
            break;
        }
    }
}

// ---- Browse Directory Modal ----
const DEFAULT_BROWSE_DIR = "/Users/neo";
let browseTargetInputId = "run-output-path";
let browseCurrentPath = DEFAULT_BROWSE_DIR;

function openBrowseDir(targetInputId: string, startPath: string) {
    browseTargetInputId = targetInputId;
    browseCurrentPath = startPath || DEFAULT_BROWSE_DIR;
    (document.getElementById("browse-new-folder") as HTMLElement).classList.add("hidden");
    (document.getElementById("modal-browse-dir") as HTMLElement).classList.remove("hidden");
    loadBrowseDir(browseCurrentPath);
}

async function loadBrowseDir(path: string) {
    const list = document.getElementById("browse-list")!;
    list.innerHTML = '<div class="text-gray-400 text-sm text-center py-8">Loading...</div>';
    try {
        const data = await api<{
            current_path: string; relative_path: string; parent_path: string;
            name: string; directories: string[]; has_parent: boolean;
        }>(`/api/browse/?path=${encodeURIComponent(path)}`);
        browseCurrentPath = data.current_path;
        document.getElementById("browse-breadcrumb")!.textContent = data.relative_path || data.current_path;
        document.getElementById("browse-current-path")!.textContent = data.relative_path || data.current_path;

        // Parent button
        const upBtn = document.getElementById("btn-browse-up")! as HTMLButtonElement;
        upBtn.disabled = !data.has_parent;
        upBtn.style.opacity = data.has_parent ? "1" : "0.4";

        const items = data.directories;
        if (items.length === 0) {
            list.innerHTML = '<div class="text-gray-400 text-sm text-center py-8">No subdirectories</div>';
            return;
        }
        list.innerHTML = items.map(d =>
            `<div class="browse-item flex items-center gap-2 px-3 py-1.5 rounded cursor-pointer hover:bg-blue-50" data-name="${d}">
                <span class="text-base">📁</span>
                <span class="text-sm text-gray-800">${d}</span>
            </div>`
        ).join("");
        list.querySelectorAll(".browse-item").forEach(el => {
            el.addEventListener("dblclick", () => {
                const name = (el as HTMLElement).dataset.name!;
                const parent = browseCurrentPath === "/" ? "" : browseCurrentPath;
                loadBrowseDir(parent ? `${parent}/${name}` : name);
            });
        });
    } catch (e: any) {
        list.innerHTML = `<div class="text-red-400 text-sm text-center py-8">Error: ${e.message}</div>`;
    }
}

function handleBrowseSelect() {
    const target = document.getElementById(browseTargetInputId) as HTMLInputElement;
    if (target) {
        const rel = (document.getElementById("browse-current-path") as HTMLElement).textContent;
        target.value = rel || browseCurrentPath;
    }
    closeModal("modal-browse-dir");
}

function handleBrowseMkdir() {
    const nameInput = document.getElementById("browse-new-folder-name") as HTMLInputElement;
    const name = nameInput.value.trim();
    if (!name) return;
    api("/api/browse/mkdir", {
        method: "POST",
        body: JSON.stringify({ path: browseCurrentPath, name }),
    }).then(() => {
        nameInput.value = "";
        (document.getElementById("browse-new-folder") as HTMLElement).classList.add("hidden");
        loadBrowseDir(browseCurrentPath);
        toast("Folder created");
    }).catch((e: any) => toast(`Failed: ${e.message}`));
}

// ---- End of Browse functions ----

function toast(msg: string) {
    const el = document.getElementById("toast")!;
    document.getElementById("toast-message")!.textContent = msg;
    el.classList.remove("hidden");
    setTimeout(() => el.classList.add("hidden"), 3000);
}

function setupEventListeners() {
    document.querySelectorAll('[data-tab]').forEach(btn => {
        btn.addEventListener("click", () => switchTab((btn as HTMLElement).dataset.tab!));
    });
    document.getElementById("btn-new-watchlist")!.addEventListener("click", openNewWatchlist);
    document.getElementById("btn-add-stock")!.addEventListener("click", openAddStockModal);
    document.getElementById("btn-batch-import")!.addEventListener("click", openBatchModal);
    document.getElementById("btn-save-watchlist")!.addEventListener("click", saveWatchlist);
    document.getElementById("btn-cancel-add")!.addEventListener("click", () => closeModal("modal-add-stock"));
    document.getElementById("btn-confirm-add")!.addEventListener("click", confirmAddStock);
    document.getElementById("add-stock-market")!.addEventListener("change", updateAddStockPreview);
    document.getElementById("add-stock-code")!.addEventListener("input", updateAddStockPreview);
    document.getElementById("btn-cancel-batch")!.addEventListener("click", () => closeModal("modal-batch"));
    document.getElementById("btn-confirm-batch")!.addEventListener("click", confirmBatchImport);
    document.getElementById("btn-cancel-task")!.addEventListener("click", () => closeModal("modal-task"));
    document.getElementById("btn-new-task")!.addEventListener("click", () => openTaskModal());
    document.getElementById("task-file-list")!.addEventListener("click", async (e) => {
        const target = e.target as HTMLElement;
        const delBtn = target.closest(".tf-delete-btn");
        if (delBtn) {
            e.stopPropagation();
            const filename = (delBtn as HTMLElement).dataset.filename;
            if (!filename) return;
            if (!confirm(`Delete "${filename}" and all tasks within?`)) return;
            try {
                await api(`/api/task-files/${encodeURIComponent(filename)}`, { method: "DELETE" });
                toast(`Deleted ${filename}`);
                if (state.selectedTaskFile === filename) {
                    state.selectedTaskFile = "";
                    renderTaskFileSidebar();
                    const emptyMsg = document.getElementById("task-file-empty")!;
                    const listArea = document.getElementById("task-list-area")!;
                    emptyMsg.classList.remove("hidden");
                    emptyMsg.textContent = "Select a task file";
                    listArea.classList.add("hidden");
                }
                loadTaskFiles();
            } catch (err) {
                alert("Failed to delete task file");
            }
            return;
        }
        const btn = target.closest(".task-file-item");
        if (btn) {
            const filename = (btn as HTMLElement).dataset.filename;
            if (filename) selectTaskFile(filename);
        }
    });
    document.getElementById("btn-new-task-file")!.addEventListener("click", async () => {
        const name = prompt("New task file name (without extension):");
        if (!name) return;
        const filename = name.startsWith("tasks") ? name + ".yaml" : "tasks_" + name.replace(/\s+/g, "_") + ".yaml";
        try {
            await api("/api/task-files", { method: "POST", body: JSON.stringify({ filename }) });
            toast(`Created ${filename}`);
            await loadTaskFiles();
            selectTaskFile(filename);
        } catch (e: any) {
            alert(`Failed: ${e.message}`);
        }
    });
    document.getElementById("search-input")!.addEventListener("input", () => {
        if (searchTimeout) clearTimeout(searchTimeout);
        searchTimeout = setTimeout(handleSearch, 300);
    });
    document.addEventListener("click", (e) => {
        const sr = document.getElementById("search-results")!;
        const si = document.getElementById("search-input")!;
        if (!sr.contains(e.target as Node) && e.target !== si) sr.classList.add("hidden");
    });
    // Event delegation for watchlist actions: delete and select
    const watchlistList = document.getElementById("watchlist-list");
    if (watchlistList) {
        watchlistList.addEventListener("click", async (e) => {
            const target = e.target as HTMLElement;
            // Delete button pressed?
            const delBtn = target.closest(".wl-delete-btn");
            if (delBtn) {
                e.stopPropagation();
                const filename = (delBtn as HTMLElement).dataset.filename;
                if (!filename) return;
    const wl = state.watchlists.find(w => w.filename === filename);
                const name = wl?.name ?? filename;
                if (!confirm(`Delete watchlist '${name}'? This cannot be undone.`)) return;
                try {
                    await api(`/api/watchlists/${filename}`, { method: "DELETE" });
                    toast(`Deleted ${name}`);
                    await loadWatchlists();
                    if (state.selectedWatchlist === filename) {
                        state.selectedWatchlist = null;
                        const content = document.getElementById("watchlist-content");
                        const empty = document.getElementById("watchlist-empty");
                        if (content) content.classList.add("hidden");
                        if (empty) empty.classList.remove("hidden");
                    }
                } catch (err) {
                    alert("Failed to delete watchlist");
                }
                return;
            }
            // Selection: clicking anywhere on the watchlist item (button area)
            const btn = target.closest('[data-filename]');
            if (btn) {
                const filename = (btn as HTMLElement).dataset.filename;
                if (filename) {
                    selectWatchlist(filename);
                }
            }
        });
    }

    const saveBtn = document.getElementById("btn-save-settings");
    if (saveBtn) saveBtn.addEventListener("click", saveSettings);

    const resetBtn = document.getElementById("btn-reset-settings");
    if (resetBtn) resetBtn.addEventListener("click", () => {
        populateSettingsForm(state.rawConfig);
        hideSaveSettings();
    });

    document.querySelectorAll("#settings-form input, #settings-form select").forEach(el => {
        el.addEventListener("input", markSettingsDirty);
        el.addEventListener("change", markSettingsDirty);
    });

    const toggleBtn = document.getElementById("btn-toggle-token");
    if (toggleBtn) toggleBtn.addEventListener("click", () => {
        const input = document.getElementById("cfg-tushare-token") as HTMLInputElement;
        const isPassword = input.type === "password";
        input.type = isPassword ? "text" : "password";
        toggleBtn.textContent = isPassword ? "🙈" : "👁️";
    });

    const copyBtn = document.getElementById("btn-copy-token");
    if (copyBtn) copyBtn.addEventListener("click", () => {
        const token = (document.getElementById("cfg-tushare-token") as HTMLInputElement).value;
        if (!token) { toast("Token is empty"); return; }
        navigator.clipboard.writeText(token).then(() => toast("Token copied to clipboard"));
    });

    // Library sub-tab switching
    document.querySelectorAll('[data-subtab]').forEach(btn => {
        btn.addEventListener("click", () => switchLibrarySubTab((btn as HTMLElement).dataset.subtab!));
    });
    document.getElementById("btn-save-params")!.addEventListener("click", saveIndicatorParams);
    document.getElementById("btn-cancel-params")!.addEventListener("click", () => closeModal("modal-indicator-params"));

    // RUNS: tab and modal wiring
    const runsTab = document.getElementById("tab-runs");
    if (runsTab) runsTab.addEventListener("click", () => switchTab("runs"));
    const newRunBtn = document.getElementById("btn-new-run");
    if (newRunBtn) newRunBtn.addEventListener("click", () => {
        resetRunModal();
        openModal("modal-new-run");
    });

    // Runs modal: cancel/back/check/execute
    document.getElementById("btn-cancel-run")?.addEventListener("click", () => {
        resetRunModal();
        closeModal("modal-new-run");
    });
    document.getElementById("btn-back-run")?.addEventListener("click", () => {
        document.getElementById("run-step-type")!.classList.remove("hidden");
        document.getElementById("run-step-config")!.classList.add("hidden");
        document.getElementById("run-step-preview")!.classList.add("hidden");
        document.getElementById("btn-back-run")!.classList.add("hidden");
        document.getElementById("btn-check-run")!.classList.add("hidden");
        document.getElementById("btn-execute-run")!.classList.add("hidden");
        selectedRunType = "";
    });
    document.getElementById("btn-check-run")?.addEventListener("click", preflightCheck);
    document.getElementById("btn-execute-run")?.addEventListener("click", executeRun);

    // Run type select cards
    document.querySelectorAll('[data-type]').forEach(btn => {
        btn.addEventListener("click", () => selectRunType((btn as HTMLElement).dataset.type!));
    });

    // CLI preview on form changes - all relevant inputs (static)
    document.getElementById("run-stock-code")?.addEventListener("input", updateCliPreview);
    document.getElementById("run-start-date")?.addEventListener("input", updateCliPreview);
    document.getElementById("run-end-date")?.addEventListener("input", updateCliPreview);
    document.getElementById("run-output-path")?.addEventListener("input", updateCliPreview);
    document.getElementById("run-watchlist-select")?.addEventListener("change", updateCliPreview);
    document.getElementById("run-task-config-select")?.addEventListener("change", updateCliPreview);
    document.getElementById("run-daily-mode")?.addEventListener("change", updateCliPreview);
    document.querySelectorAll(".run-indicator").forEach(el => {
        el.addEventListener("change", updateCliPreview);
    });
    // Event delegation for dynamically generated strategy checkboxes
    document.getElementById("run-strategy-checkboxes")?.addEventListener("change", (e) => {
        if (e.target instanceof HTMLInputElement) {
            updateCliPreview();
        }
    });

    // Run sub-tab switching
    document.querySelectorAll<HTMLElement>('[data-runtab]').forEach(button => {
        button.addEventListener("click", () => showRunTab(button.dataset.runtab!));
    });

    // Global helpers for onclick handlers
    (window as any).copyToClipboard = copyToClipboard;
    (window as any).runAgain = runAgain;
    (window as any).resumeRun = resumeRun;
    (window as any).deleteRun = deleteRun;
    (window as any).openFolder = openFolder;

    // Browse directory buttons
    document.getElementById("btn-browse-dir")?.addEventListener("click", () => {
        const input = document.getElementById("run-output-path") as HTMLInputElement;
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
        (document.getElementById("browse-new-folder") as HTMLElement).classList.toggle("hidden");
        (document.getElementById("browse-new-folder-name") as HTMLInputElement).focus();
    });
    document.getElementById("btn-browse-new-ok")?.addEventListener("click", handleBrowseMkdir);
    document.getElementById("browse-new-folder-name")?.addEventListener("keydown", (e: KeyboardEvent) => {
        if (e.key === "Enter") { e.preventDefault(); handleBrowseMkdir(); }
    });
}

init();
