import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { get, HttpError, post, signInUrl, type ChangeDetail, type ChangedFile, type Status } from "./api";
import { CHANGES, day } from "./Changes";
import { diffMarkdown, type Segment } from "./diff";
import { GitHubIcon } from "./Gate";
import Markdown from "./Markdown";

type Props = { number: number; status: Extract<Status, { configured: true }>; onApproved: () => void };

const LABELS = { added: "new page", changed: "changed", removed: "removed" };

/** One change to review: each page it touches, with what it removes and adds, and its approval. */
export default function Change({ number, status, onApproved }: Props) {
  const [change, setChange] = useState<ChangeDetail | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const [approved, setApproved] = useState(false);

  useEffect(() => {
    window.scrollTo(0, 0);
    get<ChangeDetail>(`/api/changes/${number}`).then(
      (found) => {
        document.title = `${found.title} – ${status.repo}`;
        setChange(found);
      },
      (failure) => {
        if (failure instanceof HttpError && failure.status === 404) setMissing(true);
        else setError("GitHub didn't answer, so this change can't be shown. Reload the page in a moment.");
      },
    );
  }, []);

  async function approve() {
    if (!change) return;
    setWorking(true);
    setError("");
    try {
      await post(`/api/changes/${number}/approve`, { sha: change.sha });
      setApproved(true);
      onApproved();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "The approval didn't go through. Try again in a moment.");
    } finally {
      setWorking(false);
    }
  }

  return (
    <article className="prose">
      <p className="breadcrumb">
        <Link to={CHANGES}>changes</Link>
        <span aria-hidden="true"> / </span>
        <span>#{number}</span>
      </p>
      {missing && (
        <>
          <h1>This change doesn't exist</h1>
          <p>
            {status.repo} has no pull request #{number}. <Link to={CHANGES}>See the changes to review</Link>.
          </p>
        </>
      )}
      {change && (
        <>
          <h1>{change.title}</h1>
          <div className="change-meta">
            <span className="change-author">
              <span className="avatar" aria-hidden="true">
                {change.author.charAt(0).toUpperCase()}
              </span>
              <span>
                {change.draft ? "Draft, proposed by " : "Proposed by "}
                <strong>{change.author}</strong> · {day(change)}
              </span>
            </span>
            <span className="chip">{count(change.files)}</span>
            {change.files.some((file) => file.before !== null && file.after !== null) && (
              <span className="change-key">
                <del>removed</del> <ins>added</ins>
              </span>
            )}
          </div>
          {change.description && (
            <div className="change-why">
              <p className="change-why-title">Why this changed</p>
              <Markdown file="" markdown={change.description} />
            </div>
          )}
          {change.files.map((file) => (
            <section key={file.file} className="change-card">
              <header className="change-bar">
                <span>
                  {file.file.split("/").slice(0, -1).map((folder) => `${folder} / `)}
                  <span className="change-file">{file.file.split("/").pop()}</span>
                </span>
                <span className="badge">{LABELS[file.status]}</span>
              </header>
              <div className="change-body">
                <Pages file={file} />
              </div>
            </section>
          ))}
          {approved ? (
            <p className="notice">
              Approved and merged. The docs update in a moment. <Link to={CHANGES}>See the other changes</Link>.
            </p>
          ) : change.state !== "open" ? (
            <p className="notice">
              This change is already {change.state}. <Link to={CHANGES}>See the changes to review</Link>.
            </p>
          ) : (
            <div className="change-actions">
              {error ? (
                <p className="error">{error}</p>
              ) : (
                <p>
                  {status.user && change.draft
                    ? "This change is a draft: mark it ready for review on GitHub to approve it."
                    : status.user && !change.can_approve
                      ? `Approving needs write access to ${status.repo} on GitHub.`
                      : `Approving merges this change into ${status.repo}.`}
                </p>
              )}
              <div>
                <a className="button secondary" href={change.html_url} target="_blank" rel="noreferrer">
                  View on GitHub
                </a>
                {!status.user ? (
                  <a className="button" href={signInUrl()}>
                    <GitHubIcon /> Sign in to approve
                  </a>
                ) : (
                  change.can_approve &&
                  !change.draft && (
                    <button className="button" onClick={approve} disabled={working} aria-busy={working}>
                      <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="m5 12.5 4.5 4.5L19 7.5" />
                      </svg>
                      {working ? "Approving…" : "Approve change"}
                    </button>
                  )
                )}
              </div>
            </div>
          )}
        </>
      )}
      {!change && error && <p className="error">{error}</p>}
    </article>
  );
}

/** "2 pages", or "2 files" when the change touches more than pages. */
function count(files: ChangedFile[]): string {
  const noun = files.every((file) => file.before !== null || file.after !== null) ? "page" : "file";
  return `${files.length} ${noun}${files.length === 1 ? "" : "s"}`;
}

/** An unchanged run of a page, folded until asked for. */
function Fold({ file, segment }: { file: string; segment: Segment }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="change-fold" aria-expanded={open} onClick={() => setOpen(!open)}>
        <svg aria-hidden="true" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="m9 6 6 6-6 6" />
        </svg>
        <span>{segment.label ? `Unchanged: ${segment.label}` : "Unchanged text"}</span>
        <span>{open ? "Hide" : "Show"}</span>
      </button>
      {open && <Markdown file={file} markdown={segment.markdown} />}
    </>
  );
}

/** A changed file: a page as it reads after the change, with what the change removes and adds. */
function Pages({ file }: { file: ChangedFile }) {
  const { before, after } = file;
  const segments = useMemo(() => (before !== null && after !== null ? diffMarkdown(before, after) : []), [before, after]);
  if (before === null && after === null) return <p>Not a page: view this file's change on GitHub.</p>;
  if (before === null) return <Markdown file={file.file} markdown={after!} />;
  if (after === null) {
    return (
      <div className="diff-removed">
        <Markdown file={file.file} markdown={before} />
      </div>
    );
  }
  if (before === after) return <p>The text stays the same: only the page's front matter changes.</p>;
  return segments.map((segment, i) =>
    segment.kind === "text" ? (
      <Markdown key={i} file={file.file} markdown={segment.markdown} marked />
    ) : segment.kind === "same" ? (
      <Fold key={i} file={file.file} segment={segment} />
    ) : (
      <div key={i} className={`diff-${segment.kind}`}>
        <Markdown file={file.file} markdown={segment.markdown} />
      </div>
    ),
  );
}
