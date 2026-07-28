import { FileLock2, RefreshCw, ShieldAlert } from "lucide-react";
import type { CSSProperties } from "react";
import { OnboardingTaskAction } from "./OnboardingTaskAction";
import type { OnboardingDocument, OnboardingSignature, OnboardingTask } from "./onboardingTypes";
import { useEmployeeOnboarding } from "./useEmployeeOnboarding";

function TaskEvidence({
  documents,
  onOpen,
  signatures,
}: {
  documents: OnboardingDocument[];
  onOpen(document: OnboardingDocument): Promise<void>;
  signatures: OnboardingSignature[];
}) {
  if (!documents.length && !signatures.length) return null;
  return (
    <div className="task-documents">
      {documents.map((document) => (
        <button key={document.id} type="button" onClick={() => void onOpen(document)}>
          <FileLock2 aria-hidden="true" /> {document.original_name} <small>v{document.version}</small>
        </button>
      ))}
      {signatures.map((signature) => (
        <span className="signature-record" key={signature.id}>
          Signed by {signature.typed_name} · v{signature.version}
        </span>
      ))}
    </div>
  );
}

function TaskCard({
  busy,
  documents,
  index,
  onEvidence,
  onOpen,
  onSignature,
  signatures,
  task,
}: {
  busy: boolean;
  documents: OnboardingDocument[];
  index: number;
  onEvidence(task: OnboardingTask, file: File): Promise<void>;
  onOpen(document: OnboardingDocument): Promise<void>;
  onSignature(task: OnboardingTask, typedName: string): Promise<void>;
  signatures: OnboardingSignature[];
  task: OnboardingTask;
}) {
  return (
    <article className="employee-task-card">
      <div className="task-number">{String(index + 1).padStart(2, "0")}</div>
      <div className="task-copy">
        <div className="task-line">
          <h2>{task.label}</h2>
          <span className={`task-status status-${task.status}`}>{task.status.replace("_", " ")}</span>
        </div>
        <p>{task.instructions}</p>
        {task.official_source.startsWith("https://") && (
          <a className="official-form-link" href={task.official_source} rel="noreferrer" target="_blank">
            Open official form or instructions
          </a>
        )}
        {task.latest_rejection_reason && (
          <p className="rejection-reason">
            <strong>Correction requested:</strong> {task.latest_rejection_reason}
          </p>
        )}
        <small>
          Due {task.due_date} · {task.applicability_reason}
        </small>
        <TaskEvidence documents={documents} onOpen={onOpen} signatures={signatures} />
      </div>
      <div className="task-action">
        <OnboardingTaskAction busy={busy} onEvidence={onEvidence} onSignature={onSignature} task={task} />
      </div>
    </article>
  );
}

export function EmployeeOnboardingWorkspace({ credential }: { credential: string }) {
  const onboarding = useEmployeeOnboarding(credential);
  const complete = onboarding.tasks.filter((task) => ["completed", "not_applicable"].includes(task.status)).length;
  const progress = onboarding.tasks.length ? Math.round((complete / onboarding.tasks.length) * 100) : 0;
  return (
    <section className="tasks-workspace" aria-busy={onboarding.loading}>
      <div className="task-hero">
        <div>
          <div className="section-kicker">EMPLOYEE TASKS</div>
          <h1>Welcome, {onboarding.employeeName.split(" ")[0] || "team member"}.</h1>
          <p>Complete each applicable item. Protected evidence is encrypted and access-audited.</p>
        </div>
        <div className="progress-dial" style={{ "--progress": `${progress * 3.6}deg` } as CSSProperties}>
          <strong>{progress}%</strong>
          <small>
            {complete} of {onboarding.tasks.length}
          </small>
        </div>
      </div>
      <div className="security-note">
        <ShieldAlert aria-hidden="true" /> Identity, tax, banking, medical/disability, and veteran records have stricter
        access controls.
      </div>
      {onboarding.error && (
        <div className="onboarding-error" aria-live="polite">
          <p className="form-error">{onboarding.error}</p>
          <button type="button" onClick={() => void onboarding.refresh()}>
            <RefreshCw aria-hidden="true" /> Retry
          </button>
        </div>
      )}
      <div className="employee-task-list">
        {onboarding.tasks.map((task, index) => (
          <TaskCard
            busy={onboarding.busy === task.id}
            documents={onboarding.documents.filter((document) => document.task_id === task.id)}
            index={index}
            key={task.id}
            onEvidence={onboarding.uploadEvidence}
            onOpen={onboarding.openDocument}
            onSignature={onboarding.submitSignature}
            signatures={onboarding.signatures.filter((signature) => signature.task_id === task.id)}
            task={task}
          />
        ))}
      </div>
    </section>
  );
}
