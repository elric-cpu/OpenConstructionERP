import { UserRound } from "lucide-react";
import { formatDate } from "./formatters";
import type { Note } from "./types";

export function LeadNotesPanel({
  busy,
  note,
  notes,
  save,
  setNote,
}: {
  busy: boolean;
  note: string;
  notes: Note[];
  save(change: Record<string, string>): void;
  setNote(value: string): void;
}) {
  return (
    <section className="workspace-card">
      <div className="card-heading">
        <div>
          <small>STAFF RECORD</small>
          <h2>Notes</h2>
        </div>
        <UserRound />
      </div>
      <form
        className="note-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (note.trim()) save({ note });
        }}
      >
        <textarea
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Add a factual call note, measurement, or next step…"
          aria-label="New lead note"
        />
        <button className="primary" disabled={!note.trim() || busy}>
          {busy ? "Saving…" : "Add note"}
        </button>
      </form>
      <div className="note-list">
        {notes.map((item) => (
          <article key={item.id}>
            <p>{item.body}</p>
            <small>
              {item.author} · {formatDate(item.created_at)}
            </small>
          </article>
        ))}
        {!notes.length && <p className="quiet">No staff notes yet.</p>}
      </div>
    </section>
  );
}
