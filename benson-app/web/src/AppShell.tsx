import type { ReactNode } from "react";
import {
  BriefcaseBusiness,
  CalendarDays,
  ClipboardCheck,
  Home,
  Inbox,
  LogOut,
  Menu,
  Search,
  Users,
  X,
} from "lucide-react";
import type { ActiveView, RequestStatus } from "./types";

const nav = [
  [Home, "Overview", "overview"],
  [Inbox, "Leads", "leads"],
  [BriefcaseBusiness, "Jobs", null],
  [CalendarDays, "Schedule", null],
  [ClipboardCheck, "Estimates", null],
  [Users, "Customers", null],
] as const;

export function AppShell({
  activeView,
  children,
  credential,
  menu,
  query,
  requestStatus,
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
          {nav.map(([Icon, label, route]) =>
            route ? (
              <a
                aria-current={activeView === route ? "page" : undefined}
                className={activeView === route ? "active" : ""}
                href={`#${route}`}
                key={label}
                onClick={() => setMenu(false)}
              >
                <Icon /> {label}
              </a>
            ) : (
              <span className="nav-disabled" key={label} title={`${label} is outside the lead-foundation launch scope`}>
                <Icon /> <span>{label}</span> <small>Later</small>
              </span>
            ),
          )}
        </nav>
        <div className="rail-foot">
          <img className="avatar" src="/benson-enterprises-logo.svg" alt="" />
          <div>
            <b>Benson staff</b>
            <small>Burns, Oregon</small>
          </div>
        </div>
      </aside>
      <main>
        <header>
          <button className="menu" aria-label="Open menu" onClick={() => setMenu(true)}>
            <Menu />
          </button>
          <div className="search">
            <Search />
            <input
              aria-label="Search leads"
              placeholder="Search leads, phone, city…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
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
