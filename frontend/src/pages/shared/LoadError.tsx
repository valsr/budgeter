/** A tab's data didn't load. Shown in place of the tab's empty state, which would otherwise suggest
 * there is simply nothing there yet. */
export function LoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div>
      <p className="sub" role="alert" style={{ color: "var(--c5)", marginBottom: 12 }}>
        {message}
      </p>
      <button className="btn" onClick={onRetry}>
        Retry
      </button>
    </div>
  );
}
