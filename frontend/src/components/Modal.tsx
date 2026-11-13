import { useEffect, useRef, type ReactNode } from "react";

/** Open modals, innermost last: Escape only cancels the topmost one. */
const openModals: object[] = [];

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

  // Escape is the Cancel button. Clicking the backdrop deliberately does nothing, so a
  // stray click outside can't throw away what's been typed into the form.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  useEffect(() => {
    const token = {};
    openModals.push(token);
    function onKeyDown(e: KeyboardEvent) {
      // A control inside the modal (e.g. an open dropdown) that handles Escape itself
      // calls preventDefault() to keep the modal open.
      if (e.key !== "Escape" || e.defaultPrevented) return;
      if (openModals[openModals.length - 1] !== token) return;
      e.preventDefault();
      onCloseRef.current();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      openModals.splice(openModals.indexOf(token), 1);
    };
  }, []);

  return (
    <div className="overlay open">
      <div className="modal" style={resolvedWidth ? { width: resolvedWidth } : undefined}>
        <h2>{title}</h2>
        <div className="modal-body">{children}</div>
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
