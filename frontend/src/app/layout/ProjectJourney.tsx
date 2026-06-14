import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import clsx from 'clsx';
import {
  Route as RouteIcon,
  X,
  ChevronDown,
  ArrowRight,
  Sparkles,
  MapPin,
  type LucideIcon,
} from 'lucide-react';
import {
  JOURNEY_ARCS,
  JOURNEY_PHASES,
  JOURNEY_ALWAYS_ON,
  resolveJourneyPhaseKey,
  type JourneyArcKey,
  type JourneyModule,
} from './projectJourneyData';

/**
 * ProjectJourney - a whole-platform lifecycle map opened from the top bar.
 *
 * The header shows a compact pill naming the phase the current screen belongs
 * to ("Quantify", "Estimate", ...), so the top bar is a constant orientation
 * device. Clicking it opens the full map: three arcs, eleven numbered phases
 * in the order they happen, every major module placed on the line, and an
 * "always on" band for the cross-cutting helpers. The current phase is
 * highlighted, and every module is a link, so the map doubles as navigation.
 */

// Per-arc accent. The CURRENT phase always uses the brand blue ring so "you
// are here" is unmistakable regardless of which arc it sits in.
const ARC_ACCENT: Record<JourneyArcKey, { dot: string; text: string; bar: string }> = {
  plan: { dot: 'bg-oe-blue', text: 'text-oe-blue', bar: 'bg-oe-blue' },
  procure: { dot: 'bg-violet-500', text: 'text-violet-500', bar: 'bg-violet-500' },
  deliver: { dot: 'bg-emerald-500', text: 'text-emerald-500', bar: 'bg-emerald-500' },
};

