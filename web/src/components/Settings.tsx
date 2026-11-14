import { useCallback, useEffect, useRef, useState } from "react";
import {
  installedModels,
  magonSettings,
  saveMagonSettings,
  type EarthEngineStatus,
  type MagonSettings,
} from "../api";
import type { ThemeChoice } from "../theme";
import { CloseIcon, SettingsIcon } from "./Icons";

type Props = {
  theme: ThemeChoice;
  onTheme: (theme: ThemeChoice) => void;
  earthEngine: EarthEngineStatus | null;
  onEarthEngine: () => void;
};

type Section = "appearance" | "magon" | "earth-engine";
const SECTIONS: [Section, string][] = [
  ["magon", "Magon"],
  ["appearance", "Appearance"],
  ["earth-engine", "Earth Engine"],
];

// Temperature: how much an answer may vary. Null keeps the model's own.
const CREATIVITY: [number | null, string, string][] = [
  [null, "Model default", "The value the model was published with."],
  [
    0.2,
    "Precise",
    "Steady answers that keep close to the papers and the data.",
  ],
  [0.5, "Balanced", "Some variety in wording and in the angles taken."],
  [
    0.9,
    "Exploratory",
    "More varied answers, for brainstorming. More likely to drift.",
  ],
];

// Settings, opened from the foot of the rail. A dot on the button says when Earth Engine needs
// attention.
export default function SettingsMenu(props: Props) {
  const { earthEngine } = props;
  const [open, setOpen] = useState(false);
  const connected = earthEngine?.connected ?? false;
  return (
    <>
      <button
        className="rail-link"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label="Settings"
        title="Settings"
        onClick={() => setOpen(true)}
      >
        <SettingsIcon size={22} />
        {earthEngine !== null && !connected && (
          <span className="attention" aria-hidden="true" />
        )}
      </button>
      {open && <SettingsDialog {...props} onClose={() => setOpen(false)} />}
    </>
  );
}

function SettingsDialog({
  theme,
  onTheme,
  earthEngine,
  onEarthEngine,
  onClose,
}: Props & { onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [section, setSection] = useState<Section>("magon");
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  const connected = earthEngine?.connected ?? false;

  return (
    <dialog
      ref={dialog}
      className="settings-dialog"
      aria-labelledby="settings-title"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => e.target === dialog.current && onClose()}
    >
      <div className="settings-frame">
        <nav className="settings-nav" aria-label="Settings sections">
          <h2 id="settings-title">Settings</h2>
          {SECTIONS.map(([key, label]) => (
            <button
              key={key}
              aria-current={section === key}
              onClick={() => setSection(key)}
            >
              {label}
              {key === "earth-engine" && earthEngine !== null && !connected && (
                <span className="attention" aria-hidden="true" />
              )}
            </button>
          ))}
        </nav>
        <div className="settings-body">
          <button
            className="icon-button settings-close"
            aria-label="Close settings"
            onClick={onClose}
          >
            <CloseIcon size={16} />
          </button>
          {section === "appearance" && (
            <section aria-labelledby="appearance-title">
              <h3 id="appearance-title">Appearance</h3>
              <div className="choice-cards" role="group" aria-label="Theme">
                {(
                  [
                    ["light", "Light"],
                    ["dark", "Dark"],
                    ["system", "Same as the system"],
                  ] as const
                ).map(([value, label]) => (
                  <button
                    key={value}
                    aria-pressed={theme === value}
                    onClick={() => onTheme(value)}
                  >
                    <span className={`theme-swatch ${value}`} aria-hidden="true" />
                    {label}
                  </button>
                ))}
              </div>
            </section>
          )}
          {section === "magon" && <MagonSection />}
          {section === "earth-engine" && (
            <section aria-labelledby="ee-title">
              <h3 id="ee-title">Google Earth Engine</h3>
              <p className="settings-help">
                Magonia reads satellite data through your own Earth Engine
                project. Research use is free.
              </p>
              <p className="engine-line">
                <span className="dot" data-ok={connected} />
                {earthEngine === null
                  ? "Checking…"
                  : connected
                    ? "Connected"
                    : "Not connected"}
              </p>
              {connected && earthEngine?.project && (
                <p className="meta">
                  Project <span className="mono">{earthEngine.project}</span>
                </p>
              )}
              <div>
                <button
                  className="button"
                  onClick={() => {
                    onClose();
                    onEarthEngine();
                  }}
                >
                  {connected ? "Change project…" : "Connect…"}
                </button>
              </div>
            </section>
          )}
        </div>
      </div>
    </dialog>
  );
}

