import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router";
import { get, HttpError, signOut, type ChangeSummary, type NavNode, type Page, type Status } from "./api";
import Change from "./Change";
import Changes, { CHANGES } from "./Changes";
import { Unreachable } from "./Gate";
import Mark from "./Mark";
import Markdown from "./Markdown";
import { readingOrder, trail } from "./nav";

type Props = { status: Extract<Status, { configured: true }> };
type Loaded = { path: string; page: Page | null };

export default function Docs({ status }: Props) {
  const location = useLocation();
  const path = decodeURI(location.pathname).replace(/^\/+|\/+$/g, "");
  const [nav, setNav] = useState<NavNode[]>([]);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [unreachable, setUnreachable] = useState(false);
  // The changes to review live under a path no page can have: the list, or one change by its number.
  const review = new RegExp(`^${CHANGES.slice(1)}(?:/(\\d+))?$`).exec(path);
  const [waiting, setWaiting] = useState(0);
  // Folders start folded; the ones leading to the current page unfold.
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  function toggle(folder: string, open = !expanded.has(folder)) {
    const next = new Set(expanded);
    if (open) next.add(folder);
    else next.delete(folder);
    setExpanded(next);
  }

  useEffect(() => {
    const parts = path.split("/").filter(Boolean);
    setExpanded((current) => new Set([...current, ...parts.map((_, i) => parts.slice(0, i + 1).join("/"))]));
  }, [path]);

  useEffect(() => {
    get<NavNode[]>("/api/nav").then(setNav, () => setUnreachable(true));
    countChanges();
  }, []);

  /** The menu counts the changes waiting for review. Without an answer, it shows no count. */
  function countChanges() {
    get<ChangeSummary[]>("/api/changes").then((changes) => setWaiting(changes.length), () => setWaiting(0));
  }

  useEffect(() => {
    setMenuOpen(false);
    setQuery("");
    if (review) return;
    get<Page>(`/api/page?path=${encodeURIComponent(path)}`).then(
      (page) => setLoaded({ path, page }),
      (error) => {
        if (error instanceof HttpError && error.status === 404) setLoaded({ path, page: null });
        else setUnreachable(true);
      },
    );
  }, [path]);

  useEffect(() => {
    if (!loaded) return;
    document.title = loaded.page ? `${loaded.page.title} – ${status.repo}` : status.repo;
    const target = location.hash && document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (target) target.scrollIntoView();
    else window.scrollTo(0, 0);
  }, [loaded]);

  const repoUrl = `https://github.com/${status.repo}`;
  const shown = useMemo(() => (query ? filter(nav, query) : nav), [nav, query]);
  const pages = useMemo(() => readingOrder(nav), [nav]);
  const index = pages.findIndex((p) => p.path === loaded?.path);
  const previous = index > 0 ? pages[index - 1] : null;
  const next = index >= 0 && index < pages.length - 1 ? pages[index + 1] : null;

  if (unreachable) return <Unreachable />;
  return (
    <div className="docs">
      <header className="topbar">
        <button
          className="menu-toggle"
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          aria-expanded={menuOpen}
          aria-controls="sidebar"
          onClick={() => setMenuOpen(!menuOpen)}
        >
          <svg viewBox="0 0 20 20" width="22" height="22" aria-hidden="true">
            <path d={menuOpen ? "M5 5l10 10M15 5L5 15" : "M3 7h14M3 13h14"} stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </button>
        <Link to="/" className="home" aria-label="Ohara home">
          <Mark />
        </Link>
        <a className="chip" href={repoUrl} target="_blank" rel="noreferrer">
          {status.private && (
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <rect x="3" y="7" width="10" height="7" rx="1.5" />
              <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" />
            </svg>
          )}
          {status.repo}
        </a>
        {status.user && (
          <span className="user">
            {status.user.avatar ? (
              <img className="avatar" src={status.user.avatar} alt="" width="32" height="32" />
            ) : (
              <span className="avatar">{status.user.login[0]?.toUpperCase()}</span>
            )}
            <span className="login">{status.user.login}</span>
            <button className="button secondary small" onClick={signOut}>
              Sign out
            </button>
          </span>
        )}
      </header>

      <nav id="sidebar" className={menuOpen ? "sidebar open" : "sidebar"} aria-label="Documentation">
        <Search value={query} onChange={setQuery} />
        {(!query || matches("Overview", query)) && (
          <NavLink to="/" end className="nav-link">
            Overview
          </NavLink>
        )}
        {!query && (
          <NavLink to={CHANGES} className="nav-link changes">
            Changes
            {waiting > 0 && (
              <span className="count" aria-label={`${waiting} to review`}>
                {waiting}
              </span>
            )}
          </NavLink>
        )}
        <Tree nodes={shown} expanded={query ? null : expanded} onToggle={toggle} />
        {query && !matches("Overview", query) && shown.length === 0 && (
          <p className="nav-empty">No pages match “{query}”</p>
        )}
        {status.user && (
          <div className="sidebar-account">
            <span>Signed in as {status.user.login}</span>
            <button className="button secondary small" onClick={signOut}>
              Sign out
            </button>
          </div>
        )}
      </nav>

      <main className="content">
        {review?.[1] ? (
          <Change key={review[1]} number={Number(review[1])} status={status} onApproved={countChanges} />
        ) : review ? (
          <Changes repo={status.repo} />
        ) : loaded && (
          <article key={loaded.path} className="prose">
            {loaded.path && (
              <p className="breadcrumb">
                {trail(nav, loaded.path).map((crumb, i) => (
                  <Fragment key={i}>
                    {i > 0 && <span aria-hidden="true"> / </span>}
                    {crumb.to ? <Link to={crumb.to}>{crumb.label}</Link> : <span>{crumb.label}</span>}
                  </Fragment>
                ))}
              </p>
            )}
            {loaded.page ? (
              <Markdown file={loaded.page.file} markdown={loaded.page.markdown} />
            ) : loaded.path ? (
              <Empty title="This page doesn't exist">
                It may have been moved or renamed in {status.repo}. <Link to="/">Go to the overview</Link>.
              </Empty>
            ) : (
              <Empty title="Add an overview page">
                Create a <code>README.md</code> at the root of {status.repo}. It becomes this page once merged.
              </Empty>
            )}

            {loaded.page && (
              <footer className="page-footer">
                <a
                  className="suggest"
                  href={loaded.page.source?.edit_url ?? `${repoUrl}/edit/${status.branch}/${loaded.page.file}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                    <path d="M11 2.5l2.5 2.5L6 12.5H3.5V10z" />
                  </svg>
                  {loaded.page.source ? `suggest a change in ${loaded.page.source.repo}` : "suggest a change on GitHub"}
                </a>
                <div className="page-links">
                  {previous && (
                    <Link className="page-link" to={`/${previous.path}`}>
                      <span className="label">previous</span>
                      <span className="title">{previous.title}</span>
                    </Link>
                  )}
                  {next && (
                    <Link className="page-link next" to={`/${next.path}`}>
                      <span className="label">next</span>
                      <span className="title">{next.title}</span>
                    </Link>
                  )}
                </div>
              </footer>
            )}
          </article>
        )}
      </main>
    </div>
  );
}

const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

function Search({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target;
      const typing =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        (target instanceof HTMLElement && target.isContentEditable);

      if (event.key === "/" && !typing) {
        event.preventDefault();
        input.current?.focus();
        return;
      }

      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        input.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <label className="nav-search">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
        <circle cx="11" cy="11" r="7" />
        <path d="M20 20l-3.5-3.5" />
      </svg>
      <input
        ref={input}
        type="search"
        placeholder="Search docs"
        aria-label="Search docs"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => e.key === "Escape" && onChange("")}
      />
      {!value && <kbd>{isMac ? "⌘K" : "Ctrl K"}</kbd>}
    </label>
  );
}

function matches(title: string, query: string): boolean {
  return title.toLowerCase().includes(query.trim().toLowerCase());
}

/** Keeps pages whose title matches, with the folders that lead to them. */
function filter(nodes: NavNode[], query: string): NavNode[] {
  return nodes.flatMap((node) => {
    const children = filter(node.children, query);
    return matches(node.title, query) || children.length ? [{ ...node, children }] : [];
  });
}

const Chevron = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M6 9l6 6 6-6" />
  </svg>
);

type TreeProps = { nodes: NavNode[]; expanded: Set<string> | null; onToggle: (folder: string, open?: boolean) => void; nested?: boolean };

function Tree({ nodes, expanded, onToggle, nested }: TreeProps) {
  const here = decodeURI(useLocation().pathname).replace(/^\/+|\/+$/g, "");
  // While searching (expanded is null), every folder is open.
  const isOpen = (folder: string) => !expanded || expanded.has(folder);
  return (
    <ul className={nested ? "nav-children" : undefined}>
      {nodes.map((node) =>
        node.folder !== undefined ? (
          <li key={node.folder}>
            {node.path !== null ? (
              <div className="nav-folder">
                <button
                  className="nav-toggle"
                  aria-expanded={isOpen(node.folder)}
                  aria-label={`${isOpen(node.folder) ? "Collapse" : "Expand"} ${node.title}`}
                  onClick={() => onToggle(node.folder!)}
                >
                  <Chevron />
                </button>
                <NavLink
                  to={`/${node.path}`}
                  end
                  // Opening the folder's page unfolds it; clicking it again while there folds it.
                  onClick={() => onToggle(node.folder!, here === node.path ? !isOpen(node.folder!) : true)}
                >
                  {node.title}
                </NavLink>
              </div>
            ) : (
              <button
                className="nav-folder"
                aria-expanded={isOpen(node.folder)}
                onClick={() => onToggle(node.folder!)}
              >
                <span className="nav-toggle">
                  <Chevron />
                </span>
                <span>{node.title}</span>
              </button>
            )}
            {node.children.length > 0 && isOpen(node.folder) && (
              <Tree nodes={node.children} expanded={expanded} onToggle={onToggle} nested />
            )}
          </li>
        ) : (
          <li key={node.path}>
            <NavLink to={`/${node.path}`} end className="nav-link">
              {node.title}
            </NavLink>
          </li>
        ),
      )}
    </ul>
  );
}

function Empty({ title, children }: { title: string; children: ReactNode }) {
  return (
    <>
      <h1>{title}</h1>
      <p>{children}</p>
    </>
  );
}
