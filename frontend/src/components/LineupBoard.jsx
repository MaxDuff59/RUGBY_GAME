import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { POSITION_SHORT, POSITIONS, formatNote } from "../format.js";
import { buildLineup, lineupChoice, movePlayer, ratingAt, unavailability } from "../lineup.js";
import InjuryIcon from "./InjuryIcon.jsx";
import Pitch from "./Pitch.jsx";

// L'édition d'une composition, partagée par l'écran Effectif (club ou sélection) et le
// match libre : le XV sur le terrain, le glisser-déposer, la fenêtre de choix, et ce
// que chaque changement fait aux notes de l'équipe (avec « Annuler »).

// Écart à partir duquel un appui devient un glissement (en px).
const DRAG_THRESHOLD = 6;
// Durée pendant laquelle une place qui vient de changer reste marquée (ms).
const FLASH_MS = 1600;

// `team` : la composition telle que l'API la renvoie (ClubDetail) ;
// `save(choice)` et `reset()` : les appels qui l'enregistrent (renvoient une promesse) ;
// `onSaved(result)` : reçoit leur réponse.
export function useLineupEditor({ team, save, reset, onSaved }) {
  const [picking, setPicking] = useState(null); // numéro de la place touchée
  const [previous, setPrevious] = useState(null); // avant le dernier changement : { strength, choice, custom }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [flash, setFlash] = useState([]); // places qui viennent de changer
  const lineup = buildLineup(team.players, team.strength.lineup_ids);

  useEffect(() => {
    if (!flash.length) return undefined;
    const timer = setTimeout(() => setFlash([]), FLASH_MS);
    return () => clearTimeout(timer);
  }, [flash]);

  // Enregistre un changement ; garde l'état d'avant pour « Annuler » et les écarts.
  async function commit(call, { keepHistory = true, changed = [] } = {}) {
    setBusy(true);
    setError(null);
    const before = { strength: team.strength, choice: lineupChoice(lineup), custom: team.lineup_custom };
    try {
      onSaved(await call());
      setPrevious(keepHistory ? before : null);
      setFlash(changed);
    } catch (err) {
      setError(err);
      throw err;
    } finally {
      setBusy(false);
    }
  }

  // `candidate` prend la place `slotNumber` (échange s'il était titulaire).
  function place(slotNumber, candidate) {
    const from = lineup.find((entry) => entry.player.id === candidate.id)?.slot.number;
    const next = movePlayer(lineup, slotNumber, candidate);
    if (next === lineup) return Promise.resolve();
    return commit(() => save(lineupChoice(next)), { changed: [slotNumber, from].filter(Boolean) });
  }

  const drag = useDrag((player, slotNumber) => {
    place(slotNumber, player).catch(() => {});
  });

  return {
    team,
    lineup,
    picking: picking === null ? null : (lineup.find((entry) => entry.slot.number === picking) ?? null),
    pick: (slotNumber) => setPicking(slotNumber),
    closePicker: () => setPicking(null),
    place,
    busy,
    error,
    flash,
    previous,
    drag,
    undo: () =>
      previous &&
      commit(() => (previous.custom ? save(previous.choice) : reset()), { keepHistory: false }).catch(() => {}),
    reset: () => commit(reset).catch(() => {}),
  };
}

