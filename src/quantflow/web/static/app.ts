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
    output: string;
    days_back?: number | null;
}

interface StrategyInfo {
    id: string;
    name: string;
    type: string;
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
    await Promise.allSettled([loadStrategies(), loadWatchlists(), loadTaskFiles(), loadConfig()]);
    selectTaskFile("");
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

async function loadWatchlists() {
    state.watchlists = await api<WatchlistSummary[]>("/api/watchlists");
    renderWatchlistSidebar();
}

async function loadTasks(filename?: string) {
    const url = filename ? `/api/tasks?filename=${encodeURIComponent(filename)}` : "/api/tasks";
    state.tasks = await api<TaskData[]>(url);
    renderTaskTable();
    loadTaskFiles();
}

async function loadTaskFiles() {
    state.taskFiles = await api<TaskFileInfo[]>("/api/task-files");
    renderTaskFileSelect();
}

function renderTaskFileSelect() {
    const sel = document.getElementById("task-file-select") as HTMLSelectElement;
    const prev = sel.value;
    sel.innerHTML = '<option value="">-- Choose file --</option>';
    for (const tf of state.taskFiles) {
        sel.innerHTML += `<option value="${tf.filename}">${tf.filename} (${tf.taskCount} tasks)</option>`;
    }
    if (state.selectedTaskFile && [...sel.options].some(o => o.value === state.selectedTaskFile)) {
        sel.value = state.selectedTaskFile;
    } else if (prev && [...sel.options].some(o => o.value === prev)) {
        sel.value = prev;
    }
}

function selectTaskFile(filename: string) {
    state.selectedTaskFile = filename;
    const deleteBtn = document.getElementById("btn-delete-task-file")!;
    const emptyMsg = document.getElementById("task-file-empty")!;
    const listArea = document.getElementById("task-list-area")!;
    const header = document.getElementById("task-file-header")!;
    if (!filename) {
        deleteBtn.classList.add("hidden");
        emptyMsg.classList.remove("hidden");
        listArea.classList.add("hidden");
        return;
    }
    deleteBtn.classList.remove("hidden");
    emptyMsg.classList.add("hidden");
    listArea.classList.remove("hidden");
    header.innerHTML = `<h3 class="font-medium text-gray-900">${filename}</h3>`;
    loadTasks(filename);
}

async function loadConfig() {
    const config = await api("/api/config");
    document.getElementById("config-display")!.textContent = JSON.stringify(config, null, 2);
}

function switchTab(tab: string) {
    for (const t of ["watchlists", "tasks", "settings"]) {
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
}

function renderWatchlistSidebar() {
    const list = document.getElementById("watchlist-list")!;
    list.innerHTML = "";
    for (const wl of state.watchlists) {
        const li = document.createElement("li");
        const isSelected = state.selectedWatchlist === wl.filename;
        li.innerHTML = `
            <button data-filename="${wl.filename}" class="w-full text-left px-3 py-2 rounded text-sm transition-colors
                ${isSelected ? "bg-blue-100 text-blue-700 font-medium" : "hover:bg-gray-100 text-gray-700"}">
                <div class="truncate">${wl.name}</div>
                <div class="text-xs text-gray-400">${wl.itemCount} stocks</div>
            </button>`;
        li.querySelector("button")!.addEventListener("click", () => selectWatchlist(wl.filename));
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
            const idx = parseInt((e.target as HTMLElement).dataset.idx || "0");
            state.currentWatchlistData!.items.splice(idx, 1);
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

function openModal(id: string) { document.getElementById(id)!.classList.remove("hidden"); }
function closeModal(id: string) { document.getElementById(id)!.classList.add("hidden"); }

function openAddStockModal() {
    document.getElementById("add-stock-code")!.value = "";
    document.getElementById("add-stock-name")!.value = "";
    document.getElementById("add-stock-tags")!.value = "";
    document.getElementById("add-stock-warning")!.classList.add("hidden");
    openModal("modal-add-stock");
}

async function confirmAddStock() {
    const code = (document.getElementById("add-stock-code") as HTMLInputElement).value.trim();
    const name = (document.getElementById("add-stock-name") as HTMLInputElement).value.trim();
    const tagsStr = (document.getElementById("add-stock-tags") as HTMLInputElement).value.trim();
    if (!code) { alert("Code is required"); return; }
    try {
        const res = await api("/api/watchlists/search", { method: "POST", body: JSON.stringify({ code }) });
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
    const emptyMsg = document.getElementById("task-file-empty")!;
    const listArea = document.getElementById("task-list-area")!;
    if (state.tasks.length === 0) {
        emptyMsg.classList.remove("hidden");
        listArea.classList.add("hidden");
        return;
    }
    emptyMsg.classList.add("hidden");
    listArea.classList.remove("hidden");
    for (const task of state.tasks) {
        const tr = document.createElement("tr");
        tr.className = "hover:bg-gray-50";
        tr.innerHTML = `
            <td class="px-4 py-2 text-sm font-medium text-gray-900">${task.name}</td>
            <td class="px-4 py-2 text-sm text-gray-600">${task.watchlist}</td>
            <td class="px-4 py-2 text-sm text-gray-600">${task.strategies.join(", ")}</td>
            <td class="px-4 py-2 text-sm text-gray-600 font-mono text-xs">${task.output}</td>
            <td class="px-4 py-2 text-sm">
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
    (document.getElementById("task-config-select") as HTMLElement).style.display = isEdit ? "none" : "block";
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
    const fileSelect = document.getElementById("task-config-file") as HTMLSelectElement;
    fileSelect.innerHTML = "";
    const configFiles = [
        ...new Set(state.tasks.map(t => t.filename)),
        "tasks.yaml",
    ];
    for (const f of configFiles) {
        const opt = document.createElement("option");
        opt.value = f;
        opt.textContent = f;
        fileSelect.appendChild(opt);
    }
    if (isEdit) {
        const task = state.tasks.find(t => t.id === taskId);
        if (!task) return;
        (document.getElementById("task-name") as HTMLInputElement).value = task.name;
        (document.getElementById("task-output") as HTMLInputElement).value = task.output;
        wlSelect.value = task.watchlist;
        stratContainer.querySelectorAll(".task-strategy-cb").forEach((cb: HTMLInputElement) => {
            cb.checked = task.strategies.includes(cb.value);
        });
    } else {
        (document.getElementById("task-name") as HTMLInputElement).value = "";
        (document.getElementById("task-output") as HTMLInputElement).value = "./output";
    }
    const newSaveBtn = (document.getElementById("btn-save-task")!.cloneNode(true)) as HTMLButtonElement;
    document.getElementById("btn-save-task")!.parentNode!.replaceChild(newSaveBtn, document.getElementById("btn-save-task")!);
    newSaveBtn.addEventListener("click", async () => {
        const taskName = (document.getElementById("task-name") as HTMLInputElement).value.trim();
        if (!taskName) { alert("Name required"); return; }
        const strategies = [...stratContainer.querySelectorAll(".task-strategy-cb:checked")].map(cb => (cb as HTMLInputElement).value);
        const output = (document.getElementById("task-output") as HTMLInputElement).value.trim() || "./output";
        const payload = { name: taskName, watchlist: wlSelect.value, strategies, output };
        try {
            if (isEdit) {
                await api(`/api/tasks/${taskId}`, { method: "PUT", body: JSON.stringify(payload) });
                toast("Task updated");
            } else {
                const file = state.selectedTaskFile;
                await api(`/api/tasks?filename=${encodeURIComponent(file)}`, { method: "POST", body: JSON.stringify(payload) });
                toast("Task created");
            }
            closeModal("modal-task");
            loadTasks(state.selectedTaskFile);
            loadTaskFiles();
        } catch (e: any) {
            alert(`Failed: ${e.message}`);
        }
    });
    openModal("modal-task");
}

let searchTimeout: ReturnType<typeof setTimeout> | null = null;

async function handleSearch() {
    const input = (document.getElementById("search-input") as HTMLInputElement).value.trim();
    const resultsDiv = document.getElementById("search-results")!;
    const statusDiv = document.getElementById("search-status")!;
    if (input.length < 2) { resultsDiv.classList.add("hidden"); statusDiv.classList.add("hidden"); return; }
    const res = await api("/api/watchlists/search", { method: "POST", body: JSON.stringify({ code: input }) });
    resultsDiv.classList.remove("hidden");
    if (res.found) {
        statusDiv.classList.remove("hidden");
        statusDiv.innerHTML = `<span class="text-green-600">Found in:</span> ${res.inLists.join(", ")}`;
        resultsDiv.innerHTML = res.inLists.map(l => `<div class="px-3 py-2 text-sm text-gray-600 hover:bg-gray-50">In: ${l}</div>`).join("");
    } else if (res.fuzzyMatches?.length) {
        statusDiv.classList.add("hidden");
        resultsDiv.innerHTML = res.fuzzyMatches.map((m: any) => `<div class="px-3 py-2 text-sm hover:bg-gray-50"><span class="text-gray-900">${m.code}</span> <span class="text-gray-500 ml-2">${m.name || ""}</span></div>`).join("");
    } else {
        statusDiv.classList.remove("hidden");
        statusDiv.innerHTML = '<span class="text-red-500">Not found</span>';
        resultsDiv.innerHTML = '<div class="px-3 py-2 text-sm text-gray-400">No matches</div>';
    }
}

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
    document.getElementById("btn-cancel-batch")!.addEventListener("click", () => closeModal("modal-batch"));
    document.getElementById("btn-confirm-batch")!.addEventListener("click", confirmBatchImport);
    document.getElementById("btn-cancel-task")!.addEventListener("click", () => closeModal("modal-task"));
    document.getElementById("btn-new-task")!.addEventListener("click", () => openTaskModal());
    document.getElementById("task-file-select")!.addEventListener("change", (e) => {
        selectTaskFile((e.target as HTMLSelectElement).value);
    });
    document.getElementById("btn-new-task-file")!.addEventListener("click", async () => {
        const name = prompt("New task file name (without extension):");
        if (!name) return;
        const filename = name.startsWith("tasks") ? name + ".yaml" : "tasks_" + name.replace(/\s+/g, "_") + ".yaml";
        await api("/api/task-files", { method: "POST", body: JSON.stringify({ filename }) });
        toast(`Created ${filename}`);
        loadTaskFiles();
    });
    document.getElementById("btn-delete-task-file")!.addEventListener("click", async () => {
        const f = state.selectedTaskFile;
        if (!f) return;
        if (confirm(`Delete all tasks in "${f}" and the file itself?`)) {
            await api(`/api/task-files/${encodeURIComponent(f)}`, { method: "DELETE" });
            toast(`Deleted ${f}`);
            state.selectedTaskFile = "";
            loadTaskFiles();
            selectTaskFile("");
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
}

init();
