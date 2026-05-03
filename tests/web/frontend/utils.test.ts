import { describe, it, expect } from "vitest";
import {
    MARKET_SUFFIX,
    SETTINGS_FIELD_MAP,
    getNestedValue,
    setNestedValue,
    formatStockCode,
} from "@utils";

describe("MARKET_SUFFIX", () => {
    it("has correct suffix for US market", () => {
        expect(MARKET_SUFFIX["US"]).toBe(".US");
    });

    it("has correct suffix for HK market", () => {
        expect(MARKET_SUFFIX["HK"]).toBe(".HK");
    });

    it("has correct suffix for Shanghai market", () => {
        expect(MARKET_SUFFIX["SH"]).toBe(".SH");
    });

    it("has correct suffix for Shenzhen market", () => {
        expect(MARKET_SUFFIX["SZ"]).toBe(".SZ");
    });

    it("has correct suffix for Japan market", () => {
        expect(MARKET_SUFFIX["JP"]).toBe(".T");
    });

    it("has correct suffix for Korea market", () => {
        expect(MARKET_SUFFIX["KR"]).toBe(".KS");
    });

    it("returns undefined for unknown market", () => {
        expect(MARKET_SUFFIX["UNKNOWN"]).toBeUndefined();
    });

    it("has all 6 supported markets", () => {
        expect(Object.keys(MARKET_SUFFIX).length).toBe(6);
    });
});

describe("SETTINGS_FIELD_MAP", () => {
    it("maps cn-primary to correct path", () => {
        expect(SETTINGS_FIELD_MAP["cfg-cn-primary"]).toBe("data.markets.cn.primary");
    });

    it("maps us-primary to correct path", () => {
        expect(SETTINGS_FIELD_MAP["cfg-us-primary"]).toBe("data.markets.us.primary");
    });

    it("maps lookback-multiplier to correct path", () => {
        expect(SETTINGS_FIELD_MAP["cfg-lookback-multiplier"]).toBe("lookback.calendar_multiplier");
    });

    it("maps lookback-buffer to correct path", () => {
        expect(SETTINGS_FIELD_MAP["cfg-lookback-buffer"]).toBe("lookback.buffer_days");
    });

    it("maps web-port to correct path", () => {
        expect(SETTINGS_FIELD_MAP["cfg-web-port"]).toBe("web.port");
    });

    it("maps tushare-token to correct path", () => {
        expect(SETTINGS_FIELD_MAP["cfg-tushare-token"]).toBe("tushare.token");
    });

    it("maps log-level to correct path", () => {
        expect(SETTINGS_FIELD_MAP["cfg-log-level"]).toBe("logging.level");
    });

    it("has expected number of field mappings", () => {
        expect(Object.keys(SETTINGS_FIELD_MAP).length).toBe(16);
    });
});

describe("getNestedValue", () => {
    it("returns value from single-level path", () => {
        const obj = { a: 1, b: 2 };
        expect(getNestedValue(obj, "a")).toBe(1);
        expect(getNestedValue(obj, "b")).toBe(2);
    });

    it("returns value from two-level nested path", () => {
        const obj = { data: { markets: { cn: { primary: "baostock" } } } };
        expect(getNestedValue(obj, "data.markets.cn.primary")).toBe("baostock");
    });

    it("returns value from three-level nested path", () => {
        const obj = { lookback: { calendar_multiplier: 2, buffer_days: 30 } };
        expect(getNestedValue(obj, "lookback.calendar_multiplier")).toBe(2);
        expect(getNestedValue(obj, "lookback.buffer_days")).toBe(30);
    });

    it("returns undefined for non-existent top-level key", () => {
        const obj = { a: 1 };
        expect(getNestedValue(obj, "b")).toBeUndefined();
    });

    it("returns undefined for non-existent nested key", () => {
        const obj = { a: { b: 1 } };
        expect(getNestedValue(obj, "a.c")).toBeUndefined();
    });

    it("returns undefined for path exceeding object depth", () => {
        const obj = { a: { b: 1 } };
        expect(getNestedValue(obj, "a.b.c.d")).toBeUndefined();
    });

    it("returns undefined for empty object", () => {
        expect(getNestedValue({}, "a.b.c")).toBeUndefined();
    });

    it("handles numeric values", () => {
        const obj = { port: 8080, multiplier: 2.5 };
        expect(getNestedValue(obj, "port")).toBe(8080);
        expect(getNestedValue(obj, "multiplier")).toBe(2.5);
    });

    it("handles string values", () => {
        const obj = { host: "127.0.0.1", level: "INFO" };
        expect(getNestedValue(obj, "host")).toBe("127.0.0.1");
        expect(getNestedValue(obj, "level")).toBe("INFO");
    });

    it("handles array values", () => {
        const obj = { strategies: ["daily_bull_oversold", "kdj_dead_cross"] };
        expect(getNestedValue(obj, "strategies")).toEqual(["daily_bull_oversold", "kdj_dead_cross"]);
    });

    it("handles null values in path", () => {
        const obj = { a: null };
        expect(getNestedValue(obj, "a.b")).toBeUndefined();
    });
});

