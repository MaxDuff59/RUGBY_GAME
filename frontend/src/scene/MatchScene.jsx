import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api.js";
import { clubInfo, clubTheme, inkOn } from "../clubs.js";
import { crunchResult, crunchSituation, crunchStake, dilemmaText, signed } from "../decisions.js";
import { CRUNCH_OPTIONS, DILEMMAS, formatNote } from "../format.js";
import { PHONE_QUERY, useMediaQuery } from "../hooks/useMediaQuery.js";
import { defaultJersey, distance } from "../jersey.js";
import { loadLogos } from "../sponsors.js";
import { useScenePrefs } from "./prefs.js";
import { buildCrunch } from "./scripts/crunch.js";
import { buildKick } from "./scripts/kick.js";
import { createStage } from "./stage.js";

// Une décision en match mise en scène en 3D, à la place de la fenêtre de texte : le
// dilemme du joueur incarné (`kind` "dilemma") ou le choix crucial du manager
// ("crunch"). Le serveur décide, la scène met en scène : elle lit ce que l'API renvoie
// (la situation, les voies et leurs chances, puis l'issue tirée et les événements du
// match) et joue l'issue telle qu'elle est.
//
// Trois temps : la mise en place (la caméra arrive, l'action ralentit et se fige), le
// choix (les voies sont des boutons posés sur l'image ; au survol, ou au premier toucher
// sur téléphone, la voie se dessine sur la pelouse), l'issue (l'action se joue, puis la
// carte de résultat). Un clic ou Espace saute à la fin du temps en cours. Une réussite
// qui en appelle une autre s'enchaîne dans la même scène ; si la suivante n'a pas de
// scène, la fenêtre de texte prend le relais (`onHandOff`). Sans WebGL : `onFail`.

// Les scènes des dilemmes, par situation (engine/dilemmas.py) ; prefs.js les nomme.
const DILEMMA_SCENES = { kick: buildKick };

// Les maillots des deux clubs : chacun le sien à domicile ; l'équipe qui se déplace
// passe à sa tenue extérieure (puis au third) si les deux se ressemblent trop.
function kits(homeName, awayName) {
  const home = defaultJersey(homeName, "home");
  let away = defaultJersey(awayName, "home");
  if (distance(away.base, home.base) < 120) away = defaultJersey(awayName, "away");
  if (distance(away.base, home.base) < 90) away = defaultJersey(awayName, "third");
  return { home, away };
}

// L'heure du match n'est pas connue : les phases finales et un match sur trois se jouent
// le soir, toujours les mêmes.
const evening = (live) => live.knockout || (live.match_id * 2654435761) % 3 === 0;

function sceneContext(live, side, phone, prefs) {
  const homeName = live.home.club.name;
  const awayName = live.away.club.name;
  const jerseys = kits(homeName, awayName);
  const homeColors = clubInfo(homeName).colors;
  const awayColors = clubInfo(awayName).colors;
  const pressure =
    live.dilemma?.pressure ?? (live.crunch ? 1.5 * (live.knockout ? 1.25 : 1) * (live.stage === "final" ? 1.5 : 1) : 1);
  return {
    home: { name: homeName, jersey: jerseys.home, colors: homeColors, ink: inkOn(homeColors[0]) },
    away: { name: awayName, jersey: jerseys.away, colors: awayColors, ink: inkOn(awayColors[0]) },
    us: side === live.home ? "home" : "away",
    accent: clubTheme(side.club.name).accent,
    weather: live.weather,
    evening: evening(live),
    pressure,
    seed: live.match_id * 131 + (live.dilemma?.minute ?? live.crunch?.minute ?? live.minute),
    muted: !prefs.sound,
    phone,
  };
}

