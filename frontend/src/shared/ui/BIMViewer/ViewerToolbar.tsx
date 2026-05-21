/**
 * ViewerToolbar — floating overlay surfacing the three BIMcollab-style
 * tools added by this slice: Section Box, Walk mode, Measure.
 *
 * Only one tool is active at a time (mutual exclusion is enforced at the
 * component level, not at the helper level — each helper is independent).
 * The active tool's sub-panel renders directly below the button row.
 *
 * The toolbar is intentionally additive: it lives in its own React tree,
 * does not depend on the rest of the viewer's Zustand stores, and is
 * driven only by the three helper instances passed in as props. That
 * keeps it composable from FederationsPage (which has multiple viewers)
 * and the single-model BIMPage alike.
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import clsx from 'clsx';
import { Crop, Move3d, Ruler } from 'lucide-react';
import type { SectionBox } from './SectionBox';
import type { WalkMode } from './WalkMode';
import type { MeasureTool, Measurement } from './MeasureTool';

export type ActiveViewerTool = 'section' | 'walk' | 'measure' | null;

export interface ViewerToolbarProps {
  sectionBox: SectionBox;
  walkMode: WalkMode;
  measureTool: MeasureTool;
  /** Notified whenever the active tool changes (including to null). */
  onToolChange?: (tool: ActiveViewerTool) => void;
  /** Hook called when the user clicks "Fit to selection" / "Fit to all" /
   *  "Reset" — the host component knows the current selection / model
   *  bounds and should drive `sectionBox.setBoundsToBox(...)` from here. */
  onSectionAction?: (action: 'fit_selection' | 'fit_all' | 'reset') => void;
  /** Floating overlay position. */
  position?: 'top-right' | 'bottom-center';
  /** Initial flight speed for the walk-mode slider (m/s). */
  initialFlightSpeed?: number;
  /** Inclusive slider range for flight speed (m/s). */
  flightSpeedRange?: { min: number; max: number };
}

