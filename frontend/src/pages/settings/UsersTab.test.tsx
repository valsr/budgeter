import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { AdminUser } from "../../api/types";
import { TestAuth } from "../../test/TestAuth";
import { UsersTab } from "./UsersTab";

const listUsers = vi.fn();
const createUser = vi.fn();
const updateUser = vi.fn();
const deleteUser = vi.fn();
vi.mock("../../api/admin", () => ({
  adminApi: {
    listUsers: () => listUsers(),
    createUser: (...args: unknown[]) => createUser(...args),
    updateUser: (...args: unknown[]) => updateUser(...args),
    deleteUser: (...args: unknown[]) => deleteUser(...args),
  },
}));

const USERS: AdminUser[] = [
  { id: 1, username: "alice", is_admin: true, is_disabled: false, created_at: "2026-10-01T10:00:00" },
  { id: 2, username: "bob", is_admin: false, is_disabled: false, created_at: "2026-10-02T10:00:00" },
  { id: 3, username: "carol", is_admin: true, is_disabled: true, created_at: "2026-10-03T10:00:00" },
];

const refresh = vi.fn();

function renderTab() {
  return render(
    <TestAuth refresh={refresh}>
      <UsersTab />
    </TestAuth>,
  );
}

async function row(username: string) {
  return (await screen.findByText(username)).closest("tr")!;
}

beforeEach(() => {
  listUsers.mockReset().mockResolvedValue(USERS);
  createUser.mockReset().mockResolvedValue(USERS[1]);
  updateUser.mockReset().mockResolvedValue(USERS[1]);
  deleteUser.mockReset().mockResolvedValue(undefined);
  refresh.mockReset().mockResolvedValue(undefined);
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

afterEach(() => vi.restoreAllMocks());

it("lists users and marks the current one", async () => {
  renderTab();
  expect(within(await row("alice")).getByText("you")).toBeInTheDocument();
  expect(within(await row("bob")).queryByText("you")).not.toBeInTheDocument();
  expect(within(await row("bob")).getByText("active")).toBeInTheDocument();
  expect(within(await row("carol")).getByText("disabled")).toBeInTheDocument();
  expect(within(await row("carol")).getByRole("button", { name: "Enable" })).toBeInTheDocument();
});

it("creates a user and refreshes the list", async () => {
  renderTab();
  await row("alice");
  fireEvent.change(screen.getByLabelText("New username"), { target: { value: "dave" } });
  fireEvent.change(screen.getByLabelText("Initial password"), { target: { value: "password1" } });
  fireEvent.click(screen.getByRole("button", { name: "Add user" }));

  await waitFor(() => expect(createUser).toHaveBeenCalledWith("dave", "password1"));
  await waitFor(() => expect(listUsers).toHaveBeenCalledTimes(2));
  expect(screen.getByLabelText("New username")).toHaveValue("");
});

it("toggles disabled and admin through PATCH", async () => {
  renderTab();
  fireEvent.click(within(await row("bob")).getByRole("button", { name: "Disable" }));
  await waitFor(() => expect(updateUser).toHaveBeenCalledWith(2, { is_disabled: true }));

  fireEvent.click(within(await row("bob")).getByRole("button", { name: "Make admin" }));
  await waitFor(() => expect(updateUser).toHaveBeenCalledWith(2, { is_admin: true }));

  fireEvent.click(within(await row("carol")).getByRole("button", { name: "Remove admin" }));
  await waitFor(() => expect(updateUser).toHaveBeenCalledWith(3, { is_admin: false }));
  expect(refresh).not.toHaveBeenCalled();
});

it("re-reads the current user after changing their own account", async () => {
  renderTab();
  fireEvent.click(within(await row("alice")).getByRole("button", { name: "Remove admin" }));
  await waitFor(() => expect(updateUser).toHaveBeenCalledWith(1, { is_admin: false }));
  await waitFor(() => expect(refresh).toHaveBeenCalled());
});

it("resets a password with the value entered", async () => {
  vi.spyOn(window, "prompt").mockReturnValue("brand-new-pw");
  renderTab();
  fireEvent.click(within(await row("bob")).getByRole("button", { name: "Reset password" }));
  await waitFor(() => expect(updateUser).toHaveBeenCalledWith(2, { password: "brand-new-pw" }));
});

it("leaves the password alone when the prompt is cancelled", async () => {
  vi.spyOn(window, "prompt").mockReturnValue(null);
  renderTab();
  fireEvent.click(within(await row("bob")).getByRole("button", { name: "Reset password" }));
  expect(updateUser).not.toHaveBeenCalled();
});

it("asks before deleting and names the user", async () => {
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  renderTab();
  fireEvent.click(within(await row("bob")).getByRole("button", { name: "Delete" }));
  expect(confirm.mock.calls[0][0]).toContain("bob");
  expect(confirm.mock.calls[0][0]).toMatch(/all of their data/);
  expect(deleteUser).not.toHaveBeenCalled();

  confirm.mockReturnValue(true);
  fireEvent.click(within(await row("bob")).getByRole("button", { name: "Delete" }));
  await waitFor(() => expect(deleteUser).toHaveBeenCalledWith(2));
});
