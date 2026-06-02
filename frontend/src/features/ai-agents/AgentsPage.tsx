// AI Agents — gallery of registered agents, run them, watch the ReAct timeline.
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Bot,
  AlertCircle,
  Loader2,
  Play,
  Settings as SettingsIcon,
  History,
  Sparkles,
  MessageSquarePlus,
} from 'lucide-react';
import clsx from 'clsx';

import { useProjectContextStore } from '@/stores/useProjectContextStore';
import { SkeletonCard, EmptyState } from '@/shared/ui';
import { aiAgentsApi, type AgentDescriptor, type AgentRun } from './api';
import { AgentGallery } from './components/AgentGallery';
import { RunTimeline } from './components/RunTimeline';
import { RecentRunsList } from './components/RecentRunsList';
import {
  agentDisplayName,
  agentTagline,
  resolveAgentIcon,
} from './components/agentMeta';

// ── Page ───────────────────────────────────────────────────────────────────

export function AgentsPage(): JSX.Element {
  const { t } = useTranslation();
  const projectId = useProjectContextStore((s) => s.activeProjectId);
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();

  const [selected, setSelected] = useState<AgentDescriptor | null>(null);
  const [userInput, setUserInput] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);
  // The active run is mirrored into the URL (?run=<id>) so a reload or a
  // shared link re-attaches to the same run (and its live poll) instead of
  // orphaning it. The URL is the source of truth.
  const activeRunId = searchParams.get('run');

  const setActiveRunId = (runId: string | null) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (runId) next.set('run', runId);
        else next.delete('run');
        return next;
      },
      { replace: true },
    );
  };

  const agentsQuery = useQuery({
    queryKey: ['ai-agents', 'list'],
    queryFn: () => aiAgentsApi.listAgents(),
  });

  const runsQuery = useQuery({
    queryKey: ['ai-agents', 'runs', projectId ?? null],
    queryFn: () => aiAgentsApi.listRuns(projectId ?? undefined),
    // Keep the history fresh while a run is in flight so a just-finished
    // run flips to its terminal status without a manual refresh.
    refetchInterval: 5000,
  });

  const healthQuery = useQuery({
    queryKey: ['ai-agents', 'health'],
    queryFn: () => aiAgentsApi.health(),
    // 30 s — long enough to avoid hammering, short enough that fixing
    // /settings/ai and tabbing back updates the banner promptly.
    staleTime: 30_000,
  });
  const llmConfigured = healthQuery.data?.llm_configured ?? true;
  const healthLoaded = healthQuery.isSuccess;

  const runQuery = useQuery({
    queryKey: ['ai-agents', 'run', activeRunId],
    queryFn: () => aiAgentsApi.getRun(activeRunId!),
    enabled: !!activeRunId,
    refetchInterval: (q) => {
      const run = q.state.data as AgentRun | undefined;
      return run && run.status === 'running' ? 2000 : false;
    },
  });

  const startMutation = useMutation({
    mutationFn: () =>
      aiAgentsApi.startRun({
        agent_name: selected!.name,
        project_id: projectId ?? undefined,
        user_input: userInput.trim(),
      }),
    onSuccess: (run) => {
      setActiveRunId(run.id);
      queryClient.invalidateQueries({ queryKey: ['ai-agents', 'runs'] });
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!selected || !userInput.trim()) return;
    startMutation.mutate();
  };

  const agents = agentsQuery.data ?? [];
  const run = runQuery.data;
  const runs = runsQuery.data ?? [];

  // Select an agent and (optionally) seed the prompt input, then focus it.
  const selectAgent = (agent: AgentDescriptor, prompt?: string) => {
    setSelected(agent);
    setActiveRunId(null);
    if (prompt !== undefined) {
      setUserInput(prompt);
      // Focus + place caret at the end after React commits the value.
      requestAnimationFrame(() => {
        const el = inputRef.current;
        if (el) {
          el.focus();
          el.selectionStart = el.selectionEnd = el.value.length;
        }
      });
    }
  };

  // When a run is loaded from the URL (reload / shared link) and the user
  // hasn't picked an agent yet, reflect the run's agent in the catalogue so
  // the timeline isn't hidden behind the placeholder.
  useEffect(() => {
    if (!run || selected) return;
    const match = agents.find((a) => a.name === run.agent_name);
    if (match) setSelected(match);
  }, [run, selected, agents]);

  const runDisabledNoLlm = healthLoaded && !llmConfigured;
  const SelectedIcon = selected ? resolveAgentIcon(selected.icon) : Sparkles;
  const selectedPrompts = (selected?.example_prompts ?? []).filter((p) => p.trim().length > 0);

  return (
    <div className="mx-auto max-w-content space-y-6 p-6">
      {/* Header */}
      <div className="flex items-start gap-3">
        <div className="rounded-lg bg-oe-blue-subtle p-2 text-oe-blue-text dark:bg-oe-blue/15">
          <Bot className="h-6 w-6" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold text-content-primary">
            {t('agents.title', { defaultValue: 'AI Agents' })}
          </h1>
          <p className="mt-1 text-sm text-content-secondary">
            {t('agents.subtitle', {
              defaultValue:
                'Run autonomous AI agents that reason, call tools, and propose actions for your review.',
            })}
          </p>
        </div>
      </div>

      {/* LLM-provider banner — surfaces the most common failure cause
          (no_llm) upfront instead of letting the user write a prompt,
          hit Run, and stare at a cryptic "failed" row. */}
      {runDisabledNoLlm && (
        <div
          role="alert"
          aria-live="polite"
          aria-atomic="true"
          className="flex items-start gap-3 rounded-xl border border-semantic-warning/40 bg-semantic-warning-bg p-4"
        >
          <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-semantic-warning" />
          <div className="flex-1 text-sm">
            <p className="font-semibold text-content-primary">
              {t('agents.no_llm_title', { defaultValue: 'AI provider not configured' })}
            </p>
            <p className="mt-1 text-content-secondary">
              {t('agents.no_llm_body', {
                defaultValue:
                  'Add an API key (Anthropic, OpenAI, Gemini, OpenRouter, …) in Settings → AI to run agents. Runs started without one fail immediately.',
              })}
            </p>
            <Link
              to={healthQuery.data?.settings_url ?? '/settings?tab=ai'}
              className="mt-2 inline-flex items-center gap-1.5 rounded-md bg-semantic-warning px-3 py-1.5 text-xs font-semibold text-content-inverse hover:opacity-90"
            >
              <SettingsIcon className="h-3.5 w-3.5" />
              {t('agents.open_ai_settings', { defaultValue: 'Open AI settings' })}
            </Link>
          </div>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Main column — gallery + run console */}
        <div className="space-y-6 lg:col-span-2">
          {/* Run console (only once an agent is picked) */}
          {selected && (
            <form
              onSubmit={onSubmit}
              className="space-y-3 rounded-xl border border-border-light bg-surface-elevated p-4 shadow-xs"
            >
              <div className="flex items-center gap-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-oe-blue-subtle text-oe-blue-text">
                  <SelectedIcon className="h-4 w-4" />
                </span>
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-content-primary">
                    {agentDisplayName(selected.name, selected.display_name)}
                  </div>
                  {agentTagline(selected.tagline, selected.description) && (
                    <div className="truncate text-xs text-content-tertiary">
                      {agentTagline(selected.tagline, selected.description)}
                    </div>
                  )}
                </div>
              </div>

              <div>
                <label htmlFor="agent-input" className="sr-only">
                  {t('agents.new_run', { defaultValue: 'New run' })}
                </label>
                <textarea
                  id="agent-input"
                  ref={inputRef}
                  value={userInput}
                  onChange={(e) => setUserInput(e.target.value)}
                  rows={4}
                  placeholder={t('agents.input_placeholder', {
                    defaultValue: 'Describe what you want the agent to do…',
                  })}
                  className="w-full rounded-lg border border-border bg-surface-primary px-3 py-2 text-sm text-content-primary placeholder:text-content-tertiary focus:border-oe-blue focus:outline-none focus:ring-2 focus:ring-oe-blue/20"
                />
              </div>

              {/* Example-prompt chips for the selected agent — never a bare box. */}
              {selectedPrompts.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-2xs font-semibold uppercase tracking-wide text-content-tertiary">
                    {t('agents.try_asking', { defaultValue: 'Try asking' })}
                  </span>
                  {selectedPrompts.map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      onClick={() => selectAgent(selected, prompt)}
                      className="rounded-lg border border-border-light bg-surface-secondary/60 px-2.5 py-1 text-xs text-content-secondary transition-colors hover:border-oe-blue/40 hover:bg-oe-blue-subtle hover:text-oe-blue-text"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              )}

              <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-content-tertiary">
                <span>
                  {projectId
                    ? t('agents.project_attached', {
                        defaultValue: 'Run will be linked to active project.',
                      })
                    : t('agents.no_project', {
                        defaultValue: 'No active project — run will be global.',
                      })}
                </span>
                <button
                  type="submit"
                  disabled={!userInput.trim() || startMutation.isPending || runDisabledNoLlm}
                  title={
                    runDisabledNoLlm
                      ? t('agents.run_disabled_no_llm', {
                          defaultValue: 'Configure an AI provider in Settings → AI first.',
                        })
                      : undefined
                  }
                  aria-describedby={runDisabledNoLlm ? 'agents-run-disabled-hint' : undefined}
                  className={clsx(
                    'inline-flex items-center gap-2 rounded-lg bg-oe-blue px-4 py-2 text-sm font-medium text-content-inverse transition-all',
                    'hover:bg-oe-blue-hover disabled:cursor-not-allowed disabled:opacity-40',
                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue focus-visible:ring-offset-2',
                  )}
                >
                  {startMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4" />
                  )}
                  {t('agents.run', { defaultValue: 'Run agent' })}
                </button>
              </div>
              {runDisabledNoLlm && (
                <span id="agents-run-disabled-hint" className="sr-only">
                  {t('agents.run_disabled_no_llm', {
                    defaultValue: 'Configure an AI provider in Settings → AI first.',
                  })}
                </span>
              )}
              {startMutation.isError && (
                <div className="rounded-md bg-semantic-error-bg px-3 py-2 text-xs text-semantic-error">
                  {t('agents.start_error', { defaultValue: 'Failed to start the run.' })}{' '}
                  {(startMutation.error as Error)?.message}
                </div>
              )}
            </form>
          )}

          {/* Run timeline — rendered whenever a run is active, even if the
              run's agent is no longer in the catalogue (so a reload of an
              old run still shows its result). */}
          {activeRunId && runQuery.isLoading && !run && <SkeletonCard />}
          {activeRunId && runQuery.isError && (
            <div className="rounded-xl border border-semantic-error/30 bg-semantic-error-bg p-4 text-sm text-semantic-error">
              {t('agents.run_load_error', { defaultValue: 'Could not load this run.' })}
            </div>
          )}
          {activeRunId && run && <RunTimeline run={run} />}

          {/* Gallery */}
          <section className="space-y-4">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-content-tertiary">
              {selected
                ? t('agents.switch_agent', { defaultValue: 'Switch agent' })
                : t('agents.catalogue', { defaultValue: 'Choose an agent to get started' })}
            </h2>

            {agentsQuery.isLoading && (
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                <SkeletonCard />
                <SkeletonCard />
                <SkeletonCard />
              </div>
            )}

            {!agentsQuery.isLoading && agents.length === 0 && (
              <EmptyState
                icon={<Sparkles className="h-6 w-6" />}
                title={t('agents.empty_title', { defaultValue: 'No agents available yet' })}
                description={t('agents.empty_body', {
                  defaultValue:
                    'AI agents are installed with their modules. Once a module that ships an agent is enabled, it will appear here ready to run.',
                })}
              />
            )}

            {!agentsQuery.isLoading && agents.length > 0 && (
              <AgentGallery
                agents={agents}
                selectedName={selected?.name ?? null}
                onSelect={(agent) => selectAgent(agent)}
                onPromptPick={(agent, prompt) => selectAgent(agent, prompt)}
              />
            )}
          </section>
        </div>

        {/* Recent runs — lets the user reattach to an in-flight run after a
            reload, or revisit a finished run's timeline. */}
        <aside className="space-y-3 lg:col-span-1">
          <h2 className="flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wide text-content-tertiary">
            <History className="h-4 w-4" />
            {t('agents.recent_runs', { defaultValue: 'Recent runs' })}
          </h2>
          {runsQuery.isLoading && (
            <div className="space-y-2">
              <SkeletonCard />
              <SkeletonCard />
            </div>
          )}
          {!runsQuery.isLoading && runs.length === 0 && (
            <div className="rounded-xl border border-dashed border-border-light bg-surface-secondary/30 p-6 text-center">
              <MessageSquarePlus className="mx-auto h-6 w-6 text-content-tertiary" />
              <p className="mt-2 text-sm font-medium text-content-secondary">
                {t('agents.no_runs_title', { defaultValue: 'No runs yet' })}
              </p>
              <p className="mt-1 text-xs text-content-tertiary">
                {t('agents.no_runs_body', {
                  defaultValue: 'Pick an agent and run it — your runs will show up here.',
                })}
              </p>
            </div>
          )}
          {!runsQuery.isLoading && runs.length > 0 && (
            <RecentRunsList
              runs={runs}
              agents={agents}
              activeRunId={activeRunId}
              onSelect={(id) => setActiveRunId(id)}
            />
          )}
        </aside>
      </div>
    </div>
  );
}

export default AgentsPage;
