import { useCallback, useRef, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { api } from "../api.js";
import { useClubTheme } from "../clubs.js";
import ClubCrest from "../components/ClubCrest.jsx";
import { ActionError } from "../components/FullGame.jsx";
import { LineupLegend, LineupPitch, StrengthStrip, useLineupEditor } from "../components/LineupBoard.jsx";
import LineupPicker from "../components/LineupPicker.jsx";
import { POSITION_SHORT, formatNote, formatWorldRank } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { PHONE_QUERY, useMediaQuery } from "../hooks/useMediaQuery.js";
import { usePitchWidth } from "../hooks/usePitchWidth.js";
import { matchSheet } from "../lineup.js";
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

// Les familles d'équipes, en tête de chaque carte ; les groupes du serveur s'y rangent.
const CATEGORIES = [
  ["clubs", "Clubs"],
  ["nations", "Sélections"],
  ["legends", "Légendes"],
];
const categoryOf = (code) => (code === "nations" ? "nations" : code.endsWith("legends") ? "legends" : "clubs");

// Deux cartes face à face, une par équipe : la famille (clubs, sélections, légendes), le
// championnat, puis l'équipe, qui défile aux flèches, avec son niveau et ses notes. Chaque
// carte dit qui la dirige : toi, ou le staff. L'interface prend les couleurs de ton équipe.
function Picker({ initial, onPrepared }) {
  const groups = useApi(useCallback(api.friendlyTeams, []));
  const [home, setHome] = useState(initial?.home ?? null);
  const [away, setAway] = useState(initial?.away ?? null);
  const [mine, setMine] = useState(initial?.mine ?? "home"); // l'équipe que l'on dirige
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const teams = new Map((groups.data ?? []).flatMap((group) => group.teams.map((team) => [team.id, team])));
  // Sans affiche d'avant, les deux premières équipes du premier championnat.
  const first = groups.data?.[0]?.teams ?? [];
  const homeId = home ?? first[0]?.id ?? null;
  const awayId = away ?? first[1]?.id ?? null;
  useClubTheme(teams.get(mine === "home" ? homeId : awayId)?.name);

  if (groups.error?.status === 401) return <Navigate to="/connexion" replace />;
  if (groups.loading) return <p className="status">Préparation des équipes…</p>;
  if (groups.error) return <p className="status status--error">{groups.error.message}</p>;
  if (teams.size < 2) return <p className="status status--error">Aucune équipe à choisir.</p>;

  const ready = homeId !== null && awayId !== null && homeId !== awayId;

  async function prepare() {
    setBusy(true);
    setError(null);
    try {
      onPrepared(await api.prepareFriendly(homeId, awayId, mine === "home" ? homeId : awayId));
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <>
      <header className="page-head friendly__title">
        <div>
          <h1 className="title">Choisis l'affiche</h1>
          <p className="muted" style={{ margin: "8px 0 0" }}>
            Clubs, sélections et légendes se mélangent. Rien n'est gardé : ni résultat, ni blessure.
          </p>
        </div>
      </header>

      <div className="friendly__teams">
        <TeamCard
          label="À domicile"
          groups={groups.data}
          chosen={homeId}
          other={awayId}
          onPick={setHome}
          mine={mine === "home"}
          onMine={() => setMine("home")}
        />
        <p className="friendly__versus" aria-hidden="true">
          VS
        </p>
        <TeamCard
          label="À l'extérieur"
          groups={groups.data}
          chosen={awayId}
          other={homeId}
          onPick={setAway}
          mine={mine === "away"}
          onMine={() => setMine("away")}
        />
      </div>

      <ActionError error={error} />

      <div className="friendly__submit">
        <p className="muted friendly__mine">
          Tu diriges <strong>{teams.get(mine === "home" ? homeId : awayId)?.name}</strong>, le staff l'autre équipe.
        </p>
        <button type="button" className="button button--primary" disabled={!ready || busy} onClick={prepare}>
          {busy ? "Composition des équipes…" : "Composer mon XV"}
        </button>
      </div>
    </>
  );
}

// Une carte : qui la dirige, la famille, le championnat, puis l'équipe. « Toutes les
// équipes » montre le championnat d'un coup, à la place de l'équipe ; « Au hasard » en
// tire une, toutes familles confondues. L'équipe d'en face ne se choisit pas deux fois.
function TeamCard({ label, groups, chosen, other, onPick, mine, onMine }) {
  const phone = useMediaQuery(PHONE_QUERY);
  const [listing, setListing] = useState(false);
  const group = groups.find((item) => item.teams.some((team) => team.id === chosen)) ?? groups[0];
  const team = group.teams.find((item) => item.id === chosen) ?? group.teams[0];
  const category = categoryOf(group.code);
  const siblings = groups.filter((item) => categoryOf(item.code) === category);
  const free = (list) => list.filter((item) => item.id !== other);

  // La première équipe libre d'un groupe (ou du suivant, s'il n'a que l'adversaire).
  function openGroup(next) {
    const pick = free(next.teams)[0];
    if (pick) onPick(pick.id);
    setListing(false);
  }

  function step(list, current, delta) {
    return list[(list.indexOf(current) + delta + list.length) % list.length];
  }

  // L'équipe d'à côté dans l'ordre du championnat, en sautant l'adversaire.
  function stepTeam(delta) {
    const count = group.teams.length;
    const index = group.teams.indexOf(team);
    for (let move = 1; move < count; move += 1) {
      const next = group.teams[(((index + delta * move) % count) + count) % count];
      if (next.id !== other) {
        onPick(next.id);
        return;
      }
    }
  }

  function random() {
    const all = free(groups.flatMap((item) => item.teams)).filter((item) => item.id !== team.id);
    if (all.length) onPick(all[Math.floor(Math.random() * all.length)].id);
    setListing(false);
  }

  return (
    <section className={`card team-card${mine ? " team-card--mine" : ""}`} aria-label={label}>
      <div className="team-card__head">
        <p className="eyebrow">{label}</p>
        <button type="button" className="chip chip--small" aria-pressed={mine} onClick={onMine}>
          {mine ? "Tu diriges" : "Le staff · diriger"}
        </button>
      </div>

      <div className="chips team-card__families" role="group" aria-label={`${label} : famille d'équipes`}>
        {CATEGORIES.filter(([key]) => groups.some((item) => categoryOf(item.code) === key)).map(([key, name]) => (
          <button
            key={key}
            type="button"
            className="chip chip--small"
            aria-pressed={key === category}
            onClick={() => openGroup(groups.find((item) => categoryOf(item.code) === key))}
          >
            {name}
          </button>
        ))}
      </div>

      <Stepper
        label={`${label} : championnat`}
        disabled={siblings.length < 2}
        onPrevious={() => openGroup(step(siblings, group, -1))}
        onNext={() => openGroup(step(siblings, group, 1))}
      >
        <span className="team-card__group">{group.name}</span>
      </Stepper>

      {listing ? (
        <div className="club-list__scroll team-card__list">
          <ul className="club-list">
            {group.teams.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className="club-option"
                  aria-pressed={item.id === team.id}
                  disabled={item.id === other}
                  onClick={() => {
                    onPick(item.id);
                    setListing(false);
                  }}
                >
                  <span className="club-option__name with-crest">
                    <ClubCrest name={item.name} size={28} />
                    {item.name}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="team-card__team">
          <h2 className="team-card__name">{team.name}</h2>
          {team.world_rank != null && <p className="muted team-card__rank">{formatWorldRank(team.world_rank)}</p>}
          <Stepper
            label={`${label} : équipe`}
            disabled={free(group.teams).length < 2}
            onPrevious={() => stepTeam(-1)}
            onNext={() => stepTeam(1)}
          >
            <ClubCrest name={team.name} size={phone ? 80 : 120} className="team-card__crest" />
          </Stepper>
          {team.level != null && <Level value={team.level} />}
          {team.attack != null && (
            <dl className="team-card__notes">
              {[
                ["Attaque", team.attack],
                ["Avants", team.forwards],
                ["Défense", team.defense],
              ].map(([name, value]) => (
                <div key={name}>
                  <dt>{name}</dt>
                  <dd>{formatNote(value)}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      )}

      <div className="team-card__foot">
        <button type="button" className="button button--small" onClick={() => setListing((open) => !open)}>
          {listing ? "Retour à l'équipe" : "Toutes les équipes"}
        </button>
        <button type="button" className="button button--small" onClick={random}>
          Au hasard
        </button>
      </div>
    </section>
  );
}

// Un contenu entre deux flèches (championnat, équipe).
function Stepper({ label, disabled, onPrevious, onNext, children }) {
  return (
    <div className="stepper" role="group" aria-label={label}>
      <button type="button" className="stepper__arrow" aria-label="Précédent" disabled={disabled} onClick={onPrevious}>
        ‹
      </button>
      <div className="stepper__body">{children}</div>
      <button type="button" className="stepper__arrow" aria-label="Suivant" disabled={disabled} onClick={onNext}>
        ›
      </button>
    </div>
  );
}

// Le niveau de l'équipe parmi toutes celles au choix : cinq crans, par demi-crans.
function Level({ value }) {
  return (
    <div className="level" role="img" aria-label={`Niveau ${formatNote(value)} sur 5`}>
      {[1, 2, 3, 4, 5].map((cell) => (
        <span key={cell} className="level__cell">
          <span style={{ width: `${Math.max(0, Math.min(1, value - cell + 1)) * 100}%` }} />
        </span>
      ))}
    </div>
  );
}

// --- La composition ---------------------------------------------------------------------

// Le XV du joueur sur le terrain, comme l'écran Effectif : toucher un titulaire ouvre le
// choix de son remplaçant, le faire glisser l'échange avec un autre. Le staff compose ce
// qui n'est pas choisi, et le banc.
function Composition({ setup, onChange, onBack, onStarted }) {
  const { team } = setup;
  const pitchRef = useRef(null);
  const pitchWidth = usePitchWidth(pitchRef);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const editor = useLineupEditor({
    team,
    save: api.setFriendlyLineup,
    reset: api.resetFriendlyLineup,
    onSaved: onChange,
  });

  const sheet = matchSheet(team);
  const byId = new Map(team.players.map((player) => [player.id, player]));
  const bench = team.strength.bench_ids.map((id) => byId.get(id)).filter(Boolean);
  const opponent = setup.home.id === team.id ? setup.away : setup.home;

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
            {team.name} contre {opponent.name}
          </p>
        </div>
        <div className="friendly__actions">
          <button type="button" className="button" disabled={busy} onClick={onBack}>
            Changer d'affiche
          </button>
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
          <LineupPitch editor={editor} captainId={team.strength.captain_id} />
          <LineupLegend />
        </figure>
        <div className="friendly__side">
          <StrengthStrip editor={editor} />
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
      </div>

      {editor.picking && (
        <LineupPicker
          entry={editor.picking}
          team={team}
          players={team.players}
          sheet={sheet}
          onPick={(candidate) => editor.place(editor.picking.slot.number, candidate)}
          onClose={editor.closePicker}
        />
      )}
    </>
  );
}
