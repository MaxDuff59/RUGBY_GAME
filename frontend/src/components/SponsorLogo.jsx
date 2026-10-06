import { logoUrl } from "../sponsors.js";

// Logo d'un sponsor, en vignette : la forme et le pictogramme, puis le nom.
// `plate` : sur son fond plein, comme sur le maillot.
export default function SponsorLogo({ sponsor, height = 24, plate = false, className = "" }) {
  return (
    <img
      className={`sponsor-logo ${className}`}
      src={logoUrl(sponsor, { plate })}
      alt={sponsor.name}
      style={{ height, width: height * 4 }}
    />
  );
}
