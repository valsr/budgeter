import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import type { AuthUser } from "../api/types";
import { AuthProvider } from "./AuthProvider";
import { useAuth } from "./context";

const me = vi.fn();
const logout = vi.fn();
const status = vi.fn();
vi.mock("../api/auth", () => ({
  authApi: {
    me: () => me(),
    logout: () => logout(),
    status: () => status(),
    login: vi.fn(),
    register: vi.fn(),
  },
}));

let unauthorized: (() => void) | null = null;
vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/client")>()),
  setUnauthorizedListener: (fn: (() => void) | null) => {
    unauthorized = fn;
  },
}));

const ALICE: AuthUser = { id: 1, username: "alice", is_admin: true };

function App() {
  const { user, logout } = useAuth();
  return (
    <div>
      <span>hello {user.username}</span>
      <button onClick={logout}>out</button>
    </div>
  );
}

function renderApp() {
  return render(
    <AuthProvider>
      <App />
    </AuthProvider>,
  );
}

beforeEach(() => {
  me.mockReset();
  logout.mockReset().mockResolvedValue(undefined);
  status.mockReset().mockResolvedValue({ registration_open: true, has_users: true });
  unauthorized = null;
});

it("renders nothing while the session check is pending", () => {
  me.mockReturnValue(new Promise(() => {}));
  const { container } = renderApp();
  expect(container).toBeEmptyDOMElement();
});

it("shows the login screen when /auth/me is 401", async () => {
  me.mockRejectedValue(new ApiError(401, "Not authenticated"));
  renderApp();
  expect(await screen.findByRole("button", { name: "Log in" })).toBeInTheDocument();
  expect(screen.queryByText(/hello/)).not.toBeInTheDocument();
});

it("renders the app when a user is returned", async () => {
  me.mockResolvedValue(ALICE);
  renderApp();
  expect(await screen.findByText("hello alice")).toBeInTheDocument();
});

it("returns to the login screen when any later request reports 401", async () => {
  me.mockResolvedValue(ALICE);
  renderApp();
  await screen.findByText("hello alice");

  act(() => unauthorized?.());

  expect(await screen.findByRole("button", { name: "Log in" })).toBeInTheDocument();
  expect(screen.queryByText("hello alice")).not.toBeInTheDocument();
});

it("logout calls the API and shows the login screen", async () => {
  me.mockResolvedValue(ALICE);
  renderApp();
  fireEvent.click(await screen.findByText("out"));
  await waitFor(() => expect(logout).toHaveBeenCalled());
  expect(await screen.findByRole("button", { name: "Log in" })).toBeInTheDocument();
});

it("still logs out locally when the logout request fails", async () => {
  me.mockResolvedValue(ALICE);
  logout.mockRejectedValue(new Error("network"));
  renderApp();
  fireEvent.click(await screen.findByText("out"));
  expect(await screen.findByRole("button", { name: "Log in" })).toBeInTheDocument();
});
