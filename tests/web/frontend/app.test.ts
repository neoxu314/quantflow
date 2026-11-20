/** @vitest-environment jsdom */

import html from "../../../src/quantflow/web/static/index.html?raw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const scan = {
    id: "scan-1",
    name: "AAPL.US Scan",
    run_type: "stock_scan",
    status: "completed",
    created_at: "2025-06-05T20:00:00Z",
    config: { code: "AAPL.US", start_date: "2025-06-02", end_date: "2025-06-05" },
};

let runs: Array<typeof scan>;
let routes: Map<string, unknown>;
let fetchApi: ReturnType<typeof vi.fn>;

function element<T extends HTMLElement = HTMLElement>(selector: string): T {
    const node = document.querySelector<T>(selector);
    if (!node) throw new Error(`Missing page element ${selector}`);
    return node;
}

async function renderApp() {
    await import("@app");
    await vi.advanceTimersByTimeAsync(0);
}

function edit(selector: string, value: string) {
    const field = element<HTMLInputElement>(selector);
    field.value = value;
    field.dispatchEvent(new Event("input", { bubbles: true }));
    return field;
}

beforeEach(() => {
    vi.resetModules();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2025-06-05T20:00:00Z"));
    const page = new DOMParser().parseFromString(html, "text/html");
    document.body.innerHTML = page.body.innerHTML;
    runs = [];
    routes = new Map<string, unknown>([
        ["GET /api/strategies", { strategies: [{ id: "daily_bull_oversold", name: "Oversold" }] }],
        ["GET /api/watchlists", []],
        ["GET /api/task-files", []],
        ["GET /api/tasks", { tasks: [] }],
        ["GET /api/config", { raw: { web: { port: 8080 } } }],
        ["GET /api/library/strategies", { strategies: [] }],
        ["GET /api/library/indicators", { indicators: [] }],
        ["GET /api/runs/scan-1", { run: scan }],
        ["GET /api/runs/scan-1/logs?tail=500", { lines: ["Finished stock scan"] }],
        ["GET /api/runs/scan-1/files", { files: [] }],
        ["GET /api/runs/scan-1/indicator-data", { data: null }],
    ]);
    fetchApi = vi.fn(async (path: string, options?: RequestInit) => {
        const route = `${options?.method ?? "GET"} ${path}`;
        if (route === "GET /api/runs/") return Response.json({ runs });
        if (!routes.has(route)) return Response.json({ detail: `Unexpected endpoint ${route}` }, { status: 404 });
        const value = routes.get(route);
        return value instanceof Response ? value : Response.json(value);
    });
    vi.stubGlobal("fetch", fetchApi);
    vi.stubGlobal("confirm", vi.fn(() => true));
});

afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    document.body.replaceChildren();
});

describe("Runs in the real application", () => {
    it("renders the initial empty state", async () => {
        await renderApp();
        expect(element("#runs-list").textContent).toContain("No runs yet");
    });

    it("loads details, renders literal names and restores previous scan dates", async () => {
        runs = [{ ...scan, name: "<em>AAPL.US Scan</em>" }];
        await renderApp();
        const item = element('[data-run-id="scan-1"]');
        expect(item.textContent).toContain("<em>AAPL.US Scan</em>");
        expect(item.querySelector("em")).toBeNull();
        item.click();
        await vi.advanceTimersByTimeAsync(0);
        expect(element("#runtab-config").textContent).toContain("completed");
        const again = element<HTMLButtonElement>("#runtab-config button");
        expect(again.textContent).toContain("Run Again");
        // jsdom does not run the inline onclick attributes in the shipped HTML.
        (window as Window & { runAgain: (id: string) => void }).runAgain("scan-1");
        expect(element<HTMLInputElement>("#run-start-date").value).toBe("2025-06-02");
        expect(element<HTMLInputElement>("#run-end-date").value).toBe("2025-06-05");
        expect(element("#run-cli-preview").textContent).toContain("--code AAPL.US");
    });

    it("posts the values entered in the real scan form", async () => {
        routes.set("POST /api/runs/", { ok: true });
        await renderApp();
        element("#btn-new-run").click();
        element('[data-type="stock_scan"]').click();
        expect(element<HTMLInputElement>("#run-start-date").value).toBe("2025-06-05");
        edit("#run-stock-code", "MSFT.US");
        edit("#run-start-date", "2025-06-02");
        edit("#run-end-date", "2025-06-04");
        expect(element("#run-cli-preview").textContent).toContain("--start 2025-06-02 --end 2025-06-04");
        element("#btn-execute-run").click();
        await vi.advanceTimersByTimeAsync(0);
        const submitted = fetchApi.mock.calls.find(([url, options]) => url === "/api/runs/" && options.method === "POST");
        expect(JSON.parse(submitted![1].body)).toMatchObject({
            run_type: "stock_scan", code: "MSFT.US", start_date: "2025-06-02", end_date: "2025-06-04",
        });
        expect(element("#modal-new-run").classList.contains("hidden")).toBe(true);
    });

    it("keeps the run visible when the API rejects deletion", async () => {
        runs = [scan];
        routes.set("DELETE /api/runs/scan-1", Response.json({ detail: "busy" }, { status: 409 }));
        await renderApp();
        await (window as Window & { deleteRun: (id: string) => Promise<void> }).deleteRun("scan-1");
        expect(fetchApi).toHaveBeenCalledWith("/api/runs/scan-1", expect.objectContaining({ method: "DELETE" }));
        expect(element('[data-run-id="scan-1"]').textContent).toContain("AAPL.US Scan");
        expect(element("#toast-message").textContent).toBe("Delete failed: busy");
    });

    it("removes a run after confirmation and API success", async () => {
        runs = [scan];
        routes.set("DELETE /api/runs/scan-1", { ok: true });
        await renderApp();
        await (window as Window & { deleteRun: (id: string) => Promise<void> }).deleteRun("scan-1");
        expect(fetchApi).toHaveBeenCalledWith("/api/runs/scan-1", expect.objectContaining({ method: "DELETE" }));
        expect(document.querySelector('[data-run-id="scan-1"]')).toBeNull();
        expect(element("#toast-message").textContent).toBe("Run deleted");
    });
});

