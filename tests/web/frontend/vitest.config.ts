import { defineConfig } from "vitest/config";
import path from "path";

const projectRoot = path.resolve(__dirname, "..", "..", "..");

export default defineConfig({
    test: {
        include: ["**/*.test.ts"],
        globals: true,
        environment: "node",
    },
    server: { fs: { allow: [projectRoot] } },
    resolve: {
        alias: {
            "@app": path.resolve(projectRoot, "src/quantflow/web/static/app.ts"),
            "@utils": path.resolve(projectRoot, "src/quantflow/web/static/utils.ts"),
        },
    },
});