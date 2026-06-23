import { build } from "esbuild";
import { mkdirSync, copyFileSync } from "fs";
import { fileURLToPath } from "url";
import path from "path";

const here = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.join(here, "..", "static");
mkdirSync(outDir, { recursive: true });

await build({
  entryPoints: [path.join(here, "src", "index.js")],
  bundle: true,
  format: "esm",
  minify: true,
  outfile: path.join(outDir, "bundle.js"),
});

copyFileSync(path.join(here, "src", "index.html"), path.join(outDir, "index.html"));

const cssDir = path.join(here, "node_modules", "@lichess-org", "chessground", "assets");
for (const name of [
  "chessground.base.css",
  "chessground.brown.css",
  "chessground.cburnett.css",
]) {
  copyFileSync(path.join(cssDir, name), path.join(outDir, name));
}

console.log("Built chessboard frontend ->", outDir);