export default function MatchScene({ kind, live, side, busy, error, boards, onChoose, onResume, onClose, onFail, onHandOff }) {
  const host = useRef(null);
  const stage = useRef(null);
  const callbacks = useRef({});
  const phone = useMediaQuery(PHONE_QUERY);
  const [prefs, setPrefs] = useScenePrefs();
  const [phase, setPhase] = useState("setup"); // setup | choice | waiting | outcome | result
  const [choice, setChoice] = useState(null); // { option, outcomes, events }
  const [selected, setSelected] = useState(null); // téléphone : la voie touchée une fois
  const [banner, setBanner] = useState(null); // une réussite enchaînée, le temps de la suite
  const touch = useRef(false);
  callbacks.current = { onFail, onHandOff };

  const other = side === live.home ? live.away : live.home;
  const me = side.players.find((p) => p.id === live.hero?.player_id);
  const dilemma = live.dilemma;
  const outcomes = live.hero?.outcomes ?? [];
  const outcome = kind === "dilemma" && choice && outcomes.length > choice.outcomes ? outcomes[outcomes.length - 1] : null;
  const fresh = choice ? live.events.slice(choice.events) : [];
  const crunchDone = kind === "crunch" && choice !== null && !live.crunch && !busy;

  // Ce que la scène doit savoir de la situation présente, gardé du premier rendu : la
  // réponse du serveur au choix fait disparaître la décision de `live`.
  const [opening] = useState(() => ({
    dilemma: live.dilemma,
    crunch: live.crunch,
    minute: live.minute,
    margin: side.score - (side === live.home ? live.away : live.home).score,
  }));
  const [current, setCurrent] = useState(() => live.dilemma);
  const data = useMemo(() => {
    const kicker = side.players.find((p) => p.id === side.kicker_id);
    return { kickerNumber: kicker?.slot_number ?? 10, hero: me?.slot_number ?? me?.number ?? 10 };
  }, [side, me]);

  // --- Le plateau -----------------------------------------------------------------
  useEffect(() => {
    const created = createStage(host.current, sceneContext(live, side, phone, prefs), {
      onChoice: () => setPhase("choice"),
      onDone: () => setPhase("result"),
      onFail: () => callbacks.current.onFail?.(),
    });
    if (!created) return undefined;
    stage.current = created;
    if (kind === "crunch") created.begin(buildCrunch, data);
    else created.begin(DILEMMA_SCENES[opening.dilemma.situation], data);
    // Les panneaux aux sponsors du club, quand le match se joue chez lui.
    let alive = true;
    if (boards) {
      api
        .getFacilities()
        .then((facilities) => {
          const ids = new Set(facilities.sponsors.deals.map((deal) => deal.sponsor));
          return loadLogos(facilities.sponsors.library.filter((sponsor) => ids.has(sponsor.id)));
        })
        .then((images) => alive && created.setLogos([...images.values()].filter(Boolean)))
        .catch(() => {});
    }
    return () => {
      alive = false;
      created.dispose();
      stage.current = null;
    };
    // Le plateau est créé une fois par décision ; la suite passe par ses méthodes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => stage.current?.setMuted(!prefs.sound), [prefs.sound]);

  // L'issue arrive du serveur : la scène la joue.
  useEffect(() => {
    if (phase !== "waiting" || busy) return;
    if (kind === "dilemma" && outcome) {
      stage.current?.play(choice.option, { success: outcome.success, effect: outcome.effect });
      setPhase("outcome");
    } else if (crunchDone) {
      stage.current?.play(choice.option, { scored: crunchResult(choice.option, fresh).scored });
      setPhase("outcome");
    } else if (error) {
      setPhase("choice");
      setChoice(null);
    }
  }, [phase, busy, outcome, crunchDone, error, kind, choice, fresh]);

  // Une réussite qui en appelle une autre : la suite s'enchaîne dans la même scène si
  // elle en a une, sinon la fenêtre de texte prend le relais à la carte de résultat.
  const chained = kind === "dilemma" && phase === "result" && dilemma && dilemma !== current;
  const chainScene = chained ? DILEMMA_SCENES[dilemma.situation] : null;
  useEffect(() => {
    if (!chainScene) return;
    setBanner({ title: DILEMMAS[outcome.situation].options[outcome.option].label, delta: outcome.delta });
    setCurrent(dilemma);
    setChoice(null);
    setPhase("setup");
    stage.current?.begin(chainScene, data);
  }, [chainScene, dilemma, outcome, data]);
  useEffect(() => {
    if (!banner || phase !== "choice") return undefined;
    const timer = setTimeout(() => setBanner(null), 2500);
    return () => clearTimeout(timer);
  }, [banner, phase]);

  // Clic ou Espace : passer la mise en place ou l'issue. Échap : fermer le choix crucial.
  useEffect(() => {
    const onKey = (event) => {
      if (event.code === "Space" && !event.repeat && (phase === "setup" || phase === "outcome")) {
        event.preventDefault();
        stage.current?.skip();
      } else if (event.key === "Escape" && kind === "crunch" && phase === "choice" && !busy) {
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase, kind, busy, onClose]);

  const preview = (key) => phase === "choice" && stage.current?.preview(key);
  const choose = (key) => {
    stage.current?.wake();
    if (touch.current && selected !== key) {
      setSelected(key);
      preview(key);
      return;
    }
    stage.current?.preview(null);
    setSelected(null);
    setChoice({ option: key, outcomes: outcomes.length, events: live.events.length });
    setPhase("waiting");
    onChoose(key);
  };

  // --- Ce qui se lit sur l'image ---------------------------------------------------
  const situation = kind === "dilemma" ? DILEMMAS[(current ?? opening.dilemma).situation] : null;
  const margin = opening.margin;
  const crunch = live.crunch ?? opening.crunch;
  const pressure = kind === "dilemma" ? (current ?? opening.dilemma).pressure : 1;
  const options =
    kind === "dilemma"
      ? (current ?? opening.dilemma).options.map((option) => ({
          key: option.key,
          label: situation.options[option.key].label,
          scope: `${situation.options[option.key].scope} · note ${signed(option.reward)} ou ${signed(option.cost)}`,
          chance: option.success,
          odds: "de réussite",
        }))
      : crunch.options.map((option) => ({
          key: option.key,
          label: CRUNCH_OPTIONS[option.key].label,
          scope: `${CRUNCH_OPTIONS[option.key].scope} · ${crunchStake(option.key, margin)}`,
          chance: option.success,
          odds: option.key === "kick" ? "de réussite" : "d'essai",
        }));

  let head;
  if (kind === "dilemma") {
    const shown = current ?? opening.dilemma;
    head = {
      eyebrow: `${shown.chained ? "Dans la foulée" : "À toi de jouer"} · ${shown.minute}'${me ? ` · ta note ${formatNote(me.rating ?? 6)}` : ""}`,
      title: situation.title,
      text: situation.text,
      pressure: pressure > 1 ? `Moment décisif : ta note gagne ou perd ×${formatNote(pressure)}` : null,
    };
  } else {
    head = {
      eyebrow: `Choix crucial${live.derby ? ` · ${live.derby}` : ""} · ${crunch?.minute ?? opening.minute}'`,
      title: "Pénalité pour nous",
      text: crunchSituation(margin, live.last_minute - (crunch?.minute ?? live.minute)),
      pressure: null,
    };
  }

  let card = null;
  if (phase === "result" && !chainScene) {
    if (kind === "dilemma" && outcome) {
      card = {
        eyebrow: `${DILEMMAS[outcome.situation].title} · ${outcome.minute}'`,
        title: DILEMMAS[outcome.situation].options[outcome.option].label,
        good: outcome.success,
        verdict: outcome.success ? "Réussi" : "Raté",
        text: dilemmaText(outcome, fresh),
        effect: `Ta note ${signed(outcome.delta)} · ${me ? formatNote(me.rating ?? 6) : "–"} / 10 · ${side.club.name} ${side.score} – ${other.score} ${other.club.name}`,
      };
    } else if (kind === "crunch" && choice) {
      const result = crunchResult(choice.option, fresh);
      const after = side.score - other.score;
      card = {
        eyebrow: `Choix crucial · ${fresh[0]?.minute ?? live.minute}'`,
        title: CRUNCH_OPTIONS[choice.option].label,
        good: result.scored,
        verdict: result.verdict,
        text: result.text,
        effect: `${side.club.name} ${side.score} – ${other.score} ${other.club.name}${live.finished ? " · coup de sifflet final" : live.extra_time && after === 0 ? " · prolongation" : ""}`,
      };
    }
  }

  const skippable = phase === "setup" || phase === "outcome";
  const kicker = side.players.find((p) => p.id === side.kicker_id);

  return (
    <div className={`match-scene${phone ? " match-scene--phone" : ""}`} role="dialog" aria-modal="true" aria-label={head.title}>
      <div
        className={`match-scene__stage${skippable ? " is-skippable" : ""}`}
        ref={host}
        onClick={() => {
          stage.current?.wake();
          if (skippable) stage.current?.skip();
        }}
      >
        <div className="match-scene__head">
          <p className="eyebrow">{head.eyebrow}</p>
          <h2 className="match-scene__title">{head.title}</h2>
          {head.pressure && <p className="dilemma__pressure">{head.pressure}</p>}
          <p className="match-scene__text">{head.text}</p>
        </div>
        <div className="match-scene__tools">
          <button
            type="button"
            className="match-scene__tool"
            aria-pressed={prefs.sound}
            onClick={(event) => {
              event.stopPropagation();
              setPrefs({ sound: !prefs.sound });
              stage.current?.wake();
            }}
          >
            {prefs.sound ? "Son : oui" : "Son : non"}
          </button>
          {skippable && <span className="match-scene__hint">{phone ? "Touche pour passer" : "Clic ou Espace pour passer"}</span>}
        </div>
        {banner && (
          <p className="match-scene__banner">
            Réussi : {banner.title} · ta note {signed(banner.delta)}
          </p>
        )}
      </div>

      <div className="match-scene__dock">
        {card ? (
          <div className="match-scene__card">
            <div>
              <p className="eyebrow">{card.eyebrow}</p>
              <h2 className="confirm__title">{card.title}</h2>
            </div>
            <div className={`talk__outcome talk__outcome--${card.good ? "lifted" : "backfired"}`}>
              <span className="talk__verdict">{card.verdict}</span>
              <p className="confirm__text">{card.text}</p>
              <span className="muted talk__effect">{card.effect}</span>
            </div>
            <div className="confirm__actions">
              {chained ? (
                <button type="button" className="button button--primary" autoFocus onClick={() => onHandOff()}>
                  Continuer l'action
                </button>
              ) : (
                <button type="button" className="button button--primary" autoFocus onClick={live.finished ? onClose : onResume}>
                  {live.finished ? "Fermer" : "Reprendre le match"}
                </button>
              )}
            </div>
          </div>
        ) : (
          <>
            {phase === "waiting" || phase === "outcome" ? (
              <p className="match-scene__status">{kind === "crunch" ? "Le ballon est posé…" : "L'action se joue…"}</p>
            ) : (
              <ul className="match-scene__options" aria-label="Les voies">
                {options.map((option) => (
                  <li key={option.key}>
                    <button
                      type="button"
                      className={`talk__option match-scene__option${selected === option.key ? " is-selected" : ""}`}
                      disabled={busy || phase !== "choice"}
                      onPointerDown={(event) => (touch.current = event.pointerType === "touch")}
                      onMouseEnter={() => preview(option.key)}
                      onMouseLeave={() => preview(null)}
                      onFocus={() => preview(option.key)}
                      onBlur={() => !touch.current && preview(null)}
                      onClick={() => choose(option.key)}
                    >
                      <span className="talk__name">{option.label}</span>
                      <span className="muted talk__scope">
                        {selected === option.key ? "Touche encore pour jouer" : option.scope}
                      </span>
                      <span className="talk__odds">
                        <span className="crunch__chance num">{Math.round(option.chance * 100)} %</span>
                        {option.odds}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {kind === "crunch" && phase !== "outcome" && (
              <div className="match-scene__foot">
                {kicker && crunch && (
                  <span className="muted">
                    Buteur : {kicker.name} · transformation {Math.round(crunch.conversion * 100)} %
                  </span>
                )}
                <button type="button" className="button button--small" disabled={busy || phase === "waiting"} onClick={onClose}>
                  Faire un changement
                </button>
              </div>
            )}
          </>
        )}
        {error && <p className="status--error match-scene__error">{error.message}</p>}
      </div>
    </div>
  );
}