// Glisser-déposer au pointeur (souris et doigt) : on lâche un joueur sur une place du
// terrain (élément `[data-slot]`). Un appui sans glissement reste un clic.
function useDrag(onDrop) {
  const [drag, setDrag] = useState(null); // { player, from, x, y, over }
  const swallowClick = useRef(false);
  const dropRef = useRef(onDrop);
  dropRef.current = onDrop;

  function begin(event, payload) {
    if (event.button !== 0) return;
    const start = { x: event.clientX, y: event.clientY };
    let active = false;
    const overAt = (e) => {
      const target = document.elementFromPoint(e.clientX, e.clientY)?.closest("[data-slot]");
      return target ? Number(target.dataset.slot) : null;
    };
    const move = (e) => {
      if (!active && Math.hypot(e.clientX - start.x, e.clientY - start.y) < DRAG_THRESHOLD) return;
      active = true;
      setDrag({ ...payload, x: e.clientX, y: e.clientY, over: overAt(e) });
    };
    const stop = (e, dropped) => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", cancel);
      if (!active) return;
      swallowClick.current = true;
      setTimeout(() => {
        swallowClick.current = false;
      }, 0);
      setDrag(null);
      const over = dropped ? overAt(e) : null;
      if (over !== null && over !== payload.from) dropRef.current(payload.player, over);
    };
    const up = (e) => stop(e, true);
    const cancel = (e) => stop(e, false);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", cancel);
  }

  return {
    state: drag,
    begin,
    // Vrai juste après un glissement : le clic qui suit ne doit pas ouvrir la fenêtre.
    swallowed: () => swallowClick.current,
  };
}

// Le XV sur le terrain. Toucher un joueur ouvre le choix de son remplaçant ; on peut
// aussi le faire glisser sur une autre place (échange).
export function LineupPitch({ editor, captainId, style }) {
  const { team, lineup, drag, flash } = editor;
  const dragging = drag.state;
  const kickerId = team.strength.kicker_id;

  const markers = lineup.map(({ slot, player }) => {
    const rating = ratingAt(team, player, slot.position);
    const off = player.position !== slot.position;
    const badges = [];
    if (player.id === captainId) badges.push({ kind: "captain", text: "C", title: "Capitaine" });
    if (player.id === kickerId) badges.push({ kind: "kicker", text: "B", title: "Buteur" });
    let state;
    if (dragging) {
      if (dragging.player.id === player.id) state = "source";
      else state = dragging.over === slot.number ? "over" : "target";
    } else if (editor.picking?.slot.number === slot.number) state = "selected";
    else if (flash.includes(slot.number)) state = "flash";
    return {
      key: slot.number,
      x: slot.x,
      y: slot.y,
      number: slot.number,
      label: player.last_name,
      note: formatNote(rating),
      off,
      badges,
      state,
      extra: <InjuryIcon injury={player.injury} />,
      title: [
        `${player.name} · ${POSITIONS[player.position].label}`,
        `note au poste ${formatNote(rating)}`,
        off && `hors poste (n° ${slot.number} : ${POSITIONS[slot.position].label.toLowerCase()})`,
        player.id === captainId && "capitaine",
        player.id === kickerId && "buteur",
      ]
        .filter(Boolean)
        .join(" · "),
      entry: { slot, player },
    };
  });

  return (
    <>
      <Pitch
        markers={markers}
        style={style}
        onPick={(marker) => {
          if (!drag.swallowed()) editor.pick(marker.key);
        }}
        markerProps={(marker) => ({
          "data-slot": marker.key,
          disabled: editor.busy,
          onPointerDown: (event) => drag.begin(event, { player: marker.entry.player, from: marker.key }),
        })}
      />
      {dragging && createPortal(<DragGhost editor={editor} />, document.body)}
    </>
  );
}

// Sous le terrain : comment s'en servir et ce que disent les marques.
export function LineupLegend() {
  return (
    <figcaption className="muted compo-legend">
      <span>Touche un joueur pour le remplacer, ou fais-le glisser sur une autre place.</span>
      <span>
        Sous le nom : la note au poste · <span className="compo-legend__off">anneau</span> hors poste · C capitaine · B
        buteur
      </span>
    </figcaption>
  );
}