const sameSettings = (a: MagonSettings, b: MagonSettings) =>
  JSON.stringify(a) === JSON.stringify(b);

// How Magon answers: which model, on which server, how long and how varied its answers are, and
// how many papers it reads per search
function MagonSection() {
  const [saved, setSaved] = useState<MagonSettings | null>(null);
  const [form, setForm] = useState<MagonSettings | null>(null);
  const [inUse, setInUse] = useState<{
    model_url: string | null;
    model: string | null;
  }>({ model_url: null, model: null });
  const [models, setModels] = useState<string[] | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [error, setError] = useState("");

  const listModels = useCallback((url?: string) => {
    installedModels(url)
      .then((found) => {
        setModels(found.models);
        setServerError(found.error);
      })
      .catch(() => {
        setModels([]);
        setServerError("The model server did not answer at this address.");
      });
  }, []);

  useEffect(() => {
    magonSettings()
      .then(({ in_use, ...settings }) => {
        setSaved(settings);
        setForm(settings);
        setInUse(in_use);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    listModels();
  }, [listModels]);

  if (!form || !saved)
    return (
      <section>
        {error ? (
          <p className="error">{error}</p>
        ) : (
          <p className="meta">Loading…</p>
        )}
      </section>
    );
  const set = (change: Partial<MagonSettings>) =>
    setForm({ ...form, ...change });
  const dirty = !sameSettings(form, saved);

  async function save() {
    if (!form) return;
    setError("");
    try {
      const done = await saveMagonSettings(form);
      setSaved(done);
      setForm(done);
      const next = await magonSettings();
      setInUse(next.in_use);
      window.dispatchEvent(new Event("magon-settings"));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <section aria-labelledby="magon-title">
      <h3 id="magon-title">Magon</h3>
      <p className="settings-help">
        Magon answers with an open language model that runs on your own computer
        or network, through Ollama. Nothing you ask leaves it, except the
        searches for papers.
      </p>

      <div className="setting-row">
        <label className="field">
          Language model
          <select
            className="select"
            value={form.model ?? ""}
            onChange={(e) => set({ model: e.target.value || null })}
            disabled={models === null}
          >
            <option value="">
              Default{inUse.model && !form.model ? ` (${inUse.model})` : ""}
            </option>
            {(models ?? []).map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
            {form.model && models && !models.includes(form.model) && (
              <option value={form.model}>{form.model} (not found)</option>
            )}
          </select>
        </label>
        <p className="settings-help">
          Larger models follow the rules better. In Magonia&apos;s evaluation,
          qwen2.5:7b answered best of the five models tried.
        </p>
      </div>

      <div className="setting-row">
        <span className="field-title" id="detail-title">
          Answers
        </span>
        <div className="segmented" role="group" aria-labelledby="detail-title">
          {(
            [
              ["concise", "Concise"],
              ["detailed", "Detailed"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              aria-pressed={form.detail === value}
              onClick={() => set({ detail: value })}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="settings-help">
          {form.detail === "concise"
            ? "Short answers that get to the point."
            : "Longer answers that give the reasoning, the setting of each finding and its limits."}
        </p>
      </div>

      <div className="setting-row">
        <span className="field-title" id="creativity-title">
          Creativity (temperature)
        </span>
        <div
          className="segmented"
          role="group"
          aria-labelledby="creativity-title"
        >
          {CREATIVITY.map(([value, label]) => (
            <button
              key={label}
              aria-pressed={form.temperature === value}
              onClick={() => set({ temperature: value })}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="settings-help">
          {CREATIVITY.find(([value]) => value === form.temperature)?.[2] ??
            `Temperature ${form.temperature}.`}{" "}
          Citations and numbers are checked whatever the setting.
        </p>
      </div>

      <div className="setting-row">
        <label className="field">
          Papers read per search
          <select
            className="select"
            value={form.papers_per_search}
            onChange={(e) => set({ papers_per_search: Number(e.target.value) })}
          >
            {[4, 6, 8, 10].map((n) => (
              <option key={n} value={n}>
                {n} papers{n === 6 ? " (default)" : ""}
              </option>
            ))}
          </select>
        </label>
        <p className="settings-help">
          More papers give a broader view, but answers take longer and a small
          model may lose track.
        </p>
      </div>

      <div className="setting-row">
        <label className="field">
          Searching the literature
          <select
            className="select"
            value={form.search}
            onChange={(e) => set({ search: e.target.value as MagonSettings["search"] })}
          >
            <option value="keyword">By words (default)</option>
            <option value="hybrid">By words and by meaning</option>
          </select>
        </label>
        <p className="settings-help">
          Searching by meaning also finds papers that say the same thing in other words. It uses
          more of the daily search allowance.
        </p>
      </div>

      <div className="setting-row">
        <label className="field">
          Statements the papers do not support
          <select
            className="select"
            value={form.claims}
            onChange={(e) => set({ claims: e.target.value as MagonSettings["claims"] })}
          >
            <option value="withdraw">Withdraw them from the answer (default)</option>
            <option value="mark">Keep them, marked</option>
          </select>
        </label>
        <p className="settings-help">
          A withdrawn statement is listed under the answer with the passage it was checked against.
        </p>
      </div>

      <div className="setting-row">
        <label className="field">
          Checking sentences against papers
          <select
            className="select"
            value={form.verifier}
            onChange={(e) => set({ verifier: e.target.value as MagonSettings["verifier"] })}
          >
            <option value="model">The chat model (default)</option>
            <option value="nli">Inference model (DeBERTa NLI)</option>
            <option value="minicheck-roberta">MiniCheck RoBERTa</option>
            <option value="minicheck-deberta">MiniCheck DeBERTa</option>
          </select>
        </label>
        <p className="settings-help">
          A separate model trained only to tell whether a passage supports a sentence, instead of
          asking the model that wrote the answer. Runs on this computer; needs the verify extra.
        </p>
      </div>

      <details className="setting-row advanced">
        <summary>Model server</summary>
        <label className="field">
          Ollama address
          <span className="row">
            <input
              className="input"
              value={form.model_url ?? ""}
              placeholder={inUse.model_url ?? "http://localhost:11434"}
              onChange={(e) =>
                set({ model_url: e.target.value.trim() || null })
              }
            />
            <button
              className="button"
              onClick={() => {
                setModels(null);
                listModels(form.model_url ?? undefined);
              }}
            >
              Check
            </button>
          </span>
        </label>
        <p className="settings-help">
          {serverError ??
            (models === null
              ? "Looking for the models on the server…"
              : `${models.length} ${models.length === 1 ? "model" : "models"} found. Leave empty to use the address set when Magonia was installed.`)}
        </p>
      </details>

      {error && <p className="error">{error}</p>}
      <div className="settings-actions">
        {dirty ? (
          <>
            <button className="button" onClick={() => setForm(saved)}>
              Cancel
            </button>
            <button className="primary" onClick={save}>
              Save
            </button>
          </>
        ) : (
          <span className="state">Saved</span>
        )}
      </div>
    </section>
  );
}
