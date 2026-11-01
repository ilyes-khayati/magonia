import { useEffect } from "react";
import type { Readable } from "../reader";
import { CloseIcon } from "./Icons";

// A paper of the researcher's library, read inside Magonia in the browser's own PDF viewer,
// open at the page a citation names. Escape or the close button returns to the work.
export default function Reader({ paper, onClose }: { paper: Readable; onClose: () => void }) {
  useEffect(() => {
    const close = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [onClose]);
  const page = /#page=(\d+)/.exec(paper.url)?.[1];
  return (
    <div className="reader-backdrop" onClick={onClose}>
      <section className="card reader" role="dialog" aria-modal="true" aria-label={`Reading ${paper.title}`} onClick={(e) => e.stopPropagation()}>
        <div className="card-head">
          <div>
            <h3>{paper.title}</h3>
            <span className="meta">{page ? `Opened at page ${page}` : "Your library"}</span>
          </div>
          <div className="row">
            <a className="link" href={paper.url} target="_blank" rel="noreferrer">
              Open in a new tab
            </a>
            <button className="icon-button" aria-label="Close the paper" title="Close (Esc)" onClick={onClose}>
              <CloseIcon size={14} />
            </button>
          </div>
        </div>
        <iframe title={paper.title} src={paper.url} />
      </section>
    </div>
  );
}
