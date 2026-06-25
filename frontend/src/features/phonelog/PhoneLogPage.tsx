// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Phone Log - capture a phone call, voice note, or verbal instruction so it is
// on the project record before it is disputed. The quick-entry form takes a
// free-form capture (who was on the call, which way it went, when, how long,
// and what was said); the server normalizes it and the list below shows the
// resulting dispute-ready record: direction and channel, the parties, a short
// summary, and the instruction-bearing sentences pulled out of the transcript.

import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Phone, Users, Mic, MessageSquare, Clock, ListChecks, Inbox } from 'lucide-react';
import { Card, Badge, EmptyState, SkeletonTable, DismissibleInfo } from '@/shared/ui';
import { getErrorMessage } from '@/shared/lib/api';
import { useProjectContextStore } from '@/stores/useProjectContextStore';
import { listPhoneLogs, createPhoneLog } from './api';
import type { PhoneChannel, PhoneDirection, PhoneLog } from './types';

type BadgeVariant = 'neutral' | 'blue' | 'success' | 'warning' | 'error';

const DIRECTION_VARIANT: Record<PhoneDirection, BadgeVariant> = {
  inbound: 'blue',
  outbound: 'success',
  internal: 'neutral',
  unknown: 'neutral',
};

const CHANNEL_VARIANT: Record<PhoneChannel, BadgeVariant> = {
  phone: 'neutral',
  voice_note: 'warning',
  chat: 'blue',
  other: 'neutral',
};

// The canonical values the form submits. The server also accepts informal
// synonyms, but the picker offers the clean set so the stored value is exact.
const DIRECTIONS: PhoneDirection[] = ['inbound', 'outbound', 'internal'];
const CHANNELS: PhoneChannel[] = ['phone', 'voice_note', 'chat'];

interface FormState {
  raw_parties: string;
  direction: PhoneDirection;
  channel: PhoneChannel;
  started_at: string;
  duration_minutes: string;
  transcript: string;
  summary: string;
}

const EMPTY_FORM: FormState = {
  raw_parties: '',
  direction: 'inbound',
  channel: 'phone',
  started_at: '',
  duration_minutes: '',
  transcript: '',
  summary: '',
};

function directionLabel(t: (k: string, o: { defaultValue: string }) => string, d: PhoneDirection): string {
  return t(`phonelog.direction_${d}`, {
    defaultValue: { inbound: 'Inbound', outbound: 'Outbound', internal: 'Internal', unknown: 'Unknown' }[d],
  });
}

function channelLabel(t: (k: string, o: { defaultValue: string }) => string, c: PhoneChannel): string {
  return t(`phonelog.channel_${c}`, {
    defaultValue: { phone: 'Phone call', voice_note: 'Voice note', chat: 'Chat', other: 'Other' }[c],
  });
}

function formatDuration(seconds: number | null): string {
  if (seconds == null || seconds <= 0) return '-';
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins === 0) return `${secs}s`;
  return secs === 0 ? `${mins}m` : `${mins}m ${secs}s`;
}

