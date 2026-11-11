import "@fontsource/ibm-plex-sans-arabic/arabic-400.css";
import "@fontsource/ibm-plex-sans-arabic/arabic-500.css";
import "@fontsource/ibm-plex-sans-arabic/arabic-600.css";
import "@fontsource/ibm-plex-sans-arabic/arabic-700.css";
import "@fontsource/ibm-plex-sans-arabic/latin-400.css";
import "@fontsource/ibm-plex-sans-arabic/latin-500.css";
import "@fontsource/ibm-plex-sans-arabic/latin-600.css";
import "@fontsource/ibm-plex-sans-arabic/latin-700.css";
import "./index.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { RtlProvider } from "./components/ui/RtlProvider";

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <RtlProvider>
        <ErrorBoundary>
          <App />
        </ErrorBoundary>
      </RtlProvider>
    </StrictMode>,
  );
}
