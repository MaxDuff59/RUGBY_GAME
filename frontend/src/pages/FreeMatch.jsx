import { useCallback, useRef, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { api } from "../api.js";
import ClubCrest from "../components/ClubCrest.jsx";
import { ActionError } from "../components/FullGame.jsx";
import LineupPicker from "../components/LineupPicker.jsx";
import Pitch from "../components/Pitch.jsx";
import { POSITION_SHORT, POSITIONS, formatNote } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { PHONE_QUERY, useMediaQuery } from "../hooks/useMediaQuery.js";
import { usePitchWidth } from "../hooks/usePitchWidth.js";
import { buildLineup, lineupChoice } from "../lineup.js";
import { LiveScreen } from "./Match.jsx";

// Match libre : deux équipes au choix, clubs ou sélections (Toulouse contre les All
// Blacks, c'est permis), puis sa composition, puis le match en direct comme en
// carrière. Rien ne se garde dans une partie : ni résultat, ni blessure. Il faut
// seulement être connecté (un invité suffit).
const CALLS = {
  get: api.getFriendly,
  advance: api.advanceFriendly,
  tactics: api.setFriendlyTactics,
  talk: api.talkFriendly,
  decide: api.decideFriendly,
  choose: api.chooseFriendly,
  substitute: api.substituteFriendly,
  finish: api.finishFriendly,
};

export default function FreeMatch() {
  // Un nouveau match remonte l'écran du direct : il retombe sur la composition (mêmes
  // équipes), ou sur le choix des équipes, celles du match d'avant déjà cochées.
  const [round, setRound] = useState(0);
  const [picks, setPicks] = useState(null); // { home, away, mine } du match d'avant

  return (
    <div className="start friendly">
      <div className="friendly__bar">
        <Link className="button button--small" to="/parties">
          ← Accueil
        </Link>
        <p className="eyebrow friendly__crumbs">Match libre</p>
      </div>
      <LiveScreen
        key={round}
        calls={CALLS}
        title="Match libre"
        empty={(onStarted) => <Setup picks={picks} onStarted={onStarted} />}
        endActions={(live) => (
          <EndActions
            live={live}
            onReplay={() => setRound((n) => n + 1)}
            onChangeTeams={(previous) => {
              setPicks(previous);
              setRound((n) => n + 1);
            }}
          />
        )}
        handOverText="Le reste du match se joue sans toi : le staff gère le banc jusqu'au coup de sifflet final."
      />
    </div>
  );
}

// Au coup de sifflet final : quitter, rejouer la même affiche (même XV, retour à la
// composition), ou en choisir une autre.
function EndActions({ live, onReplay, onChangeTeams }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function run(call, done) {
    setBusy(true);
    setError(null);
    try {
      await call();
      done();
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  const previous = {
    home: live.home.club.id,
    away: live.away.club.id,
    mine: live.home.club.id === live.my_club_id ? "home" : "away",
  };
  return (
    <>
      <button
        type="button"
        className="button"
        disabled={busy}
        onClick={() => run(api.dropFriendly, () => navigate("/parties"))}
      >
        Quitter
      </button>
      <button
        type="button"
        className="button"
        disabled={busy}
        onClick={() => run(api.dropFriendly, () => onChangeTeams(previous))}
      >
        Changer d'équipes
      </button>
      <button
        type="button"
        className="button button--primary"
        disabled={busy}
        onClick={() => run(api.replayFriendly, onReplay)}
      >
        Rejouer le match
      </button>
      <ActionError error={error} />
    </>
  );
}

// Avant le coup d'envoi : l'affiche à choisir, puis la composition.
function Setup({ picks, onStarted }) {
  const setup = useApi(api.getFriendlyTeam);
  if (setup.loading) return <p className="status">Chargement…</p>;
  if (setup.data) {
    return (
      <Composition
        setup={setup.data}
        onChange={setup.setData}
        onBack={async () => {
          await api.dropFriendly();
          setup.reload();
        }}
        onStarted={onStarted}
      />
    );
  }
  if (setup.error && setup.error.status !== 404) {
    return <p className="status status--error">{setup.error.message}</p>;
  }
  return <Picker initial={picks} onPrepared={setup.setData} />;
}

// --- Le choix des deux équipes ----------------------------------------------------------

function Picker({ initial, onPrepared }) {
  const groups = useApi(useCallback(api.friendlyTeams, []));
  const [home, setHome] = useState(initial?.home ?? null);
  const [away, setAway] = useState(initial?.away ?? null);
  const [mine, setMine] = useState(initial?.mine ?? "home"); // l'équipe que l'on dirige
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  if (groups.error?.status === 401) return <Navigate to="/connexion" replace />;
  if (groups.loading) return <p className="status">Préparation des équipes…</p>;
  if (groups.error) return <p className="status status--error">{groups.error.message}</p>;
  if (groups.data.length === 0) return <p className="status status--error">Aucune équipe à choisir.</p>;

  const names = new Map(groups.data.flatMap((group) => group.teams.map((team) => [team.id, team.name])));
  const ready = home !== null && away !== null && home !== away;

  async function prepare() {
    setBusy(true);
    setError(null);
    try {
      onPrepared(await api.prepareFriendly(home, away, mine === "home" ? home : away));
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
        <button type="button" className="button button--primary" disabled={!ready || busy} onClick={prepare}>
          {busy ? "Composition des équipes…" : "Composer mon XV"}
        </button>
      </div>
    </>
  );
}

// --- La composition ---------------------------------------------------------------------

// Le XV du joueur sur le terrain, comme l'écran Effectif : toucher un titulaire ouvre le
// choix de son remplaçant. Le staff compose ce qui n'est pas choisi, et le banc.
function Composition({ setup, onChange, onBack, onStarted }) {
  const { team } = setup;
  const pitchRef = useRef(null);
  const pitchWidth = usePitchWidth(pitchRef);
  const [picking, setPicking] = useState(null); // la place touchée
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const lineup = buildLineup(team.players, team.strength.lineup_ids);
  const jerseys = new Map(lineup.map(({ slot, player }) => [player.id, slot.number]));
  const byId = new Map(team.players.map((player) => [player.id, player]));
  const bench = team.strength.bench_ids.map((id) => byId.get(id)).filter(Boolean);
  const opponent = setup.home.id === team.id ? setup.away : setup.home;

  // Le joueur choisi prend la place ; s'il était titulaire, il échange avec l'ancien.
  async function replace({ slot, player }, candidate) {
    const place = lineup.findIndex((entry) => entry.slot.number === slot.number);
    const from = lineup.findIndex((entry) => entry.player.id === candidate.id);
    const next = lineup.map((entry, index) => {
      if (index === place) return { ...entry, player: candidate };
      if (index === from) return { ...entry, player };
      return entry;
    });
    onChange(await api.setFriendlyLineup(lineupChoice(next)));
  }

  async function run(call, done) {
    setBusy(true);
    setError(null);
    try {
      done(await call());
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <header className="page-head friendly__head">
        <div>
          <h1 className="title">Ta composition</h1>
          <p className="muted with-crest" style={{ margin: "8px 0 0" }}>
            <ClubCrest name={team.name} size={20} />
            {team.name} contre {opponent.name} ·{" "}
            {team.lineup_custom ? "ton XV" : "XV du staff"} · touche un joueur pour le remplacer
          </p>
        </div>
        <div className="friendly__actions">
          <button type="button" className="button" disabled={busy} onClick={onBack}>
            Changer d'affiche
          </button>
          {team.lineup_custom && (
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() => run(api.resetFriendlyLineup, onChange)}
            >
              Rendre la main au staff
            </button>
          )}
          <button
            type="button"
            className="button button--primary"
            disabled={busy}
            onClick={() => run(api.kickOffFriendly, onStarted)}
          >
            Coup d'envoi
          </button>
        </div>
      </header>

      <ActionError error={error} />

      <div className="friendly__compo">
        <figure
          ref={pitchRef}
          className="squad__pitch friendly__pitch"
          style={pitchWidth ? { width: pitchWidth, flexBasis: pitchWidth } : undefined}
          aria-label="XV de départ sur le terrain"
        >
          <Pitch
            markers={lineup.map(({ slot, player }) => ({
              key: slot.number,
              x: slot.x,
              y: slot.y,
              number: slot.number,
              label: player.last_name,
              title: `${player.name} · ${POSITIONS[player.position].label} · ${formatNote(player.overall)}`,
              entry: { slot, player },
            }))}
            onPick={(marker) => setPicking(marker.entry)}
          />
        </figure>
        <section className="card friendly__bench">
          <p className="eyebrow">Le banc · choisi par le staff</p>
          <ul>
            {bench.map((player, index) => (
              <li key={player.id}>
                <span className="num muted">{16 + index}</span>
                <span>{player.name}</span>
                <span className="muted">{POSITION_SHORT[player.position]}</span>
                <span className="note">{formatNote(player.overall)}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      {picking && (
        <LineupPicker
          entry={picking}
          players={team.players}
          jerseys={jerseys}
          onPick={(candidate) => replace(picking, candidate)}
          onClose={() => setPicking(null)}
        />
      )}
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
