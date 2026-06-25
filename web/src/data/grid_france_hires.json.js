// Data loader: France-only 0.25° local-peak (local_txx) grid for the hi-res map.
// Tolerant of a missing file so the app builds before the local-peak precompute
// has run (python -m precompute.local_peak); the section then hides itself.
import {existsSync, readFileSync} from "node:fs";
const url = new URL("../../../output/grid_france_hires.json", import.meta.url);
process.stdout.write(existsSync(url) ? readFileSync(url, "utf-8") : "null");
