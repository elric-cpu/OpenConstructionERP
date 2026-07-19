import { CheckCircle2, RefreshCw, ShieldCheck, UserRoundCog } from "lucide-react";
import { useState } from "react";
import type { IdentityProvisioningCommand, OnboardingEmployee } from "./onboardingTypes";

function statusMessage(command: IdentityProvisioningCommand): string {
  const messages: Record<IdentityProvisioningCommand["status"], string> = {
    admin_confirmation_required: "Automated license verification was unavailable. Audited confirmation is required.",
    admin_confirmed: "An administrator confirmed the no-paid-license state with evidence.",
    approved: "Approved and waiting for the Directory worker.",
    executing: "Directory provisioning is in progress.",
    failed: `Provisioning failed closed${command.failure_code ? `: ${command.failure_code}` : "."}`,
    pending_approval: "A separate approval is required before Google Directory is contacted.",
    suspended: "The managed identity is suspended.",
    verified: "Directory identity, organizational unit, and no-paid-license state are verified.",
  };
  return messages[command.status];
}

export function IdentityProvisioningPanel({
  busy,
  commands,
  employee,
  onApprove,
  onConfirm,
  onInvite,
  onRefresh,
  onRequest,
}: {
  busy: boolean;
  commands: IdentityProvisioningCommand[];
  employee: OnboardingEmployee;
  onApprove(command: IdentityProvisioningCommand): Promise<void>;
  onConfirm(command: IdentityProvisioningCommand, reason: string, evidence: string): Promise<void>;
  onInvite(employee: OnboardingEmployee): Promise<void>;
  onRefresh(employee: OnboardingEmployee): Promise<void>;
  onRequest(): Promise<void>;
}) {
  const [reason, setReason] = useState("");
  const [evidence, setEvidence] = useState("");
  const latest = commands[0];
  const verified = latest && ["verified", "admin_confirmed"].includes(latest.status);
  if (employee.classification === "independent_contractor") {
    return (
      <section className="identity-panel">
        <div className="identity-panel-title">
          <UserRoundCog aria-hidden="true" />
          <div>
            <strong>External contractor identity</strong>
            <small>Contractors use a verified external Google identity and receive contractor-only tasks.</small>
          </div>
        </div>
        {employee.status === "draft" && (
          <button disabled={busy} type="button" onClick={() => void onInvite(employee)}>
            Queue contractor invitation
          </button>
        )}
      </section>
    );
  }
  return (
    <section className="identity-panel">
      <div className="identity-panel-title">
        <ShieldCheck aria-hidden="true" />
        <div>
          <strong>Managed identity gate</strong>
          <small>Invitation stays locked until Directory and license verification succeeds.</small>
        </div>
      </div>
      {!latest ? (
        <button disabled={busy || employee.status !== "draft"} type="button" onClick={() => void onRequest()}>
          Request Directory identity
        </button>
      ) : (
        <div className={`identity-command identity-${latest.status}`}>
          <div>
            <span>{latest.status.replaceAll("_", " ")}</span>
            <p>{statusMessage(latest)}</p>
          </div>
          <button
            aria-label="Refresh provisioning status"
            disabled={busy}
            type="button"
            onClick={() => void onRefresh(employee)}
          >
            <RefreshCw aria-hidden="true" />
          </button>
        </div>
      )}
      {latest?.status === "pending_approval" && (
        <button disabled={busy} type="button" onClick={() => void onApprove(latest)}>
          Approve Directory command
        </button>
      )}
      {latest?.status === "admin_confirmation_required" && (
        <div className="identity-confirmation">
          <label>
            Confirmation reason
            <textarea required value={reason} onChange={(event) => setReason(event.target.value)} />
          </label>
          <label>
            Protected evidence reference
            <input required value={evidence} onChange={(event) => setEvidence(event.target.value)} />
          </label>
          <button
            disabled={busy || !reason.trim() || !evidence.trim()}
            type="button"
            onClick={() => void onConfirm(latest, reason.trim(), evidence.trim())}
          >
            Record audited confirmation
          </button>
        </div>
      )}
      {verified && employee.status === "draft" && (
        <button className="identity-invite" disabled={busy} type="button" onClick={() => void onInvite(employee)}>
          <CheckCircle2 aria-hidden="true" /> Queue invitation
        </button>
      )}
    </section>
  );
}
