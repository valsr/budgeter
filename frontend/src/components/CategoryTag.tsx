export function hexToRgba(hex: string, alpha: number): string {
  const clean = hex.replace("#", "");
  const r = parseInt(clean.substring(0, 2), 16);
  const g = parseInt(clean.substring(2, 4), 16);
  const b = parseInt(clean.substring(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export function CategoryTag({ label, color }: { label: string; color: string }) {
  return (
    <span className="tag" style={{ background: hexToRgba(color, 0.15), color }}>
      {label}
    </span>
  );
}
