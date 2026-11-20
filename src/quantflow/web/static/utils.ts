/**
 * Pure utility functions for QuantFlow Web UI.
 * These functions have no side effects and are easily testable.
 */

/**
 * Market code suffix mapping.
 * Used to construct full stock codes (e.g., "AAPL" + ".US" = "AAPL.US").
 */
export const MARKET_SUFFIX: Record<string, string> = {
    "US": ".US",
    "HK": ".HK",
    "SH": ".SH",
    "SZ": ".SZ",
    "JP": ".T",
    "KR": ".KS",
};

export function isActiveRunStatus(status: string): boolean {
    return ["queued", "running", "cancelling"].includes(status);
}

/**
 * Settings form field ID to config data path mapping.
 * Used to populate and collect form values from/to nested config object.
 */
export const SETTINGS_FIELD_MAP: Record<string, string> = {
    "cfg-cn-primary": "data.markets.cn.primary",
    "cfg-cn-fallback": "data.markets.cn.fallback",
    "cfg-hk-primary": "data.markets.hk.primary",
    "cfg-hk-fallback": "data.markets.hk.fallback",
    "cfg-us-primary": "data.markets.us.primary",
    "cfg-us-fallback": "data.markets.us.fallback",
    "cfg-jp-primary": "data.markets.jp.primary",
    "cfg-jp-fallback": "data.markets.jp.fallback",
    "cfg-kr-primary": "data.markets.kr.primary",
    "cfg-kr-fallback": "data.markets.kr.fallback",
    "cfg-sector-primary": "data.markets.sector.primary",
    "cfg-adjust": "data.defaults.adjust",
    "cfg-lookback-multiplier": "lookback.calendar_multiplier",
    "cfg-lookback-buffer": "lookback.buffer_days",
    "cfg-yf-chunk": "yfinance.batch.chunk_size",
    "cfg-yf-min": "yfinance.batch.sleep_min",
    "cfg-yf-max": "yfinance.batch.sleep_max",
    "cfg-yq-chunk": "yahooquery.batch.chunk_size",
    "cfg-yq-min": "yahooquery.batch.sleep_min",
    "cfg-yq-max": "yahooquery.batch.sleep_max",
    "cfg-yq-workers": "yahooquery.batch.max_workers",
    "cfg-web-host": "web.host",
    "cfg-web-port": "web.port",
    "cfg-tushare-token": "tushare.token",
    "cfg-log-console-level": "logging.console_level",
    "cfg-log-file-enabled": "logging.file_enabled",
    "cfg-log-file-level": "logging.file_level",
    "cfg-log-format": "logging.format",
};

/**
 * Get a value from a nested object using dot-separated path.
 * 
 * @param obj - The object to retrieve value from
 * @param path - Dot-separated path (e.g., "data.markets.cn.primary")
 * @returns The value at the path, or undefined if path doesn't exist
 * 
 * @example
 * getNestedValue({ a: { b: { c: 1 } } }, "a.b.c") // returns 1
 * getNestedValue({ a: { b: {} } }, "a.b.c") // returns undefined
 * getNestedValue({}, "a.b.c") // returns undefined
 */
export function getNestedValue(obj: Record<string, unknown>, path: string): unknown {
    return path.split(".").reduce<unknown>(
        (o, k) => (o && typeof o === "object" ? (o as Record<string, unknown>)[k] : undefined),
        obj
    );
}

/**
 * Set a value in a nested object using dot-separated path.
 * Creates intermediate objects if they don't exist.
 * 
 * @param obj - The object to modify
 * @param path - Dot-separated path (e.g., "data.markets.cn.primary")
 * @param value - The value to set
 * 
 * @example
 * const obj = {};
 * setNestedValue(obj, "a.b.c", 1);
 * // obj is now { a: { b: { c: 1 } } }
 * 
 * setNestedValue(obj, "a.b.d", 2);
 * // obj is now { a: { b: { c: 1, d: 2 } } }
 */
export function setNestedValue(obj: Record<string, unknown>, path: string, value: unknown): void {
    const parts = path.split(".");
    let current: Record<string, unknown> = obj;
    for (let i = 0; i < parts.length - 1; i++) {
        const key = parts[i];
        if (!(key in current) || typeof current[key] !== "object") {
            current[key] = {};
        }
        current = current[key] as Record<string, unknown>;
    }
    current[parts[parts.length - 1]] = value;
}

/**
 * Format stock code with market suffix.
 * If the code already contains a dot, returns it unchanged.
 * 
 * @param rawCode - The raw stock code (e.g., "AAPL")
 * @param market - The market identifier (e.g., "US")
 * @returns The formatted code (e.g., "AAPL.US")
 * 
 * @example
 * formatStockCode("AAPL", "US") // returns "AAPL.US"
 * formatStockCode("AAPL.US", "US") // returns "AAPL.US" (already formatted)
 * formatStockCode("AAPL", "UNKNOWN") // returns "AAPL" (no suffix for unknown market)
 */
export function formatStockCode(rawCode: string, market: string): string {
    if (rawCode.includes(".")) {
        return rawCode;
    }
    const suffix = MARKET_SUFFIX[market] || "";
    return `${rawCode}${suffix}`;
}


/** Escape plain text before interpolating it into HTML text and attribute values. */
export function escapeHtml(value: unknown): string {
    return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

export function mdToHtml(md: string): string {
    let html = escapeHtml(md)
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
