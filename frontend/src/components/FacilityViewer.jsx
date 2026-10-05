import { useState } from "react";

import { FACILITIES, formatInteger, formatMoney } from "../format.js";
import CampusView, { CAMPUS } from "./CampusView.jsx";
import Level from "./Level.jsx";
import Modal from "./Modal.jsx";
import StadiumView from "./StadiumView.jsx";

const DEFAULT_VIEW = { yaw: -32, tilt: 56 };

// Fenêtre « Voir » d'une infrastructure : la scène 3D à gauche, le panneau d'action à
// droite. Pour le stade, on clique une tribune pour voir ses emplacements et y
// installer un aménagement du catalogue ; pour les centres, le panneau liste ce que
// chaque niveau apporte.
export default function FacilityViewer({ kind, data, onClose, onInstall, onUpgrade }) {
  const [view, setView] = useState(DEFAULT_VIEW);
  const [side, setSide] = useState(null);
  const info = FACILITIES[kind];
  const upgrade = data.upgrades.find((u) => u.kind === kind);
  const isStadium = kind === "stadium";

  return (
    <Modal onClose={onClose}>
      <div className="review__head">
        <div>
          <p className="eyebrow">Infrastructures</p>
          <h2 className="affair__title">{info.label}</h2>
        </div>
        <div className="viewer__head-right">
          {isStadium ? (
            <div className="stat">
              <span className="big-num">{formatInteger(data.stadium.capacity)}</span>
              <span className="muted">places</span>
            </div>
          ) : (
            <div className="stat">
              <Level value={upgrade.current} label={`niveau ${upgrade.current} sur 5`} />
              <span className="muted">niveau {upgrade.current} sur 5</span>
            </div>
          )}
          <button type="button" className="button" onClick={onClose}>
            Fermer
          </button>
        </div>
      </div>

      <div className="viewer">
        <div className="viewer__scene card">
          {isStadium ? (
            <StadiumView
              stadium={data.stadium}
              selected={side}
              onSelect={(s) => setSide((current) => (current === s ? null : s))}
              view={view}
              onTurn={setView}
            />
          ) : (
            <CampusView kind={kind} level={upgrade.current} view={view} onTurn={setView} />
          )}
          <div className="viewer__hint">
            <span className="muted">
              Glisse pour tourner{isStadium ? " · clique une tribune pour l'aménager" : ""}
            </span>
            <button type="button" className="button button--small" onClick={() => setView(DEFAULT_VIEW)}>
              Recentrer
            </button>
          </div>
        </div>

        <aside className="viewer__panel">
          {isStadium ? (
            <StandPanel
              stadium={data.stadium}
              side={side}
              balance={data.balance}
              onInstall={onInstall}
            />
          ) : (
            <CampusPanel kind={kind} upgrade={upgrade} onUpgrade={onUpgrade} />
          )}
        </aside>
      </div>
    </Modal>
  );
}

function StandPanel({ stadium, side, balance, onInstall }) {
  const installed = stadium.stands.reduce((sum, stand) => sum + stand.amenities.length, 0);
  const stand = stadium.stands.find((s) => s.side === side);
  const labels = Object.fromEntries(stadium.catalogue.map((a) => [a.kind, a.label]));

  if (!stand) {
    return (
      <>
        <p className="eyebrow">Tribunes</p>
        <p className="viewer__text">
          Clique une tribune pour y installer des panneaux sponsors, une buvette, des loges…
          Chaque tribune a {stadium.stands[0].slots} emplacements ; agrandir le stade en ajoute.
        </p>
        <ul className="viewer__facts">
          <li>
            <span className="muted">Aménagements installés</span>
            <strong>
              {installed} / {stadium.stands.length * stadium.stands[0].slots}
            </strong>
          </li>
          {stadium.stands.map((s) => (
            <li key={s.side}>
              <span className="muted">{s.label}</span>
              <strong>{s.amenities.length ? s.amenities.map((k) => labels[k]).join(", ") : "—"}</strong>
            </li>
          ))}
        </ul>
      </>
    );
  }

  const free = stand.slots - stand.amenities.length;
  return (
    <>
      <p className="eyebrow">{stand.label}</p>
      <ol className="slots">
        {Array.from({ length: stand.slots }, (_, i) => {
          const kind = stand.amenities[i];
          return (
            <li key={i} className={kind ? "slot" : "slot slot--empty"}>
              <span className="slot__index">{i + 1}</span>
              {kind ? labels[kind] : "Emplacement libre"}
            </li>
          );
        })}
      </ol>

      <p className="eyebrow" style={{ marginTop: 18 }}>
        Catalogue
      </p>
      <ul className="catalogue">
        {stadium.catalogue.map((amenity) => {
          const full = free === 0;
          const maxed = amenity.stadium_max !== null && amenity.installed >= amenity.stadium_max;
          const affordable = balance >= amenity.cost;
          const reason = full
            ? "Tribune complète : agrandis le stade"
            : maxed
              ? amenity.stadium_max === 1
                ? "Déjà installé"
                : `${amenity.stadium_max} au maximum dans le stade`
              : !affordable
                ? "Trésorerie insuffisante"
                : null;
          return (
            <li key={amenity.kind} className="catalogue__row">
              <div>
                <div style={{ fontWeight: 600 }}>{amenity.label}</div>
                <div className="muted">
                  {amenity.effect} · {formatMoney(amenity.cost)}
                  {amenity.stadium_max !== null && ` · ${amenity.installed}/${amenity.stadium_max}`}
                </div>
              </div>
              <button
                type="button"
                className="button button--small button--primary"
                disabled={reason !== null}
                title={reason ?? undefined}
                onClick={() => onInstall(stand, amenity)}
              >
                Installer
              </button>
            </li>
          );
        })}
      </ul>
    </>
  );
}

function CampusPanel({ kind, upgrade, onUpgrade }) {
  return (
    <>
      <p className="eyebrow">Installations</p>
      <ol className="slots">
        {CAMPUS[kind].map((stage) => {
          const built = stage.level <= upgrade.current;
          return (
            <li key={stage.level} className={built ? "slot" : "slot slot--empty"}>
              <span className="slot__index">{stage.level}</span>
              {stage.label}
            </li>
          );
        })}
      </ol>
      {upgrade.next === null ? (
        <p className="muted" style={{ marginTop: 18 }}>Niveau maximum atteint.</p>
      ) : (
        <div className="facility__upgrade" style={{ marginTop: 18 }}>
          <div>
            <div style={{ fontWeight: 600 }}>Passer au niveau {upgrade.next}</div>
            <div className="muted">Coût : {formatMoney(upgrade.cost)}</div>
          </div>
          <button
            type="button"
            className="button button--primary"
            disabled={!upgrade.affordable}
            title={upgrade.affordable ? undefined : "Trésorerie insuffisante"}
            onClick={() => onUpgrade(upgrade)}
          >
            Améliorer
          </button>
        </div>
      )}
    </>
  );
}
