import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  BriefcaseBusiness,
  CalendarDays,
  ClipboardCheck,
  Hammer,
  Home,
  Inbox,
  LogOut,
  Menu,
  Search,
  Sparkles,
  Users,
  X,
} from "lucide-react";

type Dashboard = { metrics: Record<string, number>; attention: unknown[]; schedule: unknown[]; jobs: unknown[] };
type Lead = {
  id: string;
  priority: string;
  name: string;
  service_type: string;
  city: string;
  created_at: string;
};
type GoogleIdentity = {
  accounts: {
    id: {
      initialize(options: { client_id: string; callback(response: { credential: string }): void }): void;
      renderButton(element: HTMLElement, options: Record<string, string>): void;
    };
  };
};
declare global {
  interface Window {
    google?: GoogleIdentity;
  }
}

const empty: Dashboard = {
  metrics: { new_leads: 0, active_jobs: 0, open_tasks: 0, unbilled_work: 0 },
  attention: [],
  schedule: [],
  jobs: [],
};
const nav = [
  [Home, "Overview"],
  [Inbox, "Leads"],
  [BriefcaseBusiness, "Jobs"],
  [CalendarDays, "Schedule"],
  [ClipboardCheck, "Estimates"],
  [Users, "Customers"],
] as const;
const tokenKey = "benson-google-credential";

function requestHeaders(token: string): Record<string, string> {
  return token ? { authorization: `Bearer ${token}` } : {};
}

