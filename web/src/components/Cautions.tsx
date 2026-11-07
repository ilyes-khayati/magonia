import { InfoIcon } from "./Icons";
import { oneArea } from "../format";

// The guardrails' cautions on a card (AI-03): when a result should not be read at face value
export default function Cautions({ items }: { items?: string[] }) {
  if (!items?.length) return null;
  return (
    <ul className="cautions" aria-label="Cautions">
      {oneArea(items).map((text) => (
        <li key={text}>
          <InfoIcon size={14} />
          <span>{text}</span>
        </li>
      ))}
    </ul>
  );
}
