import { DeferredPanels, OverviewAgent } from "./OverviewPanels";
import { LeadQueue } from "./LeadQueue";
import { NotificationSettingsPanel } from "./NotificationSettingsPanel";
import type { ActiveView, Dashboard, Lead, NotificationSettings, SpamFilter } from "./types";

export function OperationsHome({
  activeView,
  data,
  leads,
  notificationSettings,
  settingsStatus,
  sourceFilter,
  spamFilter,
  statusFilter,
  onOpenLead,
  setSmsEnabled,
  setSourceFilter,
  setSpamFilter,
  setStatusFilter,
}: {
  activeView: ActiveView;
  data: Dashboard;
  leads: Lead[];
  notificationSettings: NotificationSettings | null;
  settingsStatus: "" | "saving" | "saved" | "error";
  sourceFilter: string;
  spamFilter: SpamFilter;
  statusFilter: string;
  onOpenLead(leadId: string): void;
  setSmsEnabled(enabled: boolean): void;
  setSourceFilter(value: string): void;
  setSpamFilter(value: SpamFilter): void;
  setStatusFilter(value: string): void;
}) {
  const today = new Intl.DateTimeFormat("en-US", { weekday: "long", month: "long", day: "numeric" }).format(new Date());
  const metrics: [string, string | number][] = [
    ["New leads", data.metrics.new_leads],
    ["Active jobs", data.metrics.active_jobs],
    ["Open tasks", data.metrics.open_tasks],
    ["Unbilled work", `$${data.metrics.unbilled_work.toLocaleString()}`],
  ];
  return (
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
        <NotificationSettingsPanel settings={notificationSettings} status={settingsStatus} onChange={setSmsEnabled} />
      )}
      <div className="grid">
        <LeadQueue
          leads={leads}
          sourceFilter={sourceFilter}
          spamFilter={spamFilter}
          statusFilter={statusFilter}
          onOpen={onOpenLead}
          setSourceFilter={setSourceFilter}
          setSpamFilter={setSpamFilter}
          setStatusFilter={setStatusFilter}
        />
        <OverviewAgent />
        {activeView === "overview" && <DeferredPanels />}
      </div>
    </>
  );
}