export function App() {
  const [data, setData] = useState(empty);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [credential, setCredential] = useState(() => sessionStorage.getItem(tokenKey) ?? "");
  const [requestStatus, setRequestStatus] = useState<"loading" | "ready" | "auth-required" | "offline">("loading");
  const [menu, setMenu] = useState(false);
  const googleButton = useRef<HTMLDivElement>(null);

  useEffect(() => {
    Promise.all([
      fetch("/api/v1/dashboard", { headers: requestHeaders(credential) }),
      fetch("/api/benson/v1/leads?limit=6", { headers: requestHeaders(credential) }),
    ])
      .then(async ([dashboardResponse, leadsResponse]) => {
        if ([401, 403, 503].includes(dashboardResponse.status)) {
          setRequestStatus("auth-required");
          return;
        }
        if (!dashboardResponse.ok || !leadsResponse.ok) throw Error("Operations API unavailable");
        setData(await dashboardResponse.json());
        setLeads((await leadsResponse.json()).leads);
        setRequestStatus("ready");
      })
      .catch(() => setRequestStatus("offline"));
  }, [credential]);

  useEffect(() => {
    if (requestStatus !== "auth-required" || !googleButton.current) return;
    fetch("/api/benson/v1/auth/config")
      .then((response) => response.json())
      .then((config: { client_id: string }) => {
        if (!config.client_id) return;
        const render = () => {
          if (!window.google || !googleButton.current) return;
          window.google.accounts.id.initialize({
            client_id: config.client_id,
            callback: ({ credential }) => {
              sessionStorage.setItem(tokenKey, credential);
              setCredential(credential);
            },
          });
          window.google.accounts.id.renderButton(googleButton.current, {
            theme: "outline",
            size: "large",
            text: "signin_with",
          });
        };
        if (window.google) return render();
        const script = document.createElement("script");
        script.src = "https://accounts.google.com/gsi/client";
        script.async = true;
        script.onload = render;
        document.head.append(script);
      })
      .catch(() => setRequestStatus("offline"));
  }, [requestStatus]);

  const signOut = () => {
    sessionStorage.removeItem(tokenKey);
    setCredential("");
    setData(empty);
    setLeads([]);
    setRequestStatus("auth-required");
  };
  const metrics: [string, string | number][] = [
    ["New leads", data.metrics.new_leads],
    ["Active jobs", data.metrics.active_jobs],
    ["Open tasks", data.metrics.open_tasks],
    ["Unbilled work", `$${data.metrics.unbilled_work.toLocaleString()}`],
  ];
  const today = new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  }).format(new Date());

  return (
    <div className="shell">
      <aside className={menu ? "open" : ""}>
        <div className="brand">
          <span>BH</span>
          <div>
            <b>Benson</b>
            <small>Operations</small>
          </div>
          <button aria-label="Close menu" onClick={() => setMenu(false)}>
            <X />
          </button>
        </div>
        <nav>
          {nav.map(([Icon, label], index) => (
            <a className={index === 0 ? "active" : ""} href={`#${label.toLowerCase()}`} key={label}>
              <Icon />
              {label}
            </a>
          ))}
        </nav>
        <div className="rail-foot">
          <div className="avatar">BH</div>
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
            <input aria-label="Search" placeholder="Search jobs, customers, addresses…" />
          </div>
          <div className="header-actions">
            <span className={requestStatus === "offline" ? "status offline" : "status"}>
              {requestStatus === "offline" ? "Connection issue" : "System ready"}
            </span>
            {credential && (
              <button className="sign-out" onClick={signOut} aria-label="Sign out">
                <LogOut />
              </button>
            )}
          </div>
        </header>
        <div className="content">
          {requestStatus === "auth-required" && (
            <section className="auth-banner" aria-label="Staff sign in">
              <div>
                <small>STAFF WORKSPACE</small>
                <h2>Sign in with your Benson Google Workspace account.</h2>
                <p>Customer, project, pricing, and accounting information stays behind staff authentication.</p>
              </div>
              <div ref={googleButton} className="google-button" />
            </section>
          )}
          <div className="headline">
            <div>
              <p>{today}</p>
              <h1>Good morning.</h1>
              <span>Here’s what needs your attention today.</span>
            </div>
            <a className="primary" href="https://bensonhomesolutions.com/contact">
              + New lead
            </a>
          </div>
          <section className="metrics">
            {metrics.map(([label, value]) => (
              <article key={label}>
                <small>{label}</small>
                <strong>{value}</strong>
                <em>Live workspace total</em>
              </article>
            ))}
          </section>
          <div className="grid">
            <Panel title="New lead queue" subtitle="Website requests waiting for staff review." link="View all">
              {leads.length ? (
                <div className="lead-list">
                  {leads.map((lead) => (
                    <article key={lead.id}>
                      <span className={lead.priority === "urgent" ? "priority urgent" : "priority"}>
                        {lead.priority}
                      </span>
                      <div>
                        <strong>{lead.name}</strong>
                        <small>
                          {lead.service_type} · {lead.city || "Location pending"}
                        </small>
                      </div>
                      <time>
                        {new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(
                          new Date(lead.created_at),
                        )}
                      </time>
                    </article>
                  ))}
                </div>
              ) : (
                <Empty
                  icon={<ClipboardCheck />}
                  title="You’re caught up"
                  body="New website requests will appear here."
                />
              )}
            </Panel>
            <section className="panel agent">
              <div className="agent-head">
                <Sparkles />
                <div>
                  <h2>Benson Assistant</h2>
                  <p>Free Claude Code gateway · reviewed construction skills</p>
                </div>
              </div>
              <p>Draft summaries, estimates, and next steps. Every mutation or external send requires confirmation.</p>
              <div className="prompts">
                <button disabled title="Assistant workspace is not enabled in this release">
                  Summarize new leads
                </button>
                <button disabled title="Assistant workspace is not enabled in this release">
                  Review estimate risks
                </button>
                <button disabled title="Assistant workspace is not enabled in this release">
                  Draft daily report
                </button>
              </div>
              <div className="ask">
                <input aria-label="Ask Benson Assistant" placeholder="Ask about your operations…" />
                <button disabled title="Assistant workspace is not enabled in this release">
                  Ask
                </button>
              </div>
            </section>
            <Panel title="Today’s schedule" subtitle="Field visits and committed work." link="Open calendar">
              <Empty
                icon={<CalendarDays />}
                title="No visits scheduled"
                body="Add work from a job or estimate."
                compact
              />
            </Panel>
            <Panel title="Active jobs" subtitle="Current residential work." link="View jobs">
              <Empty icon={<Hammer />} title="No active jobs yet" body="Accepted estimates will appear here." compact />
            </Panel>
          </div>
        </div>
      </main>
    </div>
  );
}

function Panel({
  title,
  subtitle,
  link,
  children,
}: {
  title: string;
  subtitle: string;
  link: string;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <div className="panel-title">
        <div>
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </div>
        <a href="#details">{link}</a>
      </div>
      {children}
    </section>
  );
}

function Empty({
  icon,
  title,
  body,
  compact = false,
}: {
  icon: ReactNode;
  title: string;
  body: string;
  compact?: boolean;
}) {
  return (
    <div className={`empty ${compact ? "compact" : ""}`}>
      {icon}
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  );
}
