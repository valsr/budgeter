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

it("does not offer to remove your own admin rights", async () => {
  renderTab();
  const mine = within(await row("alice")).getByRole("button", { name: "Remove admin" });
  expect(mine).toBeDisabled();
  expect(mine).toHaveAttribute("title", "You can't remove your own admin rights");
  fireEvent.click(mine);
  expect(updateUser).not.toHaveBeenCalled();
  // ...but another admin's can be removed.
  expect(within(await row("carol")).getByRole("button", { name: "Remove admin" })).toBeEnabled();
});

it("re-reads the current user after changing their own account", async () => {
  renderTab();
  fireEvent.click(within(await row("alice")).getByRole("button", { name: "Disable" }));
  await waitFor(() => expect(updateUser).toHaveBeenCalledWith(1, { is_disabled: true }));
  await waitFor(() => expect(refresh).toHaveBeenCalled());
});

async function openReset(username: string) {
  fireEvent.click(within(await row(username)).getByRole("button", { name: "Reset password" }));
  return screen.getByRole("button", { name: "Set password" });
}

it("resets a password from masked password and confirmation fields", async () => {
  const prompt = vi.spyOn(window, "prompt");
  renderTab();
  const submit = await openReset("bob");
  expect(screen.getByText("Reset password for bob")).toBeInTheDocument();
  expect(prompt).not.toHaveBeenCalled();
  expect(screen.getByLabelText("New password")).toHaveAttribute("type", "password");
  expect(screen.getByLabelText("Confirm new password")).toHaveAttribute("type", "password");
  expect(submit).toBeDisabled();

  fireEvent.change(screen.getByLabelText("New password"), { target: { value: "brand-new-pw" } });
  fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "brand-new-pw" } });
  fireEvent.click(submit);

  // silent: a refusal is shown in the dialog, not also as a toast.
  await waitFor(() => expect(updateUser).toHaveBeenCalledWith(2, { password: "brand-new-pw" }, { silent: true }));
  await waitFor(() => expect(screen.queryByText("Reset password for bob")).not.toBeInTheDocument());
});

it("won't reset a password when the confirmation differs", async () => {
  renderTab();
  const submit = await openReset("bob");
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: "brand-new-pw" } });
  fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "brand-new-px" } });

  expect(screen.getByText("Passwords don't match")).toBeInTheDocument();
  expect(submit).toBeDisabled();
  fireEvent.click(submit);
  expect(updateUser).not.toHaveBeenCalled();
});

it("leaves the password alone when the reset is cancelled", async () => {
  renderTab();
  await openReset("bob");
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: "brand-new-pw" } });
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByText("Reset password for bob")).not.toBeInTheDocument();
  expect(updateUser).not.toHaveBeenCalled();
});

it("keeps the reset dialog open with the reason when the server refuses", async () => {
  updateUser.mockRejectedValue(new Error("Password must be 8–256 characters"));
  renderTab();
  const submit = await openReset("bob");
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: "short" } });
  fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "short" } });
  fireEvent.click(submit);
  expect(await screen.findByText("Password must be 8–256 characters")).toBeInTheDocument();
  expect(screen.getByText("Reset password for bob")).toBeInTheDocument();
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
