import type { ReactNode } from "react";
import {
  BriefcaseBusiness,
  CalendarDays,
  ClipboardCheck,
  Home,
  Inbox,
  LogOut,
  ListChecks,
  Menu,
  Search,
  UserPlus,
  Users,
  X,
} from "lucide-react";
import type { ActiveView, PortalSession, RequestStatus } from "./types";

const nav = [
  [Home, "Overview", "overview"],
  [Inbox, "Leads", "leads"],
  [BriefcaseBusiness, "Jobs", "jobs"],
  [CalendarDays, "Schedule", "schedule"],
  [ClipboardCheck, "Estimates", "estimates"],
  [Users, "Customers", "customers"],
] as const;

export function AppShell({
  activeView,
  children,
  credential,
  menu,
  query,
  requestStatus,
  portalSession,
  setMenu,
  setQuery,
  signOut,
}: {
  activeView: ActiveView;
  children: ReactNode;
  credential: string;
  menu: boolean;
  query: string;
  requestStatus: RequestStatus;
  portalSession: PortalSession | null;
  setMenu(value: boolean): void;
  setQuery(value: string): void;
  signOut(): void;
}) {
  const connectionLabel = {
    loading: "Connecting",
    ready: "System ready",
    "auth-required": "Sign in required",
    offline: "Connection issue",
  }[requestStatus];
  const employeePortal = portalSession?.kind === "employee";
  const role = portalSession?.role;
  const roleNav = role === "field" ? [nav[2], nav[3]] : role === "accounting" ? [nav[2]] : nav;
  const staffNav =
    role && ["owner", "admin"].includes(role)
      ? [...roleNav.slice(0, 2), [UserPlus, "New hires", "employees"] as const, ...roleNav.slice(2)]
      : roleNav;
  const visibleNav = employeePortal ? ([[ListChecks, "Tasks", "tasks"]] as const) : staffNav;
  const showSearch = ["overview", "leads", "customers"].includes(activeView);
  return (
    <div className="shell">
      <aside className={menu ? "open" : ""}>
        <div className="brand">
          <img src="/benson-enterprises-logo.svg" alt="Benson Home Solutions" />
          <div>
            <b>Benson</b>
            <small>Operations</small>
          </div>
          <button aria-label="Close menu" onClick={() => setMenu(false)}>
            <X />
          </button>
        </div>
        <nav>
          {visibleNav.map(([Icon, label, route]) => (
            <a
              aria-current={activeView === route ? "page" : undefined}
              className={activeView === route ? "active" : ""}
              href={`#${route}`}
              key={label}
              onClick={() => setMenu(false)}
            >
              <Icon /> {label}
            </a>
          ))}
        </nav>
        <div className="rail-foot">
          <img className="avatar" src="/benson-enterprises-logo.svg" alt="" />
          <div>
            <b>{portalSession?.employee?.name || "Benson staff"}</b>
            <small>{portalSession?.email || "Burns, Oregon"}</small>
          </div>
        </div>
      </aside>
      <main>
        <header>
          <button className="menu" aria-label="Open menu" onClick={() => setMenu(true)}>
            <Menu />
          </button>
          {!employeePortal && showSearch ? (
            <div className="search">
              <Search />
              <input
                aria-label="Search leads"
                placeholder="Search leads, phone, city…"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </div>
          ) : (
            <div className="header-context">
              {employeePortal
                ? "Onboarding"
                : activeView === "estimates"
                  ? "Sales"
                  : activeView === "jobs"
                    ? "Delivery"
                    : "People operations"}
            </div>
          )}
          <div className="header-actions">
            <span className={requestStatus === "offline" ? "status offline" : "status"}>{connectionLabel}</span>
            {credential && (
              <button className="sign-out" onClick={signOut} aria-label="Sign out">
                <LogOut />
              </button>
            )}
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}
