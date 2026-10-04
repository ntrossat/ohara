import type { NavNode } from "./api";

export type PageRef = { title: string; path: string };

/** Every node in tree order: each folder followed by its children. */
function flatten(nodes: NavNode[]): NavNode[] {
  return nodes.flatMap((node) => [node, ...flatten(node.children)]);
}

/** Pages in reading order: the overview, then each folder's index page followed by its children. */
export function readingOrder(nodes: NavNode[]): PageRef[] {
  const pages = flatten(nodes).flatMap((node) => (node.path !== null ? [{ title: node.title, path: node.path }] : []));
  return [{ title: "Overview", path: "" }, ...pages];
}

/** Breadcrumb segments for a page path: each parent folder, linked when it has an index page. */
export function trail(nodes: NavNode[], path: string): { label: string; to: string | null }[] {
  const folders = new Map(flatten(nodes).flatMap((node) => (node.folder ? [[node.folder, node] as const] : [])));
  const parts = path.split("/").filter(Boolean);
  return parts.map((label, i) => {
    const prefix = parts.slice(0, i + 1).join("/");
    const folder = folders.get(prefix);
    const last = i === parts.length - 1;
    return { label, to: !last && folder?.path ? `/${folder.path}` : null };
  });
}
