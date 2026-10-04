export type Status =
  | { configured: false; url: string; install_url: string | null }
  | {
      configured: true;
      repo: string;
      branch: string;
      private: boolean;
      user: { login: string; avatar: string } | null;
      allowed: boolean;
    };

export type NavNode = { title: string; path: string | null; folder?: string; children: NavNode[] };
export type Page = { title: string; file: string; markdown: string };

export class HttpError extends Error {
  constructor(public status: number) {
    super(`Request failed with status ${status}`);
  }
}

export async function get<T>(url: string): Promise<T> {
  const response = await fetch(url, { credentials: "same-origin" });
  // Access lost (session ended or removed on GitHub): reload to show the sign-in screen.
  if (response.status === 401 || response.status === 403) location.reload();
  if (!response.ok) throw new HttpError(response.status);
  return response.json();
}

export function signInUrl(next = location.pathname + location.hash) {
  return `/api/auth/login?next=${encodeURIComponent(next)}`;
}

export async function signOut() {
  await fetch("/api/auth/logout", { method: "POST" });
  location.assign("/");
}
