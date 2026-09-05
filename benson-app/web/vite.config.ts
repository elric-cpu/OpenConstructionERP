import { defineConfig } from "vite";

export default defineConfig({
  server: { allowedHosts: ["benson-ai"] },
  preview: { allowedHosts: ["benson-ai"] },
});
