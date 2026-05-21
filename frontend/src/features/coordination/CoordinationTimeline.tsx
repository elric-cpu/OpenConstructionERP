/**
 * Activity timeline for the Coordination Hub.
 *
 * Renders the 50 most-recent events as a vertical list. Each event row
 * carries an icon picked by ``event.type``, a relative-time label, the
 * server-formatted summary and an optional click-through deep link.
 */

import {
  Radar,
  Layers,
  ClipboardCheck,
  Download,
  Activity,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { DateDisplay } from '@/shared/ui/DateDisplay';
import { EmptyState } from '@/shared/ui/EmptyState';
import type {
  CoordinationTimelineEvent,
  CoordinationTimelineResponse,
} from './types';

export interface CoordinationTimelineProps {
  data: CoordinationTimelineResponse | undefined;
  isLoading?: boolean;
}

function IconForType({ type }: { type: string }) {
  switch (type) {
    case 'clash_run':
      return <Radar size={16} className="text-amber-600" />;
    case 'federation_created':
      return <Layers size={16} className="text-blue-600" />;
    case 'rule_pack_installed':
      return <ClipboardCheck size={16} className="text-emerald-600" />;
    case 'bcf_export':
      return <Download size={16} className="text-purple-600" />;
    default:
      return <Activity size={16} className="text-content-secondary" />;
  }
}

function TimelineRow({ event }: { event: CoordinationTimelineEvent }) {
  const navigate = useNavigate();
  const clickable = Boolean(event.target);
  const handleClick = () => {
    if (event.target) navigate(event.target);
  };
  return (
    <li
      data-testid={`timeline-event-${event.type}`}
      className="flex items-start gap-3 border-b border-border py-3 last:border-b-0"
    >
      <div className="mt-0.5 flex-shrink-0">
        <IconForType type={event.type} />
      </div>
      <div className="min-w-0 flex-1">
        <button
          type="button"
          disabled={!clickable}
          onClick={handleClick}
          className={
            clickable
              ? 'text-left text-sm font-medium text-content-primary hover:text-blue-600 focus:outline-none focus-visible:underline'
              : 'cursor-default text-left text-sm font-medium text-content-primary'
          }
        >
          {event.summary}
        </button>
        <div className="mt-0.5 text-xs text-content-tertiary">
          <DateDisplay value={event.ts} format="relative" />
        </div>
      </div>
    </li>
  );
}

function SkeletonRow() {
  return (
    <li className="flex animate-pulse items-start gap-3 border-b border-border py-3 last:border-b-0">
      <div className="h-4 w-4 rounded bg-slate-200" />
      <div className="flex-1">
        <div className="h-3 w-2/3 rounded bg-slate-200" />
        <div className="mt-2 h-3 w-1/4 rounded bg-slate-100" />
      </div>
    </li>
  );
}

export function CoordinationTimeline({
  data,
  isLoading,
}: CoordinationTimelineProps) {
  const { t } = useTranslation();

  return (
    <div
      data-testid="coordination-timeline"
      className="rounded-xl border border-border bg-surface p-4 shadow-sm"
    >
      <h3 className="mb-3 text-base font-semibold text-content-primary">
        {t('coordination.timeline_title', {
          defaultValue: 'Recent Activity',
        })}
      </h3>
      {isLoading || !data ? (
        <ul>
          <SkeletonRow />
          <SkeletonRow />
          <SkeletonRow />
        </ul>
      ) : data.events.length === 0 ? (
        <EmptyState
          title={t('coordination.timeline_empty', {
            defaultValue: 'No coordination activity yet.',
          })}
          description=""
        />
      ) : (
        <ul>
          {data.events.map((event, idx) => (
            <TimelineRow
              key={`${event.ts}-${event.type}-${idx}`}
              event={event}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
