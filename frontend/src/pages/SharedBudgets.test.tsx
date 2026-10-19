import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import type { SharedBudget } from "../api/types";
import { TestAuth } from "../test/TestAuth";
import { SharedBudget as SharedBudgetPage } from "./SharedBudget";
import { SharedBudgets } from "./SharedBudgets";

const list = vi.fn();
const get = vi.fn();
const create = vi.fn();
const directory = vi.fn();
vi.mock("../api/sharedBudgets", () => ({
  sharedBudgetsApi: {
    list: () => list(),
    get: (...args: unknown[]) => get(...args),
    create: (...args: unknown[]) => create(...args),
    directory: () => directory(),
  },
}));

const HOUSEHOLD: SharedBudget = {
  id: 1,
  name: "Household",
  members: [
    { user_id: 1, username: "alice", is_disabled: false },
    { user_id: 2, username: "bob", is_disabled: false },
  ],
};

beforeEach(() => {
  list.mockReset().mockResolvedValue([HOUSEHOLD]);
  get.mockReset().mockResolvedValue(HOUSEHOLD);
  create.mockReset();
  directory.mockReset().mockResolvedValue([
    { id: 1, username: "alice" },
    { id: 2, username: "bob" },
    { id: 3, username: "carol" },
  ]);
});

function renderList() {
  return render(
    <MemoryRouter>
      <TestAuth>
        <SharedBudgets />
      </TestAuth>
    </MemoryRouter>,
  );
}

it("lists shared budgets with their member names", async () => {
  renderList();
  expect(await screen.findByRole("link", { name: "Household" })).toHaveAttribute(
    "href",
    "/shared-budgets/1",
  );
  expect(screen.getByText("alice, bob")).toBeInTheDocument();
});

it("creates a shared budget from the directory, leaving the current user out of the picker", async () => {
  const created: SharedBudget = {
    id: 2,
    name: "Trip",
    members: [
      { user_id: 1, username: "alice", is_disabled: false },
      { user_id: 3, username: "carol", is_disabled: false },
    ],
  };
  create.mockResolvedValue(created);
  renderList();
  await screen.findByText("Household");
  fireEvent.click(screen.getByRole("button", { name: "New shared budget" }));

  const dialog = await screen.findByRole("heading", { name: "New shared budget" });
  expect(dialog).toBeInTheDocument();
  await screen.findByLabelText("bob");
  expect(screen.getByLabelText("carol")).toBeInTheDocument();
  expect(screen.queryByLabelText("alice")).not.toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Trip" } });
  fireEvent.click(screen.getByLabelText("carol"));
  fireEvent.click(screen.getByRole("button", { name: "Create" }));

  await waitFor(() => expect(create).toHaveBeenCalledWith({ name: "Trip", member_ids: [3] }));
  expect(await screen.findByRole("link", { name: "Trip" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "New shared budget" })).not.toBeInTheDocument();
});

it("shows the budget shell with its three tabs", async () => {
  render(
    <MemoryRouter initialEntries={["/shared-budgets/1"]}>
      <TestAuth>
        <Routes>
          <Route path="/shared-budgets/:id" element={<SharedBudgetPage />} />
        </Routes>
      </TestAuth>
    </MemoryRouter>,
  );
  expect(await screen.findByRole("heading", { name: "Household" })).toBeInTheDocument();
  expect(get).toHaveBeenCalledWith(1);
  for (const tab of ["Report", "Setup", "My mappings"]) {
    expect(screen.getByRole("button", { name: tab })).toBeInTheDocument();
  }
  fireEvent.click(screen.getByRole("button", { name: "Setup" }));
  expect(within(screen.getByTestId("tab-panel")).getByText(/setup/i)).toBeInTheDocument();
});
