import { Check, FileSignature, Hourglass, Upload } from "lucide-react";
import { useState } from "react";
import type { OnboardingTask } from "./onboardingTypes";

export function OnboardingTaskAction({
  busy,
  onEvidence,
  onSignature,
  task,
}: {
  busy: boolean;
  onEvidence(task: OnboardingTask, file: File): Promise<void>;
  onSignature(task: OnboardingTask, typedName: string): Promise<void>;
  task: OnboardingTask;
}) {
  const [typedName, setTypedName] = useState("");
  const [accepted, setAccepted] = useState(false);
  const canSubmit = ["pending", "rejected"].includes(task.status);

  if (task.status === "completed") {
    return (
      <div className="task-state task-state-complete">
        <Check aria-hidden="true" />
        <span>Reviewed and complete</span>
      </div>
    );
  }
  if (task.status === "not_applicable") {
    return <div className="task-state">Qualified review marked this item not applicable.</div>;
  }
  if (task.status === "blocked") {
    return (
      <div className="task-state">
        <Hourglass aria-hidden="true" />
        <span>Waiting for a qualified applicability decision</span>
      </div>
    );
  }
  if (task.status === "submitted") {
    return (
      <div className="task-state">
        <Hourglass aria-hidden="true" />
        <span>Submitted for Benson review</span>
      </div>
    );
  }
  if (task.completion_method === "document_upload" && canSubmit) {
    return (
      <label className="upload-control">
        <Upload aria-hidden="true" />
        {busy ? "Encrypting…" : task.status === "rejected" ? "Upload corrected evidence" : "Upload evidence"}
        <input
          accept="application/pdf,image/jpeg,image/png,image/webp"
          disabled={busy}
          type="file"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void onEvidence(task, file);
            event.target.value = "";
          }}
        />
      </label>
    );
  }
  if (task.completion_method === "employee_signature" && canSubmit) {
    return (
      <form
        className="signature-control"
        onSubmit={(event) => {
          event.preventDefault();
          if (accepted && typedName.trim()) void onSignature(task, typedName.trim());
        }}
      >
        <p>{task.signature_statement || "Review the company acknowledgement before signing."}</p>
        <label>
          Typed legal name
          <input
            autoComplete="name"
            disabled={busy}
            required
            value={typedName}
            onChange={(event) => setTypedName(event.target.value)}
          />
        </label>
        <label className="signature-acceptance">
          <input
            checked={accepted}
            disabled={busy}
            required
            type="checkbox"
            onChange={(event) => setAccepted(event.target.checked)}
          />
          <span>I agree to this company acknowledgement.</span>
        </label>
        <button disabled={busy || !accepted || !typedName.trim()} type="submit">
          <FileSignature aria-hidden="true" /> {busy ? "Signing…" : "Sign acknowledgement"}
        </button>
      </form>
    );
  }
  if (task.completion_method === "employer_evidence") {
    return <div className="task-state">Benson HR or an authorized administrator must add this evidence.</div>;
  }
  return <div className="task-state">Benson HR must review and complete this item.</div>;
}
