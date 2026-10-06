// Logos des sponsors du maillot (engine/sponsors.py côté serveur) : des marques
// inventées, dont le logo est dessiné ici à partir de sa fiche `logo` (forme, fond,
// encre, pictogramme) et de son nom. Le même SVG sert de vignette dans l'interface
// (`SponsorLogo`) et d'image à poser sur le maillot (`loadLogos`, pour les canevas).

// Un logo tient dans ce cadre : la forme avec son pictogramme à gauche, le nom à droite.
export const LOGO_WIDTH = 320;
export const LOGO_HEIGHT = 80;

export const PLACEMENTS = ["chest", "back", "sleeve", "belly"];

// Pictogrammes : tracés dans un carré de 0 à 24.
const GLYPHS = {
  coin: "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18zm0 3a6 6 0 1 1 0 12a6 6 0 0 1 0-12zm-1 3h2v2h1.5v1.5H13v1h1.5V15H13v2h-2v-2H9.5v-1.5H11v-1H9.5V10.5H11z",
  bolt: "M13 2L4 14h6l-1 8l9-12h-6z",
  hop: "M12 2c3 2 5 5 5 9s-2 7-5 11c-3-4-5-7-5-11s2-7 5-9zm0 4c-1.5 1.5-2.5 3-2.5 5s1 4 2.5 6.5c1.5-2.5 2.5-4.5 2.5-6.5s-1-3.5-2.5-5z",
  dice: "M4 4h16v16H4zm3.5 3a1.5 1.5 0 1 0 0 3a1.5 1.5 0 0 0 0-3zm9 0a1.5 1.5 0 1 0 0 3a1.5 1.5 0 0 0 0-3zM12 10.5a1.5 1.5 0 1 0 0 3a1.5 1.5 0 0 0 0-3zM7.5 14a1.5 1.5 0 1 0 0 3a1.5 1.5 0 0 0 0-3zm9 0a1.5 1.5 0 1 0 0 3a1.5 1.5 0 0 0 0-3z",
  flame: "M12 2c1 4 5 6 5 11a5 5 0 0 1-10 0c0-2 1-3 2-4c0 2 1 3 2 3c0-3-1-6 1-10z",
  chip: "M7 7h10v10H7zm2 2v6h6V9zM4 9h2v2H4zm0 4h2v2H4zm14-4h2v2h-2zm0 4h2v2h-2zM9 4h2v2H9zm4 0h2v2h-2zM9 18h2v2H9zm4 0h2v2h-2z",
  crown: "M3 8l5 4l4-7l4 7l5-4l-2 11H5zM5 20h14v1.5H5z",
  shield: "M12 2l8 3v6c0 5-3.5 9-8 11c-4.5-2-8-6-8-11V5zm0 3L7 6.8V11c0 3.5 2 6.5 5 8.2c3-1.7 5-4.7 5-8.2V6.8z",
  pot: "M3 9h18l-1 2h-1l-1.5 9h-11L5 11H4zM8 5h8v2H8z",
  plane: "M21 12l-8-2V4.5a1 1 0 0 0-2 0V10l-8 2v2l8-1.5V18l-2.5 1.5V21l3.5-1l3.5 1v-1.5L13 18v-5.5l8 1.5z",
  wheat: "M12 2v20h-1V2zm-1 3c-2 0-3.5 1.5-3.5 3.5c2 0 3.5-1.5 3.5-3.5zm1 0c0 2 1.5 3.5 3.5 3.5C15.5 6.5 14 5 12 5zm-1 5c-2 0-3.5 1.5-3.5 3.5c2 0 3.5-1.5 3.5-3.5zm1 0c0 2 1.5 3.5 3.5 3.5c0-2-1.5-3.5-3.5-3.5zm-1 5c-2 0-3.5 1.5-3.5 3.5c2 0 3.5-1.5 3.5-3.5zm1 0c0 2 1.5 3.5 3.5 3.5c0-2-1.5-3.5-3.5-3.5z",
  wheel: "M12 2a10 10 0 1 0 0 20a10 10 0 0 0 0-20zm0 2.5a7.5 7.5 0 1 1 0 15a7.5 7.5 0 0 1 0-15zM11 5h2v6h-2zm0 8h2v6h-2zM5 11h6v2H5zm8 0h6v2h-6z",
  drop: "M12 2c4 5 7 8.5 7 12.5a7 7 0 0 1-14 0C5 10.5 8 7 12 2zm0 4.5c-2.5 3.5-4.5 6-4.5 8a4.5 4.5 0 0 0 9 0c0-2-2-4.5-4.5-8z",
  wave: "M2 13c2.5 0 2.5-3 5-3s2.5 3 5 3s2.5-3 5-3s2.5 3 5 3v2c-2.5 0-2.5-3-5-3s-2.5 3-5 3s-2.5-3-5-3s-2.5 3-5 3zm0-6c2.5 0 2.5-3 5-3s2.5 3 5 3s2.5-3 5-3s2.5 3 5 3v2c-2.5 0-2.5-3-5-3s-2.5 3-5 3s-2.5-3-5-3s-2.5 3-5 3z",
  cross: "M9 3h6v6h6v6h-6v6H9v-6H3V9h6z",
  wrench: "M21 6.5a5 5 0 0 1-6.5 4.8L7 18.8a2 2 0 0 1-2.8-2.8l7.5-7.5A5 5 0 0 1 17.5 2l-2.8 2.8l1.2 2.3l2.3 1.2z",
};

