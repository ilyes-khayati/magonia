import { useState } from "react";
import { SearchIcon } from "./Icons";

type Place = { label: string; center: [number, number] };

// "36.508, 8.561" (latitude, longitude) moves straight there; anything else is
// looked up on OpenStreetMap's Nominatim service.
function parseCoordinates(text: string): [number, number] | null {
  const match = text.trim().match(/^(-?\d+(?:\.\d+)?)\s*[,\s]\s*(-?\d+(?:\.\d+)?)$/);
  if (!match) return null;
  const [lat, lon] = [Number(match[1]), Number(match[2])];
  return Math.abs(lat) <= 90 && Math.abs(lon) <= 180 ? [lon, lat] : null;
}

export default function PlaceSearch({ onGo }: { onGo: (center: [number, number]) => void }) {
  const [text, setText] = useState("");
  const [places, setPlaces] = useState<Place[]>([]);
  const [note, setNote] = useState("");

  async function search(event: React.FormEvent) {
    event.preventDefault();
    const coordinates = parseCoordinates(text);
    if (coordinates) {
      onGo(coordinates);
      return;
    }
    if (!text.trim()) return;
    try {
      const url = `https://nominatim.openstreetmap.org/search?format=json&limit=5&q=${encodeURIComponent(text)}`;
      const found: { display_name: string; lat: string; lon: string }[] = await (await fetch(url)).json();
      setPlaces(found.map((p) => ({ label: p.display_name, center: [Number(p.lon), Number(p.lat)] })));
      setNote(found.length ? "" : "No place found.");
    } catch {
      setNote("Place search is unavailable. Coordinates still work.");
    }
  }

  function go(place: Place) {
    onGo(place.center);
    setPlaces([]);
    setText(place.label.split(",")[0]);
  }

  return (
    <form className="search" role="search" onSubmit={search}>
      <label>
        <SearchIcon size={15} />
        <span className="visually-hidden">Search a place, or type latitude, longitude</span>
        <input
          type="text"
          value={text}
          placeholder="Place or lat, lon"
          onChange={(e) => {
            setText(e.target.value);
            setNote("");
          }}
        />
      </label>
      {(places.length > 0 || note) && (
        <ul className="floating">
          {note && <li style={{ padding: 8, color: "var(--muted)" }}>{note}</li>}
          {places.map((place) => (
            <li key={place.label}>
              <button type="button" onClick={() => go(place)}>
                {place.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </form>
  );
}
