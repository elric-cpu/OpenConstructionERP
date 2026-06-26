// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Inbound Capture (admin) - a read view of what came in through the capture
// gateway. The capture endpoints (POST email / provider webhook) are driven by
// external systems; this page lets an admin see the messages that landed as
// incoming correspondence for the active project, plus the configured document
// sources (watched folders) that feed the same record. It is read-only: managing
// a source lives on the Document Connectors page, linked from here.

import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { Mailbox, Inbox, HardDrive, Paperclip, ArrowRight } from 'lucide-react';

import { Card, Badge, EmptyState, SkeletonTable, DismissibleInfo } from '@/shared/ui';
import { getErrorMessage } from '@/shared/lib/api';
import { useProjectContextStore } from '@/stores/useProjectContextStore';
import { listConnectorSources } from '@/features/connectors/api';
import type { ConnectorSource } from '@/features/connectors/types';
import { listCapturedMessages } from './api';
import type { InboundMessage } from './types';

// A short, readable timestamp for the captured time. The value is the provider's
// ISO sent_at; an unparseable / blank value falls back to a dash rather than
// rendering "Invalid Date".
function whenLabel(iso: string): string {
  if (!iso) return '-';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

function CapturedRow({ msg }: { msg: InboundMessage }) {
  const { t } = useTranslation();
  return (
    <Card className="space-y-1.5 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-content-primary">
          {msg.reference_number || t('inbound.no_reference', { defaultValue: '(no reference)' })}
        </span>
        {msg.channel ? <Badge variant="blue">{msg.channel}</Badge> : null}
        {msg.attachments.length > 0 ? (
          <Badge variant="neutral">
            <Paperclip className="h-3 w-3" />
            {msg.attachments.length}
          </Badge>
        ) : null}
        <span className="ms-auto text-xs text-content-tertiary">{whenLabel(msg.sent_at)}</span>
      </div>
      <p className="truncate text-sm text-content-secondary">
        {msg.subject || t('inbound.no_subject', { defaultValue: '(no subject)' })}
      </p>
      <p className="truncate text-xs text-content-tertiary">
        {t('inbound.from', { defaultValue: 'From' })}: {msg.sender || '-'}
      </p>
    </Card>
  );
}

function SourceRow({ source }: { source: ConnectorSource }) {
  const { t } = useTranslation();
  return (
    <Card className="space-y-1.5 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <HardDrive className="h-4 w-4 shrink-0 text-content-tertiary" />
        <span className="text-sm font-semibold text-content-primary">{source.name}</span>
        <Badge variant="neutral">{source.kind}</Badge>
        {!source.enabled ? (
          <Badge variant="warning">{t('inbound.source_disabled', { defaultValue: 'Disabled' })}</Badge>
        ) : null}
      </div>
      <code className="block truncate rounded bg-surface-secondary px-2 py-1 text-xs text-content-secondary">
        {source.root_path}
      </code>
    </Card>
  );
}

export function InboundCapturePage() {
  const { t } = useTranslation();
  const { projectId: routeProjectId } = useParams();
  const activeProjectId = useProjectContextStore((s) => s.activeProjectId);
  const projectId = routeProjectId ?? activeProjectId ?? '';

  const capturedQ = useQuery({
    queryKey: ['inbound', 'captured', projectId],
    queryFn: () => listCapturedMessages(projectId, { limit: 100 }),
    enabled: !!projectId,
    retry: false,
    staleTime: 30_000,
  });

  const sourcesQ = useQuery({
    queryKey: ['connectors', 'sources', projectId],
    queryFn: () => listConnectorSources(projectId),
    enabled: !!projectId,
    retry: false,
    staleTime: 30_000,
  });

  const captured = capturedQ.data?.items ?? [];
  const sources = sourcesQ.data ?? [];

  return (
    <div className="space-y-5 animate-fade-in">
      <header className="flex flex-wrap items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-oe-blue/10 text-oe-blue">
          <Mailbox className="h-5 w-5" />
        </span>
        <div className="flex-1">
          <h1 className="text-xl font-semibold text-content-primary">
            {t('inbound.title', { defaultValue: 'Inbound Capture' })}
          </h1>
          <p className="text-sm text-content-tertiary">
            {t('inbound.subtitle', {
              defaultValue: 'Messages captured from email and chat, and the sources that feed the record.',
            })}
          </p>
        </div>
        <a
          href="/connectors"
          className="inline-flex items-center gap-1.5 rounded-md border border-border-light bg-surface-primary px-3 py-1.5 text-sm font-medium text-content-secondary hover:bg-surface-secondary"
        >
          {t('inbound.manage_sources', { defaultValue: 'Manage sources' })}
          <ArrowRight className="h-4 w-4" />
        </a>
      </header>

      <DismissibleInfo
        storageKey="inbound-capture-admin"
        title={t('inbound.intro_title', { defaultValue: 'What lands here' })}
      >
        {t('inbound.intro_body', {
          defaultValue:
            'An external mail or chat integration posts inbound messages to the capture gateway, which stores each as incoming correspondence on the project - deduplicated on the provider message id. This view lists what was captured for the active project, alongside the watched-folder sources that import documents onto the same record.',
        })}
      </DismissibleInfo>

      {!projectId ? (
        <EmptyState
          icon={<Inbox className="h-6 w-6" />}
          title={t('inbound.no_project', { defaultValue: 'No project selected' })}
          description={t('inbound.no_project_desc', {
            defaultValue: 'Select a project to see the messages captured against it.',
          })}
        />
      ) : (
        <>
          <section className="space-y-2">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-content-secondary">
                {t('inbound.captured_heading', { defaultValue: 'Captured messages' })}
              </h2>
              {capturedQ.data ? (
                <Badge variant="neutral">{capturedQ.data.total}</Badge>
              ) : null}
            </div>
            {capturedQ.isLoading ? (
              <SkeletonTable rows={4} />
            ) : capturedQ.isError ? (
              <p className="text-sm text-status-error">{getErrorMessage(capturedQ.error)}</p>
            ) : captured.length === 0 ? (
              <EmptyState
                icon={<Mailbox className="h-6 w-6" />}
                title={t('inbound.none_captured', { defaultValue: 'Nothing captured yet' })}
                description={t('inbound.none_captured_desc', {
                  defaultValue:
                    'Inbound emails and chat messages delivered to the capture gateway will appear here.',
                })}
              />
            ) : (
              <div className="grid gap-2">
                {captured.map((m) => (
                  <CapturedRow key={m.correspondence_id} msg={m} />
                ))}
              </div>
            )}
          </section>

          <section className="space-y-2">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-content-secondary">
                {t('inbound.sources_heading', { defaultValue: 'Configured sources' })}
              </h2>
              {sourcesQ.data ? <Badge variant="neutral">{sources.length}</Badge> : null}
            </div>
            {sourcesQ.isLoading ? (
              <SkeletonTable rows={2} />
            ) : sourcesQ.isError ? (
              <p className="text-sm text-status-error">{getErrorMessage(sourcesQ.error)}</p>
            ) : sources.length === 0 ? (
              <EmptyState
                icon={<HardDrive className="h-6 w-6" />}
                title={t('inbound.no_sources', { defaultValue: 'No sources configured' })}
                description={t('inbound.no_sources_desc', {
                  defaultValue: 'Add a watched folder on the Document Connectors page to feed the record.',
                })}
              />
            ) : (
              <div className="grid gap-2">
                {sources.map((s) => (
                  <SourceRow key={s.id} source={s} />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
