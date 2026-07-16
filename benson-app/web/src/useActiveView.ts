import { useEffect, useState } from "react";
import type { ActiveView } from "./types";

export function useActiveView(onNavigate: () => void) {
  const [activeView, setActiveView] = useState<ActiveView>(() =>
    window.location.hash === "#leads" ? "leads" : "overview",
  );

  useEffect(() => {
    const syncView = () => {
      const requestedView = window.location.hash;
      const nextView = requestedView === "#leads" ? "leads" : "overview";
      if (requestedView !== "#overview" && requestedView !== "#leads") {
        window.history.replaceState(null, "", "#overview");
      }
      setActiveView(nextView);
      onNavigate();
    };
    syncView();
    window.addEventListener("hashchange", syncView);
    return () => window.removeEventListener("hashchange", syncView);
  }, [onNavigate]);

  const openLeads = () => {
    setActiveView("leads");
    window.history.replaceState(null, "", "#leads");
  };
  return { activeView, openLeads };
}