describe("setNestedValue", () => {
    it("sets value at single-level path", () => {
        const obj: Record<string, unknown> = {};
        setNestedValue(obj, "a", 1);
        expect(obj.a).toBe(1);
    });

    it("sets value at two-level path creating intermediate objects", () => {
        const obj: Record<string, unknown> = {};
        setNestedValue(obj, "a.b", 2);
        expect(obj.a).toEqual({ b: 2 });
    });

    it("sets value at three-level path creating all intermediate objects", () => {
        const obj: Record<string, unknown> = {};
        setNestedValue(obj, "data.markets.cn.primary", "tushare");
        expect(obj.data).toEqual({ markets: { cn: { primary: "tushare" } } });
    });

    it("overwrites existing value at path", () => {
        const obj: Record<string, unknown> = { a: { b: 1 } };
        setNestedValue(obj, "a.b", 2);
        expect(obj.a).toEqual({ b: 2 });
    });

    it("preserves other fields when setting new value", () => {
        const obj: Record<string, unknown> = { a: { b: 1, c: 3 } };
        setNestedValue(obj, "a.b", 2);
        expect(obj.a).toEqual({ b: 2, c: 3 });
    });

    it("converts primitive to object when setting nested value", () => {
        const obj: Record<string, unknown> = { a: 1 };
        setNestedValue(obj, "a.b", 2);
        expect(obj.a).toEqual({ b: 2 });
    });

    it("sets multiple values at different paths", () => {
        const obj: Record<string, unknown> = {};
        setNestedValue(obj, "web.port", 8080);
        setNestedValue(obj, "web.host", "127.0.0.1");
        expect(obj.web).toEqual({ port: 8080, host: "127.0.0.1" });
    });

    it("sets numeric value", () => {
        const obj: Record<string, unknown> = {};
        setNestedValue(obj, "buffer_days", 30);
        expect(obj.buffer_days).toBe(30);
    });

    it("sets string value", () => {
        const obj: Record<string, unknown> = {};
        setNestedValue(obj, "logging.level", "DEBUG");
        expect(obj.logging).toEqual({ level: "DEBUG" });
    });

    it("sets boolean value", () => {
        const obj: Record<string, unknown> = {};
        setNestedValue(obj, "enabled", true);
        expect(obj.enabled).toBe(true);
    });

    it("sets array value", () => {
        const obj: Record<string, unknown> = {};
        setNestedValue(obj, "strategies", ["s1", "s2"]);
        expect(obj.strategies).toEqual(["s1", "s2"]);
    });
});

describe("formatStockCode", () => {
    it("formats US stock code with .US suffix", () => {
        expect(formatStockCode("AAPL", "US")).toBe("AAPL.US");
    });

    it("formats HK stock code with .HK suffix", () => {
        expect(formatStockCode("00700", "HK")).toBe("00700.HK");
    });

    it("formats Shanghai stock code with .SH suffix", () => {
        expect(formatStockCode("600519", "SH")).toBe("600519.SH");
    });

    it("formats Shenzhen stock code with .SZ suffix", () => {
        expect(formatStockCode("002594", "SZ")).toBe("002594.SZ");
    });

    it("formats Japan stock code with .T suffix", () => {
        expect(formatStockCode("7203", "JP")).toBe("7203.T");
    });

    it("formats Korea stock code with .KS suffix", () => {
        expect(formatStockCode("005930", "KR")).toBe("005930.KS");
    });

    it("returns unchanged if code already contains dot", () => {
        expect(formatStockCode("AAPL.US", "US")).toBe("AAPL.US");
        expect(formatStockCode("600519.SH", "SH")).toBe("600519.SH");
    });

    it("returns code unchanged for unknown market", () => {
        expect(formatStockCode("AAPL", "UNKNOWN")).toBe("AAPL");
    });

    it("handles empty code", () => {
        expect(formatStockCode("", "US")).toBe(".US");
    });

    it("handles empty market", () => {
        expect(formatStockCode("AAPL", "")).toBe("AAPL");
    });

    it("handles already formatted code with unknown market", () => {
        expect(formatStockCode("AAPL.US", "UNKNOWN")).toBe("AAPL.US");
    });
});