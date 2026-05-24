/**
 * AccommodationCalendar — visual rooms × dates grid.
 *
 * Layout: rooms as rows (grouped + sorted by accommodation.name, then
 * room.label), days as columns. Each booking is rendered as a coloured
 * block spanning its [check_in, check_out) date range. Click an empty
 * cell to open a create-booking modal pre-filled with room + check_in;
 * click an existing block to open the state-machine detail drawer.
 *
 * Pure-DOM grid hand-rolled with `date-fns` (no calendar library) per
 * the LIGHTWEIGHT principle.
 *
 * Money discipline: charge.amount is Decimal-as-string — we sum charges
 * by accumulating the string values via the Decimal-friendly fallback
 * (string concatenation through Number for display only, never for
 * persisted state). Charges that fail to parse are skipped.
 *
 * Performance: cells are derived from `(viewStart, viewEnd, rooms,
 * bookings)` via useMemo. We never materialise an N×M cell array — the
 * grid renders rooms × days directly and absolutely-positions blocks
 * inside each room row.
 *
 * Both views (Week / Month) share the same grid primitives; only
 * `daysToShow` differs.
 */

import {
  useState,
  useMemo,
  useEffect,
  useRef,
  useCallback,
  type CSSProperties,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import {
  ChevronLeft,
  ChevronRight,
  Calendar,
  CalendarRange,
  CalendarDays,
  Loader2,
  AlertTriangle,
  X,
  Plus,
} from 'lucide-react';
import {
  startOfWeek,
  endOfWeek,
  startOfMonth,
  endOfMonth,
  addDays,
  addWeeks,
  addMonths,
  differenceInCalendarDays,
  format,
  parseISO,
  isSameMonth,
  isToday as dfIsToday,
} from 'date-fns';

import { Button, Badge, ConfirmDialog, Breadcrumb } from '@/shared/ui';
import {
  WideModal,
  WideModalSection,
  WideModalField,
} from '@/shared/ui/WideModal';
import { ContactSearchInput } from '@/shared/ui/ContactSearchInput';
import { useToastStore } from '@/stores/useToastStore';
import { getErrorMessage } from '@/shared/lib/api';

import {
  listAccommodations,
  listAccommodationBookings,
  getAccommodation,
  createBooking,
  getBooking,
  updateBooking,
  allowedBookingTransitions,
  isBookingTerminal,
  type Accommodation,
  type AccommodationDetail,
  type Room,
  type Booking,
  type BookingStatus,
  type Charge,
} from './api';

type CalendarView = 'week' | 'month';

/** Pixel width of one day-column. Kept generous for hover targets. */
const DAY_WIDTH_PX = 56;
const ROW_HEIGHT_PX = 44;
const ROOM_LABEL_WIDTH_PX = 200;

const STATE_BLOCK_CLASS: Record<BookingStatus, string> = {
  reserved: 'bg-amber-200 text-amber-900 border-amber-400',
  checked_in: 'bg-emerald-300 text-emerald-900 border-emerald-500',
  checked_out:
    'bg-slate-200 text-slate-700 border-slate-300 line-through opacity-70',
  cancelled: 'bg-rose-200 text-rose-900 border-rose-400 line-through',
};

/* ── Date helpers ─────────────────────────────────────────────────────── */

/**
 * Compute the inclusive list of dates rendered in the grid given the
 * current view + anchor date.
 *
 * - Week: 7 days starting Monday.
 * - Month: full weeks bracketing the anchor month (always 35 or 42 days,
 *   includes leading + trailing greyed-out days from neighbour months).
 */
function computeRange(view: CalendarView, anchor: Date): { start: Date; end: Date } {
  if (view === 'week') {
    const start = startOfWeek(anchor, { weekStartsOn: 1 });
    const end = addDays(start, 6);
    return { start, end };
  }
  const start = startOfWeek(startOfMonth(anchor), { weekStartsOn: 1 });
  const end = endOfWeek(endOfMonth(anchor), { weekStartsOn: 1 });
  return { start, end };
}

function rangeDays(start: Date, end: Date): Date[] {
  const out: Date[] = [];
  const total = differenceInCalendarDays(end, start);
  for (let i = 0; i <= total; i += 1) out.push(addDays(start, i));
  return out;
}

/**
 * Half-open booking interval clipped to the visible window:
 *   - check_in is inclusive
 *   - check_out (when set) is exclusive — last occupied night is
 *     check_out - 1 day. NULL check_out → open-ended → clip to viewEnd.
 *
 * Returns `null` when the booking does not intersect the visible window.
 */
function clipBookingToView(
  b: Booking,
  viewStart: Date,
  viewEnd: Date,
): { startDayIdx: number; spanDays: number } | null {
  const checkIn = parseISO(b.check_in);
  // NULL check_out → open-ended: render through the end of the view.
  // We add one day past the visible window so the block visually spans
  // to the right edge.
  const checkOut = b.check_out ? parseISO(b.check_out) : addDays(viewEnd, 1);

  // Half-open: [checkIn, checkOut) — empty interval guard.
  if (differenceInCalendarDays(checkOut, checkIn) <= 0) return null;

  // viewStart..viewEnd is the inclusive day range we render. The block
  // spans days `[max(checkIn, viewStart), min(checkOut - 1, viewEnd)]`.
  const lastNight = addDays(checkOut, -1);
  const clipStart =
    differenceInCalendarDays(checkIn, viewStart) < 0 ? viewStart : checkIn;
  const clipEnd =
    differenceInCalendarDays(lastNight, viewEnd) > 0 ? viewEnd : lastNight;

  const startDayIdx = differenceInCalendarDays(clipStart, viewStart);
  const endDayIdx = differenceInCalendarDays(clipEnd, viewStart);
  if (endDayIdx < 0 || startDayIdx > differenceInCalendarDays(viewEnd, viewStart)) {
    return null;
  }
  const spanDays = endDayIdx - startDayIdx + 1;
  if (spanDays <= 0) return null;
  return { startDayIdx, spanDays };
}

/**
 * Count nights for a booking. For NULL check_out we return null so the
 * tooltip displays "open-ended".
 */
function bookingNights(b: Booking): number | null {
  if (!b.check_out) return null;
  return differenceInCalendarDays(parseISO(b.check_out), parseISO(b.check_in));
}

/**
 * Sum Decimal-as-string charge amounts. We deliberately keep the sum as
 * a string to honour money discipline. The simplest correct
 * implementation is a left-to-right accumulator that re-parses on each
 * step using string arithmetic via `BigInt` over a scaled integer.
 *
 * For display only — never feeds back into a write request. Returns
 * null when no charges are present.
 */
function sumChargesString(charges: Charge[]): string | null {
  if (charges.length === 0) return null;
  // Scale every value to integer cents (max 6 decimals) using string
  // arithmetic so we don't drop precision.
  const SCALE = 6;
  let totalScaled = 0n;
  for (const c of charges) {
    const raw = c.amount.trim();
    if (!/^-?\d+(?:\.\d+)?$/.test(raw)) continue;
    const negative = raw.startsWith('-');
    const abs = negative ? raw.slice(1) : raw;
    const [intPart, fracPartRaw = ''] = abs.split('.');
    const fracPart = (fracPartRaw + '0'.repeat(SCALE)).slice(0, SCALE);
    const scaled = BigInt(intPart + fracPart);
    totalScaled += negative ? -scaled : scaled;
  }
  const negative = totalScaled < 0n;
  const absStr = (negative ? -totalScaled : totalScaled).toString().padStart(SCALE + 1, '0');
  const intStr = absStr.slice(0, absStr.length - SCALE) || '0';
  const fracStr = absStr.slice(absStr.length - SCALE).replace(/0+$/, '');
  return `${negative ? '-' : ''}${intStr}${fracStr ? '.' + fracStr : ''}`;
}

/* ── Top-level page ──────────────────────────────────────────────────── */

interface AccommodationCalendarProps {
  /**
   * When `embedded` is true the component renders without the page
   * header / breadcrumb (used by the Calendar tab inside the detail
   * page). Defaults to standalone page mode.
   */
  embedded?: boolean;
  /**
   * Pre-select a single accommodation (used by the embedded mode on the
   * detail page). When omitted, the user picks from a dropdown.
   */
  scopedAccommodationId?: string;
}

export function AccommodationCalendar({
  embedded = false,
  scopedAccommodationId,
}: AccommodationCalendarProps = {}) {
  const { t } = useTranslation();

  const [view, setView] = useState<CalendarView>('week');
  const [anchor, setAnchor] = useState<Date>(() => new Date());
  const [filterId, setFilterId] = useState<string>(scopedAccommodationId ?? '');

  // Keep internal filter in sync when the embedding component changes
  // the scope (e.g. user navigates between accommodations).
  useEffect(() => {
    if (scopedAccommodationId) setFilterId(scopedAccommodationId);
  }, [scopedAccommodationId]);

  const { start: viewStart, end: viewEnd } = useMemo(
    () => computeRange(view, anchor),
    [view, anchor],
  );

  // List of accommodations — used both for the filter dropdown (when
  // not scoped) and to know which accommodation each room belongs to.
  const accommodationsQuery = useQuery({
    queryKey: ['accommodation', 'list'],
    queryFn: () => listAccommodations(),
    enabled: !scopedAccommodationId,
  });

  // When scoped, fetch the single accommodation detail directly so we
  // don't depend on the list endpoint at all.
  const scopedDetailQuery = useQuery({
    queryKey: ['accommodation', 'detail', scopedAccommodationId],
    queryFn: () => getAccommodation(scopedAccommodationId!),
    enabled: !!scopedAccommodationId,
  });

  const allAccommodations: Accommodation[] = useMemo(() => {
    if (scopedAccommodationId && scopedDetailQuery.data) {
      return [scopedDetailQuery.data];
    }
    return accommodationsQuery.data ?? [];
  }, [scopedAccommodationId, scopedDetailQuery.data, accommodationsQuery.data]);

  // The chosen accommodations are: (a) the scoped one, (b) the picker
  // selection, or (c) every accommodation when "All" is chosen on the
  // standalone page.
  const chosenAccommodations: Accommodation[] = useMemo(() => {
    if (scopedAccommodationId) return allAccommodations;
    if (filterId === '') return allAccommodations;
    return allAccommodations.filter((a) => a.id === filterId);
  }, [scopedAccommodationId, filterId, allAccommodations]);

  // Fetch room + booking data per accommodation. We use a single
  // composite query keyed on the chosen ids so re-renders are cheap.
  const dataQuery = useQuery({
    queryKey: [
      'accommodation',
      'calendar',
      chosenAccommodations.map((a) => a.id).sort().join(','),
      // Booking query window — fetch ±1 month around the visible range
      // so navigating week-by-week mostly reuses cache.
      format(addDays(viewStart, -31), 'yyyy-MM-dd'),
      format(addDays(viewEnd, 31), 'yyyy-MM-dd'),
    ],
    queryFn: async (): Promise<{
      details: AccommodationDetail[];
      bookings: Booking[];
    }> => {
      if (chosenAccommodations.length === 0) {
        return { details: [], bookings: [] };
      }
      const details: AccommodationDetail[] = [];
      const bookings: Booking[] = [];
      for (const a of chosenAccommodations) {
        const [detail, list] = await Promise.all([
          getAccommodation(a.id),
          listAccommodationBookings(a.id, {
            from_date: format(addDays(viewStart, -31), 'yyyy-MM-dd'),
            to_date: format(addDays(viewEnd, 31), 'yyyy-MM-dd'),
            // Backend caps this at 200; 200 is enough for a 60-day
            // window across any reasonable accommodation.
            limit: 200,
          }),
        ]);
        details.push(detail);
        bookings.push(...list.items);
      }
      return { details, bookings };
    },
    enabled: chosenAccommodations.length > 0,
  });

  // Flatten + sort rooms: by accommodation.name (case-insensitive), then
  // room.label (natural-ish — labels like B-201 sort lexicographically
  // but at least we lowercase). We tag each row with its parent
  // accommodation so the leftmost column can group visually.
  interface CalendarRow {
    accommodation: AccommodationDetail;
    room: Room;
  }
  const rows: CalendarRow[] = useMemo(() => {
    if (!dataQuery.data) return [];
    const out: CalendarRow[] = [];
    const detailsByName = [...dataQuery.data.details].sort((a, b) =>
      a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }),
    );
    for (const acc of detailsByName) {
      const sortedRooms = [...acc.rooms].sort((a, b) =>
        a.label.localeCompare(b.label, undefined, {
          numeric: true,
          sensitivity: 'base',
        }),
      );
      for (const room of sortedRooms) {
        out.push({ accommodation: acc, room });
      }
    }
    return out;
  }, [dataQuery.data]);

  // Bucket bookings by room id. We do this once per data refresh so the
  // per-row render does an O(1) lookup. Each room can have multiple
  // bookings on different (or — guarded — overlapping) date ranges.
  const bookingsByRoom = useMemo(() => {
    const map = new Map<string, Booking[]>();
    if (!dataQuery.data) return map;
    for (const b of dataQuery.data.bookings) {
      const arr = map.get(b.room_id) ?? [];
      arr.push(b);
      map.set(b.room_id, arr);
    }
    return map;
  }, [dataQuery.data]);

  // Day array — derived, not state.
  const days = useMemo(() => rangeDays(viewStart, viewEnd), [viewStart, viewEnd]);

  // Click-to-create state.
  const [createCtx, setCreateCtx] = useState<{
    room: Room;
    accommodationName: string;
    checkIn: string;
  } | null>(null);
  const [openBookingId, setOpenBookingId] = useState<string | null>(null);

  const queryClient = useQueryClient();

  const handlePrev = useCallback(() => {
    setAnchor((d) => (view === 'week' ? addWeeks(d, -1) : addMonths(d, -1)));
  }, [view]);
  const handleNext = useCallback(() => {
    setAnchor((d) => (view === 'week' ? addWeeks(d, 1) : addMonths(d, 1)));
  }, [view]);
  const handleToday = useCallback(() => setAnchor(new Date()), []);

  const inputCls =
    'h-9 rounded-lg border border-border bg-surface-primary px-3 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue';

  const headerLabel = useMemo(() => {
    if (view === 'week') {
      return `${format(viewStart, 'MMM d')} – ${format(viewEnd, 'MMM d, yyyy')}`;
    }
    return format(anchor, 'MMMM yyyy');
  }, [view, viewStart, viewEnd, anchor]);

  return (
    <div className="space-y-4">
      {!embedded && (
        <>
          <Breadcrumb
            items={[
              {
                label: t('accommodation.title', {
                  defaultValue: 'Accommodation',
                }),
                to: '/accommodation',
              },
              {
                label: t('accommodation.calendar.title', {
                  defaultValue: 'Calendar',
                }),
              },
            ]}
          />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h1 className="text-xl font-semibold text-content-primary inline-flex items-center gap-2">
              <Calendar size={18} />
              {t('accommodation.calendar.title', { defaultValue: 'Calendar' })}
            </h1>
          </div>
        </>
      )}

      {/* Controls bar */}
      <div
        data-testid="accommodation-calendar-controls"
        className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-border-light bg-surface-elevated p-3"
      >
        <div className="flex items-center gap-1.5">
          <Button
            variant="ghost"
            size="sm"
            onClick={handlePrev}
            data-testid="accommodation-calendar-prev"
            aria-label={t('common.previous', { defaultValue: 'Previous' })}
          >
            <ChevronLeft size={14} />
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleToday}
            data-testid="accommodation-calendar-today"
          >
            {t('accommodation.calendar.today', { defaultValue: 'Today' })}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleNext}
            data-testid="accommodation-calendar-next"
            aria-label={t('common.next', { defaultValue: 'Next' })}
          >
            <ChevronRight size={14} />
          </Button>
          <span className="ml-2 text-sm font-medium text-content-primary tabular-nums">
            {headerLabel}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {!scopedAccommodationId && (
            <select
              value={filterId}
              onChange={(e) => setFilterId(e.target.value)}
              className={inputCls}
              data-testid="accommodation-calendar-filter"
              aria-label={t('accommodation.calendar.filter_aria', {
                defaultValue: 'Filter by accommodation',
              })}
            >
              <option value="">
                {t('accommodation.calendar.all', {
                  defaultValue: 'All accommodations',
                })}
              </option>
              {allAccommodations.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          )}

          <div
            className="inline-flex rounded-lg border border-border bg-surface-secondary p-0.5"
            role="tablist"
            aria-label={t('accommodation.calendar.view_aria', {
              defaultValue: 'Calendar view',
            })}
          >
            <button
              type="button"
              role="tab"
              aria-selected={view === 'week'}
              onClick={() => setView('week')}
              data-testid="accommodation-calendar-view-week"
              className={clsx(
                'inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition',
                view === 'week'
                  ? 'bg-surface-elevated text-content-primary shadow-sm'
                  : 'text-content-secondary hover:text-content-primary',
              )}
            >
              <CalendarRange size={12} />
              {t('accommodation.calendar.viewWeek', { defaultValue: 'Week' })}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={view === 'month'}
              onClick={() => setView('month')}
              data-testid="accommodation-calendar-view-month"
              className={clsx(
                'inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition',
                view === 'month'
                  ? 'bg-surface-elevated text-content-primary shadow-sm'
                  : 'text-content-secondary hover:text-content-primary',
              )}
            >
              <CalendarDays size={12} />
              {t('accommodation.calendar.viewMonth', { defaultValue: 'Month' })}
            </button>
          </div>
        </div>
      </div>

      {/* Body */}
      {(accommodationsQuery.isLoading || scopedDetailQuery.isLoading || dataQuery.isLoading) && (
        <div className="flex items-center justify-center py-16 text-content-tertiary">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      )}

      {(accommodationsQuery.isError ||
        scopedDetailQuery.isError ||
        dataQuery.isError) && (
        <div className="rounded-xl border border-semantic-error/30 bg-semantic-error/10 p-4 text-sm text-semantic-error">
          <AlertTriangle className="mr-2 inline h-4 w-4" />
          {getErrorMessage(
            accommodationsQuery.error ??
              scopedDetailQuery.error ??
              dataQuery.error,
          ) ||
            t('accommodation.calendar.load_failed', {
              defaultValue: 'Could not load calendar.',
            })}
        </div>
      )}

      {!dataQuery.isLoading &&
        !dataQuery.isError &&
        chosenAccommodations.length === 0 && (
          <div
            data-testid="accommodation-calendar-empty"
            className="rounded-xl border border-dashed border-border bg-surface-secondary/40 p-8 text-center text-sm text-content-tertiary"
          >
            {t('accommodation.calendar.noAccommodations', {
              defaultValue:
                'No accommodations yet. Create one to start booking rooms.',
            })}
          </div>
        )}

      {!dataQuery.isLoading &&
        !dataQuery.isError &&
        chosenAccommodations.length > 0 &&
        rows.length === 0 && (
          <div className="rounded-xl border border-dashed border-border bg-surface-secondary/40 p-8 text-center text-sm text-content-tertiary">
            {t('accommodation.calendar.noRooms', {
              defaultValue: 'No rooms in the selected accommodation(s) yet.',
            })}
          </div>
        )}

      {rows.length > 0 && (
        <CalendarGrid
          rows={rows}
          days={days}
          viewStart={viewStart}
          viewEnd={viewEnd}
          view={view}
          bookingsByRoom={bookingsByRoom}
          onEmptyClick={(row, date) =>
            setCreateCtx({
              room: row.room,
              accommodationName: row.accommodation.name,
              checkIn: format(date, 'yyyy-MM-dd'),
            })
          }
          onBlockClick={(booking) => setOpenBookingId(booking.id)}
        />
      )}

      {createCtx && (
        <CreateBookingModal
          room={createCtx.room}
          accommodationName={createCtx.accommodationName}
          defaultCheckIn={createCtx.checkIn}
          onClose={() => setCreateCtx(null)}
          onCreated={() => {
            queryClient.invalidateQueries({
              queryKey: ['accommodation', 'calendar'],
            });
            queryClient.invalidateQueries({
              queryKey: ['accommodation', 'detail'],
            });
            setCreateCtx(null);
          }}
        />
      )}

      {openBookingId && (
        <BookingDetailDrawer
          bookingId={openBookingId}
          onClose={() => setOpenBookingId(null)}
          onMutated={() => {
            queryClient.invalidateQueries({
              queryKey: ['accommodation', 'calendar'],
            });
            queryClient.invalidateQueries({
              queryKey: ['accommodation', 'detail'],
            });
          }}
        />
      )}
    </div>
  );
}

