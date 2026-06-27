// Bilingual (EN/FR) string table for the France heat page. Every user-facing
// string lives here; index.md renders them reactively from the current `lang`
// ("en" | "fr"). Values are either markdown strings or functions returning
// markdown strings (rendered with Observable's `md` / `html`). Keep the two
// language blocks structurally identical so a missing key is obvious.

// Location phrase for the france_peak cell. The precompute emits an English
// "near <city>" (or null); rephrase per language, with a coordinate fallback.
export function locPhrase(fp, lang) {
  if (!fp) return "";
  if (fp.nearest_place) {
    const m = /^near\s+(.*)$/i.exec(fp.nearest_place);
    if (m) return lang === "fr" ? `près de ${m[1]}` : `near ${m[1]}`;
    return fp.nearest_place;
  }
  const ns = fp.lat >= 0 ? "N" : "S";
  const ew = fp.lon < 0 ? (lang === "fr" ? "O" : "W") : "E";
  return `${lang === "fr" ? "à" : "at"} ${fp.lat.toFixed(2)}°${ns}, ${Math.abs(fp.lon).toFixed(2)}°${ew}`;
}

export const STR = {
  en: {
    langOther: "Français",
    title: "France: June 2026 heat in a warming climate",
    metricLabel: "Metric",
    metricOptions: new Map([
      ["Hottest day (France-wide average)", "regional_mean_tasmax"],
      ["Hottest 3-day spell (France-wide average)", "tx3x"]
    ]),
    headline: (d) =>
      `This heat — a France-wide average of **${d.xObs} °C**, peaking ${d.day} — is **${d.rpNow}** in today's climate (about ${d.pct}% in any given year). In a **+2 °C** world it would be **${d.rp2}** — roughly **${d.ratio}×** more likely.`,
    localOffCharts: (d) =>
      `Locally, the peak reached **${d.value} °C** ${d.loc} — so far above what that spot normally sees that it is **off the charts** (rarer than 1-in-${d.cap} even in today's climate).`,
    localRare: (d) =>
      `Locally, the peak reached **${d.value} °C** ${d.loc} — **${d.rpText}** in today's climate${d.showShift ? `, becoming **${d.rp2Text}** at **+2 °C**` : ""}.`,
    localExtent: (d) =>
      `Locally, the hottest spot reached **${d.value} °C** ${d.loc} — hot, but not a record there (about what that always-warm area sees in a normal summer). What made this heatwave stand out is **how widespread it was** — the countrywide average is the rare part, not any single local peak.`,
    note1: `These figures are a **France-wide average**, not a single town. Local highs run much hotter — around 42 °C somewhere in this heatwave — because the average folds in cooler coasts, hills and regions. How rare the heat is, though, is measured on a like-for-like basis, so the odds still hold. [How it's measured →](./methods)`,
    note2: `This puts the heat in the context of a warming world — how unusual it is, and how that shifts as warming grows. It is context, not a formal attribution study of this exact event.`,
    headingOdds: "How the odds change as the world warms",
    rpCaption: `Lower means rarer. This heat sits near the top today and slides toward "an ordinary year" as the world warms.`,
    headingSameHeat: "The same heat, climate by climate",
    panelIntro: `Each panel is a different climate. The curve runs from a common day (left) to a rare one (right); the dashed line is this event. The further left it lands, the more ordinary this heat has become.`,
    headingSeeHeat: "See the heat across France",
    seeHeatIntro: `Two views of **this heatwave**, placed in different climates: *how hot* its worst day gets, and *how often* a day that hot happens. Both are anchored to this event — **not an average summer**. The slider doesn't warm up a typical day; it asks what an extreme *as rare as June 2026* looks like in each climate. Drag it from the world before global warming toward a much hotter future, and use the tabs to switch views.`,
    sliderLabel: "Global warming",
    ofGlobalWarming: "of global warming",
    tabHot: "How hot it gets",
    tabOften: "How often it happens",
    mapGuideHot: `**How hot it gets.** The peak temperature of a heatwave **as rare as this one** in the chosen climate — town by town, deep red the fiercest. At **Now** it is the peak this June actually reached; slide warmer and the same once-in-a-generation extreme keeps climbing. (This is the rare event getting hotter, not the average summer.)`,
    mapGuideOften: `**How often it happens.** For each area, how often a day **as hot as this heatwave's local peak** comes around in the chosen climate. **Deep purple** = happens often (an ordinary summer's day); **grey** = a once-in-a-lifetime rarity. Read the colours as odds: "1-in-30" means a day this hot is expected about **once every 30 years**. Slide warmer and grey turns purple — today's rare heat becomes routine.`,
    headingBuilt: "What the current value is built from",
    provenance: (d) =>
      `Live value blends ERA5T reanalysis (through **${d.era5t}**) with the ECMWF HRES forecast (cycles ${d.cycles}), bias-corrected by ${d.bias} °C onto the reanalysis and shifted ${d.offset} °C onto the reference footing. Peak from **${d.src}** on ${d.day}. See [Methods and provenance](./methods).`,
    now: "now",
    levelLabel: {
      "0.0": "in 1850–1900", "1.0": "at ~1 °C (recent past)", "now": "now",
      "1.5": "at +1.5 °C", "2.0": "at +2 °C", "3.0": "at +3 °C"
    },
    levelNames: ["1850–1900", "Recent ~1 °C", "Now", "+1.5 °C", "+2 °C", "+3 °C"],
    gwlBlurb: ["before global warming", "the climate of the mid-2010s", "today",
      "the Paris Agreement's tougher goal", "the Paris Agreement's limit",
      "where current policies are heading"],
    shortLabel: {
      "0.0": "1850–1900", "1.0": "~1 °C", "1.5": "+1.5 °C", "2.0": "+2 °C", "3.0": "+3 °C"
    },
    axisWarming: "Global warming level (°C above 1850-1900)",
    axisReturnPeriod: "Return period (years)",
    tempMapNow: "Local peak reached (°C)",
    tempMapLevel: (lvl) => `Local peak of an equally rare event ${lvl} (°C)`,
    rpMapLabel: (lvl) => `How often this heat hits ${lvl} (1-in-N years)`,
    tickOneIn: (d) => `1-in-${d}`,
    fmtRp: (v) => (v == null ? "never" : `1-in-${Math.round(v)}`)
  },

  fr: {
    langOther: "English",
    title: "France : la chaleur de juin 2026 dans un climat qui se réchauffe",
    metricLabel: "Indicateur",
    metricOptions: new Map([
      ["Jour le plus chaud (moyenne sur la France)", "regional_mean_tasmax"],
      ["Épisode de 3 jours le plus chaud (moyenne sur la France)", "tx3x"]
    ]),
    headline: (d) =>
      `Cette chaleur — une moyenne sur la France de **${d.xObs} °C**, culminant le ${d.day} — est **${d.rpNow}** dans le climat actuel (environ ${d.pct} % une année donnée). Dans un monde à **+2 °C**, elle serait **${d.rp2}** — environ **${d.ratio}×** plus probable.`,
    localOffCharts: (d) =>
      `Localement, le pic a atteint **${d.value} °C** ${d.loc} — si loin au-dessus de ce que cet endroit connaît habituellement que c'est **hors normes** (plus rare que 1 sur ${d.cap}, même dans le climat actuel).`,
    localRare: (d) =>
      `Localement, le pic a atteint **${d.value} °C** ${d.loc} — **${d.rpText}** dans le climat actuel${d.showShift ? `, passant à **${d.rp2Text}** à **+2 °C**` : ""}.`,
    localExtent: (d) =>
      `Localement, l'endroit le plus chaud a atteint **${d.value} °C** ${d.loc} — chaud, mais pas un record local (à peu près ce que cette région toujours chaude connaît lors d'un été normal). Ce qui a rendu cette canicule remarquable, c'est **son étendue** — c'est la moyenne nationale qui est rare, pas un pic local.`,
    note1: `Ces chiffres sont une **moyenne sur la France**, pas une seule ville. Les pics locaux sont bien plus élevés — autour de 42 °C quelque part lors de cette canicule — car la moyenne intègre les côtes, les reliefs et les régions plus fraîches. La rareté de la chaleur est toutefois mesurée à conditions comparables, donc les probabilités restent valables. [Comment c'est mesuré →](./methods)`,
    note2: `Ceci replace la chaleur dans le contexte d'un monde qui se réchauffe — son caractère inhabituel et son évolution à mesure que le réchauffement s'accentue. C'est un éclairage, pas une étude d'attribution formelle de cet événement précis.`,
    headingOdds: "Comment les probabilités évoluent avec le réchauffement",
    rpCaption: `Plus bas = plus rare. Cette chaleur est proche du sommet aujourd'hui et glisse vers « une année ordinaire » à mesure que le monde se réchauffe.`,
    headingSameHeat: "La même chaleur, climat par climat",
    panelIntro: `Chaque panneau est un climat différent. La courbe va d'un jour courant (à gauche) à un jour rare (à droite) ; la ligne pointillée représente cet événement. Plus elle tombe à gauche, plus cette chaleur est devenue ordinaire.`,
    headingSeeHeat: "Voir la chaleur à travers la France",
    seeHeatIntro: `Deux vues de **cette canicule**, replacées dans différents climats : *à quel point* son pire jour est chaud, et *à quelle fréquence* un jour aussi chaud survient. Les deux sont rapportées à cet événement — **pas à un été moyen**. Le curseur ne réchauffe pas une journée typique ; il montre à quoi ressemble un extrême *aussi rare que juin 2026* dans chaque climat. Faites-le glisser du monde d'avant le réchauffement vers un futur bien plus chaud, et utilisez les onglets pour changer de vue.`,
    sliderLabel: "Réchauffement planétaire",
    ofGlobalWarming: "de réchauffement planétaire",
    tabHot: "À quel point il fait chaud",
    tabOften: "À quelle fréquence",
    mapGuideHot: `**À quel point il fait chaud.** La température de pointe d'une canicule **aussi rare que celle-ci** dans le climat choisi — ville par ville, le rouge foncé étant le plus intense. À **Aujourd'hui**, c'est le pic réellement atteint en juin ; glissez vers le chaud et le même extrême « une fois par génération » continue de grimper. (C'est l'événement rare qui se réchauffe, pas l'été moyen.)`,
    mapGuideOften: `**À quelle fréquence.** Pour chaque zone, à quelle fréquence un jour **aussi chaud que le pic local de cette canicule** revient dans le climat choisi. **Violet foncé** = fréquent (une journée d'été ordinaire) ; **gris** = une rareté d'une fois dans une vie. Lisez les couleurs comme des probabilités : « 1 sur 30 » signifie qu'un jour aussi chaud est attendu environ **une fois tous les 30 ans**. Glissez vers le chaud et le gris devient violet — la chaleur rare d'aujourd'hui devient routinière.`,
    headingBuilt: "Comment la valeur actuelle est construite",
    provenance: (d) =>
      `La valeur en direct combine la réanalyse ERA5T (jusqu'au **${d.era5t}**) avec la prévision ECMWF HRES (cycles ${d.cycles}), corrigée d'un biais de ${d.bias} °C sur la réanalyse et décalée de ${d.offset} °C sur la référence. Pic de **${d.src}** le ${d.day}. Voir [Méthodes et provenance](./methods).`,
    now: "aujourd'hui",
    levelLabel: {
      "0.0": "en 1850–1900", "1.0": "à ~1 °C (passé récent)", "now": "aujourd'hui",
      "1.5": "à +1,5 °C", "2.0": "à +2 °C", "3.0": "à +3 °C"
    },
    levelNames: ["1850–1900", "Récent ~1 °C", "Aujourd'hui", "+1,5 °C", "+2 °C", "+3 °C"],
    gwlBlurb: ["avant le réchauffement", "le climat du milieu des années 2010", "aujourd'hui",
      "l'objectif le plus ambitieux de l'Accord de Paris", "la limite de l'Accord de Paris",
      "la trajectoire des politiques actuelles"],
    shortLabel: {
      "0.0": "1850–1900", "1.0": "~1 °C", "1.5": "+1,5 °C", "2.0": "+2 °C", "3.0": "+3 °C"
    },
    axisWarming: "Niveau de réchauffement (°C au-dessus de 1850-1900)",
    axisReturnPeriod: "Période de retour (années)",
    tempMapNow: "Pic local atteint (°C)",
    tempMapLevel: (lvl) => `Pic local d'un événement aussi rare ${lvl} (°C)`,
    rpMapLabel: (lvl) => `Fréquence de cette chaleur ${lvl} (1 sur N ans)`,
    tickOneIn: (d) => `1 sur ${d}`,
    fmtRp: (v) => (v == null ? "jamais" : `1 sur ${Math.round(v)}`)
  }
};
