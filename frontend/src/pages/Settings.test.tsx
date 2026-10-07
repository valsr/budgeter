import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { TestAuth } from "../test/TestAuth";
import { Settings } from "./Settings";

vi.mock("../api/settings", () => ({
  settingsApi: { getApiKey: () => Promise.resolve({ has_key: false }) },
}));

function renderSettings(isAdmin: boolean) {
  return render(
    <TestAuth user={{ id: 1, username: "alice", is_admin: isAdmin }}>
      <Settings />
    </TestAuth>,
  );
}

it("opens on the Account tab", async () => {
  renderSettings(true);
  expect(await screen.findByRole("button", { name: "Change password" })).toBeInTheDocument();
});

it("hides the Users and Server tabs from a non-admin", () => {
  renderSettings(false);
  expect(screen.getByText("Account")).toBeInTheDocument();
  expect(screen.getByText("Categories")).toBeInTheDocument();
  expect(screen.queryByText("Users")).not.toBeInTheDocument();
  expect(screen.queryByText("Server")).not.toBeInTheDocument();
});

it("shows them to an admin", () => {
  renderSettings(true);
  expect(screen.getByText("Users")).toBeInTheDocument();
  expect(screen.getByText("Server")).toBeInTheDocument();
});
