// Route table and providers. Screen agents never edit this file: each route renders the default
// export of components/<screen>/<Screen>Screen.tsx. The frame (header, nav, footer) lives in
// components/shell/AppShell.tsx.
import { useEffect, useRef, type ComponentType } from "react";
import AboutScreen from "@/components/about/AboutScreen";
import AdminScreen from "@/components/admin/AdminScreen";
import { getAdminSession } from "@/api/client";
import { getAdminToken, useIsAdmin } from "@/api/adminToken";
import ChatScreen from "@/components/chat/ChatScreen";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import KbScreen from "@/components/kb/KbScreen";
import PlanScreen from "@/components/plan/PlanScreen";
import ProgressScreen from "@/components/progress/ProgressScreen";
import QuizScreen from "@/components/quiz/QuizScreen";
import ScenariosScreen from "@/components/scenarios/ScenariosScreen";
import { AppShell } from "@/components/shell/AppShell";
import { ToastProvider, useToast } from "@/components/ui/Toast";
import WelcomeScreen from "@/components/welcome/WelcomeScreen";
import { replace, usePath } from "@/router";
import { AppStateProvider, useAppState } from "@/state/useAppState";

interface RouteDef {
  path: string;
  Screen: ComponentType;
  /** Redirects to "#/" while no role is stored (plan D1.1: every route except "#/" and "#/about"). */
  needsRole: boolean;
  /** Admin only (P10): redirects to the sign-in screen "#/admin" without an admin token. */
  needsAdmin?: boolean;
}

export const ROUTES: readonly RouteDef[] = [
  { path: "/", Screen: WelcomeScreen, needsRole: false },
  { path: "/chat", Screen: ChatScreen, needsRole: true },
  { path: "/scenarios", Screen: ScenariosScreen, needsRole: true },
  { path: "/plan", Screen: PlanScreen, needsRole: true },
  { path: "/quiz", Screen: QuizScreen, needsRole: true },
  { path: "/progress", Screen: ProgressScreen, needsRole: true },
  { path: "/kb", Screen: KbScreen, needsRole: false, needsAdmin: true },
  { path: "/admin", Screen: AdminScreen, needsRole: false },
  { path: "/about", Screen: AboutScreen, needsRole: false },
];

/**
 * After a route change, move focus to the new screen's heading (else `main`) so keyboard and
 * screen-reader users start on the new page instead of <body>. Programmatic focus shows no ring
 * (index.css). A screen that already placed focus inside `main` (the chat composer opened from a
 * starter or a hand-off) keeps it.
 */
function focusScreen() {
  const main = document.getElementById("main");
  if (!main) return;
  const active = document.activeElement;
  if (active && active !== document.body && active !== main && main.contains(active)) return;
  const h1 = main.querySelector<HTMLElement>("h1");
  if (h1 && !h1.hasAttribute("tabindex")) h1.tabIndex = -1;
  (h1 ?? main).focus({ preventScroll: true });
}

/** Resolves the hash path to a screen, redirecting where the guard says so. */
function Routes() {
  const path = usePath();
  const { role } = useAppState();
  const admin = useIsAdmin();
  const route = ROUTES.find((r) => r.path === path);
  // "#/" with a stored role goes to the assistant; unknown paths and role-less guarded paths go to "#/";
  // admin screens go to the sign-in screen without an admin token, and the signed-in admin skips it.
  const target = !route
    ? "/"
    : route.path === "/" && role
      ? "/chat"
      : route.needsRole && !role
        ? "/"
        : route.needsAdmin && !admin
          ? "/admin"
          : route.path === "/admin" && admin
            ? "/kb"
            : null;
  const redirect = target !== null && target !== path ? target : null;
  useEffect(() => {
    if (redirect) replace(redirect);
  }, [redirect]);
  // A new screen starts at its top (instant, so reduced motion is respected) with no stale toast.
  // The chat screen is left alone: it scrolls itself to the latest message.
  const { dismissTransient } = useToast();
  const prevPath = useRef(path);
  useEffect(() => {
    if (prevPath.current === path) return;
    prevPath.current = path;
    dismissTransient();
    if (path !== "/chat" && typeof window.scrollTo === "function" && window.scrollY > 0) {
      window.scrollTo({ top: 0, left: 0, behavior: "instant" });
    }
    focusScreen();
  }, [path, dismissTransient]);
  if (!route || redirect) return null;
  const { Screen } = route;
  return <Screen key={route.path} />;
}

/** On load, check a stored admin token with the server (a restart or expiry forgets it). */
function AdminCheck() {
  useEffect(() => {
    if (!getAdminToken()) return;
    const ctl = new AbortController();
    void getAdminSession(ctl.signal);
    return () => ctl.abort();
  }, []);
  return null;
}

export default function App() {
  return (
    <ToastProvider>
      <AppStateProvider>
        <AdminCheck />
        <AppShell>
          <ErrorBoundary>
            <Routes />
          </ErrorBoundary>
        </AppShell>
      </AppStateProvider>
    </ToastProvider>
  );
}