const SHAPES = {
  disc: "M40 8a32 32 0 1 0 0 64a32 32 0 0 0 0-64z",
  square: "M12 12h56v56H12z",
  pill: "M24 12h32a16 16 0 0 1 0 32H24a16 16 0 0 1 0-32z",
  hex: "M40 6l30 17v34L40 74L10 57V23z",
  shield: "M40 6l30 8v24c0 16-12 28-30 36C22 66 10 54 10 38V14z",
  diamond: "M40 6l34 34l-34 34L6 40z",
};

// Le nom d'une marque, découpé sur deux lignes s'il est long.
function nameLines(name) {
  if (name.length <= 12) return [name];
  const words = name.split(" ");
  let first = "";
  while (words.length > 1 && (first + " " + words[0]).trim().length <= name.length / 2 + 2) {
    first = (first + " " + words.shift()).trim();
  }
  return first ? [first, words.join(" ")] : [name];
}

function escape(text) {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
}

// Le SVG d'un logo : forme et pictogramme à gauche (toujours à la même place), le nom
// en capitales condensées à droite. `plate` : sur un fond plein (patch cousu sur le
// maillot), sinon sur rien (vignettes de l'interface).
export function logoSvg(sponsor, { plate = false } = {}) {
  const { shape, bg, fg, glyph } = sponsor.logo;
  const lines = nameLines(sponsor.name);
  const size = lines.length > 1 ? 26 : 30;
  const text = lines
    .map((line, i) => {
      const y = lines.length > 1 ? 36 + i * 26 : 50;
      return `<text x="92" y="${y}" font-family="'Barlow Condensed','Arial Narrow',sans-serif" font-weight="700" font-size="${size}" fill="${plate ? fg : "#16181B"}" letter-spacing="1" textLength="${Math.min(216, line.length * size * 0.56)}" lengthAdjust="spacingAndGlyphs">${escape(line.toUpperCase())}</text>`;
    })
    .join("");
  // Le pictogramme est tracé dans un carré de 24, centré dans la forme (80 × 80).
  const pictogram = `<path transform="translate(22 22) scale(1.5)" d="${GLYPHS[glyph] ?? GLYPHS.coin}" fill="${plate ? bg : fg}" />`;
  const plateRect = plate ? `<rect width="${LOGO_WIDTH}" height="${LOGO_HEIGHT}" rx="10" fill="${bg}" />` : "";
  const shapePath = `<path d="${SHAPES[shape] ?? SHAPES.disc}" fill="${plate ? fg : bg}" />`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${LOGO_WIDTH} ${LOGO_HEIGHT}" width="${LOGO_WIDTH}" height="${LOGO_HEIGHT}">${plateRect}${shapePath}${pictogram}${text}</svg>`;
}

export function logoUrl(sponsor, options) {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(logoSvg(sponsor, options))}`;
}

// Images des logos à poser sur le maillot, par identifiant de sponsor (chargées une fois).
const images = new Map();

export function loadLogos(sponsors) {
  return Promise.all(
    sponsors.map((sponsor) => {
      if (!images.has(sponsor.id)) {
        images.set(
          sponsor.id,
          new Promise((resolve) => {
            const image = new Image();
            image.onload = () => resolve(image);
            image.onerror = () => resolve(null);
            image.src = logoUrl(sponsor, { plate: true });
          }),
        );
      }
      return images.get(sponsor.id).then((image) => [sponsor.id, image]);
    }),
  ).then((entries) => new Map(entries));
}

// Les logos des contrats en cours, avec leur emplacement : [{ placement, image }].
// Les polices SVG dans une image ne sont pas celles de la page : le nom est en
// Arial Narrow ou équivalent, ce qui va bien à un patch cousu.
export function placedLogos(deals, library, logoImages) {
  const byId = new Map(library.map((s) => [s.id, s]));
  return deals
    .map((deal) => ({ placement: deal.placement, image: logoImages?.get(deal.sponsor) ?? null, sponsor: byId.get(deal.sponsor) }))
    .filter((item) => item.image && item.sponsor);
}
