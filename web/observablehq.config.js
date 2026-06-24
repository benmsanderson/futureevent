// Observable Framework configuration for the future-climate rarity frontend.
export default {
  title: "Heat in a warming climate",
  root: "src",
  pages: [
    {name: "France: June 2026 heat", path: "/index"},
    {name: "Methods and provenance", path: "/methods"}
  ],
  // A single static event page for v1; expandable to a region menu (tier 2).
  toc: false,
  pager: false,
  header: "",
  footer:
    "Contextualization, not attribution. Built from ERA5 (Copernicus) and " +
    "CMIP6. See Methods and provenance.",
  style: "style.css"
};
