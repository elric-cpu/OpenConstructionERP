import { useState } from "react";

import { ApiError } from "../../api/client";
import type { Employee } from "./types";
import {
  useEmployeeActivationPreview,
  useReissueEmployeeActivation,
} from "./useEmployeeOnboarding";

function formatDate(value: string | null) {
  return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "Not yet";
}

function errorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : "The activation request could not be completed.";
}

export function EmployeeActivationPanel({ employee }: { employee: Employee }) {
  const reissue = useReissueEmployeeActivation();
  const preview = useEmployeeActivationPreview();
  const [reason, setReason] = useState("Manager requested a new employee activation link.");

  const canReissue = employee.status === "IDENTITY_CREATED" && !employee.erp_access_confirmed_at;
  const error = reissue.error ?? preview.error;

  async function resend() {
    await reissue.mutateAsync({ employee, reason });
  }

  return (
    <section className="activation-manager" aria-labelledby="activation-manager-title">
      <div className="card-heading">
        <div><p className="eyebrow">ERP access</p><h3 id="activation-manager-title">Activation handoff</h3></div>
        <span className={`status-badge ${employee.erp_access_confirmed_at ? "ready" : ""}`}>
          {employee.erp_access_confirmed_at ? "Access confirmed" : employee.activation_sent_at ? "Invitation sent" : "Awaiting invitation"}
        </span>
      </div>
      <dl className="activation-manager-facts">
        <div><dt>Invitation sent</dt><dd>{formatDate(employee.activation_sent_at)}</dd></div>
        <div><dt>ERP access confirmed</dt><dd>{formatDate(employee.erp_access_confirmed_at)}</dd></div>
      </dl>
      {error && <div className="alert" role="alert">{errorMessage(error)}</div>}
      {reissue.isSuccess && <p className="ready-text" role="status">A new single-use activation invitation was queued for delivery.</p>}
      {canReissue && (
        <div className="activation-manager-actions">
          <label>Resend reason
            <textarea minLength={10} required rows={2} value={reason} onChange={(event) => setReason(event.target.value)} />
          </label>
          <div className="export-actions">
            <button className="primary" disabled={reissue.isPending || reason.trim().length < 10} onClick={() => void resend()} type="button">
              {reissue.isPending ? "Queueing…" : "Send new activation link"}
            </button>
            <button className="quiet" disabled={preview.isPending} onClick={() => preview.mutate(employee.id)} type="button">
              {preview.isPending ? "Checking…" : "Open local email preview"}
            </button>
          </div>
        </div>
      )}
      {preview.data && (
        <div className="activation-preview" role="status">
          <strong>Local mock delivery</strong>
          <span>Expires {formatDate(preview.data.expires_at)}</span>
          <a className="quiet" href={preview.data.activation_url} rel="noreferrer">Open employee activation</a>
        </div>
      )}
      {!canReissue && !employee.erp_access_confirmed_at && (
        <p className="field-note">The Google identity must be created before an ERP activation can be resent.</p>
      )}
    </section>
  );
}
