/** K-row id from a number: `kId(3)` is "K03", `kId(19)` is "K19", `kId(100)` is "K100". */
export function kId(n: number): string {
  return `K${String(n).padStart(2, "0")}`;
}

/** Next free K id after the given ids (the "will be assigned" hint; the server decides). */
export function nextKId(ids: readonly string[]): string {
  const max = ids.reduce((m, id) => {
    const n = /^K(\d+)$/.exec(id);
    return n ? Math.max(m, Number(n[1])) : m;
  }, 0);
  return kId(max + 1);
}
