import type { ReactNode } from "react";

interface ModalProps {
  title: string;
  onClose: () => void;
  onSubmit?: () => void;
  submitLabel?: string;
  submitDisabled?: boolean;
  wide?: boolean;
  /** Explicit pixel width, for content wider than the standard "wide" (960px)
   * modal — e.g. the budget editor's 12-month table. Takes precedence over `wide`. */
  width?: number;
  children: ReactNode;
}

export function Modal({
  title,
  onClose,
  onSubmit,
  submitLabel = "Save",
  submitDisabled,
  wide,
  width,
  children,
}: ModalProps) {
  const resolvedWidth = width ?? (wide ? 960 : undefined);
  return (
    <div
      className="overlay open"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal" style={resolvedWidth ? { width: resolvedWidth } : undefined}>
        <h2>{title}</h2>
        {children}
        <div className="modal-actions">
          <button type="button" className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          {onSubmit && (
            <button type="button" className="btn" onClick={onSubmit} disabled={submitDisabled}>
              {submitLabel}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
