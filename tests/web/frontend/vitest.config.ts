import { defineConfig } from "vitest/config";
import path from "path";

const projectRoot = path.resolve(__dirname, "..", "..", "..");

export default defineConfig({
    test: {
        include: ["**/*.test.ts"],
        globals: true,
        environment: "node",
    },
    resolve: {
        alias: {
            "@utils": path.resolve(projectRoot, "src/quantflow/web/static/utils.ts"),
        },
    },
});