export function ProjectJourneyButton() {
  const { t } = useTranslation();
  const location = useLocation();
  const [open, setOpen] = useState(false);

  const currentPhaseKey = useMemo(
    () => resolveJourneyPhaseKey(location.pathname),
    [location.pathname],
  );
  const currentPhase = useMemo(
    () => JOURNEY_PHASES.find((p) => p.key === currentPhaseKey),
    [currentPhaseKey],
  );

  const label = currentPhase
    ? t(currentPhase.nameKey, { defaultValue: currentPhase.name })
    : t('journey.button.default', { defaultValue: 'Project journey' });

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-expanded={open}
        data-testid="project-journey-button"
        title={t('journey.button.title', {
          defaultValue: 'Project journey - see where you are and what comes next',
        })}
        className={clsx(
          'flex h-8 shrink-0 items-center gap-1.5 rounded-lg border px-2.5',
          'border-border-light bg-white/70 text-content-secondary shadow-sm dark:bg-surface-primary/60',
          'transition-colors hover:border-oe-blue/40 hover:bg-oe-blue/5 hover:text-content-primary',
        )}
      >
        <RouteIcon size={14} strokeWidth={1.75} className="shrink-0 text-oe-blue" aria-hidden />
        {currentPhase && (
          <span className="hidden text-[10px] font-medium uppercase tracking-wide text-content-quaternary md:inline">
            {t('journey.button.prefix', { defaultValue: 'Step' })}
          </span>
        )}
        <span className="hidden max-w-[10rem] truncate text-xs font-semibold sm:inline">
          {label}
        </span>
        <ChevronDown size={12} strokeWidth={2} className="shrink-0 text-content-quaternary" aria-hidden />
      </button>
      {open && (
        <ProjectJourneyPanel
          currentPhaseKey={currentPhaseKey}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

function ProjectJourneyPanel({
  currentPhaseKey,
  onClose,
}: {
  currentPhaseKey: string | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const closeRef = useRef<HTMLButtonElement>(null);

  // Close on Escape; focus the close button on open for keyboard users.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    closeRef.current?.focus();
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  const go = useCallback(
    (to: string) => {
      navigate(to);
      onClose();
    },
    [navigate, onClose],
  );

  const currentPhase = JOURNEY_PHASES.find((p) => p.key === currentPhaseKey);
  // Global 1-based number for each phase, in lifecycle order.
  const phaseNumber = (key: string) => JOURNEY_PHASES.findIndex((p) => p.key === key) + 1;

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center overflow-y-auto p-3 sm:p-6">
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-sm animate-fade-in"
        onClick={onClose}
        aria-hidden
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t('journey.title', { defaultValue: 'Your project journey' })}
        className="relative my-2 w-full max-w-6xl rounded-2xl border border-border-light bg-surface-elevated shadow-2xl animate-scale-in"
      >
        {/* ── Header ─────────────────────────────────────────────────── */}
        <div className="sticky top-0 z-10 flex items-start justify-between gap-3 rounded-t-2xl border-b border-border-light bg-surface-elevated/95 px-5 py-4 backdrop-blur">
          <div className="flex items-start gap-3 min-w-0">
            <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-oe-blue/10 text-oe-blue">
              <RouteIcon size={18} strokeWidth={1.75} />
            </span>
            <div className="min-w-0">
              <h2 className="text-base font-semibold text-content-primary">
                {t('journey.title', { defaultValue: 'Your project journey' })}
              </h2>
              <p className="mt-0.5 text-xs leading-relaxed text-content-secondary">
                {t('journey.subtitle', {
                  defaultValue:
                    'Every stage of a construction project, from first lead to handover, and where you are right now. Pick any step to jump there.',
                })}
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {currentPhase && (
              <span className="hidden items-center gap-1.5 rounded-full bg-oe-blue/10 px-2.5 py-1 text-2xs font-medium text-oe-blue sm:inline-flex">
                <MapPin size={11} aria-hidden />
                {t('journey.you_are_here_named', {
                  defaultValue: 'You are here: {{phase}}',
                  phase: t(currentPhase.nameKey, { defaultValue: currentPhase.name }),
                })}
              </span>
            )}
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              aria-label={t('common.close', { defaultValue: 'Close' })}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-content-tertiary transition-colors hover:bg-surface-secondary hover:text-content-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* ── Arcs and phases ────────────────────────────────────────── */}
        <div className="space-y-6 px-5 py-5">
          {JOURNEY_ARCS.map((arc) => {
            const accent = ARC_ACCENT[arc.key];
            const phases = JOURNEY_PHASES.filter((p) => p.arc === arc.key);
            return (
              <section key={arc.key} aria-label={t(arc.nameKey, { defaultValue: arc.name })}>
                <div className="mb-2.5 flex items-center gap-2">
                  <span className={clsx('h-2 w-2 shrink-0 rounded-full', accent.dot)} aria-hidden />
                  <h3 className={clsx('text-xs font-bold uppercase tracking-wider', accent.text)}>
                    {t(arc.nameKey, { defaultValue: arc.name })}
                  </h3>
                  <span className="truncate text-2xs text-content-tertiary">
                    {t(arc.descKey, { defaultValue: arc.desc })}
                  </span>
                </div>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {phases.map((phase) => {
                    const Icon: LucideIcon = phase.icon;
                    const isCurrent = phase.key === currentPhaseKey;
                    const num = phaseNumber(phase.key);
                    return (
                      <div
                        key={phase.key}
                        className={clsx(
                          'flex flex-col rounded-xl border p-3 transition-colors',
                          isCurrent
                            ? 'border-oe-blue bg-oe-blue/5 ring-1 ring-oe-blue/30'
                            : 'border-border-light bg-surface-primary',
                        )}
                      >
                        <div className="flex items-center gap-2.5">
                          <span
                            className={clsx(
                              'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
                              isCurrent
                                ? 'bg-oe-blue text-white'
                                : 'bg-surface-tertiary text-content-secondary',
                            )}
                          >
                            <Icon size={16} strokeWidth={1.75} />
                          </span>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-1.5">
                              <span className="text-2xs font-semibold text-content-quaternary">
                                {num}
                              </span>
                              <h4
                                className={clsx(
                                  'truncate text-sm font-semibold',
                                  isCurrent ? 'text-oe-blue' : 'text-content-primary',
                                )}
                              >
                                {t(phase.nameKey, { defaultValue: phase.name })}
                              </h4>
                            </div>
                          </div>
                          {isCurrent && (
                            <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-oe-blue/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-oe-blue">
                              {t('journey.here', { defaultValue: 'Here' })}
                            </span>
                          )}
                        </div>
                        <p className="mt-2 text-xs leading-relaxed text-content-secondary">
                          {t(phase.descKey, { defaultValue: phase.desc })}
                        </p>
                        <div className="mt-2.5 flex flex-wrap gap-1.5">
                          {phase.modules.map((m) => (
                            <ModuleChip
                              key={m.to}
                              module={m}
                              active={isOnRoute(location.pathname, m.to)}
                              onClick={() => go(m.to)}
                            />
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            );
          })}

          {/* ── Always-on band ───────────────────────────────────────── */}
          <section
            aria-label={t('journey.always_on.title', { defaultValue: 'Always on' })}
            className="rounded-xl border border-dashed border-border-light bg-surface-secondary/40 p-3"
          >
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-amber-500/15 text-amber-500">
                <Sparkles size={15} strokeWidth={1.75} />
              </span>
              <h3 className="text-xs font-bold uppercase tracking-wider text-content-secondary">
                {t('journey.always_on.title', { defaultValue: 'Always on' })}
              </h3>
              <span className="text-2xs text-content-tertiary">
                {t('journey.always_on.desc', {
                  defaultValue: 'These help across every phase, not just one.',
                })}
              </span>
            </div>
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {JOURNEY_ALWAYS_ON.map((m) => (
                <ModuleChip
                  key={m.to}
                  module={m}
                  active={isOnRoute(location.pathname, m.to)}
                  onClick={() => go(m.to)}
                />
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function ModuleChip({
  module,
  active,
  onClick,
}: {
  module: JourneyModule;
  active: boolean;
  onClick: () => void;
}) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        'group inline-flex items-center gap-1 rounded-md border px-2 py-1 text-2xs font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40',
        active
          ? 'border-oe-blue/50 bg-oe-blue/10 text-oe-blue'
          : 'border-border-light bg-surface-secondary text-content-secondary hover:border-oe-blue/40 hover:bg-oe-blue/5 hover:text-content-primary',
      )}
    >
      <span className="truncate">{t(module.labelKey, { defaultValue: module.label })}</span>
      <ArrowRight
        size={11}
        className="shrink-0 opacity-0 transition-opacity group-hover:opacity-60"
        aria-hidden
      />
    </button>
  );
}

/** True when ``pathname`` is on (or under) the module route ``to``. */
function isOnRoute(pathname: string, to: string): boolean {
  const target = to.split('?')[0]!;
  return pathname === target || pathname.startsWith(target + '/');
}
