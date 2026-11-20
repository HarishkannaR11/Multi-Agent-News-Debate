import { sparkPath, type SeriesInfo } from "@/lib/markets";

// A small trend line for one series. Decorative: the figures beside it say the same thing in words.
export function Sparkline({ points, width = 120, height = 28 }: { points: SeriesInfo["points"]; width?: number; height?: number }) {
  const path = sparkPath(points, width, height);
  if (!path) return <span className="font-sans text-xs text-muted">no trend</span>;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true" className="text-ink">
      <path d={path} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
