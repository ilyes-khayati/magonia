import { useEffect, useRef, useState } from "react";
import { addFile, getInstructions, listFiles, removeFile, restoreFile, setInstructions, type LibraryFile, type PaperCard } from "../api";
import { useReader } from "../reader";
import { CloseIcon, UploadIcon } from "./Icons";

const EXAMPLES = [
  "I work on rainfed olive orchards in northern Tunisia.",
  "Always give the sensor and its resolution when you cite a study.",
  "Answer in French.",
];

// The researcher's library: their own PDFs, which Magonia reads and cites like the papers it
// finds, and their instructions for how Magonia should answer in this workspace
type Props = {
  workspaceId: number;
  onUndoable?: (text: string, undo: () => Promise<void>) => void; // offer to bring a file back
};

export default function LibraryPage({ workspaceId, onUndoable }: Props) {
  const read = useReader();
  const [files, setFiles] = useState<LibraryFile[] | null>(null);
  const [busy, setBusy] = useState<string[]>([]); // the files being read
  const [error, setError] = useState("");
  const [instructions, setText] = useState<string | null>(null);
  const [saved, setSaved] = useState(true);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    listFiles(workspaceId).then(setFiles, (e: Error) => setError(e.message));
  }, [workspaceId]);
  useEffect(() => {
    getInstructions(workspaceId).then(
      (r) => setText(r.text),
      (e: Error) => setError(e.message),
    );
  }, [workspaceId]);

  async function upload(chosen: FileList | null) {
    setError("");
    for (const file of chosen ? [...chosen] : []) {
      setBusy((b) => [...b, file.name]);
      try {
        const added = await addFile(workspaceId, file);
        setFiles((f) => [...(f ?? []), added]);
      } catch (e) {
        setError(`${file.name}: ${(e as Error).message}`);
      } finally {
        setBusy((b) => b.filter((name) => name !== file.name));
      }
    }
    if (input.current) input.current.value = "";
  }

  async function save() {
    if (instructions === null) return;
    try {
      await setInstructions(workspaceId, instructions);
      setSaved(true);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <h1>Library</h1>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="page-grid">
        <section className="card" aria-labelledby="files-title">
          <div className="card-head">
            <div>
              <h3 id="files-title">Your papers</h3>
              <span className="meta">
                PDFs you add are read page by page. When one speaks to a question, Magon cites it like a paper it found,
                and checks what it says against it. Useful for papers whose publisher blocks downloads, your reports and
                theses.
              </span>
            </div>
          </div>
          <input
            ref={input}
            type="file"
            accept="application/pdf"
            multiple
            hidden
            data-testid="library-upload"
            onChange={(e) => upload(e.target.files)}
          />
          <button className="primary row" onClick={() => input.current?.click()}>
            <UploadIcon size={14} />
            Add PDFs
          </button>
          {busy.map((name) => (
            <p key={name} className="meta" role="status">
              Reading {name}…
            </p>
          ))}
          {files === null ? (
            <p className="meta">Loading…</p>
          ) : files.length === 0 ? (
            <p className="meta">No papers yet.</p>
          ) : (
            <ul className="library-files">
              {files.map((f) => (
                <li key={f.id}>
                  <div>
                    {f.pdf && read ? (
                      <button
                        className="link file-title"
                        title="Read it here"
                        onClick={() => read({ id: f.id, title: f.title, short: f.title, doi: null, open_access_url: null } as PaperCard)}
                      >
                        {f.title}
                      </button>
                    ) : (
                      <strong title={f.pdf === false ? "Added before Magonia kept PDFs: add it again to read it here" : undefined}>{f.title}</strong>
                    )}
                    <span className="meta">
                      {f.filename} · {f.pages} {f.pages === 1 ? "page" : "pages"} · added {f.added.slice(0, 10)}
                    </span>
                  </div>
                  <button
                    className="icon-button"
                    aria-label={`Remove ${f.title} from the library`}
                    title="Remove from the library"
                    onClick={() =>
                      removeFile(f.id).then(
                        () => {
                          setFiles((all) => (all ?? []).filter((x) => x.id !== f.id));
                          onUndoable?.(`${f.title} removed from the library`, async () => {
                            const back = await restoreFile(f.id);
                            setFiles((all) => [...(all ?? []).filter((x) => x.id !== back.id), back].sort((a, b) => a.added.localeCompare(b.added)));
                          });
                        },
                        (e: Error) => setError(e.message),
                      )
                    }
                  >
                    <CloseIcon size={14} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card" aria-labelledby="instructions-title">
          <div className="card-head">
            <div>
              <h3 id="instructions-title">How Magon should answer</h3>
              <span className="meta">
                Given to Magon with every question in this workspace, after its own rules: it still cites only what it
                found and checks every number.
              </span>
            </div>
          </div>
          <textarea
            className="instructions"
            aria-label="Instructions for Magon"
            rows={8}
            maxLength={2000}
            placeholder={EXAMPLES.join("\n")}
            value={instructions ?? ""}
            disabled={instructions === null}
            onChange={(e) => {
              setText(e.target.value);
              setSaved(false);
            }}
          />
          <div className="row" style={{ justifyContent: "space-between" }}>
            <span className="meta">{(instructions ?? "").length} / 2000</span>
            <button className="primary" disabled={saved} onClick={save}>
              {saved ? "Saved" : "Save"}
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
