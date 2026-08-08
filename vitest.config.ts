import { defineConfig } from "vitest/config";

export default defineConfig({
    test: {
        globals: true,
        include: ["src/typescript/**/*.test.ts"],
    },
});
