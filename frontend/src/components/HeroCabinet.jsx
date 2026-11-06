import { useCallback } from "react";

import { api } from "../api.js";
import { AWARDS } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import ClubCrest from "./ClubCrest.jsx";

const seasonLabel = (year) => `${year}-${String(year + 1).slice(2)}`;
const plural = (n, word) => `${n} ${word}${n > 1 ? "s" : ""}`;

// Carrière de joueur, page Palmarès : sa vitrine. Ses chiffres, ses titres en club et en
// sélection, puis ses trophées individuels, du plus récent au plus ancien.
export default function HeroCabinet() {
  const career = useApi(useCallback(api.getHeroCareer, []));
  if (career.loading) return <section className="card panel">Chargement…</section>;
  if (career.error) return <section className="card panel table__note">{career.error.message}</section>;
  const data = career.data;
  const titles = [...data.titles].sort((a, b) => b.year - a.year);
  const awards = data.awards.filter((award) => award.kind !== "team");
  const teams = data.awards.filter((award) => award.kind === "team");

  return (
    <section className="card panel hero-cabinet">
      <div className="panel__head">
        <span className="eyebrow">Ton palmarès</span>
        <span className="muted">{plural(data.tries, "essai")}</span>
      </div>
      <dl className="hero-cabinet__counts">
        {[
          ["Titres", titles.length],
          ["Trophées", awards.length + teams.length],
          ["Matchs", data.matches],
          ["Sélections", data.caps],
        ].map(([label, value]) => (
          <div key={label}>
            <dt className="muted">{label}</dt>
            <dd className="num">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="panel__body">
        {titles.length === 0 && data.awards.length === 0 ? (
          <p className="table__note">
            Pas encore de titre. Un championnat, une coupe d'Europe ou un tournoi gagné avec ton équipe s'inscrit ici.
          </p>
        ) : (
          <ul className="hero-cabinet__list">
            {titles.map((title) => (
              <li key={`${title.year}-${title.competition}`} className="hero-cabinet__item hero-cabinet__item--title">
                <span className="hero-cabinet__icon" aria-hidden="true">
                  🏆
                </span>
                <span>
                  <strong>{title.competition}</strong>
                  <span className="muted"> · {seasonLabel(title.year)}</span>
                  <span className="hero-cabinet__with">
                    <ClubCrest name={title.club.name} size={16} />
                    {title.international ? `En sélection, avec ${title.club.name}` : `Avec ${title.club.name}`}
                  </span>
                </span>
              </li>
            ))}
            {[...awards, ...teams].map((award) => (
              <li key={`${award.year}-${award.kind}-${award.league_name}`} className="hero-cabinet__item">
                <span className="hero-cabinet__icon" aria-hidden="true">
                  🏅
                </span>
                <span>
                  <strong>{AWARDS[award.kind]?.label ?? award.kind}</strong>
                  <span className="muted"> · {seasonLabel(award.year)}</span>
                  <span className="hero-cabinet__with muted">
                    {award.league_name}
                    {AWARDS[award.kind] && ` · ${AWARDS[award.kind].format(award.value)}`}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
