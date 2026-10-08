import { Fragment, memo, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import ReactMarkdown, { type Options } from "react-markdown";
import { Link, NavLink, useLocation } from "react-router";
import rehypeHighlight from "rehype-highlight";
import rehypeSlug from "rehype-slug";
import remarkGfm from "remark-gfm";
import { get, HttpError, signOut, type NavNode, type Page, type Status } from "./api";
import { resolveLink } from "./links";
import { Unreachable } from "./Gate";
import Mark from "./Mark";
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
  }, []);

  useEffect(() => {
    setMenuOpen(false);
    setQuery("");
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
        <Tree nodes={query ? filter(nav, query) : nav} expanded={query ? null : expanded} onToggle={toggle} />
        {query && !matches("Overview", query) && filter(nav, query).length === 0 && (
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
        {loaded && (
          <>
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
                <Markdown page={loaded.page} />
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
          </>
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
                  onClick={() => {
                    // Opening the folder's page unfolds it; clicking it again while there folds it.
                    const here = decodeURI(location.pathname).replace(/^\/+|\/+$/g, "") === node.path;
                    onToggle(node.folder!, here ? !isOpen(node.folder!) : true);
                  }}
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

function CodeBlock({ children, language }: { children: ReactNode; language: string }) {
  const pre = useRef<HTMLPreElement>(null);
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(pre.current?.innerText ?? "");
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="code-block">
      <div className="code-bar">
        <span className="code-language">{language || "text"}</span>
        <button className="text-button" onClick={copy}>
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <rect x="5" y="5" width="9" height="9" rx="1.5" />
            <path d="M11 5V3.5A1.5 1.5 0 0 0 9.5 2h-6A1.5 1.5 0 0 0 2 3.5v6A1.5 1.5 0 0 0 3.5 11H5" />
          </svg>
          {copied ? "copied" : "copy"}
        </button>
      </div>
      <pre ref={pre}>{children}</pre>
    </div>
  );
}

function languageOf(children: ReactNode): string {
  const child = Array.isArray(children) ? children[0] : children;
  const className: string = (child as { props?: { className?: string } })?.props?.className ?? "";
  return /language-([\w-]+)/.exec(className)?.[1] ?? "";
}

const VIDEO = /\.(mp4|webm|mov)$/i;
const remarkPlugins = [remarkGfm];
const rehypePlugins: Options["rehypePlugins"] = [rehypeSlug, [rehypeHighlight, { detect: false }]];

/** Memoized: parsing and highlighting rerun only when the page changes. */
const Markdown = memo(function Markdown({ page }: { page: Page }) {
  return (
    <ReactMarkdown
      remarkPlugins={remarkPlugins}
      rehypePlugins={rehypePlugins}
      components={{
        a({ href = "", children, node: _node, ...rest }) {
          const link = resolveLink(page.file, href);
          if (link.kind === "page") return <Link to={link.href} {...rest}>{children}</Link>;
          if (link.kind === "external") return <a href={link.href} target="_blank" rel="noreferrer" {...rest}>{children}</a>;
          return <a href={link.href} {...rest}>{children}</a>;
        },
        img({ src = "", alt = "", node: _node, ...rest }) {
          const link = typeof src === "string" ? resolveLink(page.file, src) : null;
          // ![alt](clip.mp4) plays the video once, silently, without controls.
          if (link && VIDEO.test(link.href)) {
            return <video src={link.href} aria-label={alt} autoPlay muted playsInline />;
          }
          return <img src={link?.href} alt={alt} loading="lazy" {...rest} />;
        },
        pre({ children }) {
          return <CodeBlock language={languageOf(children)}>{children}</CodeBlock>;
        },
        table({ node: _node, ...rest }) {
          return (
            <div className="table-wrap">
              <table {...rest} />
            </div>
          );
        },
      }}
    >
      {page.markdown}
    </ReactMarkdown>
  );
});
