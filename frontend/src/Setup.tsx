import { useEffect, useState, type FormEvent } from "react";
import { base, get } from "./api";
import { GitHubIcon } from "./Gate";
import Mark from "./Mark";

type Props = { url: string; installUrl: string | null; installed: boolean };
type Repository = { full_name: string; private: boolean };

export default function Setup({ url, installUrl, installed }: Props) {
  const [org, setOrg] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
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
          <li className={installed ? "done" : "current"}>
            <span className="step-number">01</span>
            <div>
              <h2>Create and install the GitHub App</h2>
              <p>
                GitHub creates the app, then asks where to install it. Pick your docs repository, and the code
                repositories whose changes should update the docs. Those with a <code>.ohara.yml</code> have their docs
                synced into the docs repository, so everyone who can read it can read them. Private code is never
                synced into a public docs repository.
              </p>
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
              {installUrl && !installed && (
                <div className="setup-actions">
                  <a className="button" href={installUrl}>
                    <GitHubIcon /> Install on GitHub
                  </a>
                  <a className="button secondary" href={`${base}/api/setup/installed`}>
                    Check again
                  </a>
                </div>
              )}
            </div>
          </li>
          <li className={installed ? "current" : ""}>
            <span className="step-number">02</span>
            <div>
              <h2>Choose the docs repository</h2>
              <p>Ohara reads the docs from it.</p>
              {installed && installUrl && <RepositoryChoice installUrl={installUrl} />}
            </div>
          </li>
        </ol>
      </main>
    </div>
  );
}

function RepositoryChoice({ installUrl }: { installUrl: string }) {
  const [repos, setRepos] = useState<Repository[] | null>(null);
  const [filter, setFilter] = useState("");
  const [chosen, setChosen] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    get<Repository[]>("/api/setup/repositories").then(
      (found) => {
        setRepos(found);
        if (found.length === 1) setChosen(found[0].full_name);
      },
      () => setError("Ohara couldn't list the app's repositories. Check the server logs, then reload."),
    );
  }, []);

  async function choose(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const response = await fetch(`${base}/api/setup/repository`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ full_name: chosen }),
    }).catch(() => null);
    if (response?.ok) {
      location.assign(`${base}/`);
    } else {
      setError("Ohara couldn't use this repository. Check that the app is still installed on it, then try again.");
      setBusy(false);
    }
  }

  if (!repos) return error ? <p className="error">{error}</p> : null;
  const query = filter.trim().toLowerCase();
  const shown = repos.filter((repo) => repo.full_name.toLowerCase().includes(query));

  return (
    <form onSubmit={choose}>
      {repos.length > 6 && (
        <input
          aria-label="Filter repositories"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter repositories"
          autoComplete="off"
          spellCheck={false}
        />
      )}
      <div className="repo-list" role="radiogroup" aria-label="Repositories">
        {shown.map((repo) => (
          <label key={repo.full_name} className={repo.full_name === chosen ? "chosen" : ""}>
            <input
              type="radio"
              name="repo"
              value={repo.full_name}
              checked={repo.full_name === chosen}
              onChange={() => setChosen(repo.full_name)}
            />
            {repo.full_name}
            {repo.private && (
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-label="private">
                <rect x="3" y="7" width="10" height="7" rx="1.5" />
                <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" />
              </svg>
            )}
          </label>
        ))}
        {!shown.length && <p className="repo-empty">No repository matches.</p>}
      </div>
      <div className="setup-actions">
        <button className="button" disabled={!chosen || busy}>
          {busy ? "Connecting…" : "Use this repository"}
        </button>
        <a className="button secondary" href={installUrl}>
          Change repositories on GitHub
        </a>
      </div>
      {error && <p className="error">{error}</p>}
    </form>
  );
}
