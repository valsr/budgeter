import { apiFetch } from "./client";
import type { Account, AccountType } from "./types";

export interface AccountInput {
  name: string;
  account_number?: string | null;
  type: AccountType;
  opening_balance: number;
  color?: string | null;
}

export const accountsApi = {
  list: () => apiFetch<Account[]>("/api/accounts"),
  get: (id: number) => apiFetch<Account>(`/api/accounts/${id}`),
  create: (input: AccountInput) =>
    apiFetch<Account>("/api/accounts", { method: "POST", body: JSON.stringify(input) }),
  update: (id: number, input: Partial<AccountInput>) =>
    apiFetch<Account>(`/api/accounts/${id}`, { method: "PATCH", body: JSON.stringify(input) }),
};
