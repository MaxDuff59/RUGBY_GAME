// Niveau de 1 à `max`, dessiné en petits carrés pleins ou vides.
export default function Level({ value, max = 5, label }) {
  return (
    <span className="level" role="img" aria-label={label ?? `${value} sur ${max}`}>
      {Array.from({ length: max }, (_, index) => (
        <span key={index} className={index < value ? "level__dot level__dot--on" : "level__dot"} />
      ))}
    </span>
  );
}
