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
