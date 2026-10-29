// The data choices, beside the charts they shape
export default function Sidebar({ children }: { children?: React.ReactNode }) {
  return (
    <aside className="sidebar" aria-label="Data">
      {children}
    </aside>
  );
}
