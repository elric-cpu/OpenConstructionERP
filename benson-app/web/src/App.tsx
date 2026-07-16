import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  BellRing,
  BriefcaseBusiness,
  CalendarDays,
  ClipboardCheck,
  Hammer,
  Home,
  Inbox,
  LogOut,
  Menu,
  Search,
  ShieldAlert,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import { LeadWorkspace } from "./LeadWorkspace";
import type { Lead } from "./LeadWorkspace";

type Dashboard = { metrics: Record<string, number>; attention: unknown[]; schedule: unknown[]; jobs: unknown[] };
type NotificationSettings = { email_enabled: true; sms_enabled: boolean; sms_configured: boolean };
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
  [Home, "Overview", "overview"],
  [Inbox, "Leads", "leads"],
  [BriefcaseBusiness, "Jobs", null],
  [CalendarDays, "Schedule", null],
  [ClipboardCheck, "Estimates", null],
  [Users, "Customers", null],
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
  const [selectedLead, setSelectedLead] = useState("");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [spamFilter, setSpamFilter] = useState<"active" | "spam" | "all">("active");
  const [notificationSettings, setNotificationSettings] = useState<NotificationSettings | null>(null);
  const [settingsStatus, setSettingsStatus] = useState<"" | "saving" | "saved" | "error">("");
  const [activeView, setActiveView] = useState<"overview" | "leads">(() =>
    window.location.hash === "#leads" ? "leads" : "overview",
  );
  const googleButton = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const syncView = () => {
      const requestedView = window.location.hash;
      const nextView = requestedView === "#leads" ? "leads" : "overview";
      if (requestedView !== "#overview" && requestedView !== "#leads") {
        window.history.replaceState(null, "", "#overview");
      }
      setActiveView(nextView);
      setSelectedLead("");
    };
    syncView();
    window.addEventListener("hashchange", syncView);
    return () => window.removeEventListener("hashchange", syncView);
  }, []);

  useEffect(() => {
    if (!credential) {
      setData(empty);
      setLeads([]);
      setSelectedLead("");
      setNotificationSettings(null);
      setRequestStatus("auth-required");
      return;
    }
    const controller = new AbortController();
    let active = true;
    const protectedHeaders = requestHeaders(credential);
    Promise.all([
      fetch("/api/v1/dashboard", { headers: protectedHeaders, signal: controller.signal }),
      fetch(`/api/benson/v1/leads?${leadQuery(statusFilter, sourceFilter, spamFilter, query)}`, {
        headers: protectedHeaders,
        signal: controller.signal,
      }),
      fetch("/api/benson/v1/settings/notifications", { headers: protectedHeaders, signal: controller.signal }),
    ])
      .then(async ([dashboardResponse, leadsResponse, settingsResponse]) => {
        if (!active) return;
        if ([dashboardResponse, leadsResponse].some((response) => [401, 403].includes(response.status))) {
          setData(empty);
          setLeads([]);
          setSelectedLead("");
          setNotificationSettings(null);
          setRequestStatus("auth-required");
          return;
        }
        if (dashboardResponse.status === 503 || leadsResponse.status === 503) throw Error("Operations API unavailable");
        if (!dashboardResponse.ok || !leadsResponse.ok) throw Error("Operations API unavailable");
        const [nextData, nextLeads, nextSettings] = await Promise.all([
          dashboardResponse.json(),
          leadsResponse.json(),
          settingsResponse.ok ? settingsResponse.json() : Promise.resolve(null),
        ]);
        if (!active) return;
        setData(nextData);
        setLeads(nextLeads.leads);
        setNotificationSettings(nextSettings);
        setRequestStatus("ready");
      })
      .catch((error) => {
        if (active && error instanceof Error && error.name !== "AbortError") setRequestStatus("offline");
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [credential, query, sourceFilter, spamFilter, statusFilter]);

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
      .catch(() => setRequestStatus("auth-required"));
  }, [requestStatus]);

  const signOut = () => {
    sessionStorage.removeItem(tokenKey);
    setCredential("");
    setData(empty);
    setLeads([]);
    setSelectedLead("");
    setNotificationSettings(null);
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
  const connectionLabel = {
    loading: "Connecting",
    ready: "System ready",
    "auth-required": "Sign in required",
    offline: "Connection issue",
  }[requestStatus];

  const setSmsEnabled = async (smsEnabled: boolean) => {
    if (!notificationSettings) return;
    const previous = notificationSettings;
    setNotificationSettings({ ...notificationSettings, sms_enabled: smsEnabled });
    setSettingsStatus("saving");
    try {
      const response = await fetch("/api/benson/v1/settings/notifications", {
        method: "PATCH",
        headers: { ...requestHeaders(credential), "content-type": "application/json" },
        body: JSON.stringify({ sms_enabled: smsEnabled }),
      });
      if (!response.ok) throw new Error("Settings update failed");
      setNotificationSettings(await response.json());
      setSettingsStatus("saved");
    } catch {
      setNotificationSettings(previous);
      setSettingsStatus("error");
    }
  };

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
                <Icon />
                {label}
              </a>
            ) : (
              <span className="nav-disabled" key={label} title={`${label} is outside the lead-foundation launch scope`}>
                <Icon />
                <span>{label}</span>
                <small>Later</small>
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
        <div className={selectedLead ? "content lead-content" : "content"}>
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
          {requestStatus === "ready" && selectedLead ? (
            <LeadWorkspace
              leadId={selectedLead}
              credential={credential}
              onBack={() => setSelectedLead("")}
              onChanged={(changed) =>
                setLeads((current) => current.map((lead) => (lead.id === changed.id ? changed : lead)))
              }
              onDeleted={(leadId) => {
                setLeads((current) => current.filter((lead) => lead.id !== leadId));
                setSelectedLead("");
              }}
            />
          ) : requestStatus === "ready" ? (
            <>
              <div className="headline">
                <div>
                  <p>{activeView === "overview" ? today : "LEAD WORKSPACE"}</p>
                  <h1>{activeView === "overview" ? "Good morning." : "Leads"}</h1>
                  <span>
                    {activeView === "overview"
                      ? "Here’s what needs your attention today."
                      : "Review website requests, ownership, notes, and follow-up."}
                  </span>
                </div>
                <a className="primary" href="https://bensonhomesolutions.com/contact">
                  + New lead
                </a>
              </div>
              {activeView === "overview" && (
                <section className="metrics">
                  {metrics.map(([label, value]) => (
                    <article key={label}>
                      <small>{label}</small>
                      <strong>{value}</strong>
                      <em>Live workspace total</em>
                    </article>
                  ))}
                </section>
              )}
              {activeView === "overview" && notificationSettings && (
                <section
                  className="notification-settings"
                  id="notification-settings"
                  aria-label="Notifications settings"
                >
                  <div className="settings-icon">
                    <BellRing />
                  </div>
                  <div>
                    <small>OWNER SETTINGS</small>
                    <h2>Lead notifications</h2>
                    <p>
                      Email alerts stay on. SMS alerts are optional and are currently{" "}
                      {notificationSettings.sms_enabled ? "on" : "off"}.
                    </p>
                  </div>
                  <label className="toggle-setting">
                    <input
                      type="checkbox"
                      checked={notificationSettings.sms_enabled}
                      disabled={!notificationSettings.sms_configured || settingsStatus === "saving"}
                      onChange={(event) => void setSmsEnabled(event.target.checked)}
                    />
                    <span>Emergency SMS alerts</span>
                    <small>
                      {notificationSettings.sms_configured
                        ? settingsStatus === "saving"
                          ? "Saving…"
                          : settingsStatus === "saved"
                            ? "Saved"
                            : "Twilio configured"
                        : "Configure Twilio before enabling"}
                    </small>
                  </label>
                  {settingsStatus === "error" && <p className="form-error">Notification settings were not saved.</p>}
                </section>
              )}
              <div className="grid">
                <Panel title="Lead queue" subtitle="Website requests and staff follow-up." link="Live">
                  <div className="queue-tools">
                    <label>
                      Status
                      <select
                        aria-label="Filter leads by status"
                        value={statusFilter}
                        onChange={(event) => setStatusFilter(event.target.value)}
                      >
                        <option value="">All statuses</option>
                        {["new", "contacted", "qualified", "scheduled", "closed"].map((status) => (
                          <option key={status}>{status}</option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Source
                      <select
                        aria-label="Filter leads by source"
                        value={sourceFilter}
                        onChange={(event) => setSourceFilter(event.target.value)}
                      >
                        <option value="">All sources</option>
                        {[...new Set(leads.map((lead) => lead.source))].sort().map((source) => (
                          <option key={source}>{source}</option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Queue
                      <select
                        aria-label="Filter spam leads"
                        value={spamFilter}
                        onChange={(event) => setSpamFilter(event.target.value as "active" | "spam" | "all")}
                      >
                        <option value="active">Active leads</option>
                        <option value="spam">Spam</option>
                        <option value="all">All leads</option>
                      </select>
                    </label>
                    <span>{leads.length} shown</span>
                  </div>
                  {leads.length ? (
                    <div className="lead-list">
                      {leads.map((lead) => (
                        <button
                          className="lead-row"
                          key={lead.id}
                          onClick={() => {
                            setActiveView("leads");
                            window.history.replaceState(null, "", "#leads");
                            setSelectedLead(lead.id);
                          }}
                        >
                          <span className={lead.priority === "urgent" ? "priority urgent" : "priority"}>
                            {lead.priority}
                          </span>
                          <div>
                            <strong>{lead.name}</strong>
                            <small>
                              {lead.service_type} · {lead.city || "Location pending"}
                            </small>
                            <small className="lead-source">Source: {lead.source}</small>
                          </div>
                          <time>
                            {new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(
                              new Date(lead.created_at),
                            )}
                          </time>
                          <span className="lead-status">{lead.status}</span>
                          {lead.is_spam && (
                            <span className="spam-flag">
                              <ShieldAlert /> Spam
                            </span>
                          )}
                        </button>
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
                <section className="panel agent overview-agent">
                  <div className="agent-head">
                    <Sparkles />
                    <div>
                      <h2>Benson Assistant</h2>
                      <p>Free Claude Code gateway · reviewed construction skills</p>
                    </div>
                  </div>
                  <p>Select a lead to draft a fact-scoped summary, next steps, or reviewed construction analysis.</p>
                  <div className="prompts">
                    <button disabled title="Select a lead first">
                      Summarize new leads
                    </button>
                    <button disabled title="Select a lead first">
                      Review estimate risks
                    </button>
                    <button disabled title="Select a lead first">
                      Draft daily report
                    </button>
                  </div>
                  <div className="ask">
                    <input aria-label="Ask Benson Assistant" placeholder="Ask about your operations…" />
                    <button disabled title="Select a lead first">
                      Ask
                    </button>
                  </div>
                </section>
                {activeView === "overview" && (
                  <>
                    <Panel title="Today’s schedule" subtitle="Field visits and committed work." link="Coming later">
                      <Empty
                        icon={<CalendarDays />}
                        title="Schedule is outside launch scope"
                        body="The lead foundation does not schedule field work yet."
                        compact
                      />
                    </Panel>
                    <Panel title="Active jobs" subtitle="Current residential work." link="Coming later">
                      <Empty
                        icon={<Hammer />}
                        title="Jobs are outside launch scope"
                        body="Qualified leads stay in the lead queue for this release."
                        compact
                      />
                    </Panel>
                  </>
                )}
              </div>
            </>
          ) : null}
        </div>
      </main>
    </div>
  );
}

function leadQuery(status: string, source: string, spam: string, query: string): string {
  const params = new URLSearchParams({ limit: "100", spam });
  if (status) params.set("status", status);
  if (source) params.set("source", source);
  if (query) params.set("query", query);
  return params.toString();
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
