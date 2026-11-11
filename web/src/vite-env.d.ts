/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Build id (git short sha) injected by vite.config.ts; "dev" when not set. */
  readonly VITE_BUILD: string;
  /** Only for `vite dev` against another origin. Empty in the served build. */
  readonly VITE_API_BASE?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
