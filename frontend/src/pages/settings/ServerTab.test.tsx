import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { formatTimestamp } from "../../format";
import { TestAuth } from "../../test/TestAuth";
import { ServerTab } from "./ServerTab";

const getSettings = vi.fn();
const updateSettings = vi.fn();
const restoreBackup = vi.fn();
const getHealth = vi.fn();
vi.mock("../../api/admin", () => ({
  adminApi: {
    getHealth: () => getHealth(),
    getSettings: () => getSettings(),
    updateSettings: (...args: unknown[]) => updateSettings(...args),
    downloadBackup: vi.fn(),
    restoreBackup: (...args: unknown[]) => restoreBackup(...args),
  },
}));

const SETTINGS = {
  registration_open: true,
  port: 8000,
  ssl_enabled: false,
  ssl_certfile: null,
  ssl_keyfile: null,
  managed: true,
  restart_required: false,
  port_override: null,
  ssl_disabled_override: false,
};

const HEALTH = {
  status: "ok",
  version: {
    version: "2026.10.07+5dcc9d3",
    sha: "5dcc9d3a1b2c3d4e5f60718293a4b5c6d7e8f901",
    commit_date: "2026-10-07T14:03:22-04:00",
    build_date: "2026-10-08T09:15:00Z",
    dirty: false,
  },
  checks: { server_db: "ok", books: "ok", ssl: "disabled" },
  started_at: "2026-10-07T15:50:10",
  uptime_seconds: 93784,
  serving: { port: 8000, https: false },
  restart_required: false,
  users: { total: 3, active_admins: 2, disabled: 1 },
  data_dir: "/data",
  storage: { books_files: 3, books_bytes: 1572864, server_db_bytes: 57344 },
  schema: { server: "9f2c4d7a1e55", books: "b27eace77f79" },
  python_version: "3.14.7",
};

const refresh = vi.fn();

function renderTab() {
  return render(
    <TestAuth refresh={refresh}>
      <ServerTab />
    </TestAuth>,
  );
}

beforeEach(() => {
  getSettings.mockReset().mockResolvedValue(SETTINGS);
  updateSettings.mockReset().mockImplementation((patch) => Promise.resolve({ ...SETTINGS, ...patch }));
  getHealth.mockReset().mockResolvedValue(HEALTH);
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

// --- port and SSL -----------------------------------------------------

it("shows the saved port and SSL settings", async () => {
  getSettings.mockResolvedValue({
    ...SETTINGS,
    port: 8443,
    ssl_enabled: true,
    ssl_certfile: "/certs/fullchain.pem",
    ssl_keyfile: "/certs/privkey.pem",
  });
  renderTab();
  expect(await screen.findByLabelText("Port")).toHaveValue("8443");
  expect(screen.getByLabelText("Serve over HTTPS (SSL)")).toBeChecked();
  expect(screen.getByLabelText("Certificate file")).toHaveValue("/certs/fullchain.pem");
  expect(screen.getByLabelText("Private key file")).toHaveValue("/certs/privkey.pem");
});

it("saves port and SSL together, only when Save is pressed", async () => {
  renderTab();
  fireEvent.change(await screen.findByLabelText("Port"), { target: { value: "8443" } });
  fireEvent.click(screen.getByLabelText("Serve over HTTPS (SSL)"));
  fireEvent.change(screen.getByLabelText("Certificate file"), { target: { value: "/certs/fullchain.pem" } });
  fireEvent.change(screen.getByLabelText("Private key file"), { target: { value: "/certs/privkey.pem" } });
  expect(updateSettings).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: "Save network settings" }));

  await waitFor(() =>
    expect(updateSettings).toHaveBeenCalledWith(
      { port: 8443, ssl_enabled: true, ssl_certfile: "/certs/fullchain.pem", ssl_keyfile: "/certs/privkey.pem" },
      { silent: true }, // refusals are shown inline, not as a toast
    ),
  );
});

it("disables the file fields until HTTPS is switched on", async () => {
  renderTab();
  const cert = await screen.findByLabelText("Certificate file");
  await waitFor(() => expect(screen.getByLabelText("Port")).toHaveValue("8000"));
  expect(cert).toBeDisabled();
  fireEvent.click(screen.getByLabelText("Serve over HTTPS (SSL)"));
  expect(cert).toBeEnabled();
});

it("won't save a port that isn't a port", async () => {
  renderTab();
  fireEvent.change(await screen.findByLabelText("Port"), { target: { value: "99999" } });
  expect(screen.getByRole("button", { name: "Save network settings" })).toBeDisabled();
  expect(screen.getByText("Port must be between 1 and 65535")).toBeInTheDocument();
});

