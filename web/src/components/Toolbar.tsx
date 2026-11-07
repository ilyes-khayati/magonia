import { useRef, useState } from "react";
import type { Area } from "../api";
import AreaChip from "./AreaChip";
import { CoordinatesIcon, InspectIcon, LayersIcon, PlusIcon, PolygonIcon, RectangleIcon, RulerIcon, UploadIcon } from "./Icons";
import { parseCoordinates } from "../geo";
import type { Tool } from "./MapView";
import PlaceSearch from "./PlaceSearch";

type Props = {
  tool: Tool;
  onTool: (tool: Tool) => void;
  onUpload: (file: File) => void;
  onGo: (center: [number, number]) => void;
  areas: Area[];
  colours: Map<number, string>;
  hidden: Set<number>;
  onZoom: (area: Area) => void;
  onToggle: (area: Area) => void;
  onRename: (area: Area, name: string) => void;
  onDelete: (area: Area) => void;
  layers: boolean;
  onLayers: () => void;
  onShape: (geometry: GeoJSON.Polygon) => void;
};

// A tool button: an icon, its name and its key in the tooltip
function ToolButton({ label, keyName, pressed, onClick, children }: { label: string; keyName?: string; pressed?: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button className="tool" aria-label={label} title={keyName ? `${label} (${keyName})` : label} aria-pressed={pressed} onClick={onClick}>
      {children}
    </button>
  );
}

export default function Toolbar(props: Props) {
  const { tool, onTool, areas, colours, hidden } = props;
  const upload = useRef<HTMLInputElement>(null);
  const pick = (next: Tool) => onTool(tool === next ? null : next);
  const [typed, setTyped] = useState(false);
  const [text, setText] = useState("");
  const read = parseCoordinates(text);

  return (
    <div className="toolbar-wrap">
      <div className="floating toolbar" role="toolbar" aria-label="Areas">
        <ToolButton label="Draw a polygon" keyName="D" pressed={tool === "polygon"} onClick={() => pick("polygon")}>
          <PolygonIcon />
        </ToolButton>
        <ToolButton label="Draw a rectangle" keyName="R" pressed={tool === "rectangle"} onClick={() => pick("rectangle")}>
          <RectangleIcon />
        </ToolButton>
        <ToolButton label="Measure a distance" keyName="M" pressed={tool === "measure"} onClick={() => pick("measure")}>
          <RulerIcon />
        </ToolButton>
        <ToolButton label="Inspect a pixel" keyName="I" pressed={tool === "inspect"} onClick={() => pick("inspect")}>
          <InspectIcon />
        </ToolButton>
        <span className="divider" />
        <ToolButton label="Layers" keyName="L" pressed={props.layers} onClick={props.onLayers}>
          <LayersIcon />
        </ToolButton>
        <ToolButton label="Enter coordinates" keyName="C" pressed={typed} onClick={() => setTyped(!typed)}>
          <CoordinatesIcon />
        </ToolButton>
        <ToolButton label="Upload GeoJSON, KML or zipped shapefile" onClick={() => upload.current?.click()}>
          <UploadIcon />
        </ToolButton>
        <input
          ref={upload}
          type="file"
          accept=".geojson,.json,.kml,.zip"
          hidden
          data-testid="upload"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) props.onUpload(file);
            e.target.value = "";
          }}
        />
        <PlaceSearch onGo={props.onGo} />
        <span className="divider" />
        {areas.map((area) => (
          <AreaChip
            key={area.id}
            area={area}
            colour={colours.get(area.id)!}
            hidden={hidden.has(area.id)}
            onZoom={() => props.onZoom(area)}
            onToggle={() => props.onToggle(area)}
            onRename={(name) => props.onRename(area, name)}
            onDelete={() => props.onDelete(area)}
          />
        ))}
        <ToolButton label="Add an area" keyName="D" onClick={() => onTool("polygon")}>
          <PlusIcon size={16} />
        </ToolButton>
      </div>
      {typed && (
        <form
          className="floating panel coordinates"
          aria-label="Enter coordinates"
          onSubmit={(e) => {
            e.preventDefault();
            if (!read) return;
            if ("point" in read) props.onGo(read.point);
            else props.onShape(read.polygon);
            setText("");
            setTyped(false);
          }}
        >
          <label className="field">
            <span>Coordinates</span>
            <textarea
              className="mono"
              rows={3}
              autoFocus
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={"36.5080, 8.5610  (a point: lat, lon)\n8.55, 36.50, 8.57, 36.52  (a box: W, S, E, N)\nor lon lat pairs, one corner per line"}
            />
          </label>
          <div className="row spread">
            <span className="meta">{!text ? "" : !read ? "Not coordinates yet" : "point" in read ? "Go to this point" : `Area with ${read.polygon.coordinates[0].length - 1} corners`}</span>
            <button className="button" type="submit" disabled={!read}>
              {read && "polygon" in read ? "Add area" : "Go"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
