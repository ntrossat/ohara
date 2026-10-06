import { useEffect, useState } from "react";
import { base, get } from "./api";
import Gate from "./Gate";
import Mark from "./Mark";

type Details = { client: string; redirect: string; login: string };

/** Asks the signed-in user to approve an MCP client before Ohara gives it a token. */
export default function Consent({ repo }: { repo: string }) {
  const [details, setDetails] = useState<Details | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    get<Details>("/api/auth/consent").then(setDetails, () => setFailed(true));
  }, []);

  async function answer(approve: boolean) {
    setBusy(true);
    const response = await fetch(`${base}/api/auth/consent`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approve }),
    });
    if (!response.ok) return setFailed(true);
    location.assign((await response.json()).redirect);
  }

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
          <button className="button" disabled={busy} onClick={() => answer(true)}>
            Connect
          </button>
          <button className="button secondary" disabled={busy} onClick={() => answer(false)}>
            Cancel
          </button>
        </div>
      </main>
    </div>
  );
}
