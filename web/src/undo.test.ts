import { describe, expect, it } from "vitest";
import { isUndoKey, removeFrom, restoreAt } from "./undo";

const list = [{ id: 1 }, { id: 2 }, { id: 3 }];

describe("removing and restoring", () => {
  it("puts an item back where it was", () => {
    const { rest, removed } = removeFrom(list, 2);
    expect(rest).toEqual([{ id: 1 }, { id: 3 }]);
    expect(restoreAt(rest, removed!)).toEqual(list);
  });

  it("keeps what changed meanwhile", () => {
    const { removed } = removeFrom(list, 3);
    const changed = [{ id: 1 }, { id: 4 }];
    expect(restoreAt(changed, removed!)).toEqual([{ id: 1 }, { id: 4 }, { id: 3 }]);
  });

  it("lands at the end if the list became shorter", () => {
    const { removed } = removeFrom(list, 3);
    expect(restoreAt([], removed!)).toEqual([{ id: 3 }]);
  });

  it("does not restore twice", () => {
    const { removed } = removeFrom(list, 1);
    expect(restoreAt(list, removed!)).toBe(list);
  });

  it("ignores an id that is not there", () => {
    expect(removeFrom(list, 9)).toEqual({ rest: list, removed: null });
  });
});

describe("the undo key", () => {
  const key = (init: Partial<KeyboardEvent>, target: object = {}) =>
    ({ metaKey: false, ctrlKey: false, shiftKey: false, altKey: false, ...init, target: { closest: () => null, ...target } }) as unknown as KeyboardEvent;

  it("is ⌘Z or Ctrl+Z", () => {
    expect(isUndoKey(key({ key: "z", metaKey: true }))).toBe(true);
    expect(isUndoKey(key({ key: "z", ctrlKey: true }))).toBe(true);
    expect(isUndoKey(key({ key: "z" }))).toBe(false);
    expect(isUndoKey(key({ key: "z", metaKey: true, shiftKey: true }))).toBe(false); // redo
  });

  it("is left to text fields", () => {
    expect(isUndoKey(key({ key: "z", metaKey: true }, { closest: () => ({}) }))).toBe(false);
  });
});
