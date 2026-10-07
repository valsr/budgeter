import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import { authApi } from "../api/auth";
import type { AuthStatus, AuthUser } from "../api/types";
import { errorMessage } from "../api/client";

interface LoginProps {
  onAuthenticated: (user: AuthUser) => void;
}

type Mode = "login" | "register";

export function Login({ onAuthenticated }: LoginProps) {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    authApi
      .status()
      .then((s) => {
        setStatus(s);
        // Nobody to log in as yet: the only useful thing is creating the first account.
        if (!s.has_users) setMode("register");
      })
      .catch(() => {
        // Leave the plain login form up; submitting it will surface the problem.
      });
  }, []);

  const canRegister = status !== null && (status.registration_open || !status.has_users);

  function switchMode(next: Mode) {
    setMode(next);
    setError(null);
    setConfirm("");
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (mode === "register" && password !== confirm) {
      setError("Passwords don't match");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const user =
        mode === "login" ? await authApi.login(username, password) : await authApi.register(username, password);
      onAuthenticated(user);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <div className="auth-screen">
      <form className="card auth-card" onSubmit={submit}>
        <div className="auth-title">Finance</div>
        <p className="sub" style={{ marginBottom: 16 }}>
          {mode === "login" ? "Log in to your books." : "Create an account."}
        </p>
        {mode === "register" && status !== null && !status.has_users && (
          <div className="notice" style={{ marginBottom: 14 }}>
            The first account takes over this server's existing data.
          </div>
        )}
        <div className="field">
          <label htmlFor="auth-username">Username</label>
          <input
            id="auth-username"
            autoComplete="username"
            autoCapitalize="none"
            autoFocus
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="auth-password">Password</label>
          <input
            id="auth-password"
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {mode === "register" && (
          <div className="field">
            <label htmlFor="auth-confirm">Confirm password</label>
            <input
              id="auth-confirm"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
          </div>
        )}
        {error && (
          <p className="sub" role="alert" style={{ color: "var(--c5)", marginBottom: 12 }}>
            {error}
          </p>
        )}
        <button className="btn" type="submit" disabled={busy} style={{ width: "100%" }}>
          {mode === "login" ? "Log in" : "Create account"}
        </button>
        {mode === "login" && canRegister && (
          <p className="sub auth-switch">
            <span onClick={() => switchMode("register")}>Create an account</span>
          </p>
        )}
        {mode === "register" && status?.has_users && (
          <p className="sub auth-switch">
            <span onClick={() => switchMode("login")}>I already have an account</span>
          </p>
        )}
      </form>
    </div>
  );
}
