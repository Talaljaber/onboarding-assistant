/** Build id (git short sha, or "dev") injected at build time by vite.config.ts. */
export const BUILD_ID: string = import.meta.env.VITE_BUILD;
