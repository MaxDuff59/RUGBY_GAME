import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useOutletContext } from "react-router-dom";

import { api } from "../api.js";
import ClubCrest from "../components/ClubCrest.jsx";
import PlayerAvatar from "../components/PlayerAvatar.jsx";
import ScoutBadge from "../components/ScoutBadge.jsx";
import { useConfirm } from "../components/ConfirmDialog.jsx";
import Level from "../components/Level.jsx";
import Modal from "../components/Modal.jsx";
import SortHeader from "../components/SortHeader.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import {
  DEALS,
  NEGOTIATION_STAGES,
  POSITIONS,
  formatContractEnd,
  formatLastSeason,
  formatMoney,
  formatNote,
  formatShortDate,
} from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { PHONE_QUERY, useMediaQuery } from "../hooks/useMediaQuery.js";
import { useSort } from "../hooks/useSort.js";
import { SLOTS, matchSheet } from "../lineup.js";

// Filtres par voie de recrutement.
const WAYS = [
  { key: null, label: "Tous" },
  { key: "precontract", label: "Pré-contrat" },
  { key: "transfer", label: "Transfert" },
  { key: "loan", label: "Prêt" },
  { key: "free", label: "Agents libres" },
];

// Téléphone : tris du marché proposés dans une liste déroulante.
const PHONE_SORTS = [
  { key: "player.value", dir: "desc", label: "Valeur" },
  { key: "player.overall", dir: "desc", label: "Note" },
  { key: "player.age", dir: "asc", label: "Âge" },
  { key: "player.wage", dir: "asc", label: "Salaire" },
];
const PHONE_PAGE = 30; // joueurs affichés par « Voir plus »

const hasWay = (listing, way) =>
  way === null ||
  (way === "free" && listing.free_agent) ||
  (way === "precontract" && listing.precontract) ||
  (way === "transfer" && listing.transfer_fee !== null) ||
  (way === "loan" && listing.loanable);

// Places du XV par poste (2 piliers, 1 talonneur...) : de quoi situer une recrue
// dans notre effectif. Un effectif sain en compte au moins le double à chaque poste.
const STARTERS = SLOTS.reduce((count, slot) => ({ ...count, [slot.position]: (count[slot.position] ?? 0) + 1 }), {});

// Nos pros par poste, du meilleur au moins bon (notes générales).
function depthOf(players) {
  const depth = Object.fromEntries(Object.keys(POSITIONS).map((key) => [key, []]));
  for (const player of players) if (player.squad !== "youth") depth[player.position].push(player);
  for (const key of Object.keys(depth)) depth[key].sort((a, b) => b.overall - a.overall);
  return depth;
}

// Sa place chez nous : titulaire, doublure ou réserviste, et l'écart avec le moins bon
// de nos titulaires à son poste (null si le poste n'a pas assez de titulaires).
function fitIn(player, depth) {
  const mine = depth[player.position];
  const slots = STARTERS[player.position];
  const better = mine.filter((p) => p.overall > player.overall).length;
  const role = better < slots ? "starter" : better < 2 * slots ? "backup" : "reserve";
  const delta = mine.length >= slots ? player.overall - mine[slots - 1].overall : null;
  return { role, delta };
}

const FIT_LABELS = { starter: "Titulaire", backup: "Doublure", reserve: "Réserviste" };

// Sans accents ni majuscules, pour chercher un nom.
const fold = (text) =>
  text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();

