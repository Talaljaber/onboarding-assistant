import { Component, type ErrorInfo, type ReactNode } from "react";
import { useT } from "@/i18n";
import { Button } from "./ui/Button";

function Fallback({ error, stack }: { error: Error; stack: string }) {
  const t = useT();
  return (
    <div role="alert" className="mx-auto my-8 max-w-xl rounded-md border border-danger bg-surface-0 p-5">
      <h1 className="text-xl font-semibold text-fg-1">{t("error.title")}</h1>
      <p className="mt-2 text-fg-2">{t("error.text")}</p>
      <div className="mt-4">
        <Button onClick={() => window.location.reload()}>{t("error.reload")}</Button>
      </div>
      <details className="mt-4 text-sm text-fg-3" dir="ltr">
        <summary className="cursor-pointer">{error.name}</summary>
        <pre className="mt-2 overflow-x-auto whitespace-pre-wrap">{error.message + (stack ? `\n${stack}` : "")}</pre>
      </details>
    </div>
  );
}

interface Props {
  children: ReactNode;
  /** Replaces the full-page fallback (the chat wraps each card with its own small one). */
  fallback?: (error: Error) => ReactNode;
}
interface BoundaryState {
  error: Error | null;
  stack: string;
}

/** Catches render errors below it; logs to `console.error` only. */
export class ErrorBoundary extends Component<Props, BoundaryState> {
  override state: BoundaryState = { error: null, stack: "" };

  static getDerivedStateFromError(error: Error): Partial<BoundaryState> {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    this.setState({ stack: info.componentStack ?? "" });
    console.error(error, info.componentStack);
  }

  override render(): ReactNode {
    const { error, stack } = this.state;
    if (!error) return this.props.children;
    return this.props.fallback ? this.props.fallback(error) : <Fallback error={error} stack={stack} />;
  }
}
