import { useMemo } from "react";
import { useAuth } from "./context";

export interface UserStorage {
  get: (key: string) => string | null;
  set: (key: string, value: string) => void;
  remove: (key: string) => void;
}

/** localStorage namespaced per user, for remembered UI choices (the last budget on the Overview,
 * the last category picked). */
export function userStorage(userId: number): UserStorage {
  const full = (key: string) => `budgeter.u${userId}.${key}`;
  return {
    get: (key) => localStorage.getItem(full(key)),
    set: (key, value) => localStorage.setItem(full(key), value),
    remove: (key) => localStorage.removeItem(full(key)),
  };
}

export function useUserStorage(): UserStorage {
  const { user } = useAuth();
  return useMemo(() => userStorage(user.id), [user.id]);
}