// Ce qui suit le pointeur pendant un glissement : le joueur, et sur une place, sa note
// au poste comparée à celle du titulaire.
function DragGhost({ editor }) {
  const { team, lineup } = editor;
  const { player, x, y, over, from } = editor.drag.state;
  const target = over === null ? null : lineup.find((entry) => entry.slot.number === over);
  let detail = null;
  if (target && over !== from) {
    const mine = ratingAt(team, player, target.slot.position);
    const theirs = ratingAt(team, target.player, target.slot.position);
    detail = (
      <>
        n° {over} · au poste {formatNote(mine)} <Delta value={mine - theirs} />
        <span className="drag-ghost__swap">
          {from ? `échange avec ${target.player.last_name}` : `à la place de ${target.player.last_name}`}
        </span>
      </>
    );
  }
  return (
    <div className="drag-ghost" style={{ left: x, top: y }}>
      <span className="drag-ghost__disc">{from ?? POSITION_SHORT[player.position]}</span>
      <span className="drag-ghost__text">
        <strong>{player.name}</strong>
        <span className="drag-ghost__detail">{detail ?? "Lâche-le sur une place du terrain"}</span>
      </span>
    </div>
  );
}

// Un écart de note : « +0,4 » en vert, « −1,2 » en rouge ; sous 0,05, « = » (ou rien
// avec `quiet`).
export function Delta({ value, quiet = false }) {
  if (Math.abs(value) < 0.05) return quiet ? null : <span className="delta delta--flat">=</span>;
  return (
    <span className={`delta ${value > 0 ? "delta--up" : "delta--down"}`}>
      {value > 0 ? "+" : "−"}
      {formatNote(Math.abs(value))}
    </span>
  );
}

const STRENGTH_LINES = [
  { key: "set_piece", label: "Conquête" },
  { key: "pack", label: "Paquet" },
  { key: "attack", label: "Attaque" },
  { key: "defense", label: "Défense" },
];

// Les notes de l'équipe pour ce XV ; après un changement, l'écart et « Annuler ».
// Dessous, qui a composé (toi ou le staff), `children` (JIFF, doublon…) et les actions.
export function StrengthStrip({ editor, children }) {
  const { team, previous } = editor;
  const { strength } = team;
  const kicker = team.players.find((p) => p.id === strength.kicker_id);
  return (
    <section className="card compo-strip" aria-label="Notes de l'équipe pour ce XV">
      <div className="compo-strip__notes">
        {STRENGTH_LINES.map((line) => (
          <div key={line.key} className="compo-note">
            <span className="compo-note__label">{line.label}</span>
            <span className="compo-note__value">
              {formatNote(strength[line.key])}
              {previous && <Delta quiet value={strength[line.key] - previous.strength[line.key]} />}
            </span>
          </div>
        ))}
        <div className="compo-note" title="Le meilleur pied du XV tire les pénalités et les transformations">
          <span className="compo-note__label">Buteur</span>
          <span className="compo-note__value">
            {strength.kicking}
            {previous && <Delta quiet value={strength.kicking - previous.strength.kicking} />}
          </span>
          {kicker && <span className="compo-note__who">{kicker.last_name}</span>}
        </div>
      </div>
      <div className="compo-strip__foot">
        <span className="compo-owner-group">
          <span className={`compo-owner${team.lineup_custom ? " compo-owner--mine" : ""}`}>
            {team.lineup_custom ? "Ta composition" : "Composition du staff"}
          </span>
          {team.lineup_custom && (
            <button
              type="button"
              className="link-button compo-strip__reset"
              disabled={editor.busy}
              onClick={editor.reset}
            >
              Rendre la main au staff
            </button>
          )}
        </span>
        {children}
        <span className="compo-strip__actions">
          {previous && (
            <button type="button" className="button button--small" disabled={editor.busy} onClick={editor.undo}>
              Annuler
            </button>
          )}
        </span>
      </div>
      {editor.error && <p className="status--error compo-strip__error">{editor.error.message}</p>}
    </section>
  );
}

// Peut-on faire glisser ce joueur (depuis une liste) sur le terrain ?
export const canDrag = (player) => unavailability(player) === null;
