import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import { TestAuth } from "../../test/TestAuth";
import { AccountTab } from "./AccountTab";

const changePassword = vi.fn();
const deleteMe = vi.fn();
vi.mock("../../api/auth", () => ({
  authApi: {
    changePassword: (...args: unknown[]) => changePassword(...args),
    deleteMe: (...args: unknown[]) => deleteMe(...args),
  },
}));
const getApiKey = vi.fn();
const regenerateApiKey = vi.fn();
vi.mock("../../api/settings", () => ({
  settingsApi: {
    getApiKey: () => getApiKey(),
    regenerateApiKey: () => regenerateApiKey(),
  },
}));

const refresh = vi.fn();

function renderTab() {
  return render(
    <TestAuth refresh={refresh}>
      <AccountTab />
    </TestAuth>,
  );
}

beforeEach(() => {
  changePassword.mockReset().mockResolvedValue(undefined);
  deleteMe.mockReset().mockResolvedValue(undefined);
  getApiKey.mockReset().mockResolvedValue({ has_key: false });
  regenerateApiKey.mockReset().mockResolvedValue({ api_key: "fresh-key-123" });
  refresh.mockReset().mockResolvedValue(undefined);
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

afterEach(() => vi.restoreAllMocks());

function fillPasswords(current: string, next: string, confirm: string) {
  fireEvent.change(screen.getByLabelText("Current password"), { target: { value: current } });
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: next } });
  fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: confirm } });
}

it("blocks a password change when the confirmation differs", () => {
  renderTab();
  fillPasswords("password1", "password2", "password3");
  expect(screen.getByRole("button", { name: "Change password" })).toBeDisabled();
  expect(screen.getByText("Passwords don't match")).toBeInTheDocument();
});

it("submits the current and new password", async () => {
  renderTab();
  fillPasswords("password1", "password2", "password2");
  fireEvent.click(screen.getByRole("button", { name: "Change password" }));

  await waitFor(() => expect(changePassword).toHaveBeenCalledWith("password1", "password2"));
  expect(await screen.findByText("Password changed.")).toBeInTheDocument();
  expect(screen.getByLabelText("Current password")).toHaveValue("");
});

it("shows why a password change was refused", async () => {
  changePassword.mockRejectedValue(new ApiError(403, "Current password is incorrect"));
  renderTab();
  fillPasswords("wrong", "password2", "password2");
  fireEvent.click(screen.getByRole("button", { name: "Change password" }));
  expect(await screen.findByText("Current password is incorrect")).toBeInTheDocument();
});

it("reveals a regenerated key once, and only status after a reload", async () => {
  const first = renderTab();
  expect(await screen.findByText("No key yet")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Generate key" }));

  expect(await screen.findByDisplayValue("fresh-key-123")).toBeInTheDocument();
  expect(screen.getByText("Copy it now — it won't be shown again.")).toBeInTheDocument();

  first.unmount();
  getApiKey.mockResolvedValue({ has_key: true });
  renderTab();
  expect(await screen.findByText("A key is set")).toBeInTheDocument();
  expect(screen.queryByDisplayValue("fresh-key-123")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Regenerate" })).toBeInTheDocument();
});

it("does not regenerate when the confirmation is declined", async () => {
  getApiKey.mockResolvedValue({ has_key: true });
  vi.spyOn(window, "confirm").mockReturnValue(false);
  renderTab();
  fireEvent.click(await screen.findByRole("button", { name: "Regenerate" }));
  expect(regenerateApiKey).not.toHaveBeenCalled();
});

it("deletes the account only after the password is entered and confirmed", async () => {
  renderTab();
  const button = screen.getByRole("button", { name: "Delete my account" });
  expect(button).toBeDisabled();

  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password1" } });
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  fireEvent.click(button);
  expect(confirm).toHaveBeenCalled();
  expect(deleteMe).not.toHaveBeenCalled();

  confirm.mockReturnValue(true);
  fireEvent.click(button);
  await waitFor(() => expect(deleteMe).toHaveBeenCalledWith("password1"));
  await waitFor(() => expect(refresh).toHaveBeenCalled());
});

it("keeps the account and explains when deletion is refused", async () => {
  deleteMe.mockRejectedValue(new ApiError(409, "The last active admin can't be demoted, disabled or deleted"));
  renderTab();
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password1" } });
  fireEvent.click(screen.getByRole("button", { name: "Delete my account" }));
  expect(await screen.findByText(/last active admin/)).toBeInTheDocument();
  expect(refresh).not.toHaveBeenCalled();
});
