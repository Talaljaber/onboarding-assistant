// Route table and providers. Screen agents never edit this file: each route renders the default
// export of components/<screen>/<Screen>Screen.tsx. The frame (header, nav, footer) lives in
// components/shell/AppShell.tsx.
import { useEffect, useRef, type ComponentType } from "react";
import AboutScreen from "@/components/about/AboutScreen";
import AdminScreen from "@/components/admin/AdminScreen";
import { AdminShell } from "@/components/admin/AdminShell";
import InternDetailScreen from "@/components/admin/InternDetailScreen";
import InternsScreen from "@/components/admin/InternsScreen";
import { getAdminSession } from "@/api/client";
import { getAdminToken, useIsAdmin } from "@/api/adminToken";
import ChatScreen from "@/components/chat/ChatScreen";
import CheckScreen from "@/components/check/CheckScreen";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import KbScreen from "@/components/kb/KbScreen";
import ImportReviewScreen from "@/components/kb/import/ImportReviewScreen";
import ImportScreen from "@/components/kb/import/ImportScreen";
import PlanScreen from "@/components/plan/PlanScreen";
import ProgressScreen from "@/components/progress/ProgressScreen";
import QuizScreen from "@/components/quiz/QuizScreen";
import ScenariosScreen from "@/components/scenarios/ScenariosScreen";
import { AppShell } from "@/components/shell/AppShell";
import { ToastProvider, useToast } from "@/components/ui/Toast";
import WelcomeScreen from "@/components/welcome/WelcomeScreen";
import QuestionsScreen from "@/components/questions/QuestionsScreen"; // P18.1
import QuizSetEditor from "@/components/quizsets/QuizSetEditor"; // P20.2
import QuizSetsScreen from "@/components/quizsets/QuizSetsScreen"; // P20.2
import FinalReportScreen from "@/components/report/FinalReportScreen"; // P21.2
import InternReportScreen from "@/components/report/InternReportScreen"; // P21.2
import { replace, usePath } from "@/router";
import { AppStateProvider, useAppState } from "@/state/useAppState";

interface RouteDef {
  path: string;
  Screen: ComponentType;
  /** Intern only: redirects to the sign-in screen "#/" while no intern is signed in. */
  needsRole: boolean;
  /** Admin only (P10): redirects to the admin sign-in screen "#/admin" without an admin token. */
  needsAdmin?: boolean;
  /** Matches paths with a parameter (the intern detail page). */
  match?: RegExp;
}

export const ROUTES: readonly RouteDef[] = [
  { path: "/", Screen: WelcomeScreen, needsRole: false },
  { path: "/chat", Screen: ChatScreen, needsRole: true },
  { path: "/scenarios", Screen: ScenariosScreen, needsRole: true },
  { path: "/plan", Screen: PlanScreen, needsRole: true },
  { path: "/quiz", Screen: QuizScreen, needsRole: true },
  { path: "/progress", Screen: ProgressScreen, needsRole: true },
  { path: "/check", Screen: CheckScreen, needsRole: true }, // P14.2 Rumour Check
  { path: "/kb", Screen: KbScreen, needsRole: false, needsAdmin: true },
  { path: "/admin/interns", Screen: InternsScreen, needsRole: false, needsAdmin: true },
  {
    path: "/admin/interns/:id",
    Screen: InternDetailScreen,
    needsRole: false,
    needsAdmin: true,
    match: /^\/admin\/interns\/[0-9a-f-]{36}$/,
  },
  // P21.2 the final report: the comparison of all interns and one intern's printable page
  { path: "/admin/report", Screen: FinalReportScreen, needsRole: false, needsAdmin: true },
  {
    path: "/admin/interns/:id/report",
    Screen: InternReportScreen,
    needsRole: false,
    needsAdmin: true,
    match: /^\/admin\/interns\/[0-9a-f-]{36}\/report$/,
  },
  { path: "/admin/kb/import", Screen: ImportScreen, needsRole: false, needsAdmin: true },
  {
    path: "/admin/kb/import/:id",
    Screen: ImportReviewScreen,
    needsRole: false,
    needsAdmin: true,
    match: /^\/admin\/kb\/import\/[0-9a-f-]{36}$/,
  },
  { path: "/admin/questions", Screen: QuestionsScreen, needsRole: false, needsAdmin: true }, // P18.1
  { path: "/admin/quizzes", Screen: QuizSetsScreen, needsRole: false, needsAdmin: true }, // P20.2
  {
    path: "/admin/quizzes/:id",
    Screen: QuizSetEditor,
    needsRole: false,
    needsAdmin: true,
    match: /^\/admin\/quizzes\/[0-9a-f-]{36}$/,
  },
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
  const route = ROUTES.find((r) => (r.match ? r.match.test(path) : r.path === path));
  // "#/" with a signed-in intern goes to the assistant; unknown paths and intern screens without an intern
  // go to "#/" (sign-in); admin screens go to the admin sign-in without an admin token, and the signed-in
  // admin skips it.
  const target = !route
    ? "/"
    : route.path === "/" && role
      ? "/chat"
      : route.needsRole && !role
        ? "/"
        : route.needsAdmin && !admin
          ? "/admin"
          : route.path === "/admin" && admin
            ? "/admin/interns"
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
  return <Screen key={route.match ? path : route.path} />;
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

/** The admin area (signed in) gets the admin shell; everything else the intern shell. */
function Frame() {
  const path = usePath();
  const admin = useIsAdmin();
  const adminArea = admin && (path === "/kb" || path.startsWith("/admin/"));
  const Shell = adminArea ? AdminShell : AppShell;
  return (
    <Shell>
      <ErrorBoundary>
        <Routes />
      </ErrorBoundary>
    </Shell>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <AppStateProvider>
        <AdminCheck />
        <Frame />
      </AppStateProvider>
    </ToastProvider>
  );
}
