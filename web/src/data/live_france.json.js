// Data loader: stream the blended live event value into the build.
// Refreshed by the scheduled GitHub Action, which commits output/live_france.json
// and redeploys; the value is therefore baked at each scheduled deploy.
import {readFileSync} from "node:fs";
const url = new URL("../../../output/live_france.json", import.meta.url);
process.stdout.write(readFileSync(url, "utf-8"));
