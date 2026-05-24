// AI Agents — list registered agents, run them, watch the ReAct timeline.
import { useMemo, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Bot,
  Brain,
  Wrench,
  MessageSquare,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Play,
  ChevronRight,
  Settings as SettingsIcon,
} from 'lucide-react';
import clsx from 'clsx';

import { useProjectContextStore } from '@/stores/useProjectContextStore';
import { SkeletonCard } from '@/shared/ui';
import {
  aiAgentsApi,
  type AgentDescriptor,
  type AgentRun,
  type AgentStep,
  type AgentStepRole,
} from './api';

// ── Step role styling ──────────────────────────────────────────────────────

const ROLE_META: Record<
  AgentStepRole,
  { icon: typeof Brain; tone: string; labelKey: string; defaultLabel: string }
> = {
  thought: { icon: Brain, tone: 'text-violet-600', labelKey: 'agents.step.thought', defaultLabel: 'Thought' },
  tool_call: { icon: Wrench, tone: 'text-blue-600', labelKey: 'agents.step.tool_call', defaultLabel: 'Tool call' },
  observation: { icon: MessageSquare, tone: 'text-zinc-600', labelKey: 'agents.step.observation', defaultLabel: 'Observation' },
  answer: { icon: CheckCircle2, tone: 'text-emerald-600', labelKey: 'agents.step.answer', defaultLabel: 'Answer' },
  error: { icon: AlertCircle, tone: 'text-rose-600', labelKey: 'agents.step.error', defaultLabel: 'Error' },
};

// ── Page ───────────────────────────────────────────────────────────────────

