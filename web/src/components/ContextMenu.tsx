import { useEffect, useRef } from "react";

export type MenuItem = { label: string; run: () => void; hint?: string } | "divider";

// A right-click menu, placed at the pointer and kept inside the window
export default function ContextMenu({ x, y, items, onClose }: { x: number; y: number; items: MenuItem[]; onClose: () => void }) {
  const menu = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const away = (e: Event) => {
      if (!menu.current?.contains(e.target as Node)) onClose();
    };
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("pointerdown", away);
    window.addEventListener("keydown", key);
    window.addEventListener("blur", onClose);
    menu.current?.querySelector("button")?.focus();
    return () => {
      window.removeEventListener("pointerdown", away);
      window.removeEventListener("keydown", key);
      window.removeEventListener("blur", onClose);
    };
  }, [onClose]);

  const left = Math.min(x, window.innerWidth - 240);
  const top = Math.min(y, window.innerHeight - items.length * 28 - 12);

  return (
    <div ref={menu} className="context-menu" role="menu" style={{ left, top }}>
      {items.map((item, i) =>
        item === "divider" ? (
          <hr key={i} />
        ) : (
          <button
            key={item.label}
            role="menuitem"
            onClick={() => {
              item.run();
              onClose();
            }}
          >
            <span>{item.label}</span>
            {item.hint && <kbd>{item.hint}</kbd>}
          </button>
        ),
      )}
    </div>
  );
}
