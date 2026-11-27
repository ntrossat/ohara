/**
 * The differences between two versions of a Markdown page, kept as Markdown so they render like the page.
 *
 * Removed and added words are wrapped in private-use characters, which pass through the Markdown parser as text.
 * Once the page is HTML, `marks` turns them into <del> and <ins>. Code and HTML blocks can't hold marks: they show
 * whole, as removed or added.
 */

const DEL = "";
const INS = "";
const END = "";
const MAX_CELLS = 4_000_000; // the largest comparison table; larger inputs count as fully changed
const SIMILAR = 0.34; // the share of words two texts must keep to be compared word by word

const FOLD = 3; // the fewest unchanged blocks worth folding

/**
 * `text` renders in place, with its marks. `added` and `removed` are whole blocks. `same` is an unchanged run to
 * fold, with the sections it holds as its label.
 */
export type Segment = { kind: "text" | "added" | "removed" | "same"; markdown: string; label?: string };

/** A change, then the unchanged run after it. */
type Hunk = { del: string[]; ins: string[]; same: string[] };

/** The longest common subsequence of two lists, as the changes between them. */
function hunks(a: string[], b: string[]): Hunk[] {
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start++;
  let endA = a.length;
  let endB = b.length;
  while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) endA--, endB--;
  const x = a.slice(start, endA);
  const y = b.slice(start, endB);
  const out: Hunk[] = [{ del: [], ins: [], same: a.slice(0, start) }];
  if (!x.length || !y.length || x.length * y.length > MAX_CELLS) {
    out.push({ del: x, ins: y, same: [] });
  } else {
    const width = y.length + 1;
    const table = new Uint32Array((x.length + 1) * width);
    for (let i = x.length - 1; i >= 0; i--) {
      for (let j = y.length - 1; j >= 0; j--) {
        table[i * width + j] =
          x[i] === y[j] ? table[(i + 1) * width + j + 1] + 1 : Math.max(table[(i + 1) * width + j], table[i * width + j + 1]);
      }
    }
    let current: Hunk = { del: [], ins: [], same: [] };
    let i = 0;
    let j = 0;
    while (i < x.length || j < y.length) {
      if (i < x.length && j < y.length && x[i] === y[j]) {
        current.same.push(x[i]);
        i++, j++;
        continue;
      }
      if (current.same.length) {
        out.push(current);
        current = { del: [], ins: [], same: [] };
      }
      if (j >= y.length || (i < x.length && table[(i + 1) * width + j] >= table[i * width + j + 1])) current.del.push(x[i++]);
      else current.ins.push(y[j++]);
    }
    out.push(current);
  }
  out.push({ del: [], ins: [], same: a.slice(endA) });
  return out;
}

