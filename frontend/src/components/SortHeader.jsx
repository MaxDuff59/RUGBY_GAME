// En-tête de colonne cliquable, à utiliser avec le hook useSort.
// `first` : sens du premier clic ("asc" ou "desc") ; les colonnes de chiffres
// commencent souvent par "desc" (les plus grands d'abord).
export default function SortHeader({ sortKey, label, sort, onToggle, first = "asc", left, title }) {
  const active = sort?.key === sortKey;
  const ariaSort = active ? (sort.dir === "asc" ? "ascending" : "descending") : "none";
  return (
    <th scope="col" className={left ? "left" : undefined} aria-sort={ariaSort} title={title}>
      <button type="button" className={`sort${active ? " sort--active" : ""}`} onClick={() => onToggle(sortKey, first)}>
        {label}
        <span className="sort__arrow" aria-hidden="true">
          {active ? (sort.dir === "asc" ? "↑" : "↓") : "↕"}
        </span>
      </button>
    </th>
  );
}
