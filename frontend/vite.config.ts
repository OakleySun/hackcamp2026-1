// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// Never set ssr.external or resolve.external: the Worker has no runtime module resolution, so
// the build fails. Never add compression (compressPublicAssets, vite-plugin-compression):
// hosting already compresses at the edge.
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";
import type { NitroConfig } from "nitro/types";

const maritime = process.env["QUAD_MARITIME_BUILD"] === "1";
const backend = "http://127.0.0.1:8000";
const maritimeNitro: NitroConfig = {
  preset: "node_server",
  routeRules: {
    "/health": { proxy: `${backend}/health` },
    "/api/**": { proxy: `${backend}/api/**` },
    "/verify": { proxy: `${backend}/verify` },
    "/manage": { proxy: `${backend}/manage` },
  },
};

export default defineConfig({
  ...(maritime ? { nitro: maritimeNitro } : {}),
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
  },
});
