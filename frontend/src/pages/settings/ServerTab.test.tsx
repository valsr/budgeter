import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { TestAuth } from "../../test/TestAuth";
import { ServerTab } from "./ServerTab";

const getSettings = vi.fn();
const updateSettings = vi.fn();
const restoreBackup = vi.fn();
vi.mock("../../api/admin", () => ({
  adminApi: {
    getSettings: () => getSettings(),
    updateSettings: (...args: unknown[]) => updateSettings(...args),
    downloadBackup: vi.fn(),
    restoreBackup: (...args: unknown[]) => restoreBackup(...args),
  },
}));

const refresh = vi.fn();

function renderTab() {
  return render(
    <TestAuth refresh={refresh}>
      <ServerTab />
    </TestAuth>,
  );
}

beforeEach(() => {
  getSettings.mockReset().mockResolvedValue({ registration_open: true });
  updateSettings.mockReset().mockImplementation((s) => Promise.resolve(s));
  restoreBackup.mockReset().mockResolvedValue(undefined);
  refresh.mockReset().mockResolvedValue(undefined);
  vi.spyOn(window, "alert").mockImplementation(() => {});
});

afterEach(() => vi.restoreAllMocks());

it("saves the registration toggle", async () => {
  renderTab();
  const box = await screen.findByLabelText("Allow new registrations");
  await waitFor(() => expect(box).toBeChecked());

  fireEvent.click(box);

  await waitFor(() => expect(updateSettings).toHaveBeenCalledWith({ registration_open: false }));
  await waitFor(() => expect(box).not.toBeChecked());
});

it("warns before a whole-server restore and does nothing when cancelled", async () => {
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  renderTab();
  const file = new File(["zip"], "backup.zip", { type: "application/zip" });
  const input = await screen.findByLabelText("Server backup archive");

  fireEvent.change(input, { target: { files: [file] } });

  expect(confirm).toHaveBeenCalledWith(
    "This replaces every user's data and accounts with the archive. You may need to log in again. Continue?",
  );
  expect(restoreBackup).not.toHaveBeenCalled();
});

it("restores the archive when confirmed, then re-checks the session", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  renderTab();
  const file = new File(["zip"], "backup.zip", { type: "application/zip" });
  fireEvent.change(await screen.findByLabelText("Server backup archive"), { target: { files: [file] } });

  await waitFor(() => expect(restoreBackup).toHaveBeenCalledWith(file));
  await waitFor(() => expect(refresh).toHaveBeenCalled());
});
