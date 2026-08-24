import { defineConfig } from "vitest/config";

export default defineConfig({
    test: {
        globals: true,
        include: [".lc/practice-attempts/**/*.test.ts"],
    },
});
