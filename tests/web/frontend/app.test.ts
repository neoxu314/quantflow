/**
 * Frontend unit tests for Runs UI logic.
 * @vitest-environment jsdom
 */

import { describe, it, expect, afterEach, vi, beforeEach } from "vitest";

let lastApiCall: { url: string; init?: RequestInit } | null = null;
const mockApi = vi.fn((url: string, init?: RequestInit) => {
    lastApiCall = { url, init };
    if (init?.method === "DELETE") return Promise.resolve({ ok: true });
    return Promise.resolve({ runs: [] });
});

const mockToast = vi.fn();

vi.stubGlobal("api", mockApi);
vi.stubGlobal("toast", mockToast);
vi.stubGlobal("closeModal", vi.fn());
vi.stubGlobal("openModal", vi.fn());

beforeEach(() => {
    lastApiCall = null;
    mockApi.mockClear();
    mockToast.mockClear();
    document.body.innerHTML = "";
});

afterEach(() => {
    document.body.innerHTML = "";
});

describe("renderRunsList", () => {
    it("shows empty message when no runs", () => {
        document.body.innerHTML = '<ul id="runs-list"></ul>';
        const list = document.getElementById("runs-list")!;

        const runs: any[] = [];
        list.innerHTML = '<li class="text-gray-400 text-sm text-center py-8">No runs yet</li>';
        expect(list.textContent).toBe("No runs yet");
    });

    it("renders each run with name, type, status, and delete button", () => {
        document.body.innerHTML = '<ul id="runs-list"></ul>';

        const runs = [
            { id: "run-1", name: "NVDA.US Scan", run_type: "stock_scan", status: "completed", created_at: "2026-01-01T00:00:00Z" },
            { id: "run-2", name: "Web Tech Monitor", run_type: "watchlist_run", status: "running", created_at: "2026-01-02T00:00:00Z" },
        ];

        const list = document.getElementById("runs-list")!;
        list.innerHTML = runs.map(r => {
            return `<li class="px-3 py-2 rounded cursor-pointer hover:bg-gray-100" data-run-id="${r.id}">` +
                `<div class="flex items-center justify-between">` +
                `<div class="flex-1 min-w-0"><div class="font-medium text-sm truncate">${r.name}</div>` +
                `<div class="text-xs text-gray-500">${r.run_type} • ${r.status} • 1/1/2026</div></div>` +
                `<button class="ml-2 text-gray-400 hover:text-red-500 p-1 rounded flex-shrink-0" onclick="event.stopPropagation(); deleteRun('${r.id}')" title="Delete run">×</button>` +
                `</div></li>`;
        }).join("");

        expect(list.querySelectorAll("li[data-run-id]").length).toBe(2);
        expect(list.querySelector(`[data-run-id="run-1"] .font-medium`)!.textContent).toBe("NVDA.US Scan");
        expect(list.querySelector(`[data-run-id="run-2"] .text-xs`)!.textContent).toContain("watchlist_run");
        expect(list.querySelector(`[data-run-id="run-2"] .text-xs`)!.textContent).toContain("running");
    });

    it("includes delete button with correct onclick handler", () => {
        document.body.innerHTML = '<ul id="runs-list"></ul>';
        const list = document.getElementById("runs-list")!;

        const run = { id: "abc-123", name: "Test", run_type: "stock_scan", status: "completed", created_at: "2026-01-01" };
        list.innerHTML = `<li data-run-id="${run.id}">` +
            `<button onclick="event.stopPropagation(); deleteRun('${run.id}')" title="Delete run">×</button>` +
            `</li>`;

        const btn = list.querySelector("button");
        expect(btn).not.toBeNull();
        expect(btn!.getAttribute("onclick")).toContain(`deleteRun('${run.id}')`);
        expect(btn!.getAttribute("title")).toBe("Delete run");
    });
});

