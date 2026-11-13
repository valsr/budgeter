import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Modal } from "./Modal";

describe("Modal", () => {
  it("does not close when the backdrop is clicked", () => {
    const onClose = vi.fn();
    const { container } = render(
      <Modal title="Edit" onClose={onClose}>
        body
      </Modal>,
    );
    fireEvent.click(container.querySelector(".overlay")!);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("treats Escape as Cancel", () => {
    const onClose = vi.fn();
    render(
      <Modal title="Edit" onClose={onClose}>
        body
      </Modal>,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("ignores an Escape that a control inside already handled", () => {
    const onClose = vi.fn();
    render(
      <Modal title="Edit" onClose={onClose}>
        <input
          aria-label="field"
          onKeyDown={(e) => {
            if (e.key === "Escape") e.preventDefault();
          }}
        />
      </Modal>,
    );
    fireEvent.keyDown(screen.getByLabelText("field"), { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });

  it("only cancels the topmost of stacked modals", () => {
    const outer = vi.fn();
    const inner = vi.fn();
    render(
      <>
        <Modal title="Outer" onClose={outer}>
          outer
        </Modal>
        <Modal title="Inner" onClose={inner}>
          inner
        </Modal>
      </>,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(inner).toHaveBeenCalledTimes(1);
    expect(outer).not.toHaveBeenCalled();
  });
});
