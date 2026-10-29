import { useCallback } from "react";

import { api } from "../api.js";
import { formatDiff, formatRank } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { ActionError } from "./FullGame.jsx";
import Modal from "./Modal.jsx";
import { Stat } from "./SeasonReview.jsx";

// Coupe du monde : le tour atteint ; un tournoi gagné (backend/api/routers/selection.py).
const RESULTS = {
  champion: "Vainqueur",
  final: "Finaliste",
  semi: "Demi-finaliste",
  quarter: "Quart de finaliste",
  pools: "Éliminé en poules",
};

// Bilan de la saison du sélectionneur : son bilan, chaque compétition jouée (classement
// ou tour atteint), ses meilleurs marqueurs et ses joueurs les plus titularisés. Puis la
// saison suivante.
export default function SelectionReview({ onClose, onNextSeason, busy, error }) {
  const review = useApi(useCallback(api.getSelectionReview, []));
  const data = review.data;

  return (
    <Modal onClose={onClose}>
      <div className="review__head">
        <div>
          <p className="eyebrow">Bilan de la saison {data ? `${data.year}-${String(data.year + 1).slice(2)}` : ""}</p>
          <h2 className="affair__title">{data ? data.nation.name : "Résultats"}</h2>
        </div>
      </div>

      <div className="review__body">
        {review.loading && <p className="status">Chargement…</p>}
        {review.error && <p className="status status--error">{review.error.message}</p>}
        {data && <Results review={data} />}
      </div>

      <ActionError error={error} />
      <div className="affair__actions">
        <button type="button" className="button" onClick={onClose}>
          Fermer
        </button>
        {data && (
          <button type="button" className="button button--primary" disabled={busy} onClick={onNextSeason}>
            {busy ? "Intersaison…" : `Lancer la saison ${data.year + 1}`}
          </button>
        )}
      </div>
    </Modal>
  );
}

function Results({ review }) {
  const { record } = review;
  const titles = review.competitions.filter((run) => run.result === "champion");
  // Sans titre : la place dans la première compétition à classement.
  const main = review.competitions.find((run) => run.rank !== null);
  return (
    <>
      <div className="review__hero">
        <p className="hero__title">
          {titles.length > 0
            ? `Vainqueur · ${titles.map((run) => run.name).join(" · ")}`
            : main
              ? `${main.name} · ${runValue(main)}`
              : `${record.won} V · ${record.drawn} N · ${record.lost} D`}
        </p>
        <p className="hero__sub">
          {record.played} test{record.played > 1 ? "s" : ""} joué{record.played > 1 ? "s" : ""} ·{" "}
          {record.won} victoire{record.won > 1 ? "s" : ""}
        </p>
      </div>

      <dl className="review__stats">
        <Stat label="Bilan" value={`${record.won} V · ${record.drawn} N · ${record.lost} D`} />
        <Stat
          label="Points"
          value={`${review.points_for} – ${review.points_against}`}
          detail={`Différence ${formatDiff(review.points_for - review.points_against)}`}
        />
        <Stat label="Essais marqués" value={review.tries_for} />
        {review.competitions.map((run) => (
          <Stat
            key={run.code}
            label={run.name}
            value={runValue(run)}
            detail={[
              `${run.won} V · ${run.drawn} N · ${run.lost} D`,
              run.result !== "champion" && run.champion && `Vainqueur : ${run.champion.name}`,
            ]
              .filter(Boolean)
              .join(" · ")}
            muted={run.result === "pools"}
          />
        ))}
      </dl>

      {review.scorers.length > 0 && (
        <section>
          <h3 className="eyebrow">Meilleurs marqueurs</h3>
          <ol className="review__scorers">
            {review.scorers.map((scorer) => (
              <li key={scorer.player_id}>
                <span>{scorer.name}</span>
                <span className="muted">
                  {scorer.tries} essai{scorer.tries > 1 ? "s" : ""}
                </span>
                <span className="num">{scorer.points} pts</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {review.caps.length > 0 && (
        <section>
          <h3 className="eyebrow">Les plus titularisés</h3>
          <ol className="review__scorers">
            {review.caps.map((cap) => (
              <li key={cap.player_id}>
                <span>{cap.name}</span>
                <span />
                <span className="num">{cap.starts}</span>
              </li>
            ))}
          </ol>
        </section>
      )}
    </>
  );
}

// « Vainqueur », « 2e sur 4 », « Quart de finaliste », « Éliminé en poules · 3e de
// poule » ; une tournée sans classement : « 3 victoires sur 3 ».
function runValue(run) {
  if (run.rank === null) {
    const played = run.won + run.drawn + run.lost;
    return `${run.won} victoire${run.won > 1 ? "s" : ""} sur ${played}`;
  }
  const place = `${formatRank(run.rank)} ${run.code === "world_cup" ? "de poule" : `sur ${run.teams}`}`;
  if (run.code === "world_cup") return run.result === "pools" ? `Éliminé en poules · ${place}` : RESULTS[run.result];
  return run.result === "champion" ? RESULTS.champion : place;
}
