import { useCallback, useEffect, useState } from "react";
import { AppShell } from "./AppShell";
import { CustomerWorkspace } from "./CustomerWorkspace";
import { EmployeeOnboardingWorkspace } from "./EmployeeOnboardingWorkspace";
import { EstimateWorkspace } from "./EstimateWorkspace";
import { FieldRecordWorkspace } from "./FieldRecordWorkspace";
import { LeadWorkspace } from "./LeadWorkspace";
import { JobWorkspace } from "./JobWorkspace";
import { NewHireWorkspace } from "./NewHireWorkspace";
import { OperationsHome } from "./OperationsHome";
import { ScheduleWorkspace } from "./ScheduleWorkspace";
import { useActiveView } from "./useActiveView";
import { useGoogleIdentity } from "./useGoogleIdentity";
import { useOperationsData } from "./useOperationsData";
import type { ActiveView, PortalSession, RequestStatus, SpamFilter } from "./types";

function useRouteGuards(
  activeView: ActiveView,
  clearSelection: () => void,
  navigate: (view: Exclude<ActiveView, "activate">) => void,
  session: PortalSession | null,
  requestStatus: RequestStatus,
) {
  useEffect(() => {
    if (requestStatus === "auth-required") clearSelection();
  }, [clearSelection, requestStatus]);
  useEffect(() => {
    if (requestStatus !== "ready" || !session) return;
    if (session.kind === "employee" && activeView !== "tasks") navigate("tasks");
    if (session.kind === "staff" && ["tasks", "activate"].includes(activeView)) navigate("overview");
    if (
      session.kind === "staff" &&
      session.role === "field" &&
      !["jobs", "schedule", "field-records"].includes(activeView)
    )
      navigate("jobs");
    if (session.kind === "staff" && session.role === "accounting" && activeView !== "jobs") navigate("jobs");
    if (activeView === "employees" && !["owner", "admin"].includes(session.role)) navigate("overview");
  }, [activeView, navigate, requestStatus, session]);
}

function DeliveryWorkspace({
  activeView,
  credential,
  session,
}: {
  activeView: ActiveView;
  credential: string;
  session: PortalSession | null;
}) {
  const role = session?.role || "";
  if (activeView === "schedule") {
    return <ScheduleWorkspace credential={credential} email={session?.email || ""} role={role} />;
  }
  if (activeView === "field-records") {
    return <FieldRecordWorkspace credential={credential} role={role} />;
  }
  return (
    <JobWorkspace
      canCancel={["owner", "admin"].includes(role)}
      canDeliver={["owner", "admin", "office", "estimator_pm", "field"].includes(role)}
      canPlan={["owner", "admin", "office", "estimator_pm"].includes(role)}
      credential={credential}
    />
  );
}

