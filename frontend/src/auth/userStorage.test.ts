import { beforeEach, expect, it } from "vitest";
import { userStorage } from "./userStorage";

beforeEach(() => localStorage.clear());

it("keeps two users' values apart", () => {
  userStorage(1).set("overview.budget", "3");
  userStorage(2).set("overview.budget", "all");
  expect(userStorage(1).get("overview.budget")).toBe("3");
  expect(userStorage(2).get("overview.budget")).toBe("all");
  expect(localStorage.getItem("budgeter.u1.overview.budget")).toBe("3");

  userStorage(1).remove("overview.budget");
  expect(userStorage(1).get("overview.budget")).toBeNull();
  expect(userStorage(2).get("overview.budget")).toBe("all");
});
