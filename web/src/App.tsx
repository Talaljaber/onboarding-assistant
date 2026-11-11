// Route table and providers. Screen agents never edit this file: each route renders the default
// export of components/<screen>/<Screen>Screen.tsx. The frame (header, nav, footer) lives in
// components/shell/AppShell.tsx.
import { useEffect, type ComponentType } from "react";
import AboutScreen from "@/components/about/AboutScreen";
import ChatScreen from "@/components/chat/ChatScreen";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import KbScreen from "@/components/kb/KbScreen";
import PlanScreen from "@/components/plan/PlanScreen";
import ProgressScreen from "@/components/progress/ProgressScreen";
import QuizScreen from "@/components/quiz/QuizScreen";
import ScenariosScreen from "@/components/scenarios/ScenariosScreen";
import { AppShell } from "@/components/shell/AppShell";
import { ToastProvider } from "@/components/ui/Toast";
import WelcomeScreen from "@/components/welcome/WelcomeScreen";
import { replace, usePath } from "@/router";
import { AppStateProvider, useAppState } from "@/state/useAppState";

interface RouteDef {
  path: string;
  Screen: ComponentType;
  /** Redirects to "#/" while no role is stored (plan D1.1: every route except "#/" and "#/about"). */
  needsRole: boolean;
}

export const ROUTES: readonly RouteDef[] = [
  { path: "/", Screen: WelcomeScreen, needsRole: false },
  { path: "/chat", Screen: ChatScreen, needsRole: true },
  { path: "/scenarios", Screen: ScenariosScreen, needsRole: true },
  { path: "/plan", Screen: PlanScreen, needsRole: true },
  { path: "/quiz", Screen: QuizScreen, needsRole: true },
  { path: "/progress", Screen: ProgressScreen, needsRole: true },
  { path: "/kb", Screen: KbScreen, needsRole: true },
  { path: "/about", Screen: AboutScreen, needsRole: false },
];

/** Resolves the hash path to a screen, redirecting where the guard says so. */
function Routes() {
  const path = usePath();
  const { role } = useAppState();
  const route = ROUTES.find((r) => r.path === path);
  // "#/" with a stored role goes to the assistant; unknown paths and role-less guarded paths go to "#/".
  const target = !route ? "/" : route.path === "/" && role ? "/chat" : route.needsRole && !role ? "/" : null;
  const redirect = target !== null && target !== path ? target : null;
  useEffect(() => {
    if (redirect) replace(redirect);
  }, [redirect]);
  if (!route || redirect) return null;
  const { Screen } = route;
  return <Screen key={route.path} />;
}

export default function App() {
  return (
    <ToastProvider>
      <AppStateProvider>
        <AppShell>
          <ErrorBoundary>
            <Routes />
          </ErrorBoundary>
        </AppShell>
      </AppStateProvider>
    </ToastProvider>
  );
}
