// Data loader: stream the canonical precompute lookup into the build.
// Single source of truth is the repo's output/lookup.json.
import {readFileSync} from "node:fs";
const url = new URL("../../../output/lookup.json", import.meta.url);
process.stdout.write(readFileSync(url, "utf-8"));