it("shows why the server refused the settings, and keeps what was typed", async () => {
  updateSettings.mockRejectedValue(new Error("Certificate file not found: /certs/nope.pem"));
  renderTab();
  fireEvent.click(await screen.findByLabelText("Serve over HTTPS (SSL)"));
  fireEvent.change(screen.getByLabelText("Certificate file"), { target: { value: "/certs/nope.pem" } });
  fireEvent.change(screen.getByLabelText("Private key file"), { target: { value: "/certs/key.pem" } });
  fireEvent.click(screen.getByRole("button", { name: "Save network settings" }));

  expect(await screen.findByText("Certificate file not found: /certs/nope.pem")).toBeInTheDocument();
  expect(screen.getByLabelText("Certificate file")).toHaveValue("/certs/nope.pem");
});

it("says a restart is needed once the saved settings differ from what is running", async () => {
  updateSettings.mockImplementation((patch) => Promise.resolve({ ...SETTINGS, ...patch, restart_required: true }));
  renderTab();
  await screen.findByLabelText("Port");
  expect(screen.queryByText(/Restart the server to apply/)).not.toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Port"), { target: { value: "8443" } });
  fireEvent.click(screen.getByRole("button", { name: "Save network settings" }));

  expect(await screen.findByText(/Restart the server to apply/)).toBeInTheDocument();
});

it("warns when the server wasn't started in a way that applies these settings", async () => {
  getSettings.mockResolvedValue({ ...SETTINGS, managed: false });
  renderTab();
  expect(await screen.findByText(/isn't applying these settings/)).toBeInTheDocument();
});

it("points out environment overrides", async () => {
  getSettings.mockResolvedValue({ ...SETTINGS, port_override: 9000, ssl_disabled_override: true });
  renderTab();
  expect(await screen.findByText(/BUDGETER_PORT=9000/)).toBeInTheDocument();
  expect(screen.getByText(/BUDGETER_SSL_DISABLED/)).toBeInTheDocument();
});

// --- health -----------------------------------------------------------

it("shows the server's health details", async () => {
  renderTab();
  const card = (await screen.findByText("Server health")).closest(".card") as HTMLElement;
  await waitFor(() => expect(card).toHaveTextContent("Healthy"));
  expect(card).toHaveTextContent("HTTP on port 8000");
  expect(card).toHaveTextContent("2026.10.07+5dcc9d3");
  expect(card).toHaveTextContent("5dcc9d3a1b2c3d4e5f60718293a4b5c6d7e8f901");
  expect(card).toHaveTextContent(`committed ${formatTimestamp("2026-10-07T14:03:22-04:00")}`);
  expect(card).toHaveTextContent(`built ${formatTimestamp("2026-10-08T09:15:00Z")}`);
  expect(card).toHaveTextContent("1d 2h 3m");
  expect(card).toHaveTextContent("3 users (2 active admins, 1 disabled)");
  expect(card).toHaveTextContent("3 books files, 1.5 MB");
  expect(card).toHaveTextContent("/data");
  expect(card).toHaveTextContent("9f2c4d7a1e55");
  expect(card).toHaveTextContent("3.14.7");
});

it("spells out what is wrong when the server is degraded", async () => {
  getHealth.mockResolvedValue({
    ...HEALTH,
    status: "degraded",
    serving: { port: 8443, https: true },
    checks: { server_db: "ok", books: "1 of 3 books files can't be read", ssl: "Certificate file not found: /c.pem" },
  });
  renderTab();
  const card = (await screen.findByText("Server health")).closest(".card") as HTMLElement;
  await waitFor(() => expect(card).toHaveTextContent("Needs attention"));
  expect(card).toHaveTextContent("HTTPS on port 8443");
  expect(card).toHaveTextContent("1 of 3 books files can't be read");
  expect(card).toHaveTextContent("Certificate file not found: /c.pem");
});

it("re-checks health on demand", async () => {
  renderTab();
  await screen.findByText("Server health");
  await waitFor(() => expect(getHealth).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
  await waitFor(() => expect(getHealth).toHaveBeenCalledTimes(2));
});

it("says so when running from source with uncommitted changes", async () => {
  getHealth.mockResolvedValue({
    ...HEALTH,
    version: { ...HEALTH.version, version: "2026.10.07+5dcc9d3.dirty", build_date: null, dirty: true },
  });
  renderTab();
  const card = (await screen.findByText("Server health")).closest(".card") as HTMLElement;
  await waitFor(() => expect(card).toHaveTextContent("2026.10.07+5dcc9d3.dirty"));
  expect(card).toHaveTextContent("running from source, with uncommitted changes");
  expect(card).not.toHaveTextContent("built ");
});