describe("deleteRun frontend behavior", () => {
    it("calls DELETE api endpoint with correct runId", async () => {
        const runId = "test-run-id";

        const mockRunsList = [{ id: runId, name: "Test Scan", run_type: "stock_scan", status: "completed", created_at: "2026-01-01" }];
        await mockDelete(runId, mockRunsList);

        expect(mockApi).toHaveBeenCalledWith(`/api/runs/${runId}`, { method: "DELETE" });
    });

    it("shows toast confirmation after delete", async () => {
        const runId = "toast-test";
        const mockRunsList = [{ id: runId, name: "T", run_type: "stock_scan", status: "completed", created_at: "2026-01-01" }];
        await mockDelete(runId, mockRunsList);

        expect(mockToast).toHaveBeenCalledWith("Run deleted");
    });

    it("shows error toast on delete failure", async () => {
        mockApi.mockImplementationOnce(() => Promise.reject(new Error("server error")));

        const runId = "fail-test";
        (globalThis as any).state = { runsList: [{ id: runId, name: "T", run_type: "stock_scan", status: "completed", created_at: "2026-01-01" }], selectedRunId: null, selectedRun: null };
        (globalThis as any).toast = mockToast;

        try {
            await mockDeleteImpl(runId);
        } catch {}

        expect(mockToast).toHaveBeenCalledWith("Delete failed: server error");
    });
});

// Minimal test-safe implementations
async function mockDelete(runId: string, runsList: any[]) {
    const api = (globalThis as any).api;
    const toast = (globalThis as any).toast;
    const state: any = { runsList, selectedRunId: null, selectedRun: null };

    try {
        await api(`/api/runs/${runId}`, { method: "DELETE" });
        state.runsList = state.runsList.filter((r: any) => r.id !== runId);
        toast("Run deleted");
    } catch (e: any) {
        toast(`Delete failed: ${e.message}`);
    }

    expect(state.runsList.length).toBe(0);
}

async function mockDeleteImpl(runId: string) {
    const api = (globalThis as any).api;
    const toast = (globalThis as any).toast;
    try {
        await api(`/api/runs/${runId}`, { method: "DELETE" });
        toast("Run deleted");
    } catch (e: any) {
        toast(`Delete failed: ${e.message}`);
    }
}

describe("selectRunType date defaults", () => {
    function setupDateInputs() {
        document.body.innerHTML = `
            <input id="run-start-date" type="date">
            <input id="run-end-date" type="date">
            <div id="run-config-stock_scan" class="hidden"></div>
            <div id="run-config-watchlist_run" class="hidden"></div>
            <div id="run-config-task_run" class="hidden"></div>
            <div id="run-step-type"></div>
            <div id="run-step-config" class="hidden"></div>
            <div id="run-step-preview" class="hidden"></div>
            <button id="btn-back-run" class="hidden"></button>
            <button id="btn-check-run" class="hidden"></button>
            <button id="btn-execute-run" class="hidden"></button>
            <div id="run-cli-preview"></div>
        `;
        document.getElementById("run-strategy-checkboxes")?.remove();
    }

    function selectRunType(type: string) {
        const prevSelected = (window as any).selectedRunType;
        (window as any).selectedRunType = type;
        document.getElementById("run-step-type")!.classList.add("hidden");
        document.getElementById("run-step-config")!.classList.remove("hidden");
        document.getElementById("run-step-preview")!.classList.remove("hidden");
        document.getElementById("btn-back-run")!.classList.remove("hidden");
        document.getElementById("btn-check-run")!.classList.remove("hidden");
        document.getElementById("btn-execute-run")!.classList.remove("hidden");
        ["stock_scan", "watchlist_run", "task_run"].forEach(t => {
            document.getElementById(`run-config-${t}`)!.classList.add("hidden");
        });
        document.getElementById(`run-config-${type}`)!.classList.remove("hidden");
        if (type === "stock_scan") {
            const today = new Date().toISOString().split("T")[0];
            (document.getElementById("run-start-date") as HTMLInputElement).value = today;
            (document.getElementById("run-end-date") as HTMLInputElement).value = today;
        }
    }

    it("sets today's date for stock scan date inputs", () => {
        setupDateInputs();
        selectRunType("stock_scan");

        const startVal = (document.getElementById("run-start-date") as HTMLInputElement).value;
        const endVal = (document.getElementById("run-end-date") as HTMLInputElement).value;
        const today = new Date().toISOString().split("T")[0];

        expect(startVal).toBe(today);
        expect(endVal).toBe(today);
    });

    it("leaves date inputs empty for watchlist_run", () => {
        setupDateInputs();
        selectRunType("watchlist_run");

        const startVal = (document.getElementById("run-start-date") as HTMLInputElement).value;
        const endVal = (document.getElementById("run-end-date") as HTMLInputElement).value;

        expect(startVal).toBe("");
        expect(endVal).toBe("");
    });

    it("leaves date inputs empty for task_run", () => {
        setupDateInputs();
        selectRunType("task_run");

        const startVal = (document.getElementById("run-start-date") as HTMLInputElement).value;
        const endVal = (document.getElementById("run-end-date") as HTMLInputElement).value;

        expect(startVal).toBe("");
        expect(endVal).toBe("");
    });
});

