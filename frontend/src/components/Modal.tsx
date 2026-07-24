import type { ReactNode } from "react";

interface ModalProps {
  title: string;
  onClose: () => void;
  onSubmit?: () => void;
  submitLabel?: string;
  submitDisabled?: boolean;
  wide?: boolean;
  children: ReactNode;
}

export function Modal({ title, onClose, onSubmit, submitLabel = "Save", submitDisabled, wide, children }: ModalProps) {
  return (
    <div
      className="overlay open"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal" style={wide ? { width: 960 } : undefined}>
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