export function App() {
  const [menu, setMenu] = useState(false);
  const [selectedLead, setSelectedLead] = useState("");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [spamFilter, setSpamFilter] = useState<SpamFilter>("active");
  const [activationError, setActivationError] = useState("");
  const clearSelection = useCallback(() => setSelectedLead(""), []);
  const { activeView, navigate, openLeads } = useActiveView(clearSelection);
  const operations = useOperationsData(statusFilter, sourceFilter, spamFilter, query);
  const onCredential = useCallback(
    async (credential: string) => {
      if (activeView === "activate") {
        const token = new URLSearchParams(window.location.hash.split("?", 2)[1] || "").get("token");
        if (!token) {
          setActivationError("This invitation link is incomplete.");
          return;
        }
        const response = await fetch("/api/benson/v1/onboarding/activate", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ token, credential }),
        });
        if (!response.ok) {
          const body = (await response.json().catch(() => ({}))) as { detail?: string };
          setActivationError(body.detail || "This invitation could not be accepted.");
          return;
        }
      }
      operations.authenticate(credential);
    },
    [activeView, operations.authenticate],
  );
  const onIdentityUnavailable = useCallback(
    () => operations.setRequestStatus("auth-required"),
    [operations.setRequestStatus],
  );
  const googleButton = useGoogleIdentity(operations.requestStatus, onCredential, onIdentityUnavailable);
  const canApprove = ["owner", "admin"].includes(operations.portalSession?.role || "");

  useRouteGuards(activeView, clearSelection, navigate, operations.portalSession, operations.requestStatus);

  const openLead = (leadId: string) => {
    openLeads();
    setSelectedLead(leadId);
  };
  const signOut = () => {
    operations.signOut();
    clearSelection();
  };

  return (
    <AppShell
      activeView={activeView}
      credential={operations.credential}
      menu={menu}
      query={query}
      requestStatus={operations.requestStatus}
      portalSession={operations.portalSession}
      setMenu={setMenu}
      setQuery={setQuery}
      signOut={signOut}
    >
      <div className={selectedLead ? "content lead-content" : "content"}>
        {operations.requestStatus === "auth-required" && (
          <section className="auth-banner" aria-label="Staff sign in">
            <div>
              <small>{activeView === "activate" ? "SECURE INVITATION" : "STAFF WORKSPACE"}</small>
              <h2>
                {activeView === "activate"
                  ? "Accept your invitation with the assigned Benson account."
                  : "Sign in with your Benson Google Workspace account."}
              </h2>
              <p>
                {activeView === "activate"
                  ? "Use the exact unlicensed Workspace identity created for you."
                  : "Sign in to open your Benson operations workspace."}
              </p>
              {activationError && <p className="form-error">{activationError}</p>}
            </div>
            <div className="google-signin-area">
              <div ref={googleButton} className="google-button" />
              <button className="google-signin-fallback" type="button">
                Sign in with Google
              </button>
            </div>
          </section>
        )}
        {operations.requestStatus === "ready" && operations.portalSession?.kind === "employee" ? (
          <EmployeeOnboardingWorkspace credential={operations.credential} />
        ) : operations.requestStatus === "ready" && activeView === "employees" ? (
          <NewHireWorkspace credential={operations.credential} />
        ) : operations.requestStatus === "ready" && activeView === "customers" ? (
          <CustomerWorkspace
            canArchive={["owner", "admin"].includes(operations.portalSession?.role || "")}
            credential={operations.credential}
            customers={operations.customers}
            leads={operations.leads}
            setCustomers={operations.setCustomers}
          />
        ) : operations.requestStatus === "ready" && activeView === "estimates" ? (
          <EstimateWorkspace canVoid={canApprove} credential={operations.credential} customers={operations.customers} />
        ) : operations.requestStatus === "ready" && ["jobs", "schedule", "field-records"].includes(activeView) ? (
          <DeliveryWorkspace
            activeView={activeView}
            credential={operations.credential}
            session={operations.portalSession}
          />
        ) : operations.requestStatus === "ready" && selectedLead ? (
          <LeadWorkspace
            leadId={selectedLead}
            credential={operations.credential}
            onBack={clearSelection}
            onChanged={(changed) =>
              operations.setLeads((current) => current.map((lead) => (lead.id === changed.id ? changed : lead)))
            }
            onDeleted={(leadId) => {
              operations.setLeads((current) => current.filter((lead) => lead.id !== leadId));
              clearSelection();
            }}
          />
        ) : operations.requestStatus === "ready" ? (
          <OperationsHome
            activeView={activeView}
            data={operations.data}
            leads={operations.leads}
            notificationSettings={operations.notificationSettings}
            settingsStatus={operations.settingsStatus}
            sourceFilter={sourceFilter}
            spamFilter={spamFilter}
            statusFilter={statusFilter}
            onOpenLead={openLead}
            setSmsEnabled={(enabled) => void operations.setSmsEnabled(enabled)}
            setSourceFilter={setSourceFilter}
            setSpamFilter={setSpamFilter}
            setStatusFilter={setStatusFilter}
          />
        ) : null}
      </div>
    </AppShell>
  );
}
