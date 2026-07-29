export function hexToRgba(hex: string, alpha: number): string {
  const clean = hex.replace("#", "");
  const r = parseInt(clean.substring(0, 2), 16);
  const g = parseInt(clean.substring(2, 4), 16);
  const b = parseInt(clean.substring(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export function CategoryTag({
  label,
  color,
  onRemove,
}: {
  label: string;
  color: string;
  /** Renders a "| x" control inside the pill; clicking it unassigns the
   * category instead of opening the cell for editing. */
  onRemove?: () => void;
}) {
  return (
    <span className="tag" style={{ background: hexToRgba(color, 0.15), color }}>
      {label}
      {onRemove && (
        <span
          className="tag-remove"
          title="Remove category"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
        >
          ×
        </span>
      )}
    </span>
  );
}
