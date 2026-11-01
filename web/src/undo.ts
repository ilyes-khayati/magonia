// Nothing is lost by one click: what is removed can be brought back from the bar that says so,
// or with ⌘Z, instead of being asked "are you sure?" first.

export type Undo = {
  key: number; // a new key restarts the bar's timer
  text: string; // "Analysis removed"
  run: () => void | Promise<void>;
  workspace: number | null; // offered only in this workspace; null: in every workspace
};

// How long the bar stays
export const UNDO_SECONDS = 10;

// Where something removed from a list was, so that it can go back to the same place
export type Removed<T> = { item: T; index: number };

export function removeFrom<T extends { id: number }>(list: T[], id: number): { rest: T[]; removed: Removed<T> | null } {
  const index = list.findIndex((x) => x.id === id);
  if (index < 0) return { rest: list, removed: null };
  return { rest: [...list.slice(0, index), ...list.slice(index + 1)], removed: { item: list[index], index } };
}

// Puts an item back where it was, in the list as it is now: changes made since are kept, and an
// item already back is not added twice
export function restoreAt<T extends { id: number }>(list: T[], { item, index }: Removed<T>): T[] {
  if (list.some((x) => x.id === item.id)) return list;
  const at = Math.min(index, list.length);
  return [...list.slice(0, at), item, ...list.slice(at)];
}

// ⌘Z or Ctrl+Z, outside text fields, whose own undo it must not take over
type Key = Pick<KeyboardEvent, "key" | "metaKey" | "ctrlKey" | "shiftKey" | "altKey" | "target">;

export function isUndoKey(e: Key): boolean {
  if (e.key.toLowerCase() !== "z" || !(e.metaKey || e.ctrlKey) || e.shiftKey || e.altKey) return false;
  const target = e.target as HTMLElement | null;
  return !(target?.isContentEditable || target?.closest?.("input, textarea, select, [contenteditable]"));
}
