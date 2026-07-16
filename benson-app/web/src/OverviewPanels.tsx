import { CalendarDays, Hammer, Sparkles } from "lucide-react";
import { Empty, Panel } from "./SharedUi";

export function OverviewAgent() {
  return (
    <section className="panel agent overview-agent">
      <div className="agent-head">
        <Sparkles />
        <div>
          <h2>Benson Assistant</h2>
          <p>Free Claude Code gateway · reviewed construction skills</p>
        </div>
      </div>
      <p>Select a lead to draft a fact-scoped summary, next steps, or reviewed construction analysis.</p>
      <div className="prompts">
        <button disabled title="Select a lead first">
          Summarize new leads
        </button>
        <button disabled title="Select a lead first">
          Review estimate risks
        </button>
        <button disabled title="Select a lead first">
          Draft daily report
        </button>
      </div>
      <div className="ask">
        <input aria-label="Ask Benson Assistant" placeholder="Ask about your operations…" />
        <button disabled title="Select a lead first">
          Ask
        </button>
      </div>
    </section>
  );
}

export function DeferredPanels() {
  return (
    <>
      <Panel title="Today’s schedule" subtitle="Field visits and committed work." link="Coming later">
        <Empty
          icon={<CalendarDays />}
          title="Schedule is outside launch scope"
          body="The lead foundation does not schedule field work yet."
          compact
        />
      </Panel>
      <Panel title="Active jobs" subtitle="Current residential work." link="Coming later">
        <Empty
          icon={<Hammer />}
          title="Jobs are outside launch scope"
          body="Qualified leads stay in the lead queue for this release."
          compact
        />
      </Panel>
    </>
  );
}
