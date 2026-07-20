import { RefreshCw, ShieldCheck, UserRoundCog } from "lucide-react";
import { useState } from "react";
import type { IdentityProvisioningCommand, OnboardingEmployee } from "./onboardingTypes";

function statusMessage(command: IdentityProvisioningCommand): string {
  const messages: Record<IdentityProvisioningCommand["status"], string> = {
    admin_confirmation_required: "Automated license verification was unavailable. Audited setup is required.",
    admin_confirmed: "The managed account and no-paid-license state were confirmed.",
    approved: "Approved and waiting for the Directory worker.",
    executing: "Directory provisioning is in progress.",
    failed: `Provisioning failed closed${command.failure_code ? `: ${command.failure_code}` : "."}`,
    manual_review_required: "Directory provisioning requires administrator review.",
    manual_setup_required: "Create this account in Google Admin, then send a credentialed invitation below.",
    pending_approval: "A separate approval is required before Google Directory is contacted.",
    suspended: "The managed identity is suspended.",
    verified: "Directory identity, organizational unit, and no-paid-license state are verified.",
  };
  return messages[command.status];
}

function CredentialForm({
  busy,
  reissue,
  onSubmit,
}: {
  busy: boolean;
  reissue: boolean;
  onSubmit(password: string, reason: string, evidence: string): Promise<void>;
}) {
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [reason, setReason] = useState("");
  const [evidence, setEvidence] = useState("");
  const valid = password.length >= 12 && password === confirmation && reason.trim() && evidence.trim();
  const submit = async () => {
    await onSubmit(password, reason.trim(), evidence.trim());
    setPassword("");
    setConfirmation("");
  };
  return (
    <div className="identity-confirmation">
      <label>
        Fresh temporary Google password
        <input autoComplete="new-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
      </label>
      <label>
        Confirm temporary password
        <input autoComplete="new-password" type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
      </label>
      <label>
        Confirmation reason
        <textarea required value={reason} onChange={(event) => setReason(event.target.value)} />
      </label>
      <label>
        Google Admin evidence reference
        <input required value={evidence} onChange={(event) => setEvidence(event.target.value)} />
      </label>
      <small>Submitting attests that the account exists, password change is required, and no paid license is assigned.</small>
      <button disabled={busy || !valid} type="button" onClick={() => void submit()}>
        {reissue ? "Send replacement credentials and invite" : "Confirm setup and send credentials"}
      </button>
    </div>
  );
}

export function IdentityProvisioningPanel({
  busy,
  commands,
  employee,
  onApprove,
  onCredential,
  onInvite,
  onRefresh,
}: {
  busy: boolean;
  commands: IdentityProvisioningCommand[];
  employee: OnboardingEmployee;
  onApprove(command: IdentityProvisioningCommand): Promise<void>;
  onCredential(command: IdentityProvisioningCommand, password: string, reason: string, evidence: string, reissue: boolean): Promise<void>;
  onInvite(employee: OnboardingEmployee): Promise<void>;
  onRefresh(employee: OnboardingEmployee): Promise<void>;
}) {
  const latest = commands[0];
  if (employee.classification === "independent_contractor") {
    return (
      <section className="identity-panel">
        <div className="identity-panel-title"><UserRoundCog /><div><strong>External contractor identity</strong><small>Contractors use a verified external Google identity.</small></div></div>
        {employee.status === "draft" && <button disabled={busy} onClick={() => void onInvite(employee)}>Queue contractor invitation</button>}
      </section>
    );
  }
  const needsSetup = latest && ["manual_setup_required", "admin_confirmation_required"].includes(latest.status);
  const canReissue = latest && ["verified", "admin_confirmed"].includes(latest.status) && employee.status === "invited";
  return (
    <section className="identity-panel">
      <div className="identity-panel-title"><ShieldCheck /><div><strong>Managed identity gate</strong><small>No employee invite is sent without fresh Google credentials.</small></div></div>
      {latest && <div className={`identity-command identity-${latest.status}`}><div><span>{latest.status.replaceAll("_", " ")}</span><p>{statusMessage(latest)}</p></div><button aria-label="Refresh provisioning status" disabled={busy} onClick={() => void onRefresh(employee)}><RefreshCw /></button></div>}
      {latest?.status === "pending_approval" && <button disabled={busy} onClick={() => void onApprove(latest)}>Approve Directory command</button>}
      {(needsSetup || canReissue) && <CredentialForm busy={busy} reissue={Boolean(canReissue)} onSubmit={(password, reason, evidence) => onCredential(latest, password, reason, evidence, Boolean(canReissue))} />}
    </section>
  );
}
