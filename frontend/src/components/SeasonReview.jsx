import { useCallback, useState } from "react";

import { api } from "../api.js";
import {
  POSITIONS,
  formatContractEnd,
  formatDiff,
  formatMoney,
  formatNote,
  formatRank,
  formatShortDate,
  formatSignedMoney,
} from "../format.js";
import { useApi } from "../hooks/useApi.js";
import Modal from "./Modal.jsx";
import { NOTE_LINES, NoteLine, formatChange, levelOf, startValue } from "./NoteLine.jsx";

const STEPS = ["Résultats", "Vie du club", "Contrats"];

// La fraîcheur se mesure avant chaque match : sans objet pour un bilan.
const REVIEW_NOTES = NOTE_LINES.filter((line) => line.key !== "freshness");

const PLAYOFFS = {
  champion: "Champion",
  final: "Finaliste",
  semi: "Demi-finaliste",
  barrage: "Éliminé en barrage",
  quarter: "Éliminé en quart de finale",
};

// Montée et descente entre la Pro D2 et le Top 14.
const MOVEMENTS = {
  promoted: "Champion de Pro D2 : le club monte en Top 14 la saison prochaine.",
  relegated: "Dernier du Top 14 : le club descend en Pro D2 la saison prochaine.",
};

// Bilan de fin de saison, en trois étapes : résultats, notes de vie du club, puis
// joueurs en fin de contrat (à prolonger, sinon ils partent libres). La dernière
// étape lance la saison suivante.
export default function SeasonReview({ clubId, onClose, onNextSeason, busy, error }) {
  const [step, setStep] = useState(0);
  const review = useApi(useCallback(api.getSeasonReview, []));
  const notes = useApi(useCallback(() => api.getClubNotes(clubId), [clubId]));
  const contracts = useApi(useCallback(api.getContracts, []));

  const loading = review.loading || notes.loading || contracts.loading;
  const failure = review.error || notes.error || contracts.error;
  const year = review.data?.year;

  return (
    <Modal onClose={onClose}>
      <div className="review__head">
        <div>
          <p className="eyebrow">Bilan de la saison {year ? `${year}-${String(year + 1).slice(2)}` : ""}</p>
          <h2 className="affair__title">{STEPS[step]}</h2>
        </div>
        <ol className="review__steps">
          {STEPS.map((label, index) => (
            <li key={label}>
              <button
                type="button"
                className="chip"
                aria-pressed={index === step}
                aria-current={index === step ? "step" : undefined}
                onClick={() => setStep(index)}
              >
                {index + 1}. {label}
              </button>
            </li>
          ))}
        </ol>
      </div>

      <div className="review__body">
        {loading && <p className="status">Chargement…</p>}
        {failure && <p className="status status--error">{failure.message}</p>}
        {!loading && !failure && step === 0 && <Results review={review.data} />}
        {!loading && !failure && step === 1 && <Notes notes={notes.data} />}
        {!loading && !failure && step === 2 && <Contracts data={contracts.data} onChange={contracts.setData} />}
      </div>

      {error && <p className="status--error">{error.message}</p>}
      <div className="affair__actions">
        {step === 2 && contracts.data && <SquadNext data={contracts.data} />}
        {step > 0 && (
          <button type="button" className="button" onClick={() => setStep(step - 1)}>
            Précédent
          </button>
        )}
        {step < STEPS.length - 1 ? (
          <button type="button" className="button button--primary" onClick={() => setStep(step + 1)}>
            {STEPS[step + 1]}
          </button>
        ) : (
          <button
            type="button"
            className="button button--primary"
            disabled={busy || !contracts.data || contracts.data.squad_next < contracts.data.squad_min}
            onClick={onNextSeason}
          >
            {busy ? "Intersaison…" : `Lancer la saison ${year + 1}`}
          </button>
        )}
      </div>
    </Modal>
  );
}

// --- 1. Résultats --------------------------------------------------------------------

function Results({ review }) {
  const headline = PLAYOFFS[review.playoffs] ?? `${formatRank(review.rank)} · hors phases finales`;
  const { objective } = review;
  return (
    <>
      <div className="review__hero">
        <p className="hero__title">{headline}</p>
        <p className="hero__sub">
          {formatRank(review.rank)} de la saison régulière · {review.league_points} points
          {review.playoffs !== "champion" && ` · Champion : ${review.champion.name}`}
        </p>
        {review.movement && <p className="hero__sub">{MOVEMENTS[review.movement]}</p>}
      </div>

      <dl className="review__stats">
        <Stat label="Bilan" value={`${review.won} V · ${review.drawn} N · ${review.lost} D`} />
        <Stat
          label="Points"
          value={`${review.points_for} – ${review.points_against}`}
          detail={`Différence ${formatDiff(review.points_for - review.points_against)}`}
        />
        <Stat label="Essais marqués" value={review.tries_for} />
        {objective && (
          <Stat
            label={`Objectif · ${objective.label.toLowerCase()}`}
            value={review.objective_met ? "Atteint" : "Manqué"}
            detail={`${formatRank(objective.target_rank)} au plus bas · ${formatRank(review.rank)} au final`}
            muted={!review.objective_met}
          />
        )}
        {review.youth_rank && <Stat label="Espoirs" value={formatRank(review.youth_rank)} detail="Championnat espoirs" />}
        <Stat
          label="Trésorerie"
          value={formatMoney(review.balance_end)}
          detail={`${formatSignedMoney(review.balance_end - review.balance_start)} sur la saison`}
        />
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
    </>
  );
}

