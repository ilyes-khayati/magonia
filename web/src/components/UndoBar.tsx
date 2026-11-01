import { useEffect } from "react";
import { UNDO_SECONDS, isUndoKey, type Undo } from "../undo";

type Props = { undo: Undo | null; onDone: () => void; onError: (error: unknown) => void };

// "Analysis removed · Undo" at the foot of the page for ten seconds; ⌘Z does the same meanwhile
export default function UndoBar({ undo, onDone, onError }: Props) {
  useEffect(() => {
    if (!undo) return;
    const timer = window.setTimeout(onDone, UNDO_SECONDS * 1000);
    const key = (e: KeyboardEvent) => {
      if (!isUndoKey(e)) return;
      e.preventDefault();
      run();
    };
    const run = () => {
      onDone();
      Promise.resolve(undo.run()).catch(onError);
    };
    document.addEventListener("keydown", key);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("keydown", key);
    };
  }, [undo, onDone, onError]);

  if (!undo) return null;
  return (
    <div className="floating undo-bar" role="status">
      <span>{undo.text}</span>
      <button
        className="link"
        title="Undo (⌘Z)"
        onClick={() => {
          onDone();
          Promise.resolve(undo.run()).catch(onError);
        }}
      >
        Undo
      </button>
    </div>
  );
}