// Recrutement : approcher un joueur, négocier avec son club puis avec lui ; vendre les siens.
// Ordinateur : à gauche le marché (ou l'effectif à vendre) sur toute la hauteur, à droite
// les négociations, le joker et notre effectif poste par poste (un clic filtre le marché).
export default function Transfers() {
  const { career } = useOutletContext();
  const market = useApi(useCallback(api.getTransfers, []));
  const myClub = useApi(useCallback(() => api.getClub(career.club_id), [career.club_id]));

  const [position, setPosition] = useState(null); // null = tous les postes
  const [league, setLeague] = useState(null); // null = tous les championnats
  const location = useLocation();
  const [way, setWay] = useState(location.state?.way ?? null); // l'infirmerie ouvre sur les agents libres
  const [search, setSearch] = useState("");
  const [withinMeans, setWithinMeans] = useState(false);
  const [targetId, setTargetId] = useState(null); // joueur approché
  const confirm = useConfirm();
  const phone = useMediaQuery(PHONE_QUERY);
  const [tab, setTab] = useState("buy"); // « Recruter » ou « Vendre »
  const [shown, setShown] = useState(PHONE_PAGE); // téléphone : joueurs du marché affichés

  const depth = useMemo(() => depthOf(myClub.data?.players ?? []), [myClub.data]);
  // Le marché, avec la place qu'aurait chaque joueur chez nous (`fit`, triable).
  const marketRows = useMemo(
    () =>
      (market.data?.listings ?? []).map((listing) => {
        const fit = fitIn(listing.player, depth);
        return { ...listing, fit, fitDelta: fit.delta ?? 99 };
      }),
    [market.data, depth],
  );
  const squadRows = useMemo(() => {
    if (!myClub.data) return [];
    const sheet = matchSheet(myClub.data);
    return myClub.data.players.map((player) => ({ ...player, sheet: sheet.get(player.id) ?? 99 }));
  }, [myClub.data]);
  const listingSort = useSort(marketRows, { key: "player.overall", dir: "desc" });
  const squadSort = useSort(squadRows, { key: "value", dir: "desc" });

  function sell(player) {
    const { balance, squad_size: squadSize, squad_min: squadMin } = market.data;
    const left = depth[player.position].length - 1;
    confirm.ask({
      eyebrow: "Transferts · Vente",
      title: `Vendre ${player.name}`,
      text: `${POSITIONS[player.position].label}, ${player.age} ans, note ${formatNote(player.overall)}. Il part tout de suite dans un autre club, à sa valeur marchande.`,
      rows: [
        { label: "Indemnité perçue", value: formatMoney(player.value) },
        { label: "Salaire libéré", value: formatMoney(player.wage), hint: "par saison" },
        { label: "Trésorerie", from: formatMoney(balance), to: formatMoney(balance + player.value) },
        { label: "Effectif", from: squadSize, to: squadSize - 1, hint: `${squadMin} au minimum` },
        {
          label: POSITIONS[player.position].label,
          from: left + 1,
          to: left,
          hint: `${2 * STARTERS[player.position]} pour être couvert`,
        },
      ],
      warning: "Une vente est définitive.",
      confirmLabel: `Vendre pour ${formatMoney(player.value)}`,
      onConfirm: async () => {
        market.setData(await api.sellPlayer(player.id));
        myClub.reload(); // l'effectif a changé
      },
    });
  }

  // Pendant un rechargement (après une offre, une vente...), on garde la page en
  // place avec les données précédentes : sinon la modale se démonterait.
  const firstLoad = (market.loading && !market.data) || (myClub.loading && !myClub.data);
  if (firstLoad) return <p className="status">Chargement…</p>;
  if (market.error) return <p className="status status--error">{market.error.message}</p>;
  if (myClub.error) return <p className="status status--error">{myClub.error.message}</p>;

  const data = market.data;
  const squadFull = data.squad_size >= data.squad_max;
  const squadAtMinimum = data.squad_size <= data.squad_min;
  const jokerIds = new Set(data.jokers.map((joker) => joker.player.id));
  const jokerPossible = data.joker_slots.length > 0;
  const capRoom = data.salary_cap ? data.salary_cap - data.payroll : Infinity;
  // À sa portée : il discute encore, son salaire tient sous le plafond, et l'indemnité
  // (s'il en faut une) dans la trésorerie. Une estimation : la négociation tranche.
  const affordable = (listing) => {
    if (listing.talks_closed_until) return false;
    if ((listing.wage_demand ?? listing.player.wage) > capRoom) return false;
    if (listing.free_agent || listing.loanable || (listing.precontract && !listing.signed_with)) return true;
    return listing.transfer_fee !== null && listing.transfer_fee <= data.balance;
  };
  const query = fold(search.trim());
  const listings = listingSort.rows.filter(
    (listing) =>
      (position === null || listing.player.position === position) &&
      (league === null || listing.league === league) &&
      hasWay(listing, way) &&
      (!query || fold(listing.player.name).includes(query)) &&
      (!withinMeans || affordable(listing)),
  );
  const listingHeader = (key, label, first = "desc", left = false, title) => (
    <SortHeader
      sortKey={key}
      label={label}
      sort={listingSort.sort}
      onToggle={listingSort.toggle}
      first={first}
      left={left}
      title={title}
    />
  );
  const squadHeader = (key, label, first = "desc", left = false) => (
    <SortHeader sortKey={key} label={label} sort={squadSort.sort} onToggle={squadSort.toggle} first={first} left={left} />
  );
  // Un poste choisi dans « Ton effectif par poste » : le marché filtré dessus.
  const browse = (key) => {
    setPosition((current) => (current === key ? null : key));
    setTab("buy");
    setShown(PHONE_PAGE);
  };

  const negotiationsSection = data.negotiations.length > 0 && (
    <section className="section">
      <div className="section__head">
        <h2 className="eyebrow">Négociations · {data.negotiations.length}</h2>
        {phone && <span className="muted">En cours, et accords qui attendent l'intersaison</span>}
      </div>
      <div className="card">
        <ul className="deal-list">
          {data.negotiations.map((negotiation) => (
            <li key={negotiation.id}>
              <span className={`tag ${negotiation.stage === "agreed" ? "tag--injured" : "tag--fragile"}`}>
                {DEALS[negotiation.kind].label}
              </span>
              <span className="deal-list__body">
                <span className="deal-list__name">{negotiation.player_name}</span>
                <span className="muted">
                  {negotiation.club_name} · {NEGOTIATION_STAGES[negotiation.stage]}
                </span>
              </span>
              {negotiation.stage !== "agreed" && (
                <button type="button" className="button button--small" onClick={() => setTargetId(negotiation.player_id)}>
                  Reprendre
                </button>
              )}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );

  const jokerSection = (jokerPossible || data.jokers.length > 0) && (
    <section className="section">
      <div className="section__head">
        <h2 className="eyebrow" title="Un agent libre en plus de l'effectif, le temps d'une absence de plus de 3 mois">
          Joker médical
        </h2>
        {phone && <span className="muted">Un agent libre le temps d'une longue absence</span>}
      </div>
      <div className="card">
        <ul className="deal-list">
          {data.joker_slots.map((slot) => (
            <li key={slot.injury_id}>
              <span className="tag tag--severe">Possible</span>
              <span className="deal-list__body">
                <span className="deal-list__name">{slot.player.name}</span>
                <span className="muted">
                  {POSITIONS[slot.player.position].label} · {slot.kind} · retour le {formatShortDate(slot.return_date)}
                </span>
              </span>
              <button
                type="button"
                className="button button--small"
                onClick={() => {
                  setWay("free");
                  setPosition(slot.player.position);
                  setTab("buy");
                }}
              >
                Chercher
              </button>
            </li>
          ))}
          {data.jokers.map((joker) => (
            <li key={joker.player.id}>
              <span className="tag tag--light">{joker.status === "ending" ? "Fin de pige" : "En pige"}</span>
              <span className="deal-list__body">
                <Link to={`/joueurs/${joker.player.id}`} className="deal-list__name">
                  {joker.player.name}
                </Link>
                <span className="muted">
                  {POSITIONS[joker.player.position].label} · remplace {joker.injured.name}
                  {joker.status === "ending"
                    ? " · à toi de décider : vrai contrat ou départ"
                    : ` jusqu'au ${formatShortDate(joker.until)}`}
                </span>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );

  return (
    <>
      <header className="page-head">
        <div>
          <h1 className="title">Transferts</h1>
          {!phone && (
            <p className="muted transfers__intro" style={{ margin: "8px 0 0" }}>
              Saison {data.season_year}-{String(data.season_year + 1).slice(2)} · vise les fins de contrat, les prêts et
              les agents libres
            </p>
          )}
        </div>
        <div className="page-head__stats">
          <Stat value={formatMoney(data.balance)} label="trésorerie" />
          <Stat
            value={data.squad_size}
            label={
              phone
                ? `joueurs (${data.squad_min}-${data.squad_max})`
                : `joueurs (de ${data.squad_min} à ${data.squad_max})${data.jokers.length ? ` + ${data.jokers.length} joker${data.jokers.length > 1 ? "s" : ""}` : ""}`
            }
          />
          <Stat value={formatNote(data.my_level)} label={phone ? "niveau du XV" : "niveau de ton XV"} />
          {data.salary_cap && (
            <Stat
              value={formatMoney(data.salary_cap - data.payroll)}
              label={phone ? "sous le plafond" : `sous le plafond salarial (${formatMoney(data.salary_cap)})`}
            />
          )}
        </div>
      </header>

      {confirm.dialog}

      {targetId !== null && (
        <Modal onClose={() => setTargetId(null)}>
          <Negotiation
            playerId={targetId}
            squadFull={squadFull}
            onClose={() => setTargetId(null)}
            onChange={(overview, concluded) => {
              if (overview) market.setData(overview);
              else market.reload();
              if (concluded) myClub.reload();
            }}
          />
        </Modal>
      )}

      {phone && (
        <PhoneTransfers
          tab={tab}
          setTab={setTab}
          data={data}
          listings={listings}
          shown={shown}
          setShown={setShown}
          sort={listingSort}
          way={way}
          setWay={setWay}
          position={position}
          setPosition={setPosition}
          league={league}
          setLeague={setLeague}
          squad={squadSort.rows}
          jokerIds={jokerIds}
          squadAtMinimum={squadAtMinimum}
          jokerPossible={jokerPossible}
          onApproach={setTargetId}
          onSell={sell}
          negotiationsSection={negotiationsSection}
          jokerSection={jokerSection}
        />
      )}

      {!phone && (
        <div className="transfers fill">
          <section className="section transfers__main">
            <div className="transfers__bar">
              <div className="chips" role="tablist" aria-label="Recruter ou vendre">
                <button type="button" role="tab" className="chip" aria-pressed={tab === "buy"} onClick={() => setTab("buy")}>
                  Recruter · {listings.length}
                </button>
                <button type="button" role="tab" className="chip" aria-pressed={tab === "sell"} onClick={() => setTab("sell")}>
                  Vendre · {squadRows.length}
                </button>
              </div>
              {tab === "buy" && (
                <input
                  type="search"
                  className="input transfers__search"
                  placeholder="Chercher un joueur"
                  aria-label="Chercher un joueur"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              )}
            </div>
            {tab === "buy" && (
              <div className="transfers__filters">
                <select
                  className="input tactics__select"
                  aria-label="Type de contrat"
                  value={way ?? ""}
                  onChange={(event) => setWay(event.target.value || null)}
                >
                  {WAYS.map((item) => (
                    <option key={item.label} value={item.key ?? ""}>
                      {item.key === null ? "Tous les contrats" : item.label}
                    </option>
                  ))}
                </select>
                <select
                  className="input tactics__select"
                  aria-label="Filtrer par poste"
                  value={position ?? ""}
                  onChange={(event) => setPosition(event.target.value || null)}
                >
                  <option value="">Tous les postes</option>
                  {Object.entries(POSITIONS).map(([key, info]) => (
                    <option key={key} value={key}>
                      {info.label}
                    </option>
                  ))}
                </select>
                {data.leagues.length > 1 && (
                  <select
                    className="input tactics__select"
                    aria-label="Filtrer par championnat"
                    value={league ?? ""}
                    onChange={(event) => setLeague(event.target.value || null)}
                  >
                    <option value="">Tous les championnats</option>
                    {data.leagues.map((name) => (
                      <option key={name} value={name}>
                        {name}
                      </option>
                    ))}
                  </select>
                )}
                <button
                  type="button"
                  className="chip"
                  aria-pressed={withinMeans}
                  title="Il discute encore, son salaire tient sous le plafond et l'indemnité éventuelle dans ta trésorerie"
                  onClick={() => setWithinMeans(!withinMeans)}
                >
                  Dans mes moyens
                </button>
              </div>
            )}

            {tab === "buy" ? (
              <div className="card table-wrap transfers__table">
                <table className="table">
                  <thead>
                    <tr>
                      {listingHeader("player.name", "Joueur", "asc", true)}
                      {listingHeader("club_name", "Club", "asc", true)}
                      {listingHeader("player.age", "Âge", "asc")}
                      {listingHeader("player.overall", "Note")}
                      {listingHeader(
                        "fitDelta",
                        "Chez toi",
                        "desc",
                        true,
                        "Sa place dans ton effectif, et l'écart avec le moins bon de tes titulaires à son poste",
                      )}
                      {listingHeader("player.wage", "Salaire")}
                      {listingHeader("years_left", "Contrat", "asc")}
                      <th scope="col" className="left">
                        Voies
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {listings.length === 0 && (
                      <tr>
                        <td colSpan={8} className="left muted transfers__empty">
                          Aucun joueur ne correspond à ces filtres.
                        </td>
                      </tr>
                    )}
                    {listings.map((listing) => {
                      const { player } = listing;
                      return (
                        <tr
                          key={player.id}
                          className={`table__row--clickable${player.id === targetId ? " table__row--selected" : ""}`}
                          title={`Approcher ${player.name}`}
                          tabIndex={0}
                          onClick={() => setTargetId(player.id)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") setTargetId(player.id);
                          }}
                        >
                          <td className="left">
                            <div className="person">
                              <PlayerAvatar src={player.photo} size={32} />
                              <div className="transfers__person">
                                <div style={{ fontWeight: 600 }}>{player.name}</div>
                                <div className="muted">{POSITIONS[player.position].label}</div>
                              </div>
                            </div>
                          </td>
                          <td className="left">
                            {listing.free_agent ? (
                              <>
                                <div>Sans club</div>
                                <div className="muted">dernier contrat {formatLastSeason(player.contract_until)}</div>
                              </>
                            ) : (
                              <>
                                <div className="with-crest transfers__club">
                                  <ClubCrest name={listing.club_name} size={18} />
                                  <span>{listing.club_name}</span>
                                </div>
                                <div className="muted">
                                  {listing.league} · {listing.playing_time}
                                </div>
                              </>
                            )}
                          </td>
                          <td className="muted">{player.age}</td>
                          <td
                            className="note"
                            title={player.scouting === "estimate" ? "Estimée : aucun recruteur ne l'a supervisé" : undefined}
                          >
                            {player.scouting === "estimate" && <span className="transfers__approx">≈</span>}
                            {formatNote(player.overall)}
                          </td>
                          <td className="left">
                            <Fit fit={listing.fit} />
                          </td>
                          <td className="muted">{formatMoney(player.wage)}</td>
                          <td className={listing.precontract || listing.free_agent ? "cell--strong" : "muted"}>
                            {listing.free_agent ? "Libre" : formatContractEnd(player.contract_until)}
                          </td>
                          <td className="left transfers__ways">
                            <Ways listing={listing} jokerPossible={jokerPossible} />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <p className="table__note">
                  Chez toi : titulaire, doublure ou réserviste dans ton effectif à son poste, et l'écart de note avec le
                  moins bon de tes titulaires. Contrat : fin en juin de l'année indiquée, en gras quand il reste une saison
                  (négociable sans indemnité). Libre : agent libre, il signe tout de suite sans indemnité. Salaires par
                  saison ; l'indemnité demandée figure dans les voies. ≈ : note estimée, sans rapport de recruteur. Clique
                  une ligne pour l'approcher.
                </p>
              </div>
            ) : (
              <div className="card table-wrap transfers__table">
                <table className="table">
                  <thead>
                    <tr>
                      {squadHeader("name", "Joueur", "asc", true)}
                      {squadHeader("sheet", "Rôle", "asc", true)}
                      {squadHeader("age", "Âge", "asc")}
                      {squadHeader("overall", "Note")}
                      {squadHeader("wage", "Salaire")}
                      {squadHeader("contract_until", "Contrat", "asc")}
                      {squadHeader("value", "Valeur")}
                      <th scope="col" aria-label="Vendre"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {squadSort.rows.map((player) => (
                      <tr key={player.id}>
                        <td className="left">
                          <div className="person">
                            <PlayerAvatar src={player.photo} size={32} />
                            <div>
                              <div style={{ fontWeight: 600 }}>{player.name}</div>
                              <div className="muted">{POSITIONS[player.position].label}</div>
                            </div>
                          </div>
                        </td>
                        <td className="left">
                          <Role number={player.sheet} />
                        </td>
                        <td className="muted">{player.age}</td>
                        <td className="note">{formatNote(player.overall)}</td>
                        <td className="muted">{formatMoney(player.wage)}</td>
                        <td className={player.contract_until <= data.season_year ? "cell--strong" : "muted"}>
                          {player.loaned_from
                            ? `Prêt · ${player.loaned_from_name}`
                            : jokerIds.has(player.id)
                              ? "Joker · pige"
                              : formatContractEnd(player.contract_until)}
                        </td>
                        <td style={{ fontWeight: 600 }}>{formatMoney(player.value)}</td>
                        <td>
                          <button
                            type="button"
                            className="button button--small"
                            disabled={squadAtMinimum || player.loaned_from !== null || jokerIds.has(player.id)}
                            title={
                              player.loaned_from !== null
                                ? "Un joueur prêté ne se vend pas"
                                : jokerIds.has(player.id)
                                  ? "Un joker médical ne se vend pas"
                                  : squadAtMinimum
                                    ? `Effectif minimum (${data.squad_min})`
                                    : undefined
                            }
                            onClick={() => sell(player)}
                          >
                            Vendre
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="table__note">
                  Un joueur se vend à sa valeur, tout de suite, à un club du championnat. Rôle : sa place sur la feuille
                  du prochain match. Contrat en gras : il part libre en fin de saison s'il n'est pas prolongé.
                </p>
              </div>
            )}
          </section>

          <aside className="transfers__aside">
            {negotiationsSection}
            {jokerSection}
            <DepthPanel depth={depth} position={position} onPick={browse} />
          </aside>
        </div>
      )}
    </>
  );
}

// Sa place chez nous, en une pastille : « Titulaire +1,2 », « Doublure −0,4 »...
function Fit({ fit }) {
  return (
    <span className={`fit fit--${fit.role}`}>
      {FIT_LABELS[fit.role]}
      {fit.delta !== null && (
        <span className="fit__delta">
          {fit.delta >= 0 ? "+" : "−"}
          {formatNote(Math.abs(fit.delta))}
        </span>
      )}
    </span>
  );
}

// Sa place sur la feuille du prochain match (numéro de matchSheet, 99 sinon).
function Role({ number }) {
  if (number <= 15) return <span className="fit fit--starter">Titulaire · n° {number}</span>;
  if (number <= 23) return <span className="fit fit--backup">Remplaçant · n° {number}</span>;
  return <span className="muted">Hors feuille</span>;
}

// Notre effectif poste par poste : combien, et la note de nos titulaires. Un poste
// court (moins du double de ses places dans le XV) ressort ; un clic filtre le marché.
function DepthPanel({ depth, position, onPick }) {
  return (
    <section className="section">
      <div className="section__head">
        <h2 className="eyebrow">Ton effectif par poste</h2>
        <span className="muted">clic : le marché</span>
      </div>
      <div className="card">
        <ul className="depth">
          {Object.entries(POSITIONS).map(([key, info]) => {
            const players = depth[key];
            const need = 2 * STARTERS[key];
            const short = players.length < need;
            const starters = players.slice(0, STARTERS[key]);
            const injured = players.filter((p) => p.injury?.status === "active").length;
            return (
              <li key={key}>
                <button
                  type="button"
                  className="depth__row"
                  aria-pressed={position === key}
                  title={`${players.length} ${info.label.toLowerCase()}${players.length > 1 ? "s" : ""} pour ${STARTERS[key]} place${STARTERS[key] > 1 ? "s" : ""} dans le XV${injured ? ` · ${injured} blessé${injured > 1 ? "s" : ""}` : ""}`}
                  onClick={() => onPick(key)}
                >
                  <span className="depth__label">{info.label}</span>
                  <span className="depth__dots" aria-hidden="true">
                    {Array.from({ length: Math.max(need, players.length) }, (_, i) => (
                      <span
                        key={i}
                        className={`depth__dot${i >= players.length ? " depth__dot--missing" : i < STARTERS[key] ? " depth__dot--starter" : ""}`}
                      />
                    ))}
                  </span>
                  <span className={`depth__count${short ? " depth__count--short" : ""}`}>
                    {players.length}/{need}
                  </span>
                  <span className="depth__note">
                    {starters.length ? formatNote(starters.reduce((sum, p) => sum + p.overall, 0) / starters.length) : "–"}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
        <p className="table__note">
          Points noirs : tes titulaires ; en pointillé : ce qui manque pour doubler chaque place. À droite, la note
          moyenne de tes titulaires au poste.
        </p>
      </div>
    </section>
  );
}

// Téléphone : deux onglets, « Recruter » (négociations, joker, marché en liste) et
// « Vendre » (l'effectif en liste). Chaque joueur tient sur deux ou trois lignes ; on
// touche une ligne du marché pour l'approcher.
function PhoneTransfers({
  tab,
  setTab,
  data,
  listings,
  shown,
  setShown,
  sort,
  way,
  setWay,
  position,
  setPosition,
  league,
  setLeague,
  squad,
  jokerIds,
  squadAtMinimum,
  jokerPossible,
  onApproach,
  onSell,
  negotiationsSection,
  jokerSection,
}) {
  const sortValue = PHONE_SORTS.find((item) => item.key === sort.sort?.key) ?? PHONE_SORTS[0];
  return (
    <>
      <div className="chips" role="group" aria-label="Onglet">
        <button type="button" className="chip" aria-pressed={tab === "buy"} onClick={() => setTab("buy")}>
          Recruter
        </button>
        <button type="button" className="chip" aria-pressed={tab === "sell"} onClick={() => setTab("sell")}>
          Vendre
        </button>
      </div>

      {tab === "buy" && negotiationsSection}
      {tab === "buy" && jokerSection}

      {tab === "buy" && (
        <section className="section">
          <div className="section__head">
            <h2 className="eyebrow">Marché · {listings.length} joueurs</h2>
            <label className="muted market-sort">
              Trier par{" "}
              <select
                className="input tactics__select"
                value={sortValue.key}
                onChange={(event) => {
                  const item = PHONE_SORTS.find((candidate) => candidate.key === event.target.value);
                  sort.toggle(item.key, item.dir);
                }}
              >
                {PHONE_SORTS.map((item) => (
                  <option key={item.key} value={item.key}>
                    {item.label.toLowerCase()}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="chips chips--scroll" role="group" aria-label="Filtrer par voie">
            {WAYS.map((item) => (
              <button
                key={item.label}
                type="button"
                className="chip"
                aria-pressed={way === item.key}
                onClick={() => {
                  setWay(item.key);
                  setShown(PHONE_PAGE);
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="filter-row">
            <select
              className="input tactics__select"
              aria-label="Filtrer par poste"
              value={position ?? ""}
              onChange={(event) => {
                setPosition(event.target.value || null);
                setShown(PHONE_PAGE);
              }}
            >
              <option value="">Tous les postes</option>
              {Object.entries(POSITIONS).map(([key, info]) => (
                <option key={key} value={key}>
                  {info.label}
                </option>
              ))}
            </select>
            {data.leagues.length > 1 && (
              <select
                className="input tactics__select"
                aria-label="Filtrer par championnat"
                value={league ?? ""}
                onChange={(event) => {
                  setLeague(event.target.value || null);
                  setShown(PHONE_PAGE);
                }}
              >
                <option value="">Tous championnats</option>
                {data.leagues.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            )}
          </div>

          {listings.length === 0 ? (
            <p className="status">Aucun joueur ne correspond à ces filtres.</p>
          ) : (
            <ul className="card market-list">
              {listings.slice(0, shown).map((listing) => (
                <ListingItem key={listing.player.id} listing={listing} jokerPossible={jokerPossible} onApproach={onApproach} />
              ))}
            </ul>
          )}
          {listings.length > shown && (
            <button type="button" className="button market-more" onClick={() => setShown(shown + PHONE_PAGE)}>
              Voir {Math.min(PHONE_PAGE, listings.length - shown)} joueurs de plus
            </button>
          )}
        </section>
      )}

      {tab === "sell" && (
        <section className="section">
          <div className="section__head">
            <h2 className="eyebrow">Ton effectif · {squad.length} joueurs</h2>
            <span className="muted">Vente à la valeur, définitive</span>
          </div>
          <ul className="card market-list">
            {squad.map((player) => (
              <li key={player.id} className="market-item">
                <div className="market-item__main">
                  <PlayerAvatar src={player.photo} size={40} />
                  <span className="market-item__body">
                    <span className="market-item__name">{player.name}</span>
                    <span className="muted market-item__meta">
                      {POSITIONS[player.position].label} · {player.age} ans · note {formatNote(player.overall)}
                    </span>
                    <span className="muted market-item__meta">
                      {formatMoney(player.wage)} / saison · contrat {formatContractEnd(player.contract_until)}
                    </span>
                    {squadBadges(player, jokerIds.has(player.id), data.season_year).length > 0 && (
                      <span className="badges">{squadBadges(player, jokerIds.has(player.id), data.season_year)}</span>
                    )}
                  </span>
                  <span className="market-item__side">
                    <span className="market-item__price">{formatMoney(player.value)}</span>
                    <button
                      type="button"
                      className="button button--small"
                      disabled={squadAtMinimum || player.loaned_from !== null || jokerIds.has(player.id)}
                      onClick={() => onSell(player)}
                    >
                      Vendre
                    </button>
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

// Une ligne du marché sur téléphone : touche-la pour approcher le joueur.
function ListingItem({ listing, jokerPossible, onApproach }) {
  const { player } = listing;
  return (
    <li className="market-item">
      <button type="button" className="market-item__main" onClick={() => onApproach(player.id)}>
        <PlayerAvatar src={player.photo} size={40} />
        <span className="market-item__body">
          <span className="market-item__name">{player.name}</span>
          <span className="muted market-item__meta">
            {POSITIONS[player.position].label} · {player.age} ans · {listing.free_agent ? "sans club" : listing.club_name}
          </span>
          <span className="market-item__meta">
            <Fit fit={listing.fit} />
          </span>
          <span className="badges">{listingBadges(listing, jokerPossible)}</span>
        </span>
        <span className="market-item__side">
          <span className="note">
            {player.scouting === "estimate" && <span className="muted">≈ </span>}
            {formatNote(player.overall)}
          </span>
          <span className="market-item__price">{formatMoney(player.value)}</span>
        </span>
      </button>
    </li>
  );
}

function Stat({ value, label }) {
  return (
    <div className="stat">
      <span className="big-num">{value}</span>
      <span className="muted">{label}</span>
    </div>
  );
}

// Les voies ouvertes pour un joueur du marché, en étiquettes.
function Ways({ listing, jokerPossible }) {
  return <span className="badges">{listingBadges(listing, jokerPossible)}</span>;
}

// Les pastilles d'un joueur du marché : comment le recruter, et ce qui le rend abordable.
function listingBadges(listing, jokerPossible) {
  if (listing.talks_closed_until) {
    return [
      <StatusBadge
        key="closed"
        kind="closed"
        label="Ne discute plus"
        title={`Il ne veut plus discuter avant le ${formatShortDate(listing.talks_closed_until)}`}
      />,
    ];
  }
  if (listing.free_agent) {
    const badges = [
      <StatusBadge
        key="free"
        kind="free"
        label={`Libre · ${formatMoney(listing.wage_demand)}`}
        title={`Agent libre : il signe tout de suite, sans indemnité, pour ${formatMoney(listing.wage_demand)} par saison`}
      />,
    ];
    if (jokerPossible) badges.push(<StatusBadge key="joker" kind="joker" label="Joker" title="Peut venir en joker médical" />);
    return badges;
  }
  const badges = [];
  if (listing.signed_with) {
    badges.push(
      <StatusBadge
        key="signed"
        kind="locked"
        label="Déjà engagé"
        title={`Il a signé avec ${listing.signed_with} pour la saison prochaine : seul un prêt reste possible`}
      />,
    );
  }
  if (listing.precontract) {
    badges.push(
      <StatusBadge
        key="ending"
        kind="ending"
        label={`Fin de contrat ${formatContractEnd(listing.player.contract_until)}`}
        title="Dernière année de contrat : négociable sans indemnité"
      />,
    );
  }
  if (listing.transfer_fee !== null) {
    badges.push(
      <StatusBadge
        key="transfer"
        kind="transfer"
        label={`Transfert ${formatMoney(listing.transfer_fee)}`}
        title={`Son club demande ${formatMoney(listing.transfer_fee)}`}
      />,
    );
  }
  if (listing.loanable) badges.push(<StatusBadge key="loan" kind="loan" label="Prêt" title="Son club accepte un prêt" />);
  if (badges.length === 0) {
    badges.push(<StatusBadge key="locked" kind="locked" label="Intransférable" title="Son club ne le laisse pas partir" />);
  }
  if (listing.playing_time === "réserviste") {
    badges.push(<StatusBadge key="bench" kind="bench" label="Réserviste" title="Peu utilisé dans son club" />);
  }
  return badges;
}

// Les pastilles d'un joueur de l'effectif : ce qui empêche ou précipite sa vente.
function squadBadges(player, isJoker, seasonYear) {
  const badges = [];
  if (player.loaned_from) {
    badges.push(<StatusBadge key="loan" kind="loan" label={`Prêté par ${player.loaned_from_name}`} />);
  } else if (isJoker) {
    badges.push(<StatusBadge key="joker" kind="joker" label="Joker médical" />);
  } else if (player.contract_until <= seasonYear) {
    badges.push(
      <StatusBadge key="ending" kind="ending" label="Fin de contrat" title="Part libre en fin de saison s'il n'est pas prolongé" />,
    );
  }
  return badges;
}

// Approche d'un joueur : sa situation, choix de la voie, puis le fil de la négociation.
function Negotiation({ playerId, squadFull, onClose, onChange }) {
  const target = useApi(useCallback(() => api.approachPlayer(playerId), [playerId]));
  const [negotiation, setNegotiation] = useState(null);
  const [talk, setTalk] = useState([]); // fil : { who: "me" | "them", text, ok }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  // La négociation déjà ouverte avec ce joueur, s'il y en a une.
  useEffect(() => {
    const existing = target.data?.negotiation ?? null;
    setNegotiation(existing);
    setTalk(existing ? [{ who: "them", text: existing.message, ok: false }] : []);
    setError(null);
  }, [target.data]);

  const say = (line) => setTalk((previous) => [...previous, line]);

  // Le fil montre toujours les derniers messages (on remonte pour voir les anciens).
  const talkRef = useRef(null);
  useEffect(() => {
    const list = talkRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [talk]);

  async function run(call, onDone) {
    setBusy(true);
    setError(null);
    try {
      onDone(await call());
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const open = (kind, injuryId) =>
    run(
      () => api.openNegotiation(playerId, kind, injuryId),
      (opened) => {
        setNegotiation(opened);
        setTalk([{ who: "them", text: opened.message, ok: false }]);
        onChange(null, false);
      },
    );

  const offer = (payload, label) => {
    say({ who: "me", text: label });
    return run(
      () => api.makeOffer(negotiation.id, payload),
      (result) => {
        setNegotiation(result.negotiation);
        say({ who: "them", text: result.message, ok: result.accepted });
        onChange(result.overview, result.concluded);
      },
    );
  };

  const abandon = () =>
    run(
      () => api.abandonNegotiation(negotiation.id),
      (overview) => {
        setNegotiation(null);
        setTalk([]);
        onChange(overview, false);
      },
    );

  if (target.loading) return <p className="status">Approche…</p>;
  if (target.error) return <p className="status status--error">{target.error.message}</p>;

  const { player, club } = target.data;
  const free = club === null; // agent libre
  const [yearsMin, yearsMax] = target.data.preferred_years;
  const openStage = negotiation && (negotiation.stage === "club" || negotiation.stage === "player");

  return (
    <>
      <div className="section__head">
        <div className="person">
          <PlayerAvatar src={player.photo} size={56} />
          <div>
            <h2 className="eyebrow">Approche</h2>
            <div className="header__name">{player.name}</div>
            <div className="muted">
              {POSITIONS[player.position].label} · {player.age} ans · note {formatNote(player.overall)} ·{" "}
              {free ? "Agent libre" : club.name}
            </div>
            <ScoutBadge player={player} onScouted={() => target.reload()} />
          </div>
        </div>
        <button type="button" className="button button--small" onClick={onClose}>
          Fermer
        </button>
      </div>

      <div className="situation">
        <Fact label={free ? "Dernier salaire" : "Salaire actuel"} value={`${formatMoney(player.wage)} / saison`} />
        {free ? (
          <Fact label="Contrat" value={`aucun · dernier en ${formatLastSeason(player.contract_until)}`} />
        ) : (
          <>
            <Fact label="Contrat" value={`jusqu'en juin ${formatContractEnd(player.contract_until)} (${target.data.years_left} saison${target.data.years_left > 1 ? "s" : ""})`} />
            <Fact label="Dans son club" value={`${target.data.playing_time_now} · niveau ${formatNote(target.data.club_level)}`} />
          </>
        )}
        <Fact label="Chez toi" value={`${target.data.playing_time_here} · niveau ${formatNote(target.data.my_level)}`} />
        <Fact label="Il cherche" value={`un contrat de ${yearsMin} à ${yearsMax} saisons`} />
      </div>

      {error && <p className="status--error" style={{ margin: 0 }}>{error.message}</p>}

      {target.data.talks_closed_until && !negotiation && (
        <p className="negotiation__message" style={{ margin: 0 }}>
          Il ne veut plus discuter avec vous avant le {formatShortDate(target.data.talks_closed_until)}.
        </p>
      )}
      {target.data.grudges > 0 && !target.data.talks_closed_until && !negotiation && (
        <p className="negotiation__message" style={{ margin: 0 }}>
          Il n'a pas oublié vos {target.data.grudges > 1 ? `${target.data.grudges} ruptures passées` : "dernières discussions"} :
          il ouvrira plus haut et sera moins patient.
        </p>
      )}

      {!negotiation && (
        <div className="deal-options">
          {target.data.options.map((option) => {
            // Un pré-contrat attend l'intersaison, un joker vient en plus de l'effectif.
            const blocked = squadFull && option.kind !== "precontract" && option.kind !== "joker";
            return (
              <button
                key={`${option.kind}-${option.injury_id ?? ""}`}
                type="button"
                className="protocol"
                disabled={busy || !option.available || blocked}
                title={blocked ? "Effectif complet" : undefined}
                onClick={() => open(option.kind, option.injury_id)}
              >
                <span className="protocol__name">
                  {DEALS[option.kind].label}
                  {option.injured_name && ` · remplace ${option.injured_name}`}
                </span>
                {option.fee_demand !== null && option.fee_demand !== undefined && (
                  <span className="protocol__line">Le club en espère <strong>{formatMoney(option.fee_demand)}</strong></span>
                )}
                {option.wage_demand !== null && option.wage_demand !== undefined && (
                  <span className="protocol__line">Il espère <strong>{formatMoney(option.wage_demand)}</strong> / saison</span>
                )}
                {option.kind === "loan" && option.available && (
                  <span className="protocol__line">Salaire à ta charge : <strong>{formatMoney(option.wage)}</strong> / saison</span>
                )}
                <span className="protocol__line">{option.reason}</span>
              </button>
            );
          })}
        </div>
      )}

      {negotiation && (
        <>
          <div className="section__head" style={{ flexWrap: "wrap", gap: 12 }}>
            <span className="muted">
              <span className="tag tag--fragile">{DEALS[negotiation.kind].label}</span>{" "}
              {NEGOTIATION_STAGES[negotiation.stage]}
              {openStage && negotiation.rounds > 0 && ` · ${negotiation.rounds} refus`}
              {" · ouverte le "}
              {formatShortDate(negotiation.opened_on)}
            </span>
            {openStage && (
              <span className="patience muted">
                Patience
                <Level value={negotiation.patience} max={6} label={`patience ${negotiation.patience} sur 6`} />
              </span>
            )}
          </div>
          <ul className="talk" aria-live="polite" ref={talkRef}>
            {talk.map((line, index) => (
              <li key={index} className={line.who === "me" ? "talk--me" : line.ok ? "talk--ok" : undefined}>
                {line.text}
              </li>
            ))}
          </ul>
          {openStage && (
            <OfferForm
              key={negotiation.stage}
              negotiation={negotiation}
              player={player}
              years={[yearsMin, yearsMax]}
              busy={busy}
              onOffer={offer}
              onAbandon={abandon}
            />
          )}
          {!openStage && (
            <div>
              <button type="button" className="button" onClick={onClose}>Fermer</button>
            </div>
          )}
        </>
      )}
    </>
  );
}

function Fact({ label, value }) {
  return (
    <div className="stat">
      <span className="eyebrow">{label}</span>
      <span>{value}</span>
    </div>
  );
}

// Formulaire de l'étape en cours : indemnité (club), ou salaire et durée (joueur).
// Pré-rempli avec un point de départ raisonnable (valeur du joueur, salaire
// actuel), pas avec la demande : à toi de monter.
function OfferForm({ negotiation, player, years: [yearsMin, yearsMax], busy, onOffer, onAbandon }) {
  const clubStage = negotiation.stage === "club";
  const isLoan = negotiation.kind === "loan";
  const isJoker = negotiation.kind === "joker"; // une pige : pas de durée à négocier
  const [fee, setFee] = useState(player.value);
  const [wage, setWage] = useState(player.wage);
  const [years, setYears] = useState(Math.min(yearsMax, Math.max(yearsMin, 2)));

  function submit(event) {
    event.preventDefault();
    if (clubStage) onOffer({ fee: Number(fee) }, `Tu proposes ${formatMoney(Number(fee))} d'indemnité.`);
    else if (isLoan) onOffer({}, "Tu confirmes le prêt.");
    else if (isJoker) onOffer({ wage: Number(wage) }, `Tu proposes ${formatMoney(Number(wage))} par saison pour la pige.`);
    else {
      const n = Number(years);
      onOffer(
        { wage: Number(wage), years: n },
        `Tu proposes ${formatMoney(Number(wage))} par saison sur ${n} saison${n > 1 ? "s" : ""}.`,
      );
    }
  }

  return (
    <form className="offer-form" onSubmit={submit}>
      {clubStage && (
        <div className="field">
          <label htmlFor="offer-fee">Indemnité proposée (€) · demande : {formatMoney(negotiation.fee_demand)}</label>
          <input id="offer-fee" className="input" type="number" min="0" step="5000" value={fee} onChange={(e) => setFee(e.target.value)} />
        </div>
      )}
      {!clubStage && !isLoan && (
        <>
          <div className="field">
            <label htmlFor="offer-wage">Salaire (€ / saison) · demande : {formatMoney(negotiation.wage_demand)}</label>
            <input id="offer-wage" className="input" type="number" min="0" step="1000" value={wage} onChange={(e) => setWage(e.target.value)} />
          </div>
          {!isJoker && (
            <div className="field">
              <label htmlFor="offer-years">Durée (saisons)</label>
              <select id="offer-years" className="input" value={years} onChange={(e) => setYears(e.target.value)}>
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>
          )}
        </>
      )}
      <button type="submit" className="button button--primary" disabled={busy}>
        {isLoan ? `Confirmer le prêt (${formatMoney(negotiation.wage_demand)} / saison)` : "Faire l'offre"}
      </button>
      <button type="button" className="button" disabled={busy} onClick={onAbandon}>
        Quitter la table
      </button>
      {!isLoan && (
        <span className="muted">
          Monte à chaque offre : une offre qui ne bouge pas l'agace, une offre dérisoire l'insulte. Proche de sa
          demande, il peut faire un dernier effort. À bout de patience, il ne discute plus.
        </span>
      )}
    </form>
  );
}