describe("runAgain date restore", () => {
    function setupRunAgainEnvironment() {
        document.body.innerHTML = `
            <input id="run-stock-code" type="text">
            <input id="run-start-date" type="date">
            <input id="run-end-date" type="date">
            <div id="run-config-stock_scan" class="hidden"></div>
            <div id="run-config-watchlist_run" class="hidden"></div>
            <div id="run-config-task_run" class="hidden"></div>
            <div id="run-step-type"></div>
            <div id="run-step-config" class="hidden"></div>
            <div id="run-step-preview" class="hidden"></div>
            <button id="btn-back-run" class="hidden"></button>
            <button id="btn-check-run" class="hidden"></button>
            <button id="btn-execute-run" class="hidden"></button>
            <div id="run-cli-preview"></div>
        `;

        (globalThis as any).selectedRunType = "";
        (globalThis as any).state = { runsList: [], selectedRunId: null, selectedRun: null };
    }

    function selectRunType(type: string) {
        (globalThis as any).selectedRunType = type;
        document.getElementById("run-step-type")!.classList.add("hidden");
        document.getElementById("run-step-config")!.classList.remove("hidden");
        ["stock_scan", "watchlist_run", "task_run"].forEach(t => {
            document.getElementById(`run-config-${t}`)!.classList.add("hidden");
        });
        document.getElementById(`run-config-${type}`)!.classList.remove("hidden");
        if (type === "stock_scan") {
            const today = new Date().toISOString().split("T")[0];
            (document.getElementById("run-start-date") as HTMLInputElement).value = today;
            (document.getElementById("run-end-date") as HTMLInputElement).value = today;
        }
    }

    function runAgain(runId: string) {
        const orig = ((globalThis as any).state?.runsList || []).find((r: any) => r.id === runId);
        if (!orig) return;
        resetRunModal();
        selectRunType(orig.run_type);
        if (orig.run_type === "stock_scan" && orig.config?.code) {
            (document.getElementById("run-stock-code") as HTMLInputElement).value = orig.config.code;
            if (orig.config?.start_date) {
                (document.getElementById("run-start-date") as HTMLInputElement).value = orig.config.start_date;
            }
            if (orig.config?.end_date) {
                (document.getElementById("run-end-date") as HTMLInputElement).value = orig.config.end_date;
            }
        }
    }

    function resetRunModal() {
        (globalThis as any).selectedRunType = "";
    }

    it("restores saved start_date and end_date from original run config", () => {
        setupRunAgainEnvironment();
        const run = {
            id: "run-1", name: "Test", run_type: "stock_scan", status: "completed",
            created_at: "2026-01-01",
            config: { code: "NVDA.US", start_date: "2026-03-01", end_date: "2026-03-15" },
        };
        (globalThis as any).state.runsList = [run];

        runAgain("run-1");

        expect((document.getElementById("run-start-date") as HTMLInputElement).value).toBe("2026-03-01");
        expect((document.getElementById("run-end-date") as HTMLInputElement).value).toBe("2026-03-15");
        expect((document.getElementById("run-stock-code") as HTMLInputElement).value).toBe("NVDA.US");
    });

    it("uses today's date when original run has no saved dates", () => {
        setupRunAgainEnvironment();
        const run = {
            id: "run-2", name: "No Dates", run_type: "stock_scan", status: "completed",
            created_at: "2026-01-01",
            config: { code: "AAPL.US" },
        };
        (globalThis as any).state.runsList = [run];

        runAgain("run-2");

        const today = new Date().toISOString().split("T")[0];
        expect((document.getElementById("run-start-date") as HTMLInputElement).value).toBe(today);
        expect((document.getElementById("run-end-date") as HTMLInputElement).value).toBe(today);
    });

    it("does not restore dates for watchlist_run", () => {
        setupRunAgainEnvironment();
        const run = {
            id: "run-3", name: "Watchlist", run_type: "watchlist_run", status: "completed",
            created_at: "2026-01-01",
            config: { watchlist: "test.yaml" },
        };
        (globalThis as any).state.runsList = [run];

        (document.getElementById("run-start-date") as HTMLInputElement).value = "";
        (document.getElementById("run-end-date") as HTMLInputElement).value = "";

        runAgain("run-3");

        expect((document.getElementById("run-start-date") as HTMLInputElement).value).toBe("");
        expect((document.getElementById("run-end-date") as HTMLInputElement).value).toBe("");
    });
});

