import { useEffect, useState } from "react";
import { Link } from "react-router";
import { get, type ChangeSummary } from "./api";

/** Where the changes to review live: under a path no page can have. */
export const CHANGES = "/-/changes";

/** "20 Nov 2026": the day a change was last updated. */
export function day(change: ChangeSummary): string {
  return new Date(change.updated_at).toLocaleDateString(undefined, { dateStyle: "medium" });
}

/** "proposed by ada · 20 Nov 2026", as the list says it. */
function proposed(change: ChangeSummary): string {
  return `${change.draft ? "draft, " : ""}proposed by ${change.author}${change.agent ? ` with ${change.agent}` : ""} · ${day(change)}`;
}

/** The changes waiting for review: the open pull requests of the docs repository. */
export default function Changes({ repo }: { repo: string }) {
  const [changes, setChanges] = useState<ChangeSummary[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    document.title = `Changes – ${repo}`;
    window.scrollTo(0, 0);
    get<ChangeSummary[]>("/api/changes").then(setChanges, () => setFailed(true));
  }, []);

  return (
    <article className="prose">
      <h1>Changes</h1>
      <p>The changes proposed to {repo}. Approving one merges it into the docs.</p>
      {failed && <p className="error">GitHub didn't answer, so the changes can't be listed. Reload the page in a moment.</p>}
      {changes?.length === 0 && <p>Nothing to review: every proposed change is merged.</p>}
      {changes && changes.length > 0 && (
        <ul className="change-list">
          {changes.map((change) => (
            <li key={change.number}>
              <Link className="page-link" to={`${CHANGES}/${change.number}`}>
                <span className="title">{change.title}</span>
                <span className="label">
                  #{change.number} · {proposed(change)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
