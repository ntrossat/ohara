export type Status =
  | { configured: false; url: string; install_url: string | null; installed: boolean; locked: boolean }
  | {
      configured: true;
      repo: string;
      branch: string;
      private: boolean;
      user: { login: string; avatar: string } | null;
      allowed: boolean;
    };

export type NavNode = { title: string; path: string | null; folder?: string; children: NavNode[] };
export type Source = { repo: string; path: string; edit_url: string };
export type Page = { title: string; file: string; markdown: string; source: Source | null };
/** A page whose title or text matches a search, with the words around the match. */
export type SearchResult = { path: string; title: string; snippet: string };

/** A change to review: an open pull request of the docs repository. */
export type ChangeSummary = {
  number: number;
  title: string;
  author: string;
  /** The agent that wrote the change, as it names itself. */
  agent: string | null;
  branch: string;
  draft: boolean;
  updated_at: string;
  html_url: string;
};
/** A page comes with its text before and after, apart from the side it doesn't have. Other files have neither. */
export type ChangedFile = { file: string; status: "added" | "changed" | "removed"; before: string | null; after: string | null };
export type ChangeDetail = ChangeSummary & {
  description: string;
  state: "open" | "merged" | "closed";
  sha: string;
  files: ChangedFile[];
  /** The code pull request the change comes with. */
  code: { repo: string; number: number; html_url: string } | null;
  can_approve: boolean;
};

/** The path Ohara is served under, such as "/docs", set by the server. Empty at the root of the host. */
export const base = document.querySelector<HTMLMetaElement>('meta[name="ohara-base"]')?.content ?? "";

export class HttpError extends Error {
  constructor(public status: number, detail = "") {
    super(detail || `Request failed with status ${status}`);
  }
}

/** The failure of a response, with the server's message, which says what to do. */
async function failure(response: Response): Promise<HttpError> {
  const body = await response.json().catch(() => null);
  return new HttpError(response.status, typeof body?.detail === "string" ? body.detail : "");
}

export async function get<T>(url: string): Promise<T> {
  const response = await fetch(base + url, { credentials: "same-origin" });
  // Access lost (session ended or removed on GitHub): reload to show the sign-in screen.
  if (response.status === 401 || response.status === 403) location.reload();
  if (!response.ok) throw await failure(response);
  return response.json();
}

export async function post<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(base + url, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (response.status === 401 || response.status === 403) location.reload();
  if (!response.ok) throw await failure(response);
  return response.json();
}

export function signInUrl(next = location.pathname + location.hash) {
  return `${base}/api/auth/login?next=${encodeURIComponent(next)}`;
}

export async function signOut() {
  await fetch(`${base}/api/auth/logout`, { method: "POST" });
  location.assign(`${base}/`);
}
