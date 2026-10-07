import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TestAuth } from "../test/TestAuth";
import { Sidebar } from "./Sidebar";

const getVersion = vi.fn();
vi.mock("../api/version", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/version")>()),
  versionApi: { get: () => getVersion() },
}));

beforeEach(() => {
  getVersion.mockReset().mockResolvedValue({
    version: "2026.10.07+5dcc9d3",
    sha: "5dcc9d3a1b2c3d4e5f60718293a4b5c6d7e8f901",
    commit_date: "2026-10-07T14:03:22-04:00",
    build_date: "2026-10-08T09:15:00Z",
    dirty: false,
  });
});

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

  it("shows which version is running, with the full details on hover", async () => {
    render(
      <MemoryRouter>
        <TestAuth>
          <Sidebar />
        </TestAuth>
      </MemoryRouter>,
    );
    const version = await screen.findByText("2026.10.07+5dcc9d3");
    expect(version.title).toContain("5dcc9d3a1b2c3d4e5f60718293a4b5c6d7e8f901");
    expect(version.title).toContain("committed");
    expect(version.title).toContain("built");
  });

  it("shows no version line when the server can't say", async () => {
    getVersion.mockRejectedValue(new Error("nope"));
    const { container } = render(
      <MemoryRouter>
        <TestAuth>
          <Sidebar />
        </TestAuth>
      </MemoryRouter>,
    );
    await vi.waitFor(() => expect(getVersion).toHaveBeenCalled());
    expect(container.querySelector(".sidebar-version")).toBeNull();
  });
});
