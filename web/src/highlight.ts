// Highlights on the board: what the researcher marked, painted over the text where it appears
// with the browser's CSS Custom Highlight API, so a card's content is never changed to show
// them. Every card's marks go into one highlight named "board-highlight" (styled in
// index.css); browsers without the API still list the highlights under each card.

const marked = new Map<string, Range[]>(); // card id → the ranges of its highlights

function repaint() {
  if (!("highlights" in CSS)) return;
  const ranges = [...marked.values()].flat();
  if (ranges.length) CSS.highlights.set("board-highlight", new Highlight(...ranges));
  else CSS.highlights.delete("board-highlight");
}

// The ranges where each phrase occurs in the element's text, even across several text nodes
export function findRanges(root: Node, phrases: string[]): Range[] {
  const nodes: Text[] = [];
  // the list of highlights under a card repeats them, and is not marked
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (node) =>
      node.parentElement?.closest(".highlights") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
  });
  while (walker.nextNode()) nodes.push(walker.currentNode as Text);
  const raw = nodes.map((n) => n.data).join("");
  // where each node starts in the joined text
  const starts: number[] = [];
  nodes.reduce((at, n) => (starts.push(at), at + n.data.length), 0);
  // the text with each run of white space made one space, and where each character came from
  let text = "";
  const from: number[] = [];
  for (let i = 0; i < raw.length; i++) {
    if (/\s/.test(raw[i]) && (text.endsWith(" ") || !text)) continue;
    text += /\s/.test(raw[i]) ? " " : raw[i];
    from.push(i);
  }
  const locate = (offset: number, end: boolean) => {
    let i = starts.length - 1;
    while (i > 0 && (end ? starts[i] >= offset : starts[i] > offset)) i--;
    return { node: nodes[i], offset: offset - starts[i] };
  };
  const ranges: Range[] = [];
  for (const phrase of phrases) {
    const needle = phrase.replace(/\s+/g, " ").trim();
    if (!needle) continue;
    for (let at = text.indexOf(needle); at >= 0; at = text.indexOf(needle, at + needle.length)) {
      const start = locate(from[at], false);
      const end = locate(from[at + needle.length - 1] + 1, true);
      const range = document.createRange();
      range.setStart(start.node, start.offset);
      range.setEnd(end.node, end.offset);
      ranges.push(range);
    }
  }
  return ranges;
}

export function paint(id: string, root: Node | null, phrases: string[]) {
  if (root && phrases.length) marked.set(id, findRanges(root, phrases));
  else marked.delete(id);
  repaint();
}

// The text selected inside the element, if any, on one line
export function selectedIn(root: Node | null): string {
  const selection = window.getSelection();
  if (!root || !selection || selection.isCollapsed || !selection.rangeCount) return "";
  const range = selection.getRangeAt(0);
  if (!root.contains(range.commonAncestorContainer)) return "";
  return selection.toString().replace(/\s+/g, " ").trim();
}
