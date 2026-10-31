import type { Variable } from "../api";

// What a variable measures, how to read it, what it is good for and when not to trust it
export default function LearnPanel({ variable }: { variable: Variable }) {
  const learn = variable.learn;
  if (!learn) return null;
  return (
    <div className="learn" aria-label={`About ${variable.name}`} role="note">
      <p>{learn.what}</p>
      <p className="formula">{learn.formula}</p>
      <p>
        <strong>Reading it.</strong> {learn.reading}
      </p>
      <div className="learn-lists">
        <div>
          <strong>Good for</strong>
          <ul>
            {learn.uses.map((use) => (
              <li key={use}>{use}</li>
            ))}
          </ul>
        </div>
        <div>
          <strong>Watch out</strong>
          <ul>
            {learn.limits.map((limit) => (
              <li key={limit}>{limit}</li>
            ))}
          </ul>
        </div>
      </div>
      <p className="meta">
        {variable.product} · {variable.resolution} · {variable.cadence}. {variable.quality}
      </p>
    </div>
  );
}
