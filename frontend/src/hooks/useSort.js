import { useMemo, useState } from "react";

// Lit une clé en profondeur : get(row, "player.age") -> row.player.age
function get(row, key) {
  return key.split(".").reduce((value, part) => (value == null ? value : value[part]), row);
}

function compare(a, b) {
  if (a == null && b == null) return 0;
  if (a == null) return 1; // les valeurs absentes vont à la fin
  if (b == null) return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), "fr", { numeric: true });
}

// Tri d'un tableau par colonne : { rows, sort, toggle }.
// `initial` : { key, dir } ou null pour garder l'ordre d'origine.
// `toggle(key, firstDir)` trie sur cette colonne, ou inverse le sens si elle
// est déjà active.
export function useSort(rows, initial = null) {
  const [sort, setSort] = useState(initial);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const direction = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => compare(get(a, sort.key), get(b, sort.key)) * direction);
  }, [rows, sort]);

  function toggle(key, firstDir = "asc") {
    setSort((previous) =>
      previous?.key === key
        ? { key, dir: previous.dir === "asc" ? "desc" : "asc" }
        : { key, dir: firstDir },
    );
  }

  return { rows: sorted, sort, toggle };
}
