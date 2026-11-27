import { memo, useEffect, useRef, useState, type ReactNode } from "react";
import ReactMarkdown, { type Options } from "react-markdown";
import { Link } from "react-router";
import rehypeHighlight from "rehype-highlight";
import rehypeSlug from "rehype-slug";
import remarkGfm from "remark-gfm";
import { marks } from "./diff";
import { resolveLink } from "./links";

function CodeBlock({ children, language, source }: { children: ReactNode; language: string; source?: string }) {
  const pre = useRef<HTMLPreElement>(null);
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(source ?? pre.current?.innerText ?? "");
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
      {source === undefined ? <pre ref={pre}>{children}</pre> : children}
    </div>
  );
}

/** Mermaid colors and type, from the design tokens. Mermaid needs literal values, not CSS variables. */
function mermaidTheme() {
  const token = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return {
    background: token("--tint"),
    fontFamily: token("--sans"),
    fontSize: "14px",
    primaryColor: token("--bg-2"),
    primaryTextColor: token("--ink"),
    primaryBorderColor: token("--clay"),
    secondaryColor: token("--soft"),
    tertiaryColor: token("--soft"),
    lineColor: token("--muted"),
    textColor: token("--text"),
    clusterBkg: token("--soft"),
    clusterBorder: token("--line"),
    edgeLabelBackground: token("--tint"),
  };
}

let diagrams = 0;

/** A ```mermaid block drawn as a diagram. Mermaid loads only on pages that have one. Invalid source stays a code block. */
function Diagram({ source }: { source: string }) {
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let current = true;
    import("mermaid")
      .then(async ({ default: mermaid }) => {
        mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "base", themeVariables: mermaidTheme() });
        const { svg } = await mermaid.render(`diagram-${++diagrams}`, source);
        if (current) setSvg(svg);
      })
      .catch(() => current && setFailed(true));
    return () => {
      current = false;
    };
  }, [source]);

  if (failed) return <CodeBlock language="mermaid"><code>{source}</code></CodeBlock>;
  return (
    <CodeBlock language="mermaid" source={source}>
      <div className="diagram" role="img" dangerouslySetInnerHTML={svg ? { __html: svg } : undefined} />
    </CodeBlock>
  );
}

function languageOf(children: ReactNode): string {
  const child = Array.isArray(children) ? children[0] : children;
  const className: string = (child as { props?: { className?: string } })?.props?.className ?? "";
  return /language-([\w-]+)/.exec(className)?.[1] ?? "";
}

/** The plain text of a hast node, such as the source of a code block. */
function textOf(node: unknown): string {
  const { value, children } = (node ?? {}) as { value?: string; children?: unknown[] };
  return value ?? (children ?? []).map(textOf).join("");
}

const VIDEO = /\.(mp4|webm|mov)$/i;
const remarkPlugins = [remarkGfm];
const rehypePlugins: Options["rehypePlugins"] = [rehypeSlug, [rehypeHighlight, { detect: false }]];
const markedPlugins: Options["rehypePlugins"] = [[rehypeHighlight, { detect: false }], marks];

type Props = { file: string; markdown: string; marked?: boolean };

/**
 * Markdown from the file it was written in, which its relative links start from. `marked` shows the marks of a diff.
 * Memoized: parsing and highlighting rerun only when the text changes.
 */
export default memo(function Markdown({ file, markdown, marked }: Props) {
  return (
    <ReactMarkdown
      remarkPlugins={remarkPlugins}
      rehypePlugins={marked ? markedPlugins : rehypePlugins}
      components={{
        a({ href = "", children, node: _node, ...rest }) {
          const link = resolveLink(file, href);
          if (link.kind === "page") return <Link to={link.href} {...rest}>{children}</Link>;
          if (link.kind === "external") return <a href={link.href} target="_blank" rel="noreferrer" {...rest}>{children}</a>;
          return <a href={link.href} {...rest}>{children}</a>;
        },
        img({ src = "", alt = "", node: _node, ...rest }) {
          const link = typeof src === "string" ? resolveLink(file, src) : null;
          // ![alt](clip.mp4) plays the video once, silently, without controls.
          if (link && VIDEO.test(link.href)) {
            return <video src={link.href} aria-label={alt} autoPlay muted playsInline />;
          }
          return <img src={link?.href} alt={alt} loading="lazy" {...rest} />;
        },
        pre({ children, node }) {
          const language = languageOf(children);
          if (language === "mermaid") return <Diagram source={textOf(node)} />;
          return <CodeBlock language={language}>{children}</CodeBlock>;
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
      {markdown}
    </ReactMarkdown>
  );
});
