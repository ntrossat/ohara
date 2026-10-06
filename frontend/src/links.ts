import { base } from "./api";

/** Resolve links written in Markdown (relative to the source file) to site routes and asset URLs. */

const EXTERNAL = /^[a-z][a-z0-9+.-]*:|^\/\//i;

function normalize(parts: string[]): string[] {
  const out: string[] = [];
  for (const part of parts) {
    if (part === "..") out.pop();
    else if (part && part !== ".") out.push(part);
  }
  return out;
}

function resolve(file: string, target: string): string {
  const base = target.startsWith("/") ? [] : file.split("/").slice(0, -1);
  return normalize([...base, ...target.split("/")]).join("/");
}

export type Resolved = { kind: "external" | "page" | "local"; href: string };

export function resolveLink(file: string, href: string): Resolved {
  if (EXTERNAL.test(href)) return { kind: "external", href };
  if (href.startsWith("#")) return { kind: "local", href };
  const [target, hash = ""] = href.split("#");
  const path = resolve(file, decodeURI(target));
  const anchor = hash ? `#${hash}` : "";
  if (path.endsWith(".md")) {
    const page = path.replace(/(^|\/)(index|README)\.md$/, "").replace(/\.md$/, "");
    return { kind: "page", href: `/${page}${anchor}` };
  }
  return { kind: "local", href: `${base}/api/files/${encodeURI(path)}` };
}
