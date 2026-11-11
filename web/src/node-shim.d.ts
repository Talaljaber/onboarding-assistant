// Minimal typing for the one Node API the tests use (no @types/node in the pinned toolchain).
declare module "node:fs" {
  export function readFileSync(path: string | URL, encoding: "utf8"): string;
}
