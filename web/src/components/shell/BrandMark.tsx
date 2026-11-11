/**
 * Original academy mark (not the Dada logo): a doorway with a rising amber sun, i.e. "a first day".
 * Decorative only; the wordmark beside it carries the name.
 */
export function BrandMark({ size = 36, className }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" focusable="false" className={className}>
      <rect width="40" height="40" rx="11" fill="var(--da-accent)" />
      <circle cx="20" cy="22.5" r="4" fill="var(--da-amber)" />
      <path d="M11.5 30V20a8.5 8.5 0 0117 0v10" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" />
      <path d="M8.5 30h23" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
