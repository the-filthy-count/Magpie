import { useState } from "react";
import { ArrowDown, LoaderCircle, ShieldCheck, X } from "lucide-react";
import { api } from "../services/api";
export default function Login({
  setup,
  onLogin,
}: {
  setup: boolean;
  onLogin: (a: any) => void;
}) {
  const [password, setPassword] = useState(""),
    [token, setToken] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <div className="login">
      <div className="login-card">
        <img src="/logo.webp" width="68" />
        <h1>
          Welcome {setup ? "to" : "back to"} Magpie<span>.</span>
        </h1>
        <p>
          {setup
            ? "Your own little corner of the internet. Set up your administrator account."
            : "Your next good find is waiting."}
        </p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              onLogin(
                await api(
                  "/auth/" + (setup ? "setup" : "login"),
                  "POST",
                  { password },
                  setup ? { "X-Setup-Token": token } : {},
                ),
              );
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          {setup && (
            <label>
              Setup token
              <input
                required
                value={token}
                onChange={(e) => setToken(e.target.value)}
                autoComplete="off"
              />
              <small>
                Read the one-time token in /config/setup-token on your NAS.
              </small>
            </label>
          )}
          <label>
            Administrator password
            <input
              required
              type="password"
              minLength={setup ? 12 : 1}
              maxLength={256}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={setup ? "new-password" : "current-password"}
            />
            {setup && <small>At least 12 characters.</small>}
          </label>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button className="primary" disabled={busy}>
            {busy ? (
              <LoaderCircle className="spin" size={18} />
            ) : (
              <ArrowDown size={18} />
            )}{" "}
            {setup ? "Make yourself at home" : "Sign in"}
          </button>
        </form>
        <div className="login-note">
          <ShieldCheck size={15} /> Self-hosted. Private. Yours.
        </div>
      </div>
    </div>
  );
}
