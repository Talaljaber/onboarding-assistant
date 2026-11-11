// P16.5 (U12): bring a block that just opened («علّقت؟», «كيف أجبت؟») into the visible band of the chat: below
// the sticky header, above the sticky dock (practice bar + composer) and the phone bottom bar. Only scrolls
// when the block's end is hidden, never pushes its start under the header, and jumps instead of gliding
// when the person prefers reduced motion.

const GAP = 12;

export function revealIntoView(el: Element | null | undefined): void {
  if (!el || typeof window.scrollBy !== "function") return;
  const reduced = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const main = document.getElementById("main");
  const navH = main ? parseFloat(getComputedStyle(main).paddingBottom) || 0 : 0;
  const dock = document.querySelector<HTMLElement>("[data-chat-dock]");
  const top = (document.querySelector("header")?.getBoundingClientRect().bottom ?? 0) + GAP;
  const bottom = window.innerHeight - navH - (dock?.offsetHeight ?? 0) - GAP;
  const r = el.getBoundingClientRect();
  if (r.bottom <= bottom) return;
  const delta = Math.min(r.bottom - bottom, r.top - top);
  if (delta > 0) window.scrollBy({ top: delta, behavior: reduced ? "auto" : "smooth" });
}

/** After the next paint (the opened block exists and has its size). */
export function revealSoon(get: () => Element | null | undefined): void {
  const run = () => revealIntoView(get());
  if (typeof window.requestAnimationFrame === "function") window.requestAnimationFrame(run);
  else run();
}
