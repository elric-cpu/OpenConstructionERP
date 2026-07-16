import { useCallback, useEffect, useState } from "react";
import { AppShell } from "./AppShell";
import { LeadWorkspace } from "./LeadWorkspace";
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
  const clearSelection = useCallback(() => setSelectedLead(""), []);
  const { activeView, openLeads } = useActiveView(clearSelection);
  const operations = useOperationsData(statusFilter, sourceFilter, spamFilter, query);
  const onCredential = useCallback(
    (credential: string) => operations.authenticate(credential),
    [operations.authenticate],
  );
  const onIdentityUnavailable = useCallback(
    () => operations.setRequestStatus("auth-required"),
    [operations.setRequestStatus],
  );
  const googleButton = useGoogleIdentity(operations.requestStatus, onCredential, onIdentityUnavailable);

  useEffect(() => {
    if (operations.requestStatus === "auth-required") clearSelection();
  }, [clearSelection, operations.requestStatus]);

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
      setMenu={setMenu}
      setQuery={setQuery}
      signOut={signOut}
    >
      <div className={selectedLead ? "content lead-content" : "content"}>
        {operations.requestStatus === "auth-required" && (
          <section className="auth-banner" aria-label="Staff sign in">
            <div>
              <small>STAFF WORKSPACE</small>
              <h2>Sign in with your Benson Google Workspace account.</h2>
              <p>Customer, project, pricing, and accounting information stays behind staff authentication.</p>
            </div>
            <div ref={googleButton} className="google-button" />
          </section>
        )}
        {operations.requestStatus === "ready" && selectedLead ? (
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
