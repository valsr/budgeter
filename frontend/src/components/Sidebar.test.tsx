import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { TestAuth } from "../test/TestAuth";
import { Sidebar } from "./Sidebar";

describe("Sidebar", () => {
  it("renders the nav items linking to their screens", () => {
    render(
      <MemoryRouter>
        <TestAuth>
          <Sidebar />
        </TestAuth>
      </MemoryRouter>,
    );
    const expected = [
      ["Overview", "/"],
      ["Accounts", "/accounts"],
      ["Categories", "/categories"],
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
        <TestAuth>
          <Sidebar />
        </TestAuth>
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Accounts" })).toHaveClass("active");
    expect(screen.getByRole("link", { name: "Overview" })).not.toHaveClass("active");
  });

  it("shows who is logged in and logs out", () => {
    const logout = vi.fn().mockResolvedValue(undefined);
    render(
      <MemoryRouter>
        <TestAuth user={{ id: 2, username: "bob", is_admin: false }} logout={logout}>
          <Sidebar />
        </TestAuth>
      </MemoryRouter>,
    );
    expect(screen.getAllByText("bob").length).toBeGreaterThan(0);
    expect(screen.queryByText(/single user/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));
    expect(logout).toHaveBeenCalled();
  });
});
