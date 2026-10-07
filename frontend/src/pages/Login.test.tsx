import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { Login } from "./Login";

const status = vi.fn();
const login = vi.fn();
const register = vi.fn();
vi.mock("../api/auth", () => ({
  authApi: {
    status: () => status(),
    login: (...args: unknown[]) => login(...args),
    register: (...args: unknown[]) => register(...args),
  },
}));

const ALICE = { id: 1, username: "alice", is_admin: true };

beforeEach(() => {
  status.mockReset().mockResolvedValue({ registration_open: true, has_users: true });
  login.mockReset();
  register.mockReset();
});

function fill(username: string, password: string) {
  fireEvent.change(screen.getByLabelText("Username"), { target: { value: username } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
}

it("logs in and hands the user to the provider", async () => {
  login.mockResolvedValue(ALICE);
  const onAuthenticated = vi.fn();
  render(<Login onAuthenticated={onAuthenticated} />);

  fill("alice", "password1");
  fireEvent.click(await screen.findByRole("button", { name: "Log in" }));

  await waitFor(() => expect(onAuthenticated).toHaveBeenCalledWith(ALICE));
  expect(login).toHaveBeenCalledWith("alice", "password1");
});

it("shows the server's message on a failed login", async () => {
  login.mockRejectedValue(new ApiError(401, "Invalid username or password"));
  const onAuthenticated = vi.fn();
  render(<Login onAuthenticated={onAuthenticated} />);

  fill("alice", "nope");
  fireEvent.click(await screen.findByRole("button", { name: "Log in" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username or password");
  expect(onAuthenticated).not.toHaveBeenCalled();
});

it("hides Create account when registration is closed and users exist", async () => {
  status.mockResolvedValue({ registration_open: false, has_users: true });
  render(<Login onAuthenticated={() => {}} />);
  await screen.findByRole("button", { name: "Log in" });
  await waitFor(() => expect(status).toHaveBeenCalled());
  expect(screen.queryByText("Create an account")).not.toBeInTheDocument();
});

it("offers Create account when registration is open", async () => {
  render(<Login onAuthenticated={() => {}} />);
  fireEvent.click(await screen.findByText("Create an account"));
  expect(screen.getByRole("button", { name: "Create account" })).toBeInTheDocument();
  expect(screen.queryByText(/first account takes over/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("I already have an account"));
  expect(screen.getByRole("button", { name: "Log in" })).toBeInTheDocument();
});

it("opens on Create account with the takeover note when there are no users", async () => {
  status.mockResolvedValue({ registration_open: false, has_users: false });
  render(<Login onAuthenticated={() => {}} />);
  expect(await screen.findByRole("button", { name: "Create account" })).toBeInTheDocument();
  expect(screen.getByText("The first account takes over this server's existing data.")).toBeInTheDocument();
});

it("registers and enters the app", async () => {
  register.mockResolvedValue(ALICE);
  const onAuthenticated = vi.fn();
  render(<Login onAuthenticated={onAuthenticated} />);

  fireEvent.click(await screen.findByText("Create an account"));
  fill("alice", "password1");
  fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "password1" } });
  fireEvent.click(screen.getByRole("button", { name: "Create account" }));

  await waitFor(() => expect(onAuthenticated).toHaveBeenCalledWith(ALICE));
  expect(register).toHaveBeenCalledWith("alice", "password1");
});

it("does not register when the passwords differ", async () => {
  render(<Login onAuthenticated={() => {}} />);
  fireEvent.click(await screen.findByText("Create an account"));
  fill("alice", "password1");
  fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "password2" } });
  fireEvent.click(screen.getByRole("button", { name: "Create account" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Passwords don't match");
  expect(register).not.toHaveBeenCalled();
});