export function ViewerToolbar({
  sectionBox,
  walkMode,
  measureTool,
  onToolChange,
  onSectionAction,
  position = 'top-right',
  initialFlightSpeed,
  flightSpeedRange,
}: ViewerToolbarProps): JSX.Element {
  const { t } = useTranslation();
  const [active, setActive] = useState<ActiveViewerTool>(null);
  const [measurementCount, setMeasurementCount] = useState(0);
  const [flightSpeed, setFlightSpeedState] = useState<number>(
    initialFlightSpeed ?? walkMode.getFlightSpeed(),
  );

  // Subscribe to MeasureTool completions so the badge updates.
  useEffect(() => {
    const unsub = measureTool.onMeasurement((_m: Measurement) => {
      setMeasurementCount(measureTool.count());
    });
    return unsub;
  }, [measureTool]);

  const setTool = useCallback(
    (next: ActiveViewerTool) => {
      // Disable everything currently active.
      if (sectionBox.isEnabled() && next !== 'section') sectionBox.disable();
      if (walkMode.isEnabled() && next !== 'walk') walkMode.disable();
      if (measureTool.isEnabled() && next !== 'measure') measureTool.disable();

      // Enable the new tool (if any).
      try {
        if (next === 'section') sectionBox.enable();
        else if (next === 'walk') walkMode.enable();
        else if (next === 'measure') measureTool.enable();
      } catch (err) {
        // WalkMode throws if OrbitControls is still enabled; surface as
        // a console warning so the host can diagnose but don't crash.
        // The caller is expected to disable OrbitControls before this
        // toolbar enables walk mode.
        // eslint-disable-next-line no-console
        console.warn('ViewerToolbar.setTool:', err);
        return;
      }
      setActive(next);
      onToolChange?.(next);
    },
    [sectionBox, walkMode, measureTool, onToolChange],
  );

  const toggleTool = useCallback(
    (tool: Exclude<ActiveViewerTool, null>) => {
      setTool(active === tool ? null : tool);
    },
    [active, setTool],
  );

  const handleSpeedChange = useCallback(
    (next: number) => {
      walkMode.setFlightSpeed(next);
      setFlightSpeedState(next);
    },
    [walkMode],
  );

  const handleClearMeasurements = useCallback(() => {
    measureTool.clearAll();
    setMeasurementCount(0);
  }, [measureTool]);

  const positionClass =
    position === 'bottom-center'
      ? 'bottom-4 start-1/2 -translate-x-1/2'
      : 'top-4 end-4';

  return (
    <div
      className={clsx('absolute z-20 flex flex-col items-stretch gap-2', positionClass)}
      data-testid="viewer-toolbar"
      data-position={position}
    >
      <div className="flex items-center gap-1 rounded-lg bg-surface-primary border border-border-light shadow-sm p-1">
        <ToolButton
          icon={Crop}
          label={t('viewerTools.section_box', { defaultValue: 'Section box' })}
          active={active === 'section'}
          onClick={() => toggleTool('section')}
          testId="viewer-tool-section"
        />
        <ToolButton
          icon={Move3d}
          label={t('viewerTools.walk', { defaultValue: 'Walk' })}
          active={active === 'walk'}
          onClick={() => toggleTool('walk')}
          testId="viewer-tool-walk"
        />
        <ToolButton
          icon={Ruler}
          label={t('viewerTools.measure', { defaultValue: 'Measure' })}
          active={active === 'measure'}
          onClick={() => toggleTool('measure')}
          testId="viewer-tool-measure"
        />
      </div>

      {active === 'section' && (
        <div
          className="flex flex-col gap-1 rounded-md bg-surface-primary border border-border-light shadow-sm p-2 text-[11px] text-content-secondary"
          data-testid="viewer-tool-section-panel"
        >
          <button
            type="button"
            className="px-2 py-1 rounded hover:bg-surface-secondary text-start"
            onClick={() => onSectionAction?.('fit_selection')}
            data-testid="viewer-section-fit-selection"
          >
            {t('viewerTools.fit_selection', { defaultValue: 'Fit to selection' })}
          </button>
          <button
            type="button"
            className="px-2 py-1 rounded hover:bg-surface-secondary text-start"
            onClick={() => onSectionAction?.('fit_all')}
            data-testid="viewer-section-fit-all"
          >
            {t('viewerTools.fit_all', { defaultValue: 'Fit to all' })}
          </button>
          <button
            type="button"
            className="px-2 py-1 rounded hover:bg-surface-secondary text-start"
            onClick={() => onSectionAction?.('reset')}
            data-testid="viewer-section-reset"
          >
            {t('viewerTools.reset', { defaultValue: 'Reset' })}
          </button>
          <SectionOffsetsReadout sectionBox={sectionBox} />
        </div>
      )}

      {active === 'walk' && (
        <div
          className="flex flex-col gap-2 rounded-md bg-surface-primary border border-border-light shadow-sm p-2 text-[11px] text-content-secondary"
          data-testid="viewer-tool-walk-panel"
        >
          <label className="flex items-center gap-2">
            <span className="shrink-0">
              {t('viewerTools.flight_speed', { defaultValue: 'Flight speed' })}
            </span>
            <input
              type="range"
              min={flightSpeedRange?.min ?? 0.5}
              max={flightSpeedRange?.max ?? 20}
              step={0.1}
              value={flightSpeed}
              onChange={(e) => handleSpeedChange(Number(e.target.value))}
              data-testid="viewer-walk-speed"
              aria-label={t('viewerTools.flight_speed', {
                defaultValue: 'Flight speed',
              })}
            />
            <span className="tabular-nums w-10 text-end">
              {flightSpeed.toFixed(1)}
            </span>
          </label>
        </div>
      )}

      {active === 'measure' && (
        <div
          className="flex flex-col gap-2 rounded-md bg-surface-primary border border-border-light shadow-sm p-2 text-[11px] text-content-secondary"
          data-testid="viewer-tool-measure-panel"
        >
          <div className="flex items-center justify-between gap-2">
            <span data-testid="viewer-measure-count">
              {t('viewerTools.measurements_count', {
                defaultValue: 'Measurements: {{count}}',
                count: measurementCount,
              })
                .toString()
                .replace('{{count}}', String(measurementCount))}
            </span>
            <span className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-oe-blue text-white text-[10px] font-medium">
              {measurementCount}
            </span>
          </div>
          <button
            type="button"
            className="px-2 py-1 rounded hover:bg-surface-secondary text-start"
            onClick={handleClearMeasurements}
            data-testid="viewer-measure-clear"
          >
            {t('viewerTools.clear_measurements', {
              defaultValue: 'Clear all measurements',
            })}
          </button>
        </div>
      )}
    </div>
  );
}

interface ToolButtonProps {
  icon: React.ElementType;
  label: string;
  active: boolean;
  onClick: () => void;
  testId: string;
}

function ToolButton({
  icon: Icon,
  label,
  active,
  onClick,
  testId,
}: ToolButtonProps): JSX.Element {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      aria-pressed={active}
      data-testid={testId}
      className={clsx(
        'flex h-7 w-7 items-center justify-center rounded transition-colors',
        active
          ? 'bg-oe-blue text-white'
          : 'text-content-secondary hover:bg-surface-secondary hover:text-content-primary',
      )}
    >
      <Icon size={14} />
    </button>
  );
}

/** Read-only display of the current section AABB. The host can switch
 *  between metric / imperial later — for now, metres with 3 decimals. */
function SectionOffsetsReadout({
  sectionBox,
}: {
  sectionBox: SectionBox;
}): JSX.Element {
  const bounds = sectionBox.getBounds();
  const fmt = (v: number): string => v.toFixed(3);
  return (
    <div
      className="grid grid-cols-3 gap-x-2 text-[10px] text-content-tertiary tabular-nums mt-1"
      data-testid="viewer-section-offsets"
    >
      <span>X: {fmt(bounds.min.x)}…{fmt(bounds.max.x)}</span>
      <span>Y: {fmt(bounds.min.y)}…{fmt(bounds.max.y)}</span>
      <span>Z: {fmt(bounds.min.z)}…{fmt(bounds.max.z)}</span>
    </div>
  );
}
