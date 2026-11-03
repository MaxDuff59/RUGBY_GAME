import { useEffect, useRef, useState } from "react";

import { PHONE_QUERY, useMediaQuery } from "../hooks/useMediaQuery.js";
import { sceneContext } from "./context.js";
import { useScenePrefs } from "./prefs.js";
import { buildShootout } from "./scripts/shootout.js";
import { buildTrophy } from "./scripts/trophy.js";
import { buildTunnel } from "./scripts/tunnel.js";
import { buildWinningTry } from "./scripts/winningTry.js";
import { createStage } from "./stage.js";

// Un moment du match à regarder en 3D (moments.js), sans décision : le plateau joue tout
// d'une traite (l'issue de la scène, la voie « watch »), un clic ou Espace saute à la fin.

const BUILDERS = {
  shootout: buildShootout,
  winning_try: buildWinningTry,
  tunnel: buildTunnel,
  trophy: buildTrophy,
};

// Ce qui se lit sur l'image ; `shown` : les tirs déjà joués d'une séance.
function heading(moment, live, side, shown) {
  const { kind, data } = moment;
  const other = side === live.home ? live.away : live.home;
  const match = `${live.home.club.name} – ${live.away.club.name}`;
  if (kind === "shootout") {
    const goals = (us) => data.kicks.slice(0, shown).filter((kick) => kick.us === us && kick.scored).length;
    const last = shown > 0 ? data.kicks[shown - 1] : null;
    return {
      eyebrow: "Séance décisive",
      title: "Tirs au but",
      text: `${side.club.name} ${goals(true)} – ${goals(false)} ${other.club.name}${last ? ` · ${last.name} : ${last.scored ? "réussi" : "manqué"}` : ""}`,
    };
  }
  if (kind === "winning_try") return { eyebrow: `${data.minute}'`, title: "L'essai de la victoire", text: data.name };
  if (kind === "tunnel") return { eyebrow: data.final ? "La finale" : data.derby, title: "L'entrée des équipes", text: match };
  return { eyebrow: data.competition ?? "La finale", title: "Champions !", text: side.club.name };
}

export default function MomentScene({ moment, live, side, onDone, onFail }) {
  const host = useRef(null);
  const stage = useRef(null);
  const callbacks = useRef({});
  const phone = useMediaQuery(PHONE_QUERY);
  const [prefs, setPrefs] = useScenePrefs();
  const [playing, setPlaying] = useState(true);
  const [shown, setShown] = useState(0); // séance de tirs au but : les tirs déjà joués
  callbacks.current = { onFail };

  useEffect(() => {
    const created = createStage(host.current, sceneContext(live, side, phone, prefs), {
      onChoice: () => created?.play("watch", {}),
      onDone: () => setPlaying(false),
      onFail: () => callbacks.current.onFail?.(),
    });
    if (!created) return undefined;
    stage.current = created;
    created.begin(BUILDERS[moment.kind], { ...moment.data, onKick: setShown });
    return () => {
      created.dispose();
      stage.current = null;
    };
    // Le plateau est créé une fois par moment.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => stage.current?.setMuted(!prefs.sound), [prefs.sound]);

  useEffect(() => {
    const onKey = (event) => {
      if (event.code === "Space" && !event.repeat && playing) {
        event.preventDefault();
        stage.current?.skip();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [playing]);

  const head = heading(moment, live, side, shown);
  return (
    <div className={`match-scene${phone ? " match-scene--phone" : ""}`} role="dialog" aria-modal="true" aria-label={head.title}>
      <div
        className={`match-scene__stage${playing ? " is-skippable" : ""}`}
        ref={host}
        onClick={() => {
          stage.current?.wake();
          if (playing) stage.current?.skip();
        }}
      >
        <div className="match-scene__head">
          <p className="eyebrow">{head.eyebrow}</p>
          <h2 className="match-scene__title">{head.title}</h2>
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
          {playing && <span className="match-scene__hint">{phone ? "Touche pour passer" : "Clic ou Espace pour passer"}</span>}
        </div>
      </div>
      <div className="match-scene__dock">
        <div className="confirm__actions">
          {/* Remonté à la fin du moment, pour que le bouton prenne alors le focus. */}
          <button key={playing} type="button" className="button button--primary" autoFocus={!playing} disabled={playing} onClick={onDone}>
            Continuer
          </button>
        </div>
      </div>
    </div>
  );
}
