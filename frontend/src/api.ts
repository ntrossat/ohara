export type Status =
  | { configured: false; url: string; install_url: string | null; installed: boolean }
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

/** The path Ohara is served under, such as "/docs", set by the server. Empty at the root of the host. */
export const base = document.querySelector<HTMLMetaElement>('meta[name="ohara-base"]')?.content ?? "";

export class HttpError extends Error {
  constructor(public status: number) {
    super(`Request failed with status ${status}`);
  }
}

export async function get<T>(url: string): Promise<T> {
  const response = await fetch(base + url, { credentials: "same-origin" });
  // Access lost (session ended or removed on GitHub): reload to show the sign-in screen.
  if (response.status === 401 || response.status === 403) location.reload();
  if (!response.ok) throw new HttpError(response.status);
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
  if (!response.ok) throw new HttpError(response.status);
  return response.json();
}

export function signInUrl(next = location.pathname + location.hash) {
  return `${base}/api/auth/login?next=${encodeURIComponent(next)}`;
}

export async function signOut() {
  await fetch(`${base}/api/auth/logout`, { method: "POST" });
  location.assign(`${base}/`);
}
