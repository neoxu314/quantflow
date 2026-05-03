"use strict";
const MARKET_SUFFIX = {
    "US": ".US",
    "HK": ".HK",
    "SH": ".SH",
    "SZ": ".SZ",
    "JP": ".T",
    "KR": ".KS",
};
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
    await Promise.allSettled([loadStrategies(), loadWatchlists(), loadTaskFiles(), loadConfig(), loadLibraryStrategies(), loadLibraryIndicators()]);
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
    for (const t of ["watchlists", "tasks", "settings", "library"]) {
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
}
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
        previewCode.textContent = code.includes(".") ? code : `${code}${MARKET_SUFFIX[market] || ""}`;
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
    const code = rawCode.includes(".") || !market ? rawCode : `${rawCode}${MARKET_SUFFIX[market] || ""}`;
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
const SETTINGS_FIELD_MAP = {
    "cfg-cn-primary": "data.markets.cn.primary",
    "cfg-hk-primary": "data.markets.hk.primary",
    "cfg-us-primary": "data.markets.us.primary",
    "cfg-jp-primary": "data.markets.jp.primary",
    "cfg-kr-primary": "data.markets.kr.primary",
    "cfg-sector-primary": "data.markets.sector.primary",
    "cfg-adjust": "data.defaults.adjust",
    "cfg-lookback-multiplier": "lookback.calendar_multiplier",
    "cfg-lookback-buffer": "lookback.buffer_days",
    "cfg-yf-chunk": "yfinance.batch.chunk_size",
    "cfg-yf-min": "yfinance.batch.sleep_min",
    "cfg-yf-max": "yfinance.batch.sleep_max",
    "cfg-web-host": "web.host",
    "cfg-web-port": "web.port",
    "cfg-tushare-token": "tushare.token",
    "cfg-log-level": "logging.level",
};
function getNestedValue(obj, path) {
    return path.split(".").reduce((o, k) => (o && typeof o === "object" ? o[k] : undefined), obj);
}
function setNestedValue(obj, path, value) {
    const parts = path.split(".");
    let current = obj;
    for (let i = 0; i < parts.length - 1; i++) {
        const key = parts[i];
        if (!(key in current) || typeof current[key] !== "object") {
            current[key] = {};
        }
        current = current[key];
    }
    current[parts[parts.length - 1]] = value;
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
    const watchlistList = document.getElementById("watchlist-list");
    if (watchlistList) {
        watchlistList.addEventListener("click", async (e) => {
            const target = e.target;
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
    document.querySelectorAll('[data-subtab]').forEach(btn => {
        btn.addEventListener("click", () => switchLibrarySubTab(btn.dataset.subtab));
    });
    document.getElementById("btn-save-params").addEventListener("click", saveIndicatorParams);
    document.getElementById("btn-cancel-params").addEventListener("click", () => closeModal("modal-indicator-params"));
}
init();
