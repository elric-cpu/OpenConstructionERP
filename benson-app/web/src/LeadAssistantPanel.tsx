import { LoaderCircle, Send, Sparkles } from "lucide-react";
import type { Skill } from "./types";

export function LeadAssistantPanel({
  busy,
  draft,
  prompt,
  skillId,
  skills,
  runDraft,
  setPrompt,
  setSkillId,
}: {
  busy: boolean;
  draft: string;
  prompt: string;
  skillId: string;
  skills: Skill[];
  runDraft(): void;
  setPrompt(value: string): void;
  setSkillId(value: string): void;
}) {
  return (
    <section className="workspace-card lead-agent">
      <div className="agent-head">
        <Sparkles />
        <div>
          <small>LEAD-SCOPED AI</small>
          <h2>Benson Assistant</h2>
        </div>
      </div>
      <p>Drafts use only this lead’s supplied facts. No record or message is changed without staff action.</p>
      <label>
        Reviewed skill
        <select value={skillId} onChange={(event) => setSkillId(event.target.value)}>
          {skills.map((skill) => (
            <option key={skill.id} value={skill.id}>
              {skill.label}
            </option>
          ))}
        </select>
      </label>
      <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} aria-label="Lead assistant prompt" />
      <button className="agent-button" disabled={busy || !prompt.trim()} onClick={runDraft}>
        {busy ? (
          <>
            <LoaderCircle className="spin" /> Drafting…
          </>
        ) : (
          <>
            <Send /> Create draft
          </>
        )}
      </button>
      {draft && (
        <div className="draft-output">
          <small>REVIEWABLE DRAFT</small>
          <p>{draft}</p>
        </div>
      )}
    </section>
  );
}
