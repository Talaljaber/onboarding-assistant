import logoUrl from "@/assets/dada-logo.png";

/** Where the leaf sits in the official logo image (1000 x 396 px, transparent background). */
const LOGO_W = 1000;
const LOGO_H = 396;
const LEAF = { w: 113, h: 115 };

/**
 * Dada Group's yellow leaf (cropped from the official logo) on a Dada-blue tile: the small mark for the
 * header on phones and the assistant's avatar in the thread. Decorative only; the wordmark carries the name.
 */
export function BrandMark({ size = 36, className }: { size?: number; className?: string }) {
  const leaf = 23; // leaf height inside the 40-unit tile
  const w = (LEAF.w * leaf) / LEAF.h;
  // The inner <svg> is a viewport onto the leaf's corner of the logo: it crops without a clipPath, so
  // the many avatars of a thread share no element id (a fixed id was repeated once per avatar).
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" focusable="false" className={className}>
      <rect width="40" height="40" rx="11" fill="var(--da-accent)" />
      <svg x={(40 - w) / 2} y={(40 - leaf) / 2} width={w} height={leaf} viewBox={`0 0 ${LEAF.w} ${LEAF.h}`} overflow="hidden">
        <image href={logoUrl} width={LOGO_W} height={LOGO_H} />
      </svg>
    </svg>
  );
}

/** The full Dada Group logo («مجموعة الدادا»), as published on dadagroup.jo. `alt` empty when a wordmark sits beside it. */
export function DadaLogo({ height = 32, alt = "", className }: { height?: number; alt?: string; className?: string }) {
  return (
    <img
      src={logoUrl}
      alt={alt}
      height={height}
      width={Math.round((height * LOGO_W) / LOGO_H)}
      className={className}
      style={{ height, width: "auto" }}
      draggable={false}
    />
  );
}
