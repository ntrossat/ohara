import { useEffect, useState } from "react";
import { get, HttpError, post } from "./api";
import Gate, { Unreachable } from "./Gate";
import Mark from "./Mark";

type Details = { client: string; redirect: string; login: string };

/** Asks the signed-in user to approve an MCP client before Ohara gives it a token. */
export default function Consent({ repo }: { repo: string }) {
  const [details, setDetails] = useState<Details | null>(null);
  const [failed, setFailed] = useState<"expired" | "unreachable" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // The server answers 404 once the request is gone: expired, already answered, or from another browser.
  const expired = (error: unknown) => error instanceof HttpError && error.status === 404;

  useEffect(() => {
    get<Details>("/api/auth/consent").then(setDetails, (error) => setFailed(expired(error) ? "expired" : "unreachable"));
  }, []);

  async function answer(approve: boolean) {
    setBusy(true);
    setError("");
    try {
      location.assign((await post<{ redirect: string }>("/api/auth/consent", { approve })).redirect);
    } catch (error) {
      if (expired(error)) return setFailed("expired");
      setError(
        error instanceof HttpError
          ? "Ohara couldn't save your answer. Try again in a moment."
          : "Ohara couldn't reach the server. Try again in a moment.",
      );
      setBusy(false);
    }
  }

  if (failed === "unreachable") return <Unreachable />;
  if (failed)
    return <Gate title="This request expired" body="Connect again from your coding assistant to get a new sign-in link." />;
  if (!details) return null;

  return (
    <div className="gate">
      <Mark />
      <main className="gate-body">
        <p className="status-line">signed in as {details.login}</p>
        <h1 className="display">Connect {details.client}?</h1>
        <p className="gate-text">
          It will read {repo} and propose changes as {details.login}, then send you back to <code>{details.redirect}</code>.
          Only connect an app you started from your own coding assistant.
        </p>
        <div className="gate-actions">
          <button className="button" disabled={busy} aria-busy={busy} onClick={() => answer(true)}>
            Connect
          </button>
          <button className="button secondary" disabled={busy} aria-busy={busy} onClick={() => answer(false)}>
            Cancel
          </button>
        </div>
        {error && <p className="error">{error}</p>}
      </main>
    </div>
  );
}
