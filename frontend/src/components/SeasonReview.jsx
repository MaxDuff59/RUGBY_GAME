import { useCallback, useState } from "react";

import { api } from "../api.js";
import { ActionError } from "./FullGame.jsx";
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
import ClubCrest from "./ClubCrest.jsx";
import { useConfirm } from "./ConfirmDialog.jsx";
import ManagerContract from "./ManagerContract.jsx";
import Modal from "./Modal.jsx";
import { NOTE_LINES, NoteLine, formatChange, levelOf, startValue } from "./NoteLine.jsx";

const STEPS = ["Résultats", "Vie du club", "Carrière", "Contrats"];
const CONTRACTS = STEPS.length - 1;

// La fraîcheur se mesure avant chaque match : sans objet pour un bilan.
const REVIEW_NOTES = NOTE_LINES.filter((line) => line.key !== "freshness");

const PLAYOFFS = {
  champion: "Champion",
  final: "Finaliste",
  semi: "Demi-finaliste",
  barrage: "Éliminé en barrage",
  quarter: "Éliminé en quart de finale",
};

// Le parcours en coupe d'Europe (api/cup.py, `runs`).
const CUP_RESULTS = {
  champion: "Vainqueur",
  final: "Finaliste",
  semi: "Demi-finaliste",
  quarter: "Quart de finaliste",
  pools: "Éliminé en poules",
  running: "En course",
};

// Montée et descente entre la Pro D2 et le Top 14.
const MOVEMENTS = {
  promoted: "Champion de Pro D2 : le club monte en Top 14 la saison prochaine.",
  relegated: "Dernier du Top 14 : le club descend en Pro D2 la saison prochaine.",
};

// Bilan de fin de saison, en quatre étapes : résultats, notes de vie du club, carrière
// du manager (son contrat, sa réputation, et les clubs ou sélections qui le veulent),
// puis joueurs en fin de contrat (à prolonger, sinon ils partent libres). La dernière
// étape lance la saison suivante, sauf si le contrat du manager s'achève sans suite ;
// accepter une offre recharge le jeu dans le nouveau club, au début de la saison suivante.
export default function SeasonReview({ clubId, onClose, onNextSeason, onContract, busy, error }) {
  const [step, setStep] = useState(0);
  const review = useApi(useCallback(api.getSeasonReview, []));
  const notes = useApi(useCallback(() => api.getClubNotes(clubId), [clubId]));
  const contracts = useApi(useCallback(api.getContracts, []));
  const career = useApi(useCallback(api.getCareerHistory, []));
  const contract = useApi(useCallback(api.getManagerContract, []));

  const loading = review.loading || notes.loading || contracts.loading || career.loading || contract.loading;
  const failure = review.error || notes.error || contracts.error || career.error || contract.error;
  const unsettled = contract.data?.expiring ?? false;
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
        {!loading && !failure && step === 2 && (
          <Career
            data={career.data}
            clubName={review.data.club.name}
            year={year}
            contract={contract.data}
            onContract={(next) => {
              contract.setData(next);
              onContract?.(next);
            }}
          />
        )}
        {!loading && !failure && step === CONTRACTS && <Contracts data={contracts.data} onChange={contracts.setData} />}
      </div>

      <ActionError error={error} />
      <div className="affair__actions">
        {step === CONTRACTS && unsettled && (
          <span className="club-note__warning">
            Ton contrat s'achève : prolonge, signe ailleurs ou pars (étape Carrière).
          </span>
        )}
        {step === CONTRACTS && !unsettled && contracts.data && <SquadNext data={contracts.data} />}
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
            disabled={busy || unsettled || !contracts.data || contracts.data.squad_next < contracts.data.squad_min}
            onClick={onNextSeason}
          >
            {busy ? "Intersaison…" : `Lancer la saison ${year + 1}`}
          </button>
        )}
      </div>
    </Modal>
  );
}

// --- 3. Carrière ------------------------------------------------------------------------

