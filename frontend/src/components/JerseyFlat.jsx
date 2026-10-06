import { useEffect, useId, useMemo, useState } from "react";

import { loadCrest, paintJersey, sleeveColor } from "../jersey.js";
import { useLogos } from "../hooks/useLogos.js";
import { placedLogos } from "../sponsors.js";

// Maillot à plat, de face ou de dos : la silhouette découpe le canevas de jersey.js
// (le devant ou le dos), les manches prennent leur couleur et la manchette celle du col.
// `sponsors` : les contrats et la bibliothèque (API), pour poser les logos. Sert à la
// carte « Maillots » et aux vignettes des motifs.

const crests = new Map(); // blason chargé une fois par club

function useCrest(clubName) {
  const [crest, setCrest] = useState(() => crests.get(clubName) ?? null);
  useEffect(() => {
    let cancelled = false;
    if (!crests.has(clubName)) crests.set(clubName, loadCrest(clubName));
    Promise.resolve(crests.get(clubName)).then((image) => {
      crests.set(clubName, image);
      if (!cancelled) setCrest(image);
    });
    return () => {
      cancelled = true;
    };
  }, [clubName]);
  return crest instanceof Promise ? null : crest;
}

const TORSO = "M47 8 Q60 17 73 8 L95 16 L94 104 Q60 109 26 104 L25 16 Z";
const SLEEVE_LEFT = "M25 16 L7 41 L19 50 L27 36 Z";
const SLEEVE_RIGHT = "M95 16 L113 41 L101 50 L93 36 Z";
const COLLAR = "M46 7.5 Q60 18 74 7.5 L71 5 Q60 13 49 5 Z";

export default function JerseyFlat({
  jersey,
  clubName,
  back = false,
  size = 120,
  details = true,
  title,
  sponsors = null,
}) {
  const id = `jersey${useId().replace(/[^a-zA-Z0-9]/g, "")}`; // utilisable dans url(#…)
  const crest = useCrest(clubName);
  const images = useLogos(details && sponsors ? sponsors.library : []);
  const logos = useMemo(
    () => (details && sponsors ? placedLogos(sponsors.deals, sponsors.library, images) : []),
    [details, sponsors, images],
  );
  const url = useMemo(() => {
    const canvas = document.createElement("canvas");
    paintJersey(canvas, jersey, { crest, clubName, marks: details, logos, scale: size > 80 ? 0.4 : 0.2 });
    return canvas.toDataURL();
  }, [jersey, crest, clubName, details, logos, size]);
  // Logo de manche : sur la manche gauche du joueur (à droite vu de face).
  const sleeveLogo = logos.find((logo) => logo.placement === "sleeve");

  // Manche de gauche et de droite de l'image : est-ce le côté droit du maillot vu de
  // face ? De dos, les côtés s'inversent.
  const [left, right] = back ? [true, false] : [false, true];
  const outline = { fill: "none", stroke: "rgba(22,24,27,0.22)", strokeWidth: 0.8, strokeLinejoin: "round" };
  return (
    <svg
      className="jersey-flat"
      viewBox="0 0 120 112"
      width={size}
      height={(size * 112) / 120}
      role="img"
      aria-label={title ?? (back ? "Maillot de dos" : "Maillot de face")}
    >
      <defs>
        <clipPath id={`${id}torso`}>
          <path d={TORSO} />
        </clipPath>
      </defs>
      {[
        [SLEEVE_LEFT, left, "M7 41 L19 50", -13],
        [SLEEVE_RIGHT, right, "M113 41 L101 50", 97],
      ].map(([path, isRight, cuff, logoX]) => (
        <g key={path}>
          <path d={path} fill={sleeveColor(jersey, isRight)} />
          <path d={cuff} stroke={jersey.trim} strokeWidth="3.2" />
          {sleeveLogo && isRight && (
            <image
              href={sleeveLogo.image.src}
              x={logoX}
              y={27}
              width={26}
              height={6.5}
              transform={`rotate(${back ? -36 : 36} ${logoX + 13} 30)`}
            />
          )}
          <path d={path} {...outline} />
        </g>
      ))}
      <image
        href={url}
        x={back ? -45 : 25}
        y={6}
        width={140}
        height={100}
        preserveAspectRatio="none"
        clipPath={`url(#${id}torso)`}
      />
      <path d={TORSO} {...outline} />
      <path d={COLLAR} fill={jersey.trim} />
      <path d={COLLAR} {...outline} />
    </svg>
  );
}
