export const MARKET_SUFFIX = {
    "US": ".US",
    "HK": ".HK",
    "SH": ".SH",
    "SZ": ".SZ",
    "JP": ".T",
    "KR": ".KS",
};
export function isActiveRunStatus(status) {
    return ["queued", "running", "cancelling"].includes(status);
}
export const SETTINGS_FIELD_MAP = {
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
export function getNestedValue(obj, path) {
    return path.split(".").reduce((o, k) => (o && typeof o === "object" ? o[k] : undefined), obj);
}
export function setNestedValue(obj, path, value) {
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
export function formatStockCode(rawCode, market) {
    if (rawCode.includes(".")) {
        return rawCode;
    }
    const suffix = MARKET_SUFFIX[market] || "";
    return `${rawCode}${suffix}`;
}
