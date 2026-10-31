// Page d'essai des scènes (non livrée par le build) : un faux match en direct, des
// réponses du serveur simulées. ?kind=crunch|dilemma&situation=kick&weather=rain...
// Comme dans le jeu, chaque voie réussit selon ses chances affichées, et un échec tire
// son effet (engine/dilemmas.py) ; `ok=1` ou `ok=0` (`ok2` pour le deux contre un
// enchaîné) force l'issue, `fx=yellow`... force l'effet de l'échec.
import { useState } from "react";
import { createRoot } from "react-dom/client";
import "../styles.css";
import "./scene.css";
import MatchScene from "./MatchScene.jsx";

const q = new URLSearchParams(location.search);
const kind = q.get("kind") ?? "crunch";
const situation = q.get("situation") ?? "kick";
// `coach=1` : un manager tranche pour un de ses joueurs (le 12), sans joueur incarné.
const coach = q.get("coach") === "1";

const players = (base, start) =>
  Array.from({ length: 15 }, (_, i) => ({ id: base + i + 1, name: `Joueur ${start}${i + 1}`, slot_number: i + 1, number: i + 1, rating: 6.5 }));
const home = { club: { id: 1, name: q.get("home") ?? "Stade Toulousain" }, score: 17, players: players(100, "A"), kicker_id: 110 };
const away = { club: { id: 2, name: q.get("away") ?? "Racing 92" }, score: 20, players: players(200, "B"), kicker_id: 210 };
const OPTIONS = {
  kick: ["drop", "grubber", "hands"],
  one_on_one: ["step", "fend", "pass"],
  try_line: ["dive", "offload", "recycle"],
  tackle: ["smash", "hold", "ball"],
  two_on_one: ["finish", "dummy", "give"],
  ruck: ["jackal", "counter", "fold"],
  scrum: ["drive", "steady"],
  lineout: ["maul", "front"],
  throw: ["back", "maul", "front"],
  cross_kick: ["cross", "flat", "touch"],
  box_kick: ["box", "snipe", "serve"],
  counter: ["run", "up_and_under", "touch"],
  touchline: ["outside", "inside", "chip"],
  provocation: ["hit_back", "referee", "walk_away"],
};
// Effet d'une réussite (engine/dilemmas.py).
const WON = { drop: "drop", grubber: "break", step: "break", fend: "break", dive: "try", offload: "assist", recycle: "penalty_won", smash: "turnover", ball: "turnover", finish: "try", dummy: "try", give: "assist", jackal: "turnover", counter: "turnover", drive: "penalty_won", maul: "try", back: "break", cross: "assist", flat: "break", box: "turnover", snipe: "break", run: "break", up_and_under: "turnover", outside: "break", inside: "break", chip: "try", referee: "penalty_won" };
const FOLLOW = { grubber: "two_on_one", step: "two_on_one", fend: "two_on_one", flat: "two_on_one", snipe: "two_on_one", run: "two_on_one", outside: "two_on_one" };
// Effets possibles d'un échec, tirés dans l'ordre comme Option.on_failure.
const FAIL = {
  step: [["lost", 1]], fend: [["lost", 1]], pass: [["lost", 1]],
  dive: [["lost", 1]], offload: [["lost", 1]], recycle: [["lost", 0.5]],
  smash: [["try_conceded", 0.35], ["missed", 1]], hold: [["try_conceded", 0.2], ["missed", 1]], ball: [["yellow", 0.35], ["penalty_conceded", 1]],
  jackal: [["penalty_conceded", 0.7]], drive: [["penalty_conceded", 0.8]], steady: [["lost", 1]],
  maul: [["lost", 1]], front: [["lost", 1]], back: [["lost", 1]],
  grubber: [["lost", 1]], hands: [["lost", 1]], cross: [["lost", 1]], flat: [["lost", 1]], touch: [["lost", 0.5]],
  box: [["lost", 1]], snipe: [["lost", 1]], serve: [["lost", 1]], run: [["penalty_conceded", 0.3], ["lost", 1]], up_and_under: [["lost", 1]],
  outside: [["lost", 1]], inside: [["lost", 1]], chip: [["lost", 1]], hit_back: [["yellow", 0.7], ["penalty_conceded", 1]],
  finish: [["lost", 1]], dummy: [["lost", 1]], give: [["lost", 1]],
}; // prettier-ignore
const failure = (key) => q.get("fx") ?? (FAIL[key] ?? []).find(([, chance]) => Math.random() < chance)?.[0] ?? "none";
// L'issue : forcée par l'adresse, sinon tirée selon les chances affichées.
const draw = (forced, chance) => (forced === null ? Math.random() < chance : forced !== "0");
const dilemmaOf = (key, chained) => ({
  minute: 76,
  situation: key,
  pressure: Number(q.get("pressure") ?? 1.5),
  chained,
  player_id: coach ? 112 : null,
  options: OPTIONS[key].map((option, i) => ({ key: option, success: [0.4, 0.45, 0.75][i], reward: [0.6, 0.6, 0.2][i], cost: [-0.4, -0.3, -0.2][i] })),
});
const base = {
  match_id: Number(q.get("match") ?? 7),
  my_club_id: q.get("us") === "away" ? 2 : 1,
  minute: 76,
  last_minute: 80,
  weather: q.get("weather") ?? "clear",
  knockout: q.get("knockout") === "1",
  stage: "regular",
  extra_time: false,
  finished: false,
  derby: null,
  home,
  away,
  events: [],
  crunch:
    kind === "crunch"
      ? { minute: 76, conversion: 0.7, options: ["kick", "touch", "scrum", "play"].map((key, i) => ({ key, success: [0.72, 0.38, 0.33, 0.27][i] })) }
      : null,
  hero: kind === "dilemma" && !coach ? { player_id: 110, outcomes: [] } : null,
  outcomes: [],
  dilemma: kind === "dilemma" ? dilemmaOf(situation, false) : null,
};

