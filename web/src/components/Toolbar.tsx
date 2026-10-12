import { useRef } from "react";
import type { Area } from "../api";
import AreaChip from "./AreaChip";
import { PlusIcon, PolygonIcon, RectangleIcon, UploadIcon } from "./Icons";
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
  onToggle: (area: Area) => void;
  onRename: (area: Area, name: string) => void;
  onDelete: (area: Area) => void;
};

export default function Toolbar(props: Props) {
  const { tool, onTool, areas, colours, hidden } = props;
  const upload = useRef<HTMLInputElement>(null);
  const pick = (next: Tool) => onTool(tool === next ? null : next);

  return (
    <div className="toolbar-wrap">
      <div className="floating toolbar" role="toolbar" aria-label="Areas">
        <button
          className="tool"
          aria-label="Draw a polygon"
          title="Draw a polygon: click to add points, click the first point to finish"
          aria-pressed={tool === "polygon"}
          onClick={() => pick("polygon")}
        >
          <PolygonIcon />
        </button>
        <button
          className="tool"
          aria-label="Draw a rectangle"
          title="Draw a rectangle: click two opposite corners"
          aria-pressed={tool === "rectangle"}
          onClick={() => pick("rectangle")}
        >
          <RectangleIcon />
        </button>
        <button
          className="tool"
          aria-label="Upload GeoJSON, KML or zipped shapefile"
          title="Upload GeoJSON, KML or zipped shapefile"
          onClick={() => upload.current?.click()}
        >
          <UploadIcon />
        </button>
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
            onToggle={() => props.onToggle(area)}
            onRename={(name) => props.onRename(area, name)}
            onDelete={() => props.onDelete(area)}
          />
        ))}
        <button
          className="tool"
          aria-label="Add an area"
          title="Add an area"
          style={{ borderRadius: 18, border: "1px dashed var(--muted)" }}
          onClick={() => onTool("polygon")}
        >
          <PlusIcon size={16} />
        </button>
      </div>
    </div>
  );
}
