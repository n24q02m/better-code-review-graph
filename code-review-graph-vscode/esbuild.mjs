import * as esbuild from "esbuild";

const isWatch = process.argv.includes("--watch");
const isProduction = process.argv.includes("--production");

/** @type {esbuild.BuildOptions} */
const extensionConfig = {
  entryPoints: ["src/extension.ts"],
  bundle: true,
  outfile: "dist/extension.js",
  external: ["vscode", "better-sqlite3"],
  format: "cjs",
  platform: "node",
  target: "node18",
  sourcemap: !isProduction,
  minify: isProduction,
  logLevel: "info",
};

/** @type {esbuild.BuildOptions} */
const webviewConfig = {
  entryPoints: ["src/webview/graph.ts"],
  bundle: true,
  outfile: "dist/webview/graph.js",
  format: "iife",
  platform: "browser",
  target: "es2022",
  sourcemap: !isProduction,
  minify: isProduction,
  logLevel: "info",
};

async function main() {
  if (isWatch) {
    const extensionCtx = await esbuild.context(extensionConfig);
    const webviewCtx = await esbuild.context(webviewConfig);
    await Promise.all([extensionCtx.watch(), webviewCtx.watch()]);
    console.log("[watch] Build started. Watching for changes...");
  } else {
    await Promise.all([
      esbuild.build(extensionConfig),
      esbuild.build(webviewConfig),
    ]);
    console.log("Build complete.");
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
