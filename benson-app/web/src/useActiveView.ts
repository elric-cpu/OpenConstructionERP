import { useCallback, useEffect, useState } from "react";
import type { ActiveView } from "./types";

function viewFromHash(): ActiveView | null {
  const route = window.location.hash.slice(1).split("?", 1)[0];
  return ["overview", "leads", "customers", "estimates", "jobs", "employees", "tasks", "activate"].includes(route)
    ? (route as ActiveView)
    : null;
}

export function useActiveView(onNavigate: () => void) {
  const [activeView, setActiveView] = useState<ActiveView>(() => viewFromHash() ?? "overview");

  useEffect(() => {
    const syncView = () => {
      const nextView = viewFromHash();
      if (!nextView) {
        window.history.replaceState(null, "", "#overview");
      }
      setActiveView(nextView ?? "overview");
      onNavigate();
    };
    syncView();
    window.addEventListener("hashchange", syncView);
    return () => window.removeEventListener("hashchange", syncView);
  }, [onNavigate]);

  const navigate = useCallback(
    (view: Exclude<ActiveView, "activate">) => {
      setActiveView(view);
      window.history.replaceState(null, "", `#${view}`);
      onNavigate();
    },
    [onNavigate],
  );
  const openLeads = useCallback(() => navigate("leads"), [navigate]);
  return { activeView, navigate, openLeads };
}