/* ── Grid (rooms × days) ──────────────────────────────────────────────── */

interface CalendarGridProps {
  rows: { accommodation: AccommodationDetail; room: Room }[];
  days: Date[];
  viewStart: Date;
  viewEnd: Date;
  view: CalendarView;
  bookingsByRoom: Map<string, Booking[]>;
  onEmptyClick: (
    row: { accommodation: AccommodationDetail; room: Room },
    date: Date,
  ) => void;
  onBlockClick: (b: Booking) => void;
}

function CalendarGrid({
  rows,
  days,
  viewStart,
  viewEnd,
  view,
  bookingsByRoom,
  onEmptyClick,
  onBlockClick,
}: CalendarGridProps) {
  const { t } = useTranslation();
  // Use the middle day as the anchor for month-view shading. `days` is
  // never empty in practice (week=7, month=35/42) but `noUncheckedIndexedAccess`
  // makes us provide a fallback for safety.
  const anchorMonth = days[Math.floor(days.length / 2)] ?? days[0] ?? new Date();

  return (
    <div
      data-testid="accommodation-calendar-grid"
      className="overflow-x-auto rounded-2xl border border-border-light bg-surface-elevated"
    >
      <div
        style={{
          minWidth: ROOM_LABEL_WIDTH_PX + days.length * DAY_WIDTH_PX,
        }}
      >
        {/* Date header row */}
        <div
          className="sticky top-0 z-10 flex border-b border-border-light bg-surface-elevated"
          style={{ height: 56 }}
        >
          <div
            className="flex shrink-0 items-center px-3 text-xs font-semibold uppercase tracking-wide text-content-tertiary border-r border-border-light"
            style={{ width: ROOM_LABEL_WIDTH_PX }}
          >
            {t('accommodation.calendar.room_column', {
              defaultValue: 'Room',
            })}
          </div>
          <div className="flex flex-1">
            {days.map((d) => {
              const today = dfIsToday(d);
              const dim = view === 'month' && !isSameMonth(d, anchorMonth);
              return (
                <div
                  key={d.toISOString()}
                  data-testid={`accommodation-calendar-day-header-${format(d, 'yyyy-MM-dd')}`}
                  className={clsx(
                    'flex shrink-0 flex-col items-center justify-center border-r border-border-light text-xs',
                    today && 'bg-oe-blue/10',
                    dim && 'opacity-50',
                  )}
                  style={{ width: DAY_WIDTH_PX }}
                >
                  <span className="font-medium text-content-tertiary uppercase">
                    {format(d, 'EEE')}
                  </span>
                  <span
                    className={clsx(
                      'tabular-nums',
                      today
                        ? 'font-semibold text-oe-blue'
                        : 'text-content-primary',
                    )}
                  >
                    {format(d, 'd')}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Body rows */}
        <div>
          {rows.map((row, rowIdx) => {
            const roomBookings = bookingsByRoom.get(row.room.id) ?? [];
            return (
              <RoomRow
                key={row.room.id}
                row={row}
                rowIdx={rowIdx}
                days={days}
                viewStart={viewStart}
                viewEnd={viewEnd}
                view={view}
                bookings={roomBookings}
                onEmptyClick={onEmptyClick}
                onBlockClick={onBlockClick}
                showAccommodationLabel={
                  rowIdx === 0 ||
                  rows[rowIdx - 1]?.accommodation.id !== row.accommodation.id
                }
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

interface RoomRowProps {
  row: { accommodation: AccommodationDetail; room: Room };
  rowIdx: number;
  days: Date[];
  viewStart: Date;
  viewEnd: Date;
  view: CalendarView;
  bookings: Booking[];
  onEmptyClick: (
    row: { accommodation: AccommodationDetail; room: Room },
    date: Date,
  ) => void;
  onBlockClick: (b: Booking) => void;
  showAccommodationLabel: boolean;
}

function RoomRow({
  row,
  rowIdx: _rowIdx,
  days,
  viewStart,
  viewEnd,
  view,
  bookings,
  onEmptyClick,
  onBlockClick,
  showAccommodationLabel,
}: RoomRowProps) {
  const { t } = useTranslation();

  // Clip + stack bookings. We compute lanes for overlapping bookings so
  // the rare data-bug case of two bookings on the same room overlapping
  // dates is at least visually distinguishable instead of hidden.
  interface LaidOutBlock {
    booking: Booking;
    startDayIdx: number;
    spanDays: number;
    lane: number;
  }
  const blocks: LaidOutBlock[] = useMemo(() => {
    const clipped: { booking: Booking; startDayIdx: number; spanDays: number }[] = [];
    for (const b of bookings) {
      const clip = clipBookingToView(b, viewStart, viewEnd);
      if (clip) clipped.push({ booking: b, ...clip });
    }
    // Sort by start day, then by id (stable across renders).
    clipped.sort(
      (a, b) =>
        a.startDayIdx - b.startDayIdx ||
        a.booking.id.localeCompare(b.booking.id),
    );
    // Assign lanes — greedy: walk in start order, place in the first
    // lane whose previous block ended before this block starts.
    const laneEnds: number[] = [];
    return clipped.map((c) => {
      const blockEnd = c.startDayIdx + c.spanDays; // exclusive
      let assigned = -1;
      for (let i = 0; i < laneEnds.length; i += 1) {
        const end = laneEnds[i];
        if (end !== undefined && end <= c.startDayIdx) {
          assigned = i;
          break;
        }
      }
      if (assigned === -1) {
        assigned = laneEnds.length;
        laneEnds.push(blockEnd);
      } else {
        laneEnds[assigned] = blockEnd;
      }
      return { ...c, lane: assigned };
    });
  }, [bookings, viewStart, viewEnd]);

  const laneCount = Math.max(1, ...blocks.map((b) => b.lane + 1));
  const rowHeight = Math.max(ROW_HEIGHT_PX, laneCount * (ROW_HEIGHT_PX - 8) + 8);
  const anchorMonth = days[Math.floor(days.length / 2)] ?? days[0] ?? new Date();

  return (
    <div
      data-testid={`accommodation-calendar-row-${row.room.id}`}
      className="flex border-b border-border-light hover:bg-surface-secondary/30"
      style={{ height: rowHeight }}
    >
      <div
        className="flex shrink-0 flex-col justify-center px-3 border-r border-border-light"
        style={{ width: ROOM_LABEL_WIDTH_PX }}
      >
        {showAccommodationLabel && (
          <span
            className="text-2xs font-semibold uppercase tracking-wide text-content-tertiary truncate"
            title={row.accommodation.name}
          >
            {row.accommodation.name}
          </span>
        )}
        <span className="text-sm font-medium text-content-primary truncate">
          {row.room.label}
        </span>
        <span className="text-2xs text-content-tertiary">
          {t('accommodation.room.cap_short', {
            defaultValue: '{{count}} cap',
            count: row.room.capacity,
          })}
        </span>
      </div>

      <div className="relative flex-1">
        {/* Empty day cells (click-to-create) */}
        <div className="flex h-full">
          {days.map((d) => {
            const today = dfIsToday(d);
            const dim = view === 'month' && !isSameMonth(d, anchorMonth);
            return (
              <button
                key={d.toISOString()}
                type="button"
                onClick={() => onEmptyClick(row, d)}
                aria-label={t('accommodation.calendar.emptySlot', {
                  defaultValue: 'Create booking on {{date}}',
                  date: format(d, 'yyyy-MM-dd'),
                })}
                data-testid={`accommodation-calendar-cell-${row.room.id}-${format(d, 'yyyy-MM-dd')}`}
                className={clsx(
                  'group h-full shrink-0 border-r border-border-light transition focus:outline-none focus-visible:bg-oe-blue/20',
                  today && 'bg-oe-blue/5',
                  dim && 'bg-surface-secondary/20',
                  'hover:bg-oe-blue/10',
                )}
                style={{ width: DAY_WIDTH_PX }}
              >
                <span className="sr-only opacity-0 group-hover:opacity-100">
                  <Plus size={12} />
                </span>
              </button>
            );
          })}
        </div>

        {/* Booking blocks (absolutely-positioned over the cell strip) */}
        <div className="pointer-events-none absolute inset-0">
          {blocks.map(({ booking, startDayIdx, spanDays, lane }) => {
            const left = startDayIdx * DAY_WIDTH_PX + 2;
            const width = spanDays * DAY_WIDTH_PX - 4;
            const top = 4 + lane * (ROW_HEIGHT_PX - 12);
            const height = ROW_HEIGHT_PX - 16;
            const style: CSSProperties = {
              left,
              width,
              top,
              height,
            };
            const nights = bookingNights(booking);
            const tooltip = `${booking.occupant_name ?? '—'} · ${
              nights === null
                ? '∞'
                : `${nights} ${nights === 1 ? 'night' : 'nights'}`
            }`;
            return (
              <button
                key={booking.id}
                type="button"
                onClick={() => onBlockClick(booking)}
                title={tooltip}
                data-testid={`accommodation-calendar-block-${booking.id}`}
                style={style}
                className={clsx(
                  'pointer-events-auto absolute flex items-center overflow-hidden truncate rounded-md border px-2 text-xs font-medium shadow-sm transition hover:scale-[1.02] hover:shadow focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue',
                  STATE_BLOCK_CLASS[booking.status],
                )}
              >
                <span className="truncate">
                  {booking.occupant_name ??
                    t('accommodation.bookings.unnamed_occupant', {
                      defaultValue: '(unnamed)',
                    })}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ── Create-booking modal ────────────────────────────────────────────── */

interface CreateBookingModalProps {
  room: Room;
  accommodationName: string;
  defaultCheckIn: string;
  onClose: () => void;
  onCreated: () => void;
}

function CreateBookingModal({
  room,
  accommodationName,
  defaultCheckIn,
  onClose,
  onCreated,
}: CreateBookingModalProps) {
  const { t } = useTranslation();
  const addToast = useToastStore((s) => s.addToast);
  const [contactId, setContactId] = useState('');
  const [contactName, setContactName] = useState('');
  const [occupantName, setOccupantName] = useState('');
  const [checkIn, setCheckIn] = useState(defaultCheckIn);
  const [checkOut, setCheckOut] = useState('');

  const mutation = useMutation({
    mutationFn: () =>
      createBooking(room.id, {
        occupant_contact_id: contactId || null,
        occupant_name: occupantName.trim() || contactName || null,
        check_in: checkIn,
        check_out: checkOut || null,
        status: 'reserved',
        source: 'manual',
      }),
    onSuccess: () => {
      addToast({
        type: 'success',
        title: t('accommodation.booking.created_toast', {
          defaultValue: 'Booking created',
        }),
      });
      onCreated();
    },
    onError: (err) =>
      addToast({
        type: 'error',
        title: t('accommodation.booking.create_failed', {
          defaultValue: 'Could not create booking',
        }),
        message: getErrorMessage(err),
      }),
  });

  const inputCls =
    'h-10 w-full rounded-lg border border-border bg-surface-primary px-3 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue';

  const disabled = room.status === 'maintenance' || room.status === 'blocked';

  return (
    <WideModal
      open
      onClose={onClose}
      title={t('accommodation.calendar.createBooking', {
        defaultValue: 'Create booking — {{room}} ({{acc}})',
        room: room.label,
        acc: accommodationName,
      })}
      size="md"
      busy={mutation.isPending}
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose}>
            {t('common.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
            disabled={disabled || (!contactId && !occupantName.trim())}
            data-testid="accommodation-calendar-create-submit"
          >
            {t('accommodation.assign.confirm', {
              defaultValue: 'Create booking',
            })}
          </Button>
        </>
      }
    >
      {disabled && (
        <div className="mb-3 rounded-xl border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900">
          <AlertTriangle className="mr-1.5 inline h-3.5 w-3.5" />
          {t('accommodation.assign.disabled', {
            defaultValue:
              'Room is {{status}} — change its status before booking.',
            status: room.status,
          })}
        </div>
      )}
      <WideModalSection columns={2}>
        <WideModalField
          label={t('accommodation.assign.contact', {
            defaultValue: 'Contact (optional)',
          })}
          span={2}
        >
          <ContactSearchInput
            value={contactId}
            displayValue={contactName}
            onChange={(id, name) => {
              setContactId(id);
              setContactName(name);
            }}
          />
        </WideModalField>
        <WideModalField
          label={t('accommodation.assign.occupant_name', {
            defaultValue: 'Or occupant name',
          })}
          hint={t('accommodation.assign.either_or', {
            defaultValue: 'Provide a contact or a free-text name.',
          })}
          span={2}
        >
          <input
            type="text"
            value={occupantName}
            onChange={(e) => setOccupantName(e.target.value)}
            className={inputCls}
            data-testid="accommodation-calendar-occupant-name"
          />
        </WideModalField>
        <WideModalField
          label={t('accommodation.assign.check_in', {
            defaultValue: 'Check-in',
          })}
          required
        >
          <input
            type="date"
            value={checkIn}
            onChange={(e) => setCheckIn(e.target.value)}
            className={inputCls}
            data-testid="accommodation-calendar-check-in"
          />
        </WideModalField>
        <WideModalField
          label={t('accommodation.assign.check_out', {
            defaultValue: 'Check-out (optional)',
          })}
        >
          <input
            type="date"
            value={checkOut}
            onChange={(e) => setCheckOut(e.target.value)}
            className={inputCls}
            data-testid="accommodation-calendar-check-out"
          />
        </WideModalField>
      </WideModalSection>
    </WideModal>
  );
}

/* ── Booking detail drawer (state-machine actions) ───────────────────── */

interface BookingDetailDrawerProps {
  bookingId: string;
  onClose: () => void;
  onMutated: () => void;
}

function BookingDetailDrawer({
  bookingId,
  onClose,
  onMutated,
}: BookingDetailDrawerProps) {
  const { t } = useTranslation();
  const addToast = useToastStore((s) => s.addToast);
  const [confirmTarget, setConfirmTarget] = useState<BookingStatus | null>(null);
  const drawerRef = useRef<HTMLDivElement>(null);

  const detailQuery = useQuery({
    queryKey: ['accommodation', 'booking-detail', bookingId],
    queryFn: () => getBooking(bookingId),
  });

  const mutation = useMutation({
    mutationFn: (target: BookingStatus) =>
      updateBooking(bookingId, { status: target }),
    onSuccess: (_data, target) => {
      addToast({
        type: 'success',
        title: t(`accommodation.booking.transition_toast.${target}`, {
          defaultValue: 'Booking updated',
        }),
      });
      detailQuery.refetch();
      onMutated();
    },
    onError: (err) =>
      addToast({
        type: 'error',
        title: t('accommodation.booking.update_failed', {
          defaultValue: 'Could not update booking',
        }),
        message: getErrorMessage(err),
      }),
  });

  const handleAction = (target: BookingStatus) => {
    if (target === 'checked_out' || target === 'cancelled') {
      setConfirmTarget(target);
      return;
    }
    mutation.mutate(target);
  };

  // Escape-to-close.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const data = detailQuery.data;
  const nights = data ? bookingNights(data) : null;
  const totalCharges = data ? sumChargesString(data.charges) : null;
  const actions = data && !isBookingTerminal(data.status)
    ? allowedBookingTransitions(data.status)
    : [];

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/40"
        onClick={onClose}
        aria-hidden="true"
      />
      {/* Drawer */}
      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label={t('accommodation.calendar.booking_drawer_aria', {
          defaultValue: 'Booking details',
        })}
        data-testid="accommodation-calendar-booking-drawer"
        className="fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col bg-surface-elevated shadow-2xl"
      >
        <div className="flex items-start justify-between border-b border-border-light p-4">
          <div>
            <h2 className="text-base font-semibold text-content-primary">
              {t('accommodation.calendar.booking_drawer_title', {
                defaultValue: 'Booking details',
              })}
            </h2>
            {data && (
              <p className="mt-0.5 text-xs text-content-tertiary font-mono break-all">
                {data.id}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('common.close', { defaultValue: 'Close' })}
            className="rounded-md p-1 text-content-tertiary hover:bg-surface-secondary"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {detailQuery.isLoading && (
            <div className="flex items-center justify-center py-10 text-content-tertiary">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
          )}
          {detailQuery.isError && (
            <div className="rounded-xl border border-semantic-error/30 bg-semantic-error/10 p-3 text-sm text-semantic-error">
              <AlertTriangle className="mr-2 inline h-4 w-4" />
              {getErrorMessage(detailQuery.error)}
            </div>
          )}
          {data && (
            <>
              <div className="flex items-center gap-2">
                <Badge
                  variant={
                    data.status === 'checked_in'
                      ? 'success'
                      : data.status === 'reserved'
                        ? 'warning'
                        : data.status === 'cancelled'
                          ? 'error'
                          : 'neutral'
                  }
                  size="sm"
                >
                  {t(`accommodation.booking.status.${data.status}`, {
                    defaultValue: data.status,
                  })}
                </Badge>
                <span className="text-xs text-content-tertiary">
                  {t(`accommodation.booking.source.${data.source}`, {
                    defaultValue: data.source,
                  })}
                </span>
              </div>

              <dl className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <dt className="text-xs font-medium text-content-tertiary uppercase tracking-wide">
                    {t('accommodation.calendar.guest', {
                      defaultValue: 'Guest',
                    })}
                  </dt>
                  <dd className="text-content-primary">
                    {data.occupant_name ??
                      t('accommodation.bookings.unnamed_occupant', {
                        defaultValue: '(unnamed)',
                      })}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-medium text-content-tertiary uppercase tracking-wide">
                    {t('accommodation.calendar.nights', {
                      defaultValue: 'Nights',
                    })}
                  </dt>
                  <dd
                    className="text-content-primary tabular-nums"
                    data-testid="accommodation-calendar-drawer-nights"
                  >
                    {nights === null ? '∞' : nights}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-medium text-content-tertiary uppercase tracking-wide">
                    {t('accommodation.bookings.col.check_in', {
                      defaultValue: 'Check-in',
                    })}
                  </dt>
                  <dd className="text-content-primary tabular-nums">
                    {data.check_in}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-medium text-content-tertiary uppercase tracking-wide">
                    {t('accommodation.bookings.col.check_out', {
                      defaultValue: 'Check-out',
                    })}
                  </dt>
                  <dd className="text-content-primary tabular-nums">
                    {data.check_out ?? '—'}
                  </dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-xs font-medium text-content-tertiary uppercase tracking-wide">
                    {t('accommodation.calendar.total', {
                      defaultValue: 'Total charges',
                    })}
                  </dt>
                  <dd
                    className="text-content-primary tabular-nums font-mono"
                    data-testid="accommodation-calendar-drawer-total"
                  >
                    {totalCharges ?? '—'}{' '}
                    <span className="text-xs text-content-tertiary">
                      ({data.charges.length})
                    </span>
                  </dd>
                </div>
              </dl>
            </>
          )}
        </div>

        {data && actions.length > 0 && (
          <div className="border-t border-border-light p-3 flex flex-wrap gap-2 justify-end">
            {actions.map((target) => (
              <Button
                key={target}
                variant={target === 'cancelled' ? 'danger' : 'primary'}
                size="sm"
                onClick={() => handleAction(target)}
                loading={mutation.isPending && mutation.variables === target}
                data-testid={`accommodation-calendar-drawer-action-${target}`}
              >
                {t(`accommodation.booking.actions.${target}`, {
                  defaultValue:
                    target === 'checked_in'
                      ? 'Check in'
                      : target === 'checked_out'
                        ? 'Check out'
                        : target === 'cancelled'
                          ? 'Cancel booking'
                          : target,
                })}
              </Button>
            ))}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={!!confirmTarget}
        onCancel={() => setConfirmTarget(null)}
        onConfirm={() => {
          if (!confirmTarget) return;
          mutation.mutate(confirmTarget);
          setConfirmTarget(null);
        }}
        title={
          confirmTarget === 'cancelled'
            ? t('accommodation.confirm.cancel_booking_title', {
                defaultValue: 'Cancel this booking?',
              })
            : t('accommodation.confirm.checkout_title', {
                defaultValue: 'Check out this booking?',
              })
        }
        message={
          confirmTarget === 'cancelled'
            ? t('accommodation.confirm.cancel_booking_message', {
                defaultValue:
                  'Cancelling locks the booking — no further status changes are possible.',
              })
            : t('accommodation.confirm.checkout_message', {
                defaultValue:
                  'Checking out closes the stay. The booking moves to a terminal state and the room returns to "available".',
              })
        }
        confirmLabel={
          confirmTarget === 'cancelled'
            ? t('accommodation.booking.actions.cancel', {
                defaultValue: 'Cancel booking',
              })
            : t('accommodation.booking.actions.check_out', {
                defaultValue: 'Check out',
              })
        }
        variant={confirmTarget === 'cancelled' ? 'danger' : 'warning'}
        loading={mutation.isPending}
      />
    </>
  );
}