it("saves settings using the form and keeps the token field empty", async () => {
    routes.set("GET /api/config", { raw: { web: { port: 8080 } }, tushare: { tokenConfigured: true } });
    routes.set("PUT /api/config", { success: true });
    await renderApp();
    expect(element<HTMLInputElement>("#cfg-tushare-token").value).toBe("");
    edit("#cfg-web-port", "8084");
    element("#btn-save-settings").click();
    await vi.advanceTimersByTimeAsync(0);
    const saved = fetchApi.mock.calls.find(([url, options]) => url === "/api/config" && options.method === "PUT");
    expect(JSON.parse(saved![1].body).raw.web.port).toBe(8084);
    expect(JSON.parse(saved![1].body).raw.tushare?.token).toBeFalsy();
});

it("uses real SSE progress and refreshes the disk log on completion", async () => {
    let stream: TestStream;
    class TestStream extends EventTarget {
        close = vi.fn();

        constructor(readonly endpoint: string) {
            super();
            stream = this;
        }
    }
    vi.stubGlobal("EventSource", TestStream);
    runs = [{ ...scan, status: "running" }];
    routes.set("GET /api/runs/scan-1", { run: runs[0] });
    const logEndpoint = "GET /api/runs/scan-1/logs?tail=500";
    routes.set(logEndpoint, { exists: true, content: "Real file: scan started" });
    await renderApp();
    element('[data-run-id="scan-1"]').click();
    await vi.advanceTimersByTimeAsync(0);
    expect(stream!.endpoint).toBe("/api/runs/scan-1/logs:sse");

    stream!.dispatchEvent(new MessageEvent("progress", {
        data: JSON.stringify({ percentage: 50, current: 1, total: 2 }),
    }));
    expect(element("#run-progress-text").textContent).toBe("50% (1/2)");
    expect(element("#run-progress-bar").style.width).toBe("50%");
    expect(element("#run-log-container").textContent).toBe("Real file: scan started");

    runs = [scan];
    routes.set("GET /api/runs/scan-1", { run: scan });
    routes.set(logEndpoint, { exists: true, content: "Real file: scan completed" });
    stream!.dispatchEvent(new MessageEvent("status", { data: JSON.stringify({ status: "completed" }) }));
    await vi.advanceTimersByTimeAsync(0);
    expect(stream!.close).toHaveBeenCalledOnce();
    expect(element("#runtab-config").textContent).toContain("completed");
    expect(element("#run-log-container").textContent).toBe("Real file: scan completed");
});

it("reports errors from opening the run folder", async () => {
    routes.set("POST /api/runs/scan-1/open-folder", { ok: false, message: "Folder is missing" });
    await renderApp();
    await (window as Window & { openFolder: (id: string) => Promise<void> }).openFolder("scan-1");
    expect(fetchApi).toHaveBeenCalledWith("/api/runs/scan-1/open-folder", expect.objectContaining({ method: "POST" }));
    expect(element("#toast-message").textContent).toBe("Folder is missing");
});
