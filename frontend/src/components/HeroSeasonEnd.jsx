import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api.js";
import { AGENTS, AWARDS, OFFER_KINDS, OFFER_ROLES, formatMoney, formatNote } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import ClubCrest from "./ClubCrest.jsx";
import { ActionError } from "./FullGame.jsx";
import Modal from "./Modal.jsx";
import WorldAwards from "./WorldAwards.jsx";
import { Stat } from "./SeasonReview.jsx";

const plural = (n, word) => `${n} ${word}${n > 1 ? "s" : ""}`;
const seasonLabel = (year) => `${year}-${String(year + 1).slice(2)}`;

// Carrière de joueur, au bilan de chaque saison : ce que la saison a donné, puis son
// avenir (prolonger, partir, être prêté ; l'agent qui négocie pour lui), la saison
// suivante, ou la retraite. Après la retraite, le bilan de toute la carrière, et de quoi
// enchaîner sur une carrière d'entraîneur dans le même monde.
export default function HeroSeasonEnd({ name, playerId, onClose, onNextSeason, busy, error }) {
  const [view, setView] = useState("season"); // sa saison, ou les trophées du monde
  const navigate = useNavigate();
  const career = useApi(useCallback(api.getHeroCareer, []));
  const offers = useApi(useCallback(api.getHeroOffers, []));
  const [acting, setActing] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [retired, setRetired] = useState(null); // le bilan renvoyé par la retraite
  const [confirmRetire, setConfirmRetire] = useState(false);

  async function act(call, apply) {
    setActing(true);
    setActionError(null);
    try {
      apply(await call());
    } catch (err) {
      setActionError(err);
    } finally {
      setActing(false);
    }
  }

  const choose = (index) => act(() => api.chooseHeroOffer(index), offers.setData);
  const applyTo = (clubId) => act(() => api.applyHeroClub(clubId), offers.setData);
  const setAgent = (agent) => act(() => api.setHeroAgent(agent), offers.setData);
  const retire = () => act(api.retireHero, setRetired);

  if (retired) {
    return (
      <Modal onClose={() => navigate("/parties")}>
        <div className="review__head">
          <div>
            <p className="eyebrow">Fin de carrière</p>
            <h2 className="affair__title">{name} raccroche</h2>
          </div>
        </div>
        <div className="review__body">
          <CareerSummary career={retired} />
        </div>
        <div className="affair__actions">
          <span className="muted">Le monde continue sans toi : tu peux y revenir sur le banc.</span>
          <button type="button" className="button" onClick={() => navigate("/parties")}>
            Retour aux parties
          </button>
          <button
            type="button"
            className="button button--primary"
            onClick={() => navigate("/start", { state: { managerName: name } })}
          >
            Devenir entraîneur
          </button>
        </div>
      </Modal>
    );
  }

  const data = career.data;
  const season = data?.seasons[0];
  const titles = data?.titles.filter((title) => title.year === season?.year) ?? [];
  const awards = data?.awards.filter((award) => award.year === season?.year) ?? [];
  const market = offers.data;

  return (
    <Modal onClose={onClose}>
      <div className="review__head">
        <div>
          <p className="eyebrow">Bilan de la saison {season ? seasonLabel(season.year) : ""}</p>
          <h2 className="affair__title">{view === "world" ? "Trophées du monde" : name}</h2>
        </div>
        <ReviewTabs view={view} onChange={setView} first="Ta saison" />
      </div>

      <div className="review__body">
        {view === "world" ? (
          <WorldAwards isOurs={(award) => award.player_id === playerId} />
        ) : (
          <>
        {(career.loading || offers.loading) && <p className="status">Chargement…</p>}
        {data &&
          (season ? (
            <dl className="review__stats">
              <Stat label="Matchs" value={season.matches} detail={plural(season.starts, "titularisation")} />
              <Stat label="Essais" value={season.tries} />
              <Stat
                label="Moyenne"
                value={formatNote(season.average ?? 6)}
                detail={`meilleure note ${formatNote(season.best ?? 6)}`}
              />
              <Stat label="Sélections" value={data.caps} detail="en carrière" />
            </dl>
          ) : (
            <p className="muted">Pas un match joué cette saison.</p>
          ))}
        {(titles.length > 0 || awards.length > 0) && (
          <ul className="hero-honours">
            {titles.map((title) => (
              <li key={`${title.competition}-${title.year}`}>
                🏆 {title.competition} avec {title.club.name}
              </li>
            ))}
            {awards.map((award) => (
              <li key={`${award.kind}-${award.league_name}`}>
                🏅 {AWARDS[award.kind]?.label ?? award.kind} · {award.league_name}
              </li>
            ))}
          </ul>
        )}

        {market && (
          <section className="section">
            <div className="section__head">
              <h3 className="eyebrow">Ton avenir</h3>
              <span className="muted">
                Aujourd'hui : {formatMoney(market.wage)} par an, contrat jusqu'en {market.contract_until + 1}
              </span>
            </div>
            <div className="chips" role="group" aria-label="Agent">
              {Object.entries(AGENTS).map(([key, agent]) => (
                <button
                  key={key}
                  type="button"
                  className="chip"
                  aria-pressed={market.agent === key}
                  disabled={acting}
                  onClick={() => setAgent(key)}
                >
                  {agent.label}
                </button>
              ))}
            </div>
            <span className="muted">{AGENTS[market.agent].scope}</span>
            <h4 className="eyebrow">Les trois meilleures offres</h4>
            <ul className="hero-offers">
              {market.offers.map((offer) => (
                <li key={offer.index}>
                  <button
                    type="button"
                    className="club-option hero-offer"
                    aria-pressed={offer.chosen}
                    disabled={acting}
                    onClick={() => choose(offer.chosen ? null : offer.index)}
                  >
                    <span className="eyebrow">{OFFER_KINDS[offer.kind]}</span>
                    <span className="club-option__name with-crest">
                      <ClubCrest name={offer.club.name} size={28} />
                      {offer.club.name}
                    </span>
                    <span>
                      {offer.league_name} · niveau {formatNote(offer.level)} · {OFFER_ROLES[offer.role]}
                    </span>
                    <span className="num">
                      {formatMoney(offer.net_wage)} net par an
                      {offer.kind !== "loan" && ` · ${plural(offer.years, "saison")}`}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            <span className="muted">
              {[...market.offers, ...market.clubs].some((offer) => offer.chosen)
                ? "Ton choix s'applique à l'intersaison. Clique de nouveau pour l'annuler."
                : "Sans choix, tu restes dans ton club aux mêmes conditions."}
            </span>
            {market.clubs.length > 0 && (
              <AllClubs clubs={market.clubs} disabled={acting} onApply={applyTo} onCancel={() => choose(null)} />
            )}
          </section>
        )}
          </>
        )}
      </div>

      <ActionError error={actionError ?? error} />
      <div className="affair__actions">
        {confirmRetire ? (
          <>
            <span className="muted">Raccrocher met fin à ta carrière de joueur, pour de bon.</span>
            <button type="button" className="button" onClick={() => setConfirmRetire(false)}>
              Continuer à jouer
            </button>
            <button type="button" className="button button--primary" disabled={acting} onClick={retire}>
              Raccrocher
            </button>
          </>
        ) : (
          <>
            <button type="button" className="button" onClick={() => setConfirmRetire(true)}>
              Prendre ta retraite
            </button>
            <button type="button" className="button" onClick={onClose}>
              Fermer
            </button>
            <button type="button" className="button button--primary" disabled={busy || acting} onClick={onNextSeason}>
              {busy ? "Intersaison…" : "Lancer la saison suivante"}
            </button>
          </>
        )}
      </div>
    </Modal>
  );
}

// Tous les clubs du jeu, du plus fort au plus faible : il peut se proposer à ceux qui
// sont à sa portée (même un petit club qui ne l'a pas appelé) ; les autres sont grisés.
function AllClubs({ clubs, disabled, onApply, onCancel }) {
  const leagues = [...new Set(clubs.map((club) => club.league_name))];
  const [league, setLeague] = useState(null);
  const shown = league ? clubs.filter((club) => club.league_name === league) : clubs;
  const reachable = clubs.filter((club) => club.open).length;
  return (
    <>
      <div className="section__head">
        <h4 className="eyebrow">Tous les clubs</h4>
        <span className="muted">
          {reachable} sur {clubs.length} à ta portée : propose-toi à celui que tu veux
        </span>
      </div>
      {leagues.length > 1 && (
        <div className="chips" role="group" aria-label="Championnat">
          {[null, ...leagues].map((key) => (
            <button
              key={key ?? "all"}
              type="button"
              className="chip"
              aria-pressed={league === key}
              onClick={() => setLeague(key)}
            >
              {key ?? "Tous"}
            </button>
          ))}
        </div>
      )}
      <ul className="hero-clubs">
        {shown.map((club) => (
          <li key={club.club.id}>
            <button
              type="button"
              className="hero-club"
              aria-pressed={club.chosen}
              disabled={disabled || !club.open}
              title={club.open ? undefined : "Ce club vise plus haut que ton niveau"}
              onClick={() => (club.chosen ? onCancel() : onApply(club.club.id))}
            >
              <ClubCrest name={club.club.name} size={22} />
              <span className="hero-club__name">{club.club.name}</span>
              <span className="muted">
                {club.league_name} · niveau {formatNote(club.level)}
              </span>
              <span className="num">
                {club.open ? `${formatMoney(club.net_wage)} net` : "Hors de portée"}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}

// Toute la carrière : les chiffres, les titres et trophées, puis saison par saison.
export function CareerSummary({ career }) {
  return (
    <>
      <dl className="review__stats">
        <Stat label="Matchs" value={career.matches} />
        <Stat label="Essais" value={career.tries} />
        <Stat label="Moyenne" value={career.average !== null ? formatNote(career.average) : "–"} />
        <Stat label="Meilleure note" value={career.best !== null ? formatNote(career.best) : "–"} />
        <Stat label="Sélections" value={career.caps} />
      </dl>
      {(career.titles.length > 0 || career.awards.length > 0) && (
        <ul className="hero-honours">
          {career.titles.map((title) => (
            <li key={`${title.competition}-${title.year}`}>
              🏆 {title.competition} {seasonLabel(title.year)} avec {title.club.name}
            </li>
          ))}
          {career.awards.map((award) => (
            <li key={`${award.kind}-${award.league_name}-${award.year}`}>
              🏅 {AWARDS[award.kind]?.label ?? award.kind} {seasonLabel(award.year)} · {award.league_name}
            </li>
          ))}
        </ul>
      )}
      <table className="table table--nowrap">
        <thead>
          <tr>
            <th scope="col" className="left">
              Saison
            </th>
            <th scope="col" className="left">
              Club
            </th>
            <th scope="col">Matchs</th>
            <th scope="col">Essais</th>
            <th scope="col">Moyenne</th>
          </tr>
        </thead>
        <tbody>
          {career.seasons.map((season) => (
            <tr key={season.year}>
              <td className="left muted">{seasonLabel(season.year)}</td>
              <td className="left">{season.clubs.map((club) => club.name).join(", ")}</td>
              <td className="num">{season.matches}</td>
              <td className="num">{season.tries}</td>
              <td className="note">{season.average !== null ? formatNote(season.average) : "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

// Les deux pages d'un bilan : sa saison, puis les trophées mondiaux de la saison.
export function ReviewTabs({ view, onChange, first }) {
  return (
    <ol className="review__steps">
      {[
        ["season", first],
        ["world", "Trophées du monde"],
      ].map(([key, label], index) => (
        <li key={key}>
          <button
            type="button"
            className="chip"
            aria-pressed={view === key}
            aria-current={view === key ? "step" : undefined}
            onClick={() => onChange(key)}
          >
            {index + 1}. {label}
          </button>
        </li>
      ))}
    </ol>
  );
}
