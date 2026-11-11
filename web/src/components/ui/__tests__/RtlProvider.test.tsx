import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { useT } from "@/i18n";
import { LanguageSwitch } from "../LanguageSwitch";
import { RtlProvider } from "../RtlProvider";

function Probe() {
  const t = useT();
  return <p>{t("common.dismiss")}</p>;
}

describe("RtlProvider + LanguageSwitch", () => {
  it("defaults to Arabic RTL, reads the stored language, and survives a throwing store", () => {
    const { unmount } = render(<RtlProvider><Probe /></RtlProvider>);
    expect(document.documentElement.lang).toBe("ar");
    expect(document.documentElement.dir).toBe("rtl");
    unmount();
    window.localStorage.setItem("dada.v1.lang", "en");
    const second = render(<RtlProvider><Probe /></RtlProvider>);
    expect(document.documentElement.dir).toBe("ltr");
    second.unmount();
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    render(<RtlProvider><Probe /></RtlProvider>);
    expect(document.documentElement.lang).toBe("ar");
    vi.restoreAllMocks();
  });

  it("a throwing setItem does not break switching language", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    render(<RtlProvider lang="ar"><LanguageSwitch /></RtlProvider>);
    await userEvent.click(screen.getByRole("button", { name: /English/ }));
    expect(document.documentElement.lang).toBe("en");
    vi.restoreAllMocks();
  });

  it("sets html lang/dir and translates after switching to Arabic", async () => {
    render(
      <RtlProvider lang="en">
        <LanguageSwitch />
        <Probe />
      </RtlProvider>,
    );
    expect(screen.getByText("Dismiss")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /العربية/ }));
    expect(document.documentElement.lang).toBe("ar");
    expect(document.documentElement.dir).toBe("rtl");
    expect(screen.getByText("إغلاق")).toBeInTheDocument();
    expect(window.localStorage.getItem("dada.v1.lang")).toBe("ar");
    expect(screen.getByRole("button", { name: /العربية/ })).toHaveAttribute("aria-pressed", "true");
  });
});
