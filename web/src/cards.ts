// How cards are laid out on the Data and Analyses pages: their order, and each card's
// width and whether it is folded to its title. Saved with the workspace.

export type CardLayout = { wide?: boolean; collapsed?: boolean };

// The list with the item at `from` moved to where the item at `to` was
export function moved<T>(list: T[], from: number, to: number): T[] {
  if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return list;
  const next = [...list];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

// Keys in a saved order first, then any new ones in their own order
export function ordered<K>(keys: K[], saved: K[] | undefined): K[] {
  const known = (saved ?? []).filter((k) => keys.includes(k));
  return [...known, ...keys.filter((k) => !known.includes(k))];
}
