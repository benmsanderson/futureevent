// Data loader: gridded probability-ratio field for the map.
// Tolerant of a missing file so the app builds before the grid precompute has
// run; the map then shows an explanatory placeholder.
import {existsSync, readFileSync} from "node:fs";
const url = new URL("../../../output/grid_europe.json", import.meta.url);
process.stdout.write(existsSync(url) ? readFileSync(url, "utf-8") : "null");
