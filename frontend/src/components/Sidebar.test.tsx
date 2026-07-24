import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { Sidebar } from "./Sidebar";

describe("Sidebar", () => {
  it("renders all six nav items linking to their screens", () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );
    const expected = [
      ["Overview", "/"],
      ["Accounts", "/accounts"],
      ["Transactions", "/transactions"],
      ["Budgets", "/budgets"],
      ["Import", "/import"],
      ["Settings", "/settings"],
    ];
    for (const [label, href] of expected) {
      const link = screen.getByRole("link", { name: label });
      expect(link).toHaveAttribute("href", href);
    }
  });

  it("marks the current route's nav item active", () => {
    render(
      <MemoryRouter initialEntries={["/accounts"]}>
        <Sidebar />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Accounts" })).toHaveClass("active");
    expect(screen.getByRole("link", { name: "Overview" })).not.toHaveClass("active");
  });
});