/** Blocks of a page: the text between blank lines, with each fenced code block kept whole. */
function blocks(markdown: string): string[] {
  const out: string[] = [];
  let current: string[] = [];
  let fence = "";
  for (const line of markdown.replace(/\r\n/g, "\n").split("\n")) {
    const mark = /^\s{0,3}(`{3,}|~{3,})/.exec(line)?.[1] ?? "";
    if (fence) {
      current.push(line);
      if (mark[0] === fence[0] && mark.length >= fence.length && line.trim() === mark) fence = "";
    } else if (mark || line.trim()) {
      fence = mark;
      current.push(line);
    } else if (current.length) {
      out.push(current.join("\n"));
      current = [];
    }
  }
  if (current.length) out.push(current.join("\n"));
  return out;
}

/** Mark a text as removed or added. The marks go inside its emphasis, which Markdown only reads next to a space. */
function wrap(text: string, open: string): string {
  const [, lead, body, tail] = /^(\s*[*_~]*)(.*?)([*_~]*\s*)$/s.exec(text)!;
  return body ? lead + open + body + END + tail : text;
}

const TOKEN = /!?\[[^\]\n]*\]\([^)\n]*\)|`[^`\n]+`|\s+|\S+/g; // a link, inline code, spaces, or a word

/** One line of text with its changed words marked, or null when too little of it stays to read it that way. */
function words(before: string, after: string): string | null {
  const a = before.match(TOKEN) ?? [];
  const b = after.match(TOKEN) ?? [];
  const count = (tokens: string[]) => tokens.filter((token) => token.trim()).length;
  const parts = hunks(a, b);
  const most = Math.max(count(a), count(b));
  if (most && parts.reduce((kept, part) => kept + count(part.same), 0) / most < SIMILAR) return null;
  return parts.map((part) => wrap(part.del.join(""), DEL) + wrap(part.ins.join(""), INS) + part.same.join("")).join("");
}

const PREFIX = /^(\s*(?:#{1,6}\s+|[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+|>\s?)*)(.*)$/; // what makes a line a heading, item or quote
const RULE = /^[\s|:=-]*$/; // rules, table delimiter rows and heading underlines: structure, never marked
const isRow = (line: string) => /^\s*\|/.test(line);
const cells = (line: string) => line.split(/(?<!\\)\|/);

/** A whole line marked as removed or added, or null for a removed line that only held structure. */
function whole(line: string, open: string): string | null {
  if (RULE.test(line)) return open === INS ? line : null;
  if (isRow(line)) return cells(line).map((cell) => wrap(cell, open)).join("|");
  const [, prefix, rest] = PREFIX.exec(line)!;
  return prefix + wrap(rest, open);
}

/** A changed line: its words marked in place, or the old line then the new one. Table rows compare cell by cell. */
function line(before: string, after: string): string[] {
  const apart = [whole(before, DEL), whole(after, INS)].filter((marked) => marked !== null);
  if (RULE.test(before) || RULE.test(after) || isRow(before) !== isRow(after)) return apart;
  if (isRow(after)) {
    const old = cells(before);
    const now = cells(after);
    if (old.length !== now.length) return apart;
    return [now.map((cell, i) => words(old[i], cell) ?? wrap(old[i], DEL) + wrap(cell, INS)).join("|")];
  }
  const [, prefix, rest] = PREFIX.exec(after)!;
  const marked = words(PREFIX.exec(before)![2], rest);
  return marked === null ? apart : [prefix + marked];
}

const WORD = /[\p{L}\p{N}]+/gu; // letters and digits only, so list and table markup never makes two texts alike
const SOLID = /^\s*(`{3,}|~{3,}|<)/; // code and HTML blocks

/** Whether two blocks or lines are versions of the same one, to compare in place. */
function similar(a: string, b: string): boolean {
  if (SOLID.test(a) || SOLID.test(b) || isRow(a) !== isRow(b)) return false;
  const old = new Set(a.match(WORD));
  const now = new Set(b.match(WORD));
  return [...now].filter((word) => old.has(word)).length / Math.max(old.size, now.size) >= SIMILAR;
}

/** A change in reading order: each removed item with the added one that is a version of it, or alone. */
function pairs(hunk: Hunk): { old?: string; now?: string }[] {
  const out: { old?: string; now?: string }[] = [];
  let next = 0;
  for (const old of hunk.del) {
    const match = hunk.ins.findIndex((now, j) => j >= next && similar(old, now));
    if (match < 0) {
      out.push({ old });
      continue;
    }
    out.push(...hunk.ins.slice(next, match).map((now) => ({ now })), { old, now: hunk.ins[match] });
    next = match + 1;
  }
  return [...out, ...hunk.ins.slice(next).map((now) => ({ now }))];
}

/** A changed block, line by line. */
function inline(before: string, after: string): string {
  const out: (string | null)[] = [];
  for (const hunk of hunks(before.split("\n"), after.split("\n"))) {
    for (const { old, now } of pairs(hunk)) {
      if (old !== undefined && now !== undefined) out.push(...line(old, now));
      else out.push(old !== undefined ? whole(old, DEL) : whole(now!, INS));
    }
    out.push(...hunk.same);
  }
  return out.filter((marked) => marked !== null).join("\n");
}

/** The page after a change, in segments to render in order, with what the change removed and added. */
export function diffMarkdown(before: string, after: string): Segment[] {
  const out: Segment[] = [];
  const add = (kind: Segment["kind"], markdown: string) => {
    const last = out[out.length - 1];
    if (last?.kind === kind) last.markdown += `\n\n${markdown}`;
    else out.push({ kind, markdown });
  };
  /** An unchanged run: folded, apart from the page's title and the headings right above the next change. */
  const same = (run: string[], last: boolean) => {
    const head = !out.length && /^#\s/.test(run[0] ?? "") ? 1 : 0;
    let tail = run.length;
    while (!last && tail > head && HEADING.test(run[tail - 1])) tail--;
    const middle = run.slice(head, tail);
    if (middle.length < FOLD) return run.forEach((block) => add("text", block));
    run.slice(0, head).forEach((block) => add("text", block));
    const titles = middle.filter((block) => HEADING.test(block)).map((block) => HEADING.exec(block)![1].replace(/[`*_]/g, ""));
    const label = titles.length > 1 ? `${titles[0]} to ${titles[titles.length - 1]}` : titles[0];
    out.push({ kind: "same", markdown: middle.join("\n\n"), label });
    run.slice(tail).forEach((block) => add("text", block));
  };
  const parts = hunks(blocks(before), blocks(after));
  parts.forEach((hunk, i) => {
    for (const { old, now } of pairs(hunk)) {
      if (old !== undefined && now !== undefined) add("text", inline(old, now));
      else if (old !== undefined) add("removed", old);
      else add("added", now!);
    }
    same(hunk.same, i === parts.length - 1);
  });
  return out;
}

const HEADING = /^\s{0,3}#{1,6}\s+([^\n]*?)\s*#*\s*$/; // a block that is one heading line

type Node = { type: string; value?: string; tagName?: string; properties?: object; children?: Node[] };

/** A rehype plugin: puts the text between the marks in <del> and <ins>, wherever the marks fall in the page. */
export function marks() {
  return (tree: Node) => {
    let open = "";
    const visit = (node: Node) => {
      node.children = node.children?.flatMap((child): Node[] => {
        if (child.type !== "text") {
          visit(child);
          return [child];
        }
        return (child.value ?? "").split(/([-])/).flatMap((part): Node[] => {
          if (part === DEL || part === INS || part === END) {
            open = part === END ? "" : part;
            return [];
          }
          const text = { type: "text", value: part };
          if (!open || !part.trim()) return part ? [text] : [];
          return [{ type: "element", tagName: open === DEL ? "del" : "ins", properties: {}, children: [text] }];
        });
      });
    };
    visit(tree);
  };
}