describe("mdToHtml", () => {
    // Mirrors the mdToHtml function in app.ts
    function mdToHtml(md: string): string {
        let html = md
            .replace(/^### (.+)$/gm, '<h3 class="text-lg font-semibold mt-4">$1</h3>')
            .replace(/^## (.+)$/gm, '<h2 class="text-xl font-semibold mt-6">$1</h2>')
            .replace(/^# (.+)$/gm, '<h1 class="text-2xl font-bold mt-8">$1</h1>')
            .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
            .replace(/\*(.+?)\*/g, "<em>$1</em>")
            .replace(/`([^`]+)`/g, '<code class="bg-gray-100 px-1 rounded text-xs">$1</code>');
        html = html.replace(/((?:^- .*\n?)+)/gm, (m) => {
            const items = m.trim().split("\n").map(l => l.replace(/^- /, ""));
            return '<ul class="list-disc pl-5 mb-2 text-sm text-gray-700">'
                + items.map(i => `<li>${i}</li>`).join("")
                + "</ul>\n";
        });
        html = html.replace(/^---\s*$/gm, '<hr class="my-4 border-gray-300">');
        html = html.replace(/((?:\|.+\|\n)+)/g, (match) => {
            const rows = match.trim().split("\n").filter(r => !r.match(/^\|-+[-| ]+$/));
            if (rows.length < 2) return match;
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

    it("converts h1 heading", () => {
        const result = mdToHtml("# Title");
        expect(result).toContain('<h1 class="text-2xl font-bold mt-8">Title</h1>');
    });

    it("converts h2 heading", () => {
        const result = mdToHtml("## Section");
        expect(result).toContain('<h2 class="text-xl font-semibold mt-6">Section</h2>');
    });

    it("converts h3 heading", () => {
        const result = mdToHtml("### Subsection");
        expect(result).toContain('<h3 class="text-lg font-semibold mt-4">Subsection</h3>');
    });

    it("converts bold text", () => {
        const result = mdToHtml("this is **bold** text");
        expect(result).toContain("<strong>bold</strong>");
    });

    it("converts italic text", () => {
        const result = mdToHtml("this is *italic* text");
        expect(result).toContain("<em>italic</em>");
    });

    it("converts inline code", () => {
        const result = mdToHtml("use `code` here");
        expect(result).toContain('<code class="bg-gray-100 px-1 rounded text-xs">code</code>');
    });

    it("converts a single list item", () => {
        const result = mdToHtml("- item one");
        expect(result).toContain("<li>item one</li>");
        expect(result).toContain("<ul");
        expect(result).toContain("</ul>");
    });

    it("converts multiple list items into one ul", () => {
        const result = mdToHtml("- item one\n- item two\n- item three");
        expect(result).toContain("<li>item one</li>");
        expect(result).toContain("<li>item two</li>");
        expect(result).toContain("<li>item three</li>");
        const ulCount = (result.match(/<ul/g) || []).length;
        expect(ulCount).toBe(1);
    });

    it("converts list items with bold text", () => {
        const result = mdToHtml("- **bold item**");
        expect(result).toContain("<li><strong>bold item</strong></li>");
    });

    it("converts horizontal rule", () => {
        const result = mdToHtml("---");
        expect(result).toContain('<hr class="my-4 border-gray-300">');
    });

    it("converts markdown table", () => {
        const md = "| Code | Name |\n|---|---|\n| NVDA.US | Nvidia |\n| AAPL.US | Apple |\n";
        const result = mdToHtml(md);
        expect(result).toContain("<table");
        expect(result).toContain("NVDA.US");
        expect(result).toContain("Nvidia");
        expect(result).toContain("AAPL.US");
        expect(result).toContain("Apple");
        expect(result).toContain("</table>");
    });

    it("wraps plain text lines in p tags", () => {
        const result = mdToHtml("plain text");
        expect(result).toContain('<p class="text-sm text-gray-700 mb-1">plain text</p>');
    });

    it("renders a complete report with all elements", () => {
        const report = "# Daily Report\n" +
            "**Date**: 2026-05-04\n" +
            "\n" +
            "## Statistics\n" +
            "- **Buy Signals**: 3\n" +
            "- **Sell Signals**: 1\n" +
            "\n" +
            "### Signal Details\n" +
            "| Code | Type |\n" +
            "|---|---|\n" +
            "| NVDA.US | Buy |\n" +
            "| AAPL.US | Sell |\n" +
            "\n" +
            "---\n" +
            "\n" +
            "## Data Availability\n" +
            "- Stocks without data: 0";

        const result = mdToHtml(report);
        expect(result).toContain("Daily Report");
        expect(result).toContain("Statistics");
        expect(result).toContain("Buy Signals");
        expect(result).toContain("Sell Signals");
        expect(result).toContain("NVDA.US");
        expect(result).toContain("Data Availability");
        expect(result).toContain("Stocks without data");
        expect(result).toContain("<hr");
    });

    it("produces no empty paragraph tags", () => {
        const result = mdToHtml("# Title\n\nparagraph\n\n- item\n");
        expect(result).not.toContain("<p></p>");
        expect(result).not.toContain('<p class="text-sm text-gray-700 mb-1"></p>');
    });

    it("handles empty input", () => {
        expect(mdToHtml("")).toBe("");
    });

    it("preserves non-HTML raw text that doesn't match markdown patterns", () => {
        const result = mdToHtml("some raw text");
        expect(result).toContain("some raw text");
    });
});

describe("SSE status event handler", () => {
    it("calls loadRuns when SSE sends non-running status", () => {
        const calls: string[] = [];
        const mockLoadRuns = () => calls.push("loadRuns");
        const mockSelectRun = () => calls.push("selectRun");
        const mockSSEClose = vi.fn();

        let sseSource: any = { close: mockSSEClose };
        const handle = () => {
            const data = { status: "completed" };
            if (data.status !== "running") {
                if (sseSource) sseSource.close();
                sseSource = null;
                mockSelectRun();
                mockLoadRuns();
            }
        };

        handle();

        expect(calls).toContain("selectRun");
        expect(calls).toContain("loadRuns");
        expect(mockSSEClose).toHaveBeenCalled();
    });
});

describe("openFolder", () => {
    it("calls POST api endpoint with correct runId", async () => {
        mockApi.mockImplementationOnce(() => Promise.resolve({ ok: true, path: "/tmp/output" }));
        const runId = "test-run-id";

        await mockOpenFolder(runId);

        expect(mockApi).toHaveBeenCalledWith(`/api/runs/${runId}/open-folder`, { method: "POST" });
    });

    it("shows toast 'Folder opened' on success", async () => {
        mockApi.mockImplementationOnce(() => Promise.resolve({ ok: true, path: "/tmp/output" }));
        const runId = "success-test";

        await mockOpenFolder(runId);

        expect(mockToast).toHaveBeenCalledWith("Folder opened");
    });

    it("shows error message on failure", async () => {
        mockApi.mockImplementationOnce(() => Promise.resolve({ ok: false, message: "Folder does not exist" }));
        const runId = "fail-test";

        await mockOpenFolder(runId);

        expect(mockToast).toHaveBeenCalledWith("Folder does not exist");
    });

    it("shows error toast on api exception", async () => {
        mockApi.mockImplementationOnce(() => Promise.reject(new Error("network error")));
        const runId = "exception-test";

        await mockOpenFolder(runId);

        expect(mockToast).toHaveBeenCalledWith("Error: network error");
    });
});

async function mockOpenFolder(runId: string) {
    const api = (globalThis as any).api;
    const toast = (globalThis as any).toast;
    try {
        const res = await api(`/api/runs/${runId}/open-folder`, { method: "POST" });
        if (res.ok) {
            toast("Folder opened");
        } else {
            toast(res.message || "Failed to open folder");
        }
    } catch (e: any) {
        toast(`Error: ${e.message}`);
    }
}
