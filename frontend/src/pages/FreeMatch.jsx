import { useCallback, useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { api } from "../api.js";
import ClubCrest from "../components/ClubCrest.jsx";
import { ActionError } from "../components/FullGame.jsx";
import { useApi } from "../hooks/useApi.js";
import { PHONE_QUERY, useMediaQuery } from "../hooks/useMediaQuery.js";
import { LiveScreen } from "./Match.jsx";

// Match libre : deux équipes au choix, clubs ou sélections (Toulouse contre les All
// Blacks, c'est permis), puis le match en direct comme en carrière. Rien ne se garde
// dans une partie : ni résultat, ni blessure. Il faut seulement être connecté (un
// invité suffit).
const CALLS = {
  get: api.getFriendly,
  advance: api.advanceFriendly,
  tactics: api.setFriendlyTactics,
  talk: api.talkFriendly,
  decide: api.decideFriendly,
  substitute: api.substituteFriendly,
  finish: api.finishFriendly,
};

export default function FreeMatch() {
  // Un nouveau match remonte l'écran du direct : il retombe sur le choix des équipes.
  const [round, setRound] = useState(0);

  async function again() {
    await api.dropFriendly();
    setRound((n) => n + 1);
  }

  return (
    <div className="start friendly">
      <p className="eyebrow friendly__crumbs">
        <Link to="/parties">Parties</Link> · Match libre
      </p>
      <LiveScreen
        key={round}
        calls={CALLS}
        title="Match libre"
        empty={(onStarted) => <Picker onStarted={onStarted} />}
        onDone={again}
        doneLabel="Nouveau match"
        handOverText="Le reste du match se joue sans toi : le staff gère le banc jusqu'au coup de sifflet final."
      />
    </div>
  );
}

// --- Le choix des deux équipes ----------------------------------------------------------

function Picker({ onStarted }) {
  const groups = useApi(useCallback(api.friendlyTeams, []));
  const [home, setHome] = useState(null);
  const [away, setAway] = useState(null);
  const [mine, setMine] = useState("home"); // l'équipe que l'on dirige
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  if (groups.error?.status === 401) return <Navigate to="/connexion" replace />;
  if (groups.loading) return <p className="status">Préparation des équipes…</p>;
  if (groups.error) return <p className="status status--error">{groups.error.message}</p>;
  if (groups.data.length === 0) return <p className="status status--error">Aucune équipe à choisir.</p>;

  const names = new Map(groups.data.flatMap((group) => group.teams.map((team) => [team.id, team.name])));
  const ready = home !== null && away !== null && home !== away;

  async function kickOff() {
    setBusy(true);
    setError(null);
    try {
      onStarted(await api.startFriendly(home, away, mine === "home" ? home : away));
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <>
      <header className="page-head">
        <div>
          <h1 className="title">Choisis l'affiche</h1>
          <p className="muted" style={{ margin: "8px 0 0" }}>
            Clubs et sélections se mélangent. Rien n'est gardé : ni résultat, ni blessure.
          </p>
        </div>
      </header>

      <div className="friendly__teams">
        <TeamColumn label="À domicile" groups={groups.data} chosen={home} other={away} onPick={setHome} />
        <TeamColumn label="À l'extérieur" groups={groups.data} chosen={away} other={home} onPick={setAway} />
      </div>

      <ActionError error={error} />

      <div className="friendly__submit">
        {ready && (
          <div className="chips" role="group" aria-label="Tu diriges">
            {[
              ["home", home],
              ["away", away],
            ].map(([side, id]) => (
              <button
                key={side}
                type="button"
                className="chip with-crest"
                aria-pressed={mine === side}
                onClick={() => setMine(side)}
              >
                <ClubCrest name={names.get(id)} size={18} />
                Je dirige {names.get(id)}
              </button>
            ))}
          </div>
        )}
        <button type="button" className="button button--primary" disabled={!ready || busy} onClick={kickOff}>
          {busy ? "Composition des équipes…" : "Au coup d'envoi"}
        </button>
      </div>
    </>
  );
}

// Une colonne : le championnat (ou les sélections), puis l'équipe. Sur téléphone, le
// championnat se choisit dans un menu : les pastilles mangeraient la liste.
function TeamColumn({ label, groups, chosen, other, onPick }) {
  const phone = useMediaQuery(PHONE_QUERY);
  const [code, setCode] = useState(
    () => groups.find((group) => group.teams.some((team) => team.id === chosen))?.code ?? groups[0].code,
  );
  const group = groups.find((item) => item.code === code) ?? groups[0];
  return (
    <section className="section friendly__column">
      <div className="section__head">
        <p className="eyebrow">{label}</p>
        {phone && (
          <select
            className="input tactics__select"
            aria-label={`${label} : championnat`}
            value={group.code}
            onChange={(event) => setCode(event.target.value)}
          >
            {groups.map((item) => (
              <option key={item.code} value={item.code}>
                {item.name}
              </option>
            ))}
          </select>
        )}
      </div>
      {!phone && (
        <div className="chips friendly__groups" role="group" aria-label={`${label} : championnat`}>
          {groups.map((item) => (
            <button
              key={item.code}
              type="button"
              className="chip chip--small"
              aria-pressed={item.code === group.code}
              onClick={() => setCode(item.code)}
            >
              {item.name}
            </button>
          ))}
        </div>
      )}
      <div className="club-list__scroll">
        <ul className="club-list friendly__list">
          {group.teams.map((team) => (
            <li key={team.id}>
              <button
                type="button"
                className="club-option"
                aria-pressed={team.id === chosen}
                disabled={team.id === other}
                onClick={() => onPick(team.id)}
              >
                <span className="club-option__name with-crest">
                  <ClubCrest name={team.name} size={28} />
                  {team.name}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
