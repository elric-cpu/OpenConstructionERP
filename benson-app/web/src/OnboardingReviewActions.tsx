import { useState } from "react";
import type { ApplicabilityReviewInput, OnboardingTask, TaskReviewInput } from "./onboardingTypes";

function ApplicabilityReview({
  busy,
  onReview,
  task,
}: {
  busy: boolean;
  onReview(review: ApplicabilityReviewInput): Promise<void>;
  task: OnboardingTask;
}) {
  const [comment, setComment] = useState("");
  const [name, setName] = useState("");
  const [qualification, setQualification] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const submit = (decision: "applicable" | "not_applicable") => {
    if (!comment.trim() || !name.trim() || !qualification.trim() || !confirmed) return;
    void onReview({
      expected_version: task.version,
      decision,
      comment: comment.trim(),
      reviewer_name: name.trim(),
      reviewer_qualification: qualification.trim(),
      legal_review_confirmed: true,
    });
  };
  return (
    <div className="applicability-review">
      <strong>Qualified applicability review</strong>
      <label>
        Decision reason
        <textarea required value={comment} onChange={(event) => setComment(event.target.value)} />
      </label>
      <div className="reviewer-grid">
        <label>
          Reviewer name
          <input required value={name} onChange={(event) => setName(event.target.value)} />
        </label>
        <label>
          Qualification
          <input required value={qualification} onChange={(event) => setQualification(event.target.value)} />
        </label>
      </div>
      <label className="review-confirmation">
        <input checked={confirmed} type="checkbox" onChange={(event) => setConfirmed(event.target.checked)} />
        <span>I confirm I am authorized to make this applicability decision.</span>
      </label>
      <div className="review-actions">
        <button disabled={busy || !confirmed} type="button" onClick={() => submit("applicable")}>
          Applies
        </button>
        <button disabled={busy || !confirmed} type="button" onClick={() => submit("not_applicable")}>
          Does not apply
        </button>
      </div>
    </div>
  );
}

export function OnboardingReviewActions({
  busy,
  onApplicability,
  onTaskReview,
  task,
}: {
  busy: boolean;
  onApplicability(review: ApplicabilityReviewInput): Promise<void>;
  onTaskReview(review: TaskReviewInput): Promise<void>;
  task: OnboardingTask;
}) {
  const [comment, setComment] = useState("");
  if (task.applicability_status === "pending_review") {
    return <ApplicabilityReview busy={busy} onReview={onApplicability} task={task} />;
  }
  if (task.status !== "submitted") return null;
  const submit = (decision: "complete" | "reject") => {
    if (!comment.trim()) return;
    void onTaskReview({ expected_version: task.version, decision, comment: comment.trim() });
  };
  return (
    <div className="task-review-control">
      <label>
        Review note
        <textarea
          placeholder="Required for approval or rejection"
          required
          value={comment}
          onChange={(event) => setComment(event.target.value)}
        />
      </label>
      <div className="review-actions">
        <button disabled={busy || !comment.trim()} type="button" onClick={() => submit("complete")}>
          Approve evidence
        </button>
        <button disabled={busy || !comment.trim()} type="button" onClick={() => submit("reject")}>
          Reject with reason
        </button>
      </div>
    </div>
  );
}