function Stat({ label, value, detail, muted = false }) {
  return (
    <div className="review__stat">
      <dt className="muted">{label}</dt>
      <dd className={`num${muted ? " muted" : ""}`}>{value}</dd>
      {detail && <dd className="muted review__detail">{detail}</dd>}
    </div>
  );
}

// --- 2. Vie du club -------------------------------------------------------------------

function Notes({ notes }) {
  return (
    <div className="card card--padded">
      {REVIEW_NOTES.map((line) => {
        const note = notes[line.key];
        const start = startValue(note);
        const change = note.value - start;
        return (
          <div key={line.key} className="review__note">
            <NoteLine line={line} note={note} />
            <div className="review__change">
              <span className="muted">
                {formatNote(start)} → {formatNote(note.value)}
              </span>
              <span className={`num ${change < 0 ? "muted" : ""}`}>
                {Math.abs(change) < 0.05 ? "=" : formatChange(change)}
              </span>
              <span className="muted">
                {levelOf(line, start)} → {levelOf(line, note.value)}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// --- 3. Contrats ------------------------------------------------------------------------

function Contracts({ data, onChange }) {
  return (
    <div className="review__contracts">
      <ContractGroup
        title="Effectif pro"
        empty="Aucun pro en fin de contrat."
        items={data.pros}
        year={data.season_year}
        onChange={onChange}
      />
      <ContractGroup
        title="Espoirs"
        empty="Aucun espoir en fin de contrat."
        items={data.youths}
        year={data.season_year}
        onChange={onChange}
      />
    </div>
  );
}

function ContractGroup({ title, empty, items, year, onChange }) {
  return (
    <section className="review__group">
      <h3 className="eyebrow">
        {title} · {items.length}
      </h3>
      {items.length === 0 ? (
        <p className="muted">{empty}</p>
      ) : (
        <ul className="contract-list">
          {items.map((item) => (
            <ContractRow key={item.player.id} item={item} year={year} onChange={onChange} />
          ))}
        </ul>
      )}
    </section>
  );
}

function ContractRow({ item, year, onChange }) {
  const { player } = item;
  const [years, setYears] = useState(item.years_max ?? 1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function act(call) {
    setBusy(true);
    setError(null);
    try {
      onChange(await call());
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const extend = () => act(() => api.extendContract(player.id, Number(years)));
  // Un espoir qui passe pro sort de la liste des espoirs : on relit les contrats.
  const promote = () => act(() => api.promoteYouth(player.id).then(api.getContracts));

  return (
    <li className="contract">
      <div className="contract__who">
        <span className="contract__name">{player.name}</span>
        <span className="muted">
          {POSITIONS[player.position].label} · {player.age} ans · {formatNote(player.overall)}
          {item.playing_time !== "espoir" && ` · ${item.playing_time}`} · {formatMoney(player.wage)}/saison
        </span>
      </div>
      <div className="contract__what">
        {item.status === "open" && (
          <>
            <span className="muted">Demande {formatMoney(item.wage_demand)}/saison</span>
            <select
              className="input contract__years"
              aria-label={`Durée de la prolongation de ${player.name}`}
              value={years}
              onChange={(event) => setYears(event.target.value)}
            >
              {range(item.years_min, item.years_max).map((n) => (
                <option key={n} value={n}>
                  {n} saison{n > 1 ? "s" : ""} · jusqu'en {formatContractEnd(year + n)}
                </option>
              ))}
            </select>
            <button type="button" className="button button--small button--primary" disabled={busy} onClick={extend}>
              Prolonger
            </button>
          </>
        )}
        {item.status === "extended" && (
          <span>
            Prolongé jusqu'en {formatContractEnd(player.contract_until)} · {formatMoney(item.new_wage)}/saison
          </span>
        )}
        {item.status === "signed_elsewhere" && (
          <>
            <span className="tag tag--fragile">Signé ailleurs</span>
            <span className="muted">
              {item.new_club.name} · le {formatShortDate(item.signed_on)}
            </span>
          </>
        )}
        {item.status === "retiring" && <span className="muted">Prend sa retraite</span>}
        {item.status === "leaving_academy" && (
          <>
            <span className="muted">Trop âgé pour le centre</span>
            <button type="button" className="button button--small" disabled={busy} onClick={promote}>
              Passer pro
            </button>
          </>
        )}
      </div>
      {error && <p className="status--error contract__error">{error.message}</p>}
    </li>
  );
}

// Pros sous contrat la saison prochaine, au regard du minimum autorisé.
function SquadNext({ data }) {
  const short = data.squad_next < data.squad_min;
  const leaving = [...data.pros, ...data.youths].filter((item) => item.status === "open").length;
  return (
    <span className={short ? "club-note__warning" : "muted"}>
      {data.squad_next} pros sous contrat la saison prochaine (minimum {data.squad_min})
      {short
        ? " : prolonge, fais passer des espoirs pros ou recrute."
        : leaving > 0
          ? ` · sans prolongation, ${leaving > 1 ? `${leaving} joueurs partiront libres` : "1 joueur partira libre"}.`
          : "."}
    </span>
  );
}

const range = (low, high) => Array.from({ length: high - low + 1 }, (_, index) => low + index);
