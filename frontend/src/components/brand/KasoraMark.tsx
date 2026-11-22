import { cn } from "@/lib/utils";

/**
 * The KASORA AI mark: a central hub linked to five nodes (a square, a triangle, two circles and a square).
 * Drawn in `currentColor`, so it follows the surrounding text colour in light and dark themes.
 * Pass `animated` for the intro animation (it is skipped when the visitor prefers reduced motion).
 */
export function KasoraMark({ className, animated = false, title }: { className?: string; animated?: boolean; title?: string }) {
  return (
    <svg
      viewBox="0 0 200 200"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("kasora-mark", animated && "kasora-animated", className)}
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
    >
      <g fill="none" stroke="currentColor" strokeWidth="10" strokeLinecap="round" strokeLinejoin="round">
        <path className="kasora-line l1" d="M 85 85 L 55 55" />
        <path className="kasora-line l2" d="M 115 85 L 135 55" />
        <path className="kasora-line l3" d="M 115 100 L 145 100" />
        <path className="kasora-line l4" d="M 100 115 L 100 145" />
        <path className="kasora-line l5" d="M 85 115 L 55 145" />
      </g>
      <circle className="kasora-hub" cx="100" cy="100" r="28" fill="currentColor" />
      <rect className="kasora-node n1" x="30" y="30" width="35" height="35" rx="8" fill="currentColor" />
      <path className="kasora-node n2" d="M 140 35 L 165 70 L 115 70 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <circle className="kasora-node n3" cx="155" cy="100" r="18" fill="currentColor" />
      <circle className="kasora-node n4" cx="100" cy="155" r="18" fill="currentColor" />
      <rect className="kasora-node n5" x="30" y="130" width="35" height="35" rx="8" fill="currentColor" />
    </svg>
  );
}
