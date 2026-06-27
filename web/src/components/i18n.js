// Bilingual (EN/FR) string table for the France heat page. Every user-facing
// string lives here; index.md renders them reactively from the current `lang`
// ("en" | "fr"). Values are either HTML strings or functions returning HTML
// strings (rendered by setting innerHTML on an element — Observable Framework
// has no `md` global). Strings carry only trusted inline markup (<b>/<i>/<a>).
// Keep the two language blocks structurally identical so a missing key is obvious.

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
      `This heat — a France-wide average of <b>${d.xObs} °C</b>, peaking ${d.day} — is <b>${d.rpNow}</b> in today's climate (about ${d.pct}% in any given year). In a <b>+2 °C</b> world it would be <b>${d.rp2}</b> — roughly <b>${d.ratio}×</b> more likely.`,
    localOffCharts: (d) =>
      `Locally, the peak reached <b>${d.value} °C</b> ${d.loc} — so far above what that spot normally sees that it is <b>off the charts</b> (rarer than 1-in-${d.cap} even in today's climate).`,
    localRare: (d) =>
      `Locally, the peak reached <b>${d.value} °C</b> ${d.loc} — <b>${d.rpText}</b> in today's climate${d.showShift ? `, becoming <b>${d.rp2Text}</b> at <b>+2 °C</b>` : ""}.`,
    localExtent: (d) =>
      `Locally, the hottest spot reached <b>${d.value} °C</b> ${d.loc} — hot, but not a record there (about what that always-warm area sees in a normal summer). What made this heatwave stand out is <b>how widespread it was</b> — the countrywide average is the rare part, not any single local peak.`,
    note1: `These figures are a <b>France-wide average</b>, not a single town. Local highs run much hotter — around 42 °C somewhere in this heatwave — because the average folds in cooler coasts, hills and regions. How rare the heat is, though, is measured on a like-for-like basis, so the odds still hold. <a href="./methods">How it's measured →</a>`,
    note2: `This puts the heat in the context of a warming world — how unusual it is, and how that shifts as warming grows. It is context, not a formal attribution study of this exact event.`,
    forecastNotice: `<b>Heads-up — this is a live forecast.</b> The peak shown is still drawn from the weather forecast, not the final reanalysis (which lands a few days after the event). So the exact numbers may shift — and may differ from the record temperatures reported by national weather services — but how rare this heat is, and how that changes with warming, is already indicative. We'll refresh with the confirmed data once it lands.`,
    headingOdds: "How the odds change as the world warms",
    rpCaption: `Lower means rarer. This heat sits near the top today and slides toward "an ordinary year" as the world warms.`,
    headingSameHeat: "The same heat, climate by climate",
    panelIntro: `Each panel is a different climate. The curve runs from a common day (left) to a rare one (right); the dashed line is this event. The further left it lands, the more ordinary this heat has become.`,
    headingSeeHeat: "See the heat across France",
    seeHeatIntro: `Two views of <b>this heatwave</b>, placed in different climates: <i>how hot</i> its worst day gets, and <i>how often</i> a day that hot happens. Both are anchored to this event — <b>not an average summer</b>. The slider doesn't warm up a typical day; it asks what an extreme <i>as rare as June 2026</i> looks like in each climate. Drag it from the world before global warming toward a much hotter future, and use the tabs to switch views.`,
    sliderLabel: "Global warming",
    ofGlobalWarming: "of global warming",
    tabHot: "How hot it gets",
    tabOften: "How often it happens",
    mapGuideHot: `<b>How hot it gets.</b> The peak temperature of a heatwave <b>as rare as this one</b> in the chosen climate — town by town, deep red the fiercest. At <b>Now</b> it is the peak this June actually reached; slide warmer and the same once-in-a-generation extreme keeps climbing. (This is the rare event getting hotter, not the average summer.)`,
    mapGuideOften: `<b>How often it happens.</b> For each area, how often a day <b>as hot as this heatwave's local peak</b> comes around in the chosen climate. <b>Deep purple</b> = happens often (an ordinary summer's day); <b>grey</b> = a once-in-a-lifetime rarity. Read the colours as odds: "1-in-30" means a day this hot is expected about <b>once every 30 years</b>. Slide warmer and grey turns purple — today's rare heat becomes routine.`,
    headingBuilt: "What the current value is built from",
    provenance: (d) =>
      `Live value blends ERA5T reanalysis (through <b>${d.era5t}</b>) with the ECMWF HRES forecast (cycles ${d.cycles}), bias-corrected by ${d.bias} °C onto the reanalysis and shifted ${d.offset} °C onto the reference footing. Peak from <b>${d.src}</b> on ${d.day}. See <a href="./methods">Methods and provenance</a>.`,
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
      `Cette chaleur — une moyenne sur la France de <b>${d.xObs} °C</b>, culminant le ${d.day} — est <b>${d.rpNow}</b> dans le climat actuel (environ ${d.pct} % une année donnée). Dans un monde à <b>+2 °C</b>, elle serait <b>${d.rp2}</b> — environ <b>${d.ratio}×</b> plus probable.`,
    localOffCharts: (d) =>
      `Localement, le pic a atteint <b>${d.value} °C</b> ${d.loc} — si loin au-dessus de ce que cet endroit connaît habituellement que c'est <b>hors normes</b> (plus rare que 1 sur ${d.cap}, même dans le climat actuel).`,
    localRare: (d) =>
      `Localement, le pic a atteint <b>${d.value} °C</b> ${d.loc} — <b>${d.rpText}</b> dans le climat actuel${d.showShift ? `, passant à <b>${d.rp2Text}</b> à <b>+2 °C</b>` : ""}.`,
    localExtent: (d) =>
      `Localement, l'endroit le plus chaud a atteint <b>${d.value} °C</b> ${d.loc} — chaud, mais pas un record local (à peu près ce que cette région toujours chaude connaît lors d'un été normal). Ce qui a rendu cette canicule remarquable, c'est <b>son étendue</b> — c'est la moyenne nationale qui est rare, pas un pic local.`,
    note1: `Ces chiffres sont une <b>moyenne sur la France</b>, pas une seule ville. Les pics locaux sont bien plus élevés — autour de 42 °C quelque part lors de cette canicule — car la moyenne intègre les côtes, les reliefs et les régions plus fraîches. La rareté de la chaleur est toutefois mesurée à conditions comparables, donc les probabilités restent valables. <a href="./methods">Comment c'est mesuré →</a>`,
    note2: `Ceci replace la chaleur dans le contexte d'un monde qui se réchauffe — son caractère inhabituel et son évolution à mesure que le réchauffement s'accentue. C'est un éclairage, pas une étude d'attribution formelle de cet événement précis.`,
    forecastNotice: `<b>À noter — il s'agit d'une prévision en direct.</b> Le pic affiché provient encore de la prévision météo, pas de la réanalyse définitive (qui arrive quelques jours après l'événement). Les chiffres exacts peuvent donc évoluer — et différer des températures record annoncées par les services météo nationaux — mais la rareté de cette chaleur, et son évolution avec le réchauffement, sont déjà indicatives. Nous actualiserons avec les données confirmées dès qu'elles seront disponibles.`,
    headingOdds: "Comment les probabilités évoluent avec le réchauffement",
    rpCaption: `Plus bas = plus rare. Cette chaleur est proche du sommet aujourd'hui et glisse vers « une année ordinaire » à mesure que le monde se réchauffe.`,
    headingSameHeat: "La même chaleur, climat par climat",
    panelIntro: `Chaque panneau est un climat différent. La courbe va d'un jour courant (à gauche) à un jour rare (à droite) ; la ligne pointillée représente cet événement. Plus elle tombe à gauche, plus cette chaleur est devenue ordinaire.`,
    headingSeeHeat: "Voir la chaleur à travers la France",
    seeHeatIntro: `Deux vues de <b>cette canicule</b>, replacées dans différents climats : <i>à quel point</i> son pire jour est chaud, et <i>à quelle fréquence</i> un jour aussi chaud survient. Les deux sont rapportées à cet événement — <b>pas à un été moyen</b>. Le curseur ne réchauffe pas une journée typique ; il montre à quoi ressemble un extrême <i>aussi rare que juin 2026</i> dans chaque climat. Faites-le glisser du monde d'avant le réchauffement vers un futur bien plus chaud, et utilisez les onglets pour changer de vue.`,
    sliderLabel: "Réchauffement planétaire",
    ofGlobalWarming: "de réchauffement planétaire",
    tabHot: "À quel point il fait chaud",
    tabOften: "À quelle fréquence",
    mapGuideHot: `<b>À quel point il fait chaud.</b> La température de pointe d'une canicule <b>aussi rare que celle-ci</b> dans le climat choisi — ville par ville, le rouge foncé étant le plus intense. À <b>Aujourd'hui</b>, c'est le pic réellement atteint en juin ; glissez vers le chaud et le même extrême « une fois par génération » continue de grimper. (C'est l'événement rare qui se réchauffe, pas l'été moyen.)`,
    mapGuideOften: `<b>À quelle fréquence.</b> Pour chaque zone, à quelle fréquence un jour <b>aussi chaud que le pic local de cette canicule</b> revient dans le climat choisi. <b>Violet foncé</b> = fréquent (une journée d'été ordinaire) ; <b>gris</b> = une rareté d'une fois dans une vie. Lisez les couleurs comme des probabilités : « 1 sur 30 » signifie qu'un jour aussi chaud est attendu environ <b>une fois tous les 30 ans</b>. Glissez vers le chaud et le gris devient violet — la chaleur rare d'aujourd'hui devient routinière.`,
    headingBuilt: "Comment la valeur actuelle est construite",
    provenance: (d) =>
      `La valeur en direct combine la réanalyse ERA5T (jusqu'au <b>${d.era5t}</b>) avec la prévision ECMWF HRES (cycles ${d.cycles}), corrigée d'un biais de ${d.bias} °C sur la réanalyse et décalée de ${d.offset} °C sur la référence. Pic de <b>${d.src}</b> le ${d.day}. Voir <a href="./methods">Méthodes et provenance</a>.`,
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