function PhoneLogCard({ log }: { log: PhoneLog }) {
  const { t } = useTranslation();
  return (
    <Card className="space-y-2 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={DIRECTION_VARIANT[log.direction]}>{directionLabel(t, log.direction)}</Badge>
        <Badge variant={CHANNEL_VARIANT[log.channel]}>{channelLabel(t, log.channel)}</Badge>
        {log.occurred_at && (
          <span className="text-xs text-content-tertiary">{log.occurred_at.replace('T', ' ')}</span>
        )}
        <span className="ms-auto inline-flex items-center gap-1 text-xs text-content-tertiary">
          <Clock className="h-3.5 w-3.5" />
          {formatDuration(log.duration_seconds)}
        </span>
      </div>

      {log.parties.length > 0 && (
        <div className="flex items-center gap-1.5 text-sm text-content-secondary">
          <Users className="h-4 w-4 shrink-0 text-content-tertiary" />
          <span>{log.parties.join(', ')}</span>
        </div>
      )}

      {log.summary && <p className="text-sm font-medium text-content-primary">{log.summary}</p>}

      {log.instructions.length > 0 && (
        <div className="space-y-1">
          <div className="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wide text-content-tertiary">
            <ListChecks className="h-3.5 w-3.5" />
            {t('phonelog.instructions', { defaultValue: 'Instructions captured' })}
          </div>
          <ul className="space-y-1">
            {log.instructions.map((line, i) => (
              <li
                key={i}
                className="rounded-md border-s-2 border-oe-blue/50 bg-surface-secondary px-2 py-1 text-sm text-content-secondary"
              >
                {line}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

export function PhoneLogPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { projectId: routeProjectId } = useParams();
  const activeProjectId = useProjectContextStore((s) => s.activeProjectId);
  const projectId = routeProjectId ?? activeProjectId ?? '';

  const [form, setForm] = useState<FormState>(EMPTY_FORM);

  const logsQuery = useQuery({
    queryKey: ['phonelog', 'list', projectId],
    queryFn: () => listPhoneLogs(projectId),
    enabled: !!projectId,
    retry: false,
    staleTime: 30_000,
  });

  const createMutation = useMutation({
    mutationFn: () => {
      const minutes = parseFloat(form.duration_minutes);
      return createPhoneLog({
        project_id: projectId,
        raw_parties: form.raw_parties,
        direction: form.direction,
        channel: form.channel,
        started_at: form.started_at || null,
        duration_seconds: Number.isFinite(minutes) && minutes > 0 ? Math.round(minutes * 60) : null,
        transcript: form.transcript,
        summary: form.summary,
      });
    },
    onSuccess: () => {
      setForm(EMPTY_FORM);
      void queryClient.invalidateQueries({ queryKey: ['phonelog', 'list', projectId] });
    },
  });

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const canSubmit = !!projectId && (form.transcript.trim() !== '' || form.summary.trim() !== '');

  if (!projectId) {
    return (
      <div className="p-4">
        <EmptyState
          icon={<Phone className="h-6 w-6" />}
          title={t('phonelog.no_project_title', { defaultValue: 'No project selected' })}
          description={t('phonelog.no_project_desc', {
            defaultValue: 'Select a project to capture and review its phone calls and verbal instructions.',
          })}
        />
      </div>
    );
  }

  return (
    <div className="space-y-4 p-1">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-content-primary">
          <Phone className="h-5 w-5" />
          {t('phonelog.title', { defaultValue: 'Phone Log' })}
        </h1>
        <p className="mt-1 text-sm text-content-secondary">
          {t('phonelog.subtitle', {
            defaultValue: 'Put a phoned, spoken, or chatted instruction on the record before it is disputed.',
          })}
        </p>
      </div>

      <DismissibleInfo
        storageKey="phonelog-intro"
        title={t('phonelog.intro_title', { defaultValue: 'Why log a call' })}
      >
        {t('phonelog.intro_body', {
          defaultValue:
            'Verbal instructions given on site or over the phone routinely go unrecorded and are then disputed weeks later. Capturing the call here turns it into a searchable record - who was on it, which way it went, and the instruction-bearing sentences pulled out of what was said.',
        })}
      </DismissibleInfo>

      <Card className="space-y-3 p-4">
        <h2 className="text-sm font-semibold text-content-primary">
          {t('phonelog.capture', { defaultValue: 'Capture a call' })}
        </h2>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-sm text-content-secondary">
            {t('phonelog.parties', { defaultValue: 'Parties' })}
            <input
              value={form.raw_parties}
              onChange={(e) => set('raw_parties', e.target.value)}
              placeholder={t('phonelog.parties_ph', { defaultValue: 'You -> Acme site office' })}
              className="rounded-md border border-border-light bg-surface-primary px-2 py-1 text-sm text-content-primary"
            />
          </label>

          <label className="flex flex-col gap-1 text-sm text-content-secondary">
            {t('phonelog.when', { defaultValue: 'When' })}
            <input
              type="datetime-local"
              value={form.started_at}
              onChange={(e) => set('started_at', e.target.value)}
              className="rounded-md border border-border-light bg-surface-primary px-2 py-1 text-sm text-content-primary"
            />
          </label>

          <label className="flex flex-col gap-1 text-sm text-content-secondary">
            {t('phonelog.direction', { defaultValue: 'Direction' })}
            <select
              value={form.direction}
              onChange={(e) => set('direction', e.target.value as PhoneDirection)}
              className="rounded-md border border-border-light bg-surface-primary px-2 py-1 text-sm text-content-primary"
            >
              {DIRECTIONS.map((d) => (
                <option key={d} value={d}>
                  {directionLabel(t, d)}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-sm text-content-secondary">
            {t('phonelog.channel', { defaultValue: 'Channel' })}
            <select
              value={form.channel}
              onChange={(e) => set('channel', e.target.value as PhoneChannel)}
              className="rounded-md border border-border-light bg-surface-primary px-2 py-1 text-sm text-content-primary"
            >
              {CHANNELS.map((c) => (
                <option key={c} value={c}>
                  {channelLabel(t, c)}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-sm text-content-secondary">
            {t('phonelog.duration_min', { defaultValue: 'Duration (minutes)' })}
            <input
              type="number"
              min="0"
              step="1"
              value={form.duration_minutes}
              onChange={(e) => set('duration_minutes', e.target.value)}
              className="rounded-md border border-border-light bg-surface-primary px-2 py-1 text-sm text-content-primary"
            />
          </label>

          <label className="flex flex-col gap-1 text-sm text-content-secondary">
            {t('phonelog.summary', { defaultValue: 'Summary (optional)' })}
            <input
              value={form.summary}
              onChange={(e) => set('summary', e.target.value)}
              placeholder={t('phonelog.summary_ph', { defaultValue: 'Agreed to revise the slab pour date' })}
              className="rounded-md border border-border-light bg-surface-primary px-2 py-1 text-sm text-content-primary"
            />
          </label>
        </div>

        <label className="flex flex-col gap-1 text-sm text-content-secondary">
          {t('phonelog.transcript', { defaultValue: 'What was said' })}
          <textarea
            value={form.transcript}
            onChange={(e) => set('transcript', e.target.value)}
            rows={4}
            placeholder={t('phonelog.transcript_ph', {
              defaultValue: 'Type or paste the conversation. Instruction sentences are pulled out automatically.',
            })}
            className="rounded-md border border-border-light bg-surface-primary px-2 py-1 text-sm text-content-primary"
          />
        </label>

        {createMutation.isError && (
          <p className="text-sm text-red-600">{getErrorMessage(createMutation.error)}</p>
        )}

        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={!canSubmit || createMutation.isPending}
            onClick={() => createMutation.mutate()}
            className="inline-flex items-center gap-1.5 rounded-md bg-oe-blue px-3 py-1.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {form.channel === 'voice_note' ? <Mic className="h-4 w-4" /> : <Phone className="h-4 w-4" />}
            {t('phonelog.log_call', { defaultValue: 'Log the call' })}
          </button>
          <span className="text-xs text-content-tertiary">
            {t('phonelog.log_hint', { defaultValue: 'Add a summary or what was said to log the call.' })}
          </span>
        </div>
      </Card>

      <div className="space-y-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-content-primary">
          <MessageSquare className="h-4 w-4" />
          {t('phonelog.recent', { defaultValue: 'Recent calls' })}
        </h2>

        {logsQuery.isLoading ? (
          <SkeletonTable rows={3} />
        ) : logsQuery.isError ? (
          <EmptyState
            icon={<Inbox className="h-6 w-6" />}
            title={t('phonelog.error_title', { defaultValue: 'Could not load the phone log' })}
            description={getErrorMessage(logsQuery.error)}
          />
        ) : !logsQuery.data || logsQuery.data.length === 0 ? (
          <EmptyState
            icon={<Phone className="h-6 w-6" />}
            title={t('phonelog.empty_title', { defaultValue: 'No calls logged yet' })}
            description={t('phonelog.empty_desc', {
              defaultValue: 'Capture the next phone call or verbal instruction above and it will show up here.',
            })}
          />
        ) : (
          <div className="space-y-3">
            {logsQuery.data.map((log) => (
              <PhoneLogCard key={log.id} log={log} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