function Lab() {
  const [live, setLive] = useState(base);
  const [busy, setBusy] = useState(false);
  const mine = live.my_club_id === 1 ? "home" : "away";
  const choose = (key) => {
    const options = kind === "crunch" ? live.crunch.options : live.dilemma.options;
    const chance = options.find((option) => option.key === key).success;
    const good = draw(q.get(live.dilemma?.chained ? "ok2" : "ok"), chance);
    const effect = good ? (WON[key] ?? "none") : failure(key);
    setBusy(true);
    setTimeout(() => {
      setBusy(false);
      setLive((current) => {
        const side = current[mine];
        if (kind === "crunch") {
          const scored = good;
          const events = scored
            ? key === "kick"
              ? [{ minute: 76, type: "penalty_goal", club_id: side.club.id, player_name: "Joueur A10", points: 3 }]
              : [
                  { minute: 76, type: "try", club_id: side.club.id, player_name: "Joueur A8", points: 5 },
                  { minute: 76, type: "conversion", club_id: side.club.id, player_name: "Joueur A10", points: 2 },
                ]
            : [];
          const points = events.reduce((sum, e) => sum + e.points, 0);
          return { ...current, crunch: null, events, [mine]: { ...side, score: side.score + points } };
        }
        const now = current.dilemma.situation;
        const scoring = { drop: ["drop_goal", 3], try: ["try", 5], assist: ["try", 5] }[effect];
        const events = scoring ? [{ minute: 76, type: scoring[0], club_id: side.club.id, player_name: "Joueur A11", points: scoring[1] }] : [];
        const outcomes = [...current.outcomes, { minute: 76, situation: now, option: key, success: good, chance, delta: good ? 0.9 : -0.4, effect, pressure: 1.5, player_id: coach ? 112 : null }];
        return {
          ...current,
          dilemma: good && FOLLOW[key] ? dilemmaOf(FOLLOW[key], true) : null,
          events: [...current.events, ...events],
          hero: current.hero && { ...current.hero, outcomes },
          outcomes,
          [mine]: { ...side, score: side.score + events.reduce((sum, e) => sum + e.points, 0) },
        };
      });
    }, 250);
  };
  return (
    <MatchScene
      kind={kind}
      live={live}
      side={live[mine]}
      busy={busy}
      error={null}
      onChoose={choose}
      onResume={() => (document.title = "resume")}
      onClose={() => (document.title = "close")}
      onFail={() => (document.title = "fail")}
      onHandOff={() => (document.title = "handoff")}
    />
  );
}

createRoot(document.getElementById("root")).render(<Lab />);
