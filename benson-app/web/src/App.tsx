import { useCallback, useEffect, useState } from "react";
import { AppShell } from "./AppShell";
import { CustomerWorkspace } from "./CustomerWorkspace";
import { EmployeeTasks } from "./EmployeeTasks";
import { EstimateWorkspace } from "./EstimateWorkspace";
import { LeadWorkspace } from "./LeadWorkspace";
import { NewHireWorkspace } from "./NewHireWorkspace";
import { OperationsHome } from "./OperationsHome";
import { useActiveView } from "./useActiveView";
import { useGoogleIdentity } from "./useGoogleIdentity";
import { useOperationsData } from "./useOperationsData";
import type { SpamFilter } from "./types";

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

  useEffect(() => {
    if (operations.requestStatus === "auth-required") clearSelection();
  }, [clearSelection, operations.requestStatus]);
  useEffect(() => {
    if (operations.requestStatus !== "ready" || !operations.portalSession) return;
    if (operations.portalSession.kind === "employee" && activeView !== "tasks") navigate("tasks");
    if (operations.portalSession.kind === "staff" && ["tasks", "activate"].includes(activeView)) navigate("overview");
    if (activeView === "employees" && !["owner", "admin"].includes(operations.portalSession.role)) navigate("overview");
  }, [activeView, navigate, operations.portalSession, operations.requestStatus]);

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
                  : "Customer, project, pricing, and accounting information stays behind staff authentication."}
              </p>
              {activationError && <p className="form-error">{activationError}</p>}
            </div>
            <div ref={googleButton} className="google-button" />
          </section>
        )}
        {operations.requestStatus === "ready" && operations.portalSession?.kind === "employee" ? (
          <EmployeeTasks
            credential={operations.credential}
            documents={operations.employeeDocuments}
            session={operations.portalSession}
            setDocuments={operations.setEmployeeDocuments}
            setTasks={operations.setEmployeeTasks}
            tasks={operations.employeeTasks}
          />
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
          <EstimateWorkspace
            canVoid={["owner", "admin"].includes(operations.portalSession?.role || "")}
            credential={operations.credential}
            customers={operations.customers}
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