export function AgentsPage(): JSX.Element {
  const { t } = useTranslation();
  const projectId = useProjectContextStore((s) => s.activeProjectId);
  const queryClient = useQueryClient();

  const [selected, setSelected] = useState<AgentDescriptor | null>(null);
  const [userInput, setUserInput] = useState('');
  const [activeRunId, setActiveRunId] = useState<string | null>(null);

  const agentsQuery = useQuery({
    queryKey: ['ai-agents', 'list'],
    queryFn: () => aiAgentsApi.listAgents(),
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

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-start gap-3">
        <div className="rounded-lg bg-violet-100 p-2 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300">
          <Bot className="h-6 w-6" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            {t('agents.title', 'AI Agents')}
          </h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            {t(
              'agents.subtitle',
              'Run autonomous AI agents that reason, call tools, and propose actions for your review.',
            )}
          </p>
        </div>
      </div>

      {/* LLM-provider banner — surfaces the most common failure cause
          (no_llm) upfront instead of letting the user write a prompt,
          hit Run, and stare at a cryptic "failed" row. */}
      {healthLoaded && !llmConfigured && (
        <div
          role="alert"
          aria-live="polite"
          aria-atomic="true"
          className="flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4 dark:border-amber-700 dark:bg-amber-900/20"
        >
          <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600 dark:text-amber-300" />
          <div className="flex-1 text-sm">
            <p className="font-semibold text-amber-900 dark:text-amber-100">
              {t('agents.no_llm_title', 'AI provider not configured')}
            </p>
            <p className="mt-1 text-amber-800 dark:text-amber-200">
              {t(
                'agents.no_llm_body',
                'Add an API key (Anthropic, OpenAI, Gemini, OpenRouter, …) in Settings → AI to run agents. Runs started without one fail immediately.',
              )}
            </p>
            <Link
              to={healthQuery.data?.settings_url ?? '/settings/ai'}
              className="mt-2 inline-flex items-center gap-1.5 rounded-md bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700"
            >
              <SettingsIcon className="h-3.5 w-3.5" />
              {t('agents.open_ai_settings', 'Open AI settings')}
            </Link>
          </div>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Agent catalogue */}
        <section className="space-y-3 lg:col-span-1">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">
            {t('agents.catalogue', 'Available agents')}
          </h2>
          {agentsQuery.isLoading && (
            <div className="space-y-2">
              <SkeletonCard />
              <SkeletonCard />
            </div>
          )}
          {!agentsQuery.isLoading && agents.length === 0 && (
            <div className="rounded-lg border border-dashed border-zinc-300 p-6 text-center text-sm text-zinc-500">
              {t('agents.empty', 'No agents registered.')}
            </div>
          )}
          {agents.map((a) => (
            <button
              key={a.name}
              type="button"
              onClick={() => {
                setSelected(a);
                setActiveRunId(null);
              }}
              className={clsx(
                'block w-full rounded-lg border p-4 text-left transition',
                selected?.name === a.name
                  ? 'border-violet-400 bg-violet-50 dark:bg-violet-900/20'
                  : 'border-zinc-200 hover:border-zinc-400 dark:border-zinc-700',
              )}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-zinc-900 dark:text-zinc-100">{a.name}</span>
                <ChevronRight className="h-4 w-4 text-zinc-400" />
              </div>
              <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">{a.description}</p>
              <div className="mt-2 flex flex-wrap gap-1">
                {a.allowed_tools.map((tool) => (
                  <span
                    key={tool}
                    className="rounded bg-zinc-100 px-2 py-0.5 text-[10px] font-mono text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                  >
                    {tool}
                  </span>
                ))}
              </div>
            </button>
          ))}
        </section>

        {/* New run + timeline */}
        <section className="space-y-4 lg:col-span-2">
          {!selected && (
            <div className="rounded-lg border border-dashed border-zinc-300 p-10 text-center text-sm text-zinc-500">
              {t('agents.pick_one', 'Select an agent on the left to start a new run.')}
            </div>
          )}

          {selected && (
            <>
              <form
                onSubmit={onSubmit}
                className="space-y-3 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-900"
              >
                <div>
                  <label
                    htmlFor="agent-input"
                    className="block text-xs font-semibold uppercase tracking-wide text-zinc-500"
                  >
                    {t('agents.new_run', 'New run')} · {selected.name}
                  </label>
                  <textarea
                    id="agent-input"
                    value={userInput}
                    onChange={(e) => setUserInput(e.target.value)}
                    rows={4}
                    placeholder={t(
                      'agents.input_placeholder',
                      'Describe what you want the agent to do…',
                    )}
                    className="mt-2 w-full rounded-md border border-zinc-300 px-3 py-2 text-sm text-zinc-900 focus:border-violet-400 focus:outline-none dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                  />
                </div>
                <div className="flex items-center justify-between gap-3 text-xs text-zinc-500">
                  <span>
                    {projectId
                      ? t('agents.project_attached', 'Run will be linked to active project.')
                      : t('agents.no_project', 'No active project — run will be global.')}
                  </span>
                  <button
                    type="submit"
                    disabled={
                      !userInput.trim() ||
                      startMutation.isPending ||
                      (healthLoaded && !llmConfigured)
                    }
                    title={
                      healthLoaded && !llmConfigured
                        ? t(
                            'agents.run_disabled_no_llm',
                            'Configure an AI provider in Settings → AI first.',
                          )
                        : undefined
                    }
                    aria-describedby={
                      healthLoaded && !llmConfigured ? 'agents-run-disabled-hint' : undefined
                    }
                    className={clsx(
                      'inline-flex items-center gap-2 rounded-md bg-violet-600 px-4 py-2 text-sm font-medium text-white transition',
                      'hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-zinc-400',
                      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400 focus-visible:ring-offset-2',
                    )}
                  >
                    {startMutation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Play className="h-4 w-4" />
                    )}
                    {t('agents.run', 'Run')}
                  </button>
                </div>
                {healthLoaded && !llmConfigured && (
                  <span id="agents-run-disabled-hint" className="sr-only">
                    {t(
                      'agents.run_disabled_no_llm',
                      'Configure an AI provider in Settings → AI first.',
                    )}
                  </span>
                )}
                {startMutation.isError && (
                  <div className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:bg-rose-900/20 dark:text-rose-300">
                    {t('agents.start_error', 'Failed to start the run.')}{' '}
                    {(startMutation.error as Error)?.message}
                  </div>
                )}
              </form>

              {/* Run timeline */}
              {activeRunId && run && <RunTimeline run={run} />}
            </>
          )}
        </section>
      </div>
    </div>
  );
}

// ── Run timeline component ─────────────────────────────────────────────────

function RunTimeline({ run }: { run: AgentRun }): JSX.Element {
  const { t } = useTranslation();
  const steps = useMemo(() => run.steps ?? [], [run.steps]);

  // Humanise the few backend failure_reason enum values we know about so
  // the user sees "AI provider not configured" instead of "no_llm". For
  // unknown enums, prefer the message from the last error step (which the
  // backend often fills with a user-friendly sentence, e.g. invalid key)
  // before falling back to the raw enum label.
  const failureLabel = (() => {
    if (!run.failure_reason) return null;
    switch (run.failure_reason) {
      case 'no_llm':
        return t(
          'agents.failure.no_llm',
          'AI provider not configured — add an API key in Settings → AI.',
        );
      case 'unknown_agent':
        return t('agents.failure.unknown_agent', 'Unknown agent registered.');
      case 'exception':
        return t('agents.failure.exception', 'Agent crashed during execution.');
      default: {
        const lastError = [...steps].reverse().find((s) => s.role === 'error');
        const msg =
          lastError && typeof lastError.content === 'object' && lastError.content
            ? (lastError.content as { message?: string }).message
            : undefined;
        return msg ?? run.failure_reason;
      }
    }
  })();

  return (
    <div className="space-y-4 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-900">
      <header className="flex items-center justify-between gap-3 text-sm">
        <div className="flex items-center gap-2">
          <span
            className={clsx(
              'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium',
              run.status === 'running' && 'bg-amber-100 text-amber-800',
              run.status === 'completed' && 'bg-emerald-100 text-emerald-800',
              run.status === 'failed' && 'bg-rose-100 text-rose-800',
            )}
          >
            {run.status === 'running' && <Loader2 className="h-3 w-3 animate-spin" />}
            {t(`agents.status.${run.status}`, run.status)}
          </span>
          <span className="text-xs text-zinc-500">
            {t('agents.iterations', 'Iterations')}: {run.iterations} ·{' '}
            {t('agents.tokens', 'Tokens')}: {run.total_tokens}
          </span>
        </div>
        {failureLabel && (
          <span className="text-right text-xs text-rose-600">{failureLabel}</span>
        )}
      </header>

      {run.failure_reason === 'no_llm' && (
        <Link
          to="/settings/ai"
          className="inline-flex items-center gap-1.5 self-start rounded-md bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700"
        >
          <SettingsIcon className="h-3.5 w-3.5" />
          {t('agents.open_ai_settings', 'Open AI settings')}
        </Link>
      )}

      {/* Steps timeline */}
      <ol className="space-y-3">
        {steps.length === 0 && (
          <li className="text-sm text-zinc-500">
            {t('agents.waiting', 'Waiting for the first step…')}
          </li>
        )}
        {steps.map((step) => (
          <StepRow key={step.id} step={step} />
        ))}
      </ol>

      {/* Final output */}
      {run.final_output && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm dark:border-emerald-700 dark:bg-emerald-900/20">
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-300">
            {t('agents.final_output', 'Final answer (review before applying)')}
          </div>
          <pre className="whitespace-pre-wrap text-sm text-zinc-800 dark:text-zinc-100">
            {run.final_output}
          </pre>
        </div>
      )}
    </div>
  );
}

function StepRow({ step }: { step: AgentStep }): JSX.Element {
  const { t } = useTranslation();
  const meta = ROLE_META[step.role] ?? ROLE_META.observation;
  const Icon = meta.icon;
  return (
    <li className="flex gap-3 border-l-2 border-zinc-200 pl-4 dark:border-zinc-700">
      <Icon className={clsx('mt-0.5 h-4 w-4 shrink-0', meta.tone)} />
      <div className="flex-1">
        <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">
          {t(meta.labelKey, meta.defaultLabel)} · #{step.step_idx}
        </div>
        <pre className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded bg-zinc-50 p-2 text-xs text-zinc-800 dark:bg-zinc-800 dark:text-zinc-100">
          {typeof step.content === 'string'
            ? step.content
            : JSON.stringify(step.content, null, 2)}
        </pre>
      </div>
    </li>
  );
}

export default AgentsPage;
