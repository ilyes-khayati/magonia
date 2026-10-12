import { useEffect, useRef, useState } from "react";
import { setEarthEngineProject, type EarthEngineStatus } from "../api";

type Props = {
  status: EarthEngineStatus;
  onConnected: (status: EarthEngineStatus) => void;
  onClose: (() => void) | null; // null while Earth Engine is not connected: there is nothing to go back to
};

// Explains how to connect Earth Engine and saves the project once it answers (#26)
export default function EarthEngineSetup({ status, onConnected, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [project, setProject] = useState(status.project ?? "");
  const [error, setError] = useState(status.connected ? "" : (status.error ?? ""));
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    dialog.current?.showModal();
  }, []);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setChecking(true);
    setError("");
    try {
      onConnected(await setEarthEngineProject(project.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setChecking(false);
    }
  }

  return (
    <dialog
      ref={dialog}
      className="setup"
      aria-labelledby="setup-title"
      onCancel={(e) => {
        if (onClose) onClose();
        else e.preventDefault();
      }}
    >
      <h2 id="setup-title">Connect Google Earth Engine</h2>
      <p>
        Magonia reads satellite and climate data through Earth Engine, using your own project. It is
        free for research and non-commercial use.
      </p>
      <ol>
        <li>
          Register a Cloud project for Earth Engine at{" "}
          <a href="https://code.earthengine.google.com/register" target="_blank" rel="noreferrer">
            code.earthengine.google.com/register
          </a>{" "}
          (choose “Unpaid usage” and your institution).
        </li>
        <li>
          Once, in a terminal in Magonia’s <code>engine</code> folder, sign in with{" "}
          <code>uv run earthengine authenticate</code>.
        </li>
        <li>Enter the project id below. Magonia checks that Earth Engine answers before saving it.</li>
      </ol>
      <form onSubmit={save}>
        <label className="field" htmlFor="project">
          Project id
        </label>
        <div className="row">
          <input
            id="project"
            className="input"
            style={{ flex: 1 }}
            value={project}
            placeholder="my-research-project"
            onChange={(e) => setProject(e.target.value)}
            autoFocus
            required
          />
          <button className="primary" disabled={checking || !project.trim()}>
            {checking ? "Checking…" : "Connect"}
          </button>
        </div>
        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}
      </form>
      {onClose && (
        <button className="text-button close" onClick={onClose}>
          Close
        </button>
      )}
    </dialog>
  );
}
