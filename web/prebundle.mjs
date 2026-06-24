// Pre-populate Observable Framework's npm cache from local node_modules.
// Framework normally self-hosts npm imports by downloading +esm bundles from
// jsdelivr at build time. That CDN is not reachable from this environment's
// egress policy (only the npm registry is), so we bundle each package locally
// with esbuild and write it to the exact cache path Framework checks first
// (it skips the download when the cache file already exists). In GitHub Actions,
// where jsdelivr is reachable, this step is unnecessary and harmless.
import {build} from "esbuild";
import {createRequire} from "node:module";
import {mkdirSync, writeFileSync, readFileSync} from "node:fs";
import {dirname, join} from "node:path";

const require = createRequire(import.meta.url);
const CACHE = join(process.cwd(), "src", ".observablehq", "cache", "_npm");

const packages = ["d3", "@observablehq/plot", "htl", "isoformat",
  "@observablehq/inputs", "@observablehq/runtime"];

for (const name of packages) {
  let version;
  try {
    version = JSON.parse(
      readFileSync(join(process.cwd(), "node_modules", name, "package.json"))
    ).version;
  } catch {
    console.log(`skip ${name} (not installed)`);
    continue;
  }
  const outfile = join(CACHE, `${name}@${version}`, "_esm.js");
  mkdirSync(dirname(outfile), {recursive: true});
  const entry = `import * as ns from "${name}";\n`
    + `export * from "${name}";\n`
    + `export default ns.default ?? ns;\n`;
  await build({
    stdin: {contents: entry, resolveDir: process.cwd(), loader: "js"},
    bundle: true, format: "esm", outfile, logLevel: "error",
    legalComments: "none", target: "es2022"
  });
  console.log(`bundled ${name}@${version} -> ${outfile.replace(process.cwd(), ".")}`);
}
