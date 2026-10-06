import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import { base, get } from "./api";
import { GitHubIcon } from "./Gate";
import Mark from "./Mark";

type Props = { url: string; installUrl: string | null };

export default function Setup({ url, installUrl }: Props) {
  const [org, setOrg] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [params] = useSearchParams();
  const opened = location.origin + base;
  const urlMismatch = url !== opened;

  async function createApp(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { action, manifest } = await get<{ action: string; manifest: string }>(
        `/api/setup/manifest?org=${encodeURIComponent(org.trim())}`,
      );
      const form = document.createElement("form");
      form.method = "post";
      form.action = action;
      const field = document.createElement("input");
      field.type = "hidden";
      field.name = "manifest";
      field.value = manifest;
      form.append(field);
      document.body.append(form);
      form.submit();
    } catch {
      setError("Ohara couldn't prepare the GitHub App. Check the server logs, then try again.");
      setBusy(false);
    }
  }

  return (
    <div className="setup">
      <Mark />
      <main className="setup-grid">
        <div>
          <p className="status-line">first launch</p>
          <h1 className="display">Connect your docs repository</h1>
          <p className="setup-text">
            Everyone who can read the repository can read these docs. If the repository is public, the docs are public
            too.
          </p>
          {urlMismatch && (
            <p className="notice">
              This instance is set up for <code>{url}</code>, but you opened <code>{opened}</code>. GitHub will
              send you back to {url}. Set <code>OHARA_URL</code> to the address people use, then restart.
            </p>
          )}
        </div>

        <ol className="steps">
          <li className={installUrl ? "done" : "current"}>
            <span className="step-number">01</span>
            <div>
              <h2>Create the GitHub App</h2>
              <p>GitHub opens with everything filled in. Review it and confirm.</p>
              {!installUrl && (
                <form onSubmit={createApp}>
                  <label htmlFor="org">Organization that owns the docs repository</label>
                  <input
                    id="org"
                    value={org}
                    onChange={(e) => setOrg(e.target.value)}
                    placeholder="Leave empty for your personal account"
                    autoComplete="off"
                    spellCheck={false}
                  />
                  <button className="button" disabled={busy}>
                    <GitHubIcon /> {busy ? "Opening GitHub…" : "Create GitHub App"}
                  </button>
                  {error && <p className="error">{error}</p>}
                </form>
              )}
            </div>
          </li>
          <li className={installUrl ? "current" : ""}>
            <span className="step-number">02</span>
            <div>
              <h2>Install it on your docs repository</h2>
              <p>Choose “Only select repositories” and pick the one that holds your docs.</p>
              {params.get("error") === "one-repository" && (
                <p className="error">The app was installed on more than one repository. Select only your docs repository.</p>
              )}
              {installUrl && (
                <a className="button" href={installUrl}>
                  <GitHubIcon /> Install on GitHub
                </a>
              )}
            </div>
          </li>
        </ol>
      </main>
    </div>
  );
}