// Le contrat du manager, sa réputation, et les clubs (ou la sélection) qui le veulent ;
// accepter l'offre d'un club joue l'intersaison (réglée par son staff) et recharge le jeu.
function Career({ data, clubName, year, contract, onContract }) {
  const confirm = useConfirm();
  const [error, setError] = useState(null);

  function accept(offer) {
    const nation = offer.kind === "nation";
    const rows = [{ label: "Niveau du XV", value: formatNote(offer.level), hint: "sur 20" }];
    if (offer.balance !== null) rows.push({ label: "Trésorerie", value: formatMoney(offer.balance) });
    if (offer.seasons) rows.push({ label: "Contrat", value: `${offer.seasons} saisons`, hint: "à partir de la prochaine" });
    if (offer.indemnity > 0) {
      rows.push({
        label: "Indemnité",
        value: formatMoney(offer.indemnity),
        hint: nation ? `versée à ${clubName} par la fédération` : `versée à ${clubName} par ton nouveau club`,
      });
    }
    confirm.ask({
      eyebrow: `Offre · ${offer.league_name}`,
      title: nation ? `Sélectionneur : ${offer.club.name}` : `Rejoindre ${offer.club.name}`,
      text: nation
        ? `Tu quittes ${clubName} dès maintenant pour diriger ${offer.club.name} : plus de club à gérer, une liste à annoncer avant chaque rendez-vous. Tes négociations en cours tombent.`
        : `Tu quittes ${clubName} dès maintenant et arrives à ${offer.club.name} pour lancer la saison ${year + 1} : son staff règle l'intersaison (contrats, espoirs, recrues). Tes négociations en cours tombent.`,
      rows,
      confirmLabel: "Accepter l'offre",
      onConfirm: async () => {
        try {
          await (nation ? api.acceptNationOffer(offer.nation) : api.acceptOffer(offer.club.id));
          window.location.assign("/");
        } catch (err) {
          setError(err);
        }
      },
    });
  }

  const seasons = data.seasons.filter((s) => s.rank !== null).length;
  const titles = data.seasons.filter((s) => s.champion).length;
  return (
    <>
      {confirm.dialog}
      <section>
        <h3 className="eyebrow">Mon contrat</h3>
        <ManagerContract contract={contract} onChange={onContract} />
      </section>
      <div className="review__hero">
        <p className="hero__title">{data.label}</p>
        <p className="hero__sub">
          Réputation {Math.round(data.reputation)} / 100 · {seasons} saison{seasons > 1 ? "s" : ""} · {titles} titre
          {titles > 1 ? "s" : ""}
        </p>
      </div>
      {error && <p className="status--error">{error.message}</p>}
      {data.offers.length === 0 ? (
        <p className="muted">
          Aucun club plus prestigieux ne t'a appelé cette saison. Les titres, les phases finales et un classement
          meilleur qu'attendu font grimper la réputation ; un limogeage la ruine. Les sélections, elles, n'appellent
          que les managers reconnus.
        </p>
      ) : (
        <ul className="career-offers">
          {data.offers.map((offer) => (
            <li key={`${offer.kind}-${offer.club.id}`} className="career-offer">
              <ClubCrest name={offer.club.name} size={40} />
              <div>
                <p className="career-offer__name">{offer.club.name}</p>
                <p className="muted">
                  {offer.league_name} · XV {formatNote(offer.level)}
                  {offer.balance !== null && ` · trésorerie ${formatMoney(offer.balance)}`}
                  {offer.seasons && ` · contrat de ${offer.seasons} saisons`}
                </p>
              </div>
              <button type="button" className="button" onClick={() => accept(offer)}>
                Accepter
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
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
            detail={
              review.playoffs === "champion" && review.rank > objective.target_rank
                ? `Titre remporté · ${formatRank(review.rank)} de la saison régulière`
                : `${formatRank(objective.target_rank)} au plus bas · ${formatRank(review.rank)} au final`
            }
            muted={!review.objective_met}
          />
        )}
        {review.cups.map((cup) => (
          <Stat
            key={cup.code}
            label={cup.name}
            value={CUP_RESULTS[cup.result]}
            detail={[
              `${cup.won} V · ${cup.drawn} N · ${cup.lost} D`,
              cup.result !== "champion" && cup.champion && `Vainqueur : ${cup.champion.name}`,
            ]
              .filter(Boolean)
              .join(" · ")}
            muted={cup.result === "pools"}
          />
        ))}
        {review.youth_rank && <Stat label="Espoirs" value={formatRank(review.youth_rank)} detail="Championnat espoirs" />}
        <Stat
          label="Trésorerie"
          value={formatMoney(review.balance_end)}
          detail={`${formatSignedMoney(review.balance_end - review.balance_start)} sur la saison`}
        />
      </dl>

      {review.scorers.length > 0 && (
        <section>
          <h3 className="eyebrow">Meilleurs marqueurs{review.cups.length > 0 && " · coupes comprises"}</h3>
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

export function Stat({ label, value, detail, muted = false }) {
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
