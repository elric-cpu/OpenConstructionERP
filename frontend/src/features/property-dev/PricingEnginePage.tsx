/**
 * Pricing Engine — versioned, rule-driven property-dev sales pricing.
 *
 * Backed by /api/v1/property-dev/{developments,price-lists}/... (see
 * backend/app/modules/property_dev/router.py — pricing engine section).
 *
 * Four tabs:
 *   1. Price Lists  — table of versions (draft/active/superseded) + create form.
 *   2. Rules        — editor for the currently-active list (CRUD + reorder).
 *   3. Simulator    — pick plot + promo + buyer → live PriceQuote with waterfall.
 *   4. Quote History — historical `price_breakdown_snapshot` from reservations.
 *
 * i18n: EN + DE + RU strings live in `app/locales`; the other 17 locales
 * fall back to EN via i18next default (marked `// TODO_TRANSLATE` below).
 * Tabs collapse to a dropdown <768px.
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import {
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import clsx from 'clsx';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  AlertOctagon,
  CheckCircle2,
  ChevronUp,
  ChevronDown,
  History,
  Loader2,
  PlayCircle,
  Plus,
  Receipt,
  Settings2,
  Sparkles,
  Trash2,
} from 'lucide-react';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  SkeletonTable,
} from '@/shared/ui';
import { useTabKeyboardNav } from '@/shared/hooks/useTabKeyboardNav';
import { useToastStore } from '@/stores/useToastStore';
import { getErrorMessage } from '@/shared/lib/api';
import {
  activatePriceList,
  createPriceList,
  createPricingRule,
  deletePricingRule,
  listPlots,
  listPriceLists,
  listPricingRules,
  listReservations,
  quotePrice,
  updatePricingRule,
  type CreatePricingRulePayload,
  type PriceList,
  type PriceQuote,
  type PricingRule,
  type PricingRuleType,
  type Plot,
  type Reservation,
} from './api';

const RULE_TYPES: PricingRuleType[] = [
  'early_bird',
  'view_premium',
  'floor_premium',
  'corner_premium',
  'size_premium',
  'promo_code',
  'friends_family',
  'loyalty',
  'bulk_buy',
];

type Tab = 'lists' | 'rules' | 'sim' | 'history';
const PRICING_TAB_IDS: readonly Tab[] = ['lists', 'rules', 'sim', 'history'];

const inputCls =
  'h-9 w-full rounded-lg border border-border bg-surface-primary px-3 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue';
const labelCls =
  'block text-xs font-medium text-content-secondary mb-1';

function fmtMoney(amount: string | number, currency: string): string {
  const n = typeof amount === 'string' ? Number(amount) : amount;
  if (!Number.isFinite(n)) return String(amount);
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: currency || 'EUR',
      maximumFractionDigits: 2,
    }).format(n);
  } catch {
    return `${n.toFixed(2)} ${currency}`;
  }
}

function statusBadge(status: PriceList['status']): JSX.Element {
  const map: Record<PriceList['status'], { variant: 'success' | 'warning' | 'neutral'; label: string }> = {
    active: { variant: 'success', label: 'Active' },
    draft: { variant: 'warning', label: 'Draft' },
    superseded: { variant: 'neutral', label: 'Superseded' },
  };
  const m = map[status];
  return <Badge variant={m.variant}>{m.label}</Badge>;
}

// ── Tabs (compact responsive) ────────────────────────────────────────

interface TabsProps {
  tab: Tab;
  setTab: (t: Tab) => void;
}

function Tabs({ tab, setTab }: TabsProps): JSX.Element {
  const { t } = useTranslation();
  const onTabKeyDown = useTabKeyboardNav<Tab>({
    ids: PRICING_TAB_IDS,
    activeId: tab,
    onChange: setTab,
    orientation: 'horizontal',
  });
  const items: Array<{ key: Tab; icon: JSX.Element; label: string }> = [
    {
      key: 'lists',
      icon: <Receipt className="h-4 w-4" />,
      label: t('propdev.pricing.tab.lists', 'Price Lists'),
    },
    {
      key: 'rules',
      icon: <Settings2 className="h-4 w-4" />,
      label: t('propdev.pricing.tab.rules', 'Rules'),
    },
    {
      key: 'sim',
      icon: <Sparkles className="h-4 w-4" />,
      label: t('propdev.pricing.tab.sim', 'Simulator'),
    },
    {
      key: 'history',
      icon: <History className="h-4 w-4" />,
      label: t('propdev.pricing.tab.history', 'Quote History'),
    },
  ];
  return (
    <>
      {/* Mobile dropdown */}
      <div className="md:hidden">
        <select
          aria-label={t('propdev.pricing.tabs_aria', {
            defaultValue: 'Pricing engine sections',
          })}
          className={inputCls}
          value={tab}
          onChange={(e) => setTab(e.target.value as Tab)}
        >
          {items.map((it) => (
            <option key={it.key} value={it.key}>
              {it.label}
            </option>
          ))}
        </select>
      </div>
      {/* Desktop tab bar */}
      <div
        role="tablist"
        aria-label={t('propdev.pricing.tabs_aria', {
          defaultValue: 'Pricing engine sections',
        })}
        onKeyDown={onTabKeyDown}
        className="hidden md:flex items-center gap-1 border-b border-border"
      >
        {items.map((it) => (
          <button
            key={it.key}
            type="button"
            role="tab"
            id={`pricing-tab-${it.key}`}
            aria-selected={tab === it.key}
            aria-controls={`pricing-panel-${it.key}`}
            tabIndex={tab === it.key ? 0 : -1}
            onClick={() => setTab(it.key)}
            className={clsx(
              'flex items-center gap-2 px-3 py-2 -mb-px text-sm',
              tab === it.key
                ? 'border-b-2 border-oe-blue text-content-primary font-medium'
                : 'text-content-secondary hover:text-content-primary',
            )}
          >
            {it.icon}
            {it.label}
          </button>
        ))}
      </div>
    </>
  );
}

// ── Price Lists tab ──────────────────────────────────────────────────

interface PriceListsTabProps {
  devId: string;
}

function PriceListsTab({ devId }: PriceListsTabProps): JSX.Element {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    name: '',
    effective_from: new Date().toISOString().slice(0, 10),
    currency: 'EUR',
    notes: '',
  });

  const listsQuery = useQuery<PriceList[]>({
    queryKey: ['propdev', 'price-lists', devId],
    queryFn: () => listPriceLists(devId),
    enabled: Boolean(devId),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createPriceList(devId, {
        name: form.name.trim(),
        effective_from: form.effective_from,
        currency: form.currency.trim().toUpperCase(),
        notes: form.notes.trim() || null,
        entries: [],
        rules: [],
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['propdev', 'price-lists', devId] });
      addToast({
        type: 'success',
        title: t('propdev.pricing.created', 'Price list created'),
      });
      setShowForm(false);
      setForm((f) => ({ ...f, name: '', notes: '' }));
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });

  const activateMutation = useMutation({
    mutationFn: (id: string) => activatePriceList(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['propdev', 'price-lists', devId] });
      addToast({
        type: 'success',
        title: t('propdev.pricing.activated', 'Price list activated'),
      });
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });

  const rows = listsQuery.data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">
          {t('propdev.pricing.lists_title', 'Price lists')}
        </h2>
        <Button
          variant="primary"
          icon={<Plus className="h-4 w-4" />}
          onClick={() => setShowForm((v) => !v)}
        >
          {showForm
            ? t('common.cancel', 'Cancel')
            : t('propdev.pricing.new', 'New price list')}
        </Button>
      </div>

      {showForm && (
        <Card padding="md">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className={labelCls} htmlFor="pl-name">
                {t('propdev.pricing.name', 'Name')}
              </label>
              <input
                id="pl-name"
                className={inputCls}
                value={form.name}
                onChange={(e) =>
                  setForm((f) => ({ ...f, name: e.target.value }))
                }
              />
            </div>
            <div>
              <label className={labelCls} htmlFor="pl-from">
                {t('propdev.pricing.effective_from', 'Effective from')}
              </label>
              <input
                id="pl-from"
                type="date"
                className={inputCls}
                value={form.effective_from}
                onChange={(e) =>
                  setForm((f) => ({ ...f, effective_from: e.target.value }))
                }
              />
            </div>
            <div>
              <label className={labelCls} htmlFor="pl-cur">
                {t('propdev.pricing.currency', 'Currency')}
              </label>
              <input
                id="pl-cur"
                className={inputCls}
                maxLength={3}
                value={form.currency}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    currency: e.target.value.toUpperCase(),
                  }))
                }
              />
            </div>
            <div className="sm:col-span-2">
              <label className={labelCls} htmlFor="pl-notes">
                {t('propdev.pricing.notes', 'Notes')}
              </label>
              <textarea
                id="pl-notes"
                className={clsx(inputCls, 'h-20')}
                value={form.notes}
                onChange={(e) =>
                  setForm((f) => ({ ...f, notes: e.target.value }))
                }
              />
            </div>
          </div>
          <div className="mt-3 flex justify-end">
            <Button
              variant="primary"
              disabled={
                !form.name.trim() || createMutation.isPending
              }
              onClick={() => createMutation.mutate()}
              icon={
                createMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : undefined
              }
            >
              {t('common.create', 'Create')}
            </Button>
          </div>
        </Card>
      )}

      {listsQuery.isLoading ? (
        <SkeletonTable rows={3} columns={4} />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={<Receipt className="h-8 w-8" />}
          title={t('propdev.pricing.empty_lists', 'No price lists yet')}
          description={t(
            'propdev.pricing.empty_lists_desc',
            'Create a draft list, add per-plot prices and rules, then activate it to start quoting.',
          )}
        />
      ) : (
        <Card padding="none" className="overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-surface-secondary text-left text-xs uppercase tracking-wide text-content-secondary">
              <tr>
                <th className="px-3 py-2">{t('propdev.pricing.name', 'Name')}</th>
                <th className="px-3 py-2">
                  {t('propdev.pricing.status', 'Status')}
                </th>
                <th className="px-3 py-2">
                  {t('propdev.pricing.effective_from', 'Effective from')}
                </th>
                <th className="px-3 py-2">
                  {t('propdev.pricing.currency', 'Currency')}
                </th>
                <th className="px-3 py-2 text-right">
                  {t('common.actions', 'Actions')}
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((pl) => (
                <tr key={pl.id} className="border-t border-border">
                  <td className="px-3 py-2 font-medium">{pl.name}</td>
                  <td className="px-3 py-2">{statusBadge(pl.status)}</td>
                  <td className="px-3 py-2">{pl.effective_from}</td>
                  <td className="px-3 py-2">{pl.currency}</td>
                  <td className="px-3 py-2 text-right">
                    {pl.status === 'draft' && (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => activateMutation.mutate(pl.id)}
                        disabled={activateMutation.isPending}
                      >
                        {t('propdev.pricing.activate', 'Activate')}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

// ── Rules tab ────────────────────────────────────────────────────────

interface RulesTabProps {
  devId: string;
}

function defaultConditionFor(type: PricingRuleType): Record<string, unknown> {
  switch (type) {
    case 'early_bird':
      return { before: new Date().toISOString().slice(0, 10) };
    case 'view_premium':
      return { plot_attribute: 'view', values: ['sea'] };
    case 'floor_premium':
      return { min_floor: 10 };
    case 'corner_premium':
      return { plot_attribute: 'is_corner', value: true };
    case 'size_premium':
      return { min_area_m2: '100' };
    case 'promo_code':
      return { code: 'LAUNCH' };
    case 'friends_family':
      return { buyer_tag: 'ff' };
    case 'loyalty':
      return { prior_purchases_min: 1 };
    case 'bulk_buy':
      return { min_plots: 3 };
  }
}

function RulesTab({ devId }: RulesTabProps): JSX.Element {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);

  const listsQuery = useQuery<PriceList[]>({
    queryKey: ['propdev', 'price-lists', devId],
    queryFn: () => listPriceLists(devId),
    enabled: Boolean(devId),
  });
  const active = useMemo(
    () => (listsQuery.data ?? []).find((p) => p.status === 'active') ?? null,
    [listsQuery.data],
  );

  const rulesQuery = useQuery<PricingRule[]>({
    queryKey: ['propdev', 'pricing-rules', active?.id],
    queryFn: () => listPricingRules(active!.id),
    enabled: Boolean(active?.id),
  });

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<CreatePricingRulePayload>({
    name: '',
    rule_type: 'early_bird',
    condition_json: defaultConditionFor('early_bird'),
    adjustment_pct: '0',
    adjustment_fixed: null,
    priority: 100,
    active: true,
    effective_from: '',
    effective_to: null,
    max_uses: null,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createPricingRule(active!.id, {
        ...form,
        adjustment_fixed:
          form.adjustment_fixed && String(form.adjustment_fixed).trim() !== ''
            ? form.adjustment_fixed
            : null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: ['propdev', 'pricing-rules', active?.id],
      });
      addToast({
        type: 'success',
        title: t('propdev.pricing.rule_created', 'Rule created'),
      });
      setShowForm(false);
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });

  const deleteMutation = useMutation({
    mutationFn: (ruleId: string) => deletePricingRule(active!.id, ruleId),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: ['propdev', 'pricing-rules', active?.id],
      });
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });

  const reorderMutation = useMutation({
    mutationFn: (params: { ruleId: string; priority: number }) =>
      updatePricingRule(active!.id, params.ruleId, {
        priority: params.priority,
      }),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: ['propdev', 'pricing-rules', active?.id],
      });
    },
    onError: (err) => addToast({ type: 'error', title: getErrorMessage(err) }),
  });

  if (!active) {
    return (
      <EmptyState
        icon={<Settings2 className="h-8 w-8" />}
        title={t(
          'propdev.pricing.no_active',
          'No active price list',
        )}
        description={t(
          'propdev.pricing.no_active_desc',
          'Activate a draft list on the Price Lists tab to start editing its rules.',
        )}
      />
    );
  }

  const rules = rulesQuery.data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">
            {t('propdev.pricing.rules_title', 'Rules')}{' '}
            <span className="text-sm font-normal text-content-secondary">
              ({active.name})
            </span>
          </h2>
          <p className="text-xs text-content-secondary">
            {t(
              'propdev.pricing.rules_hint',
              'Lower priority value applies first. Click the up/down arrows to reorder.',
            )}
          </p>
        </div>
        <Button
          variant="primary"
          icon={<Plus className="h-4 w-4" />}
          onClick={() => setShowForm((v) => !v)}
        >
          {showForm
            ? t('common.cancel', 'Cancel')
            : t('propdev.pricing.new_rule', 'New rule')}
        </Button>
      </div>

      {showForm && (
        <Card padding="md">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className={labelCls} htmlFor="rule-name">
                {t('propdev.pricing.rule_name', 'Rule name')}
              </label>
              <input
                id="rule-name"
                className={inputCls}
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              />
            </div>
            <div>
              <label className={labelCls} htmlFor="rule-type">
                {t('propdev.pricing.rule_type', 'Rule type')}
              </label>
              <select
                id="rule-type"
                className={inputCls}
                value={form.rule_type}
                onChange={(e) => {
                  const next = e.target.value as PricingRuleType;
                  setForm((f) => ({
                    ...f,
                    rule_type: next,
                    condition_json: defaultConditionFor(next),
                  }));
                }}
              >
                {RULE_TYPES.map((t2) => (
                  <option key={t2} value={t2}>
                    {t2}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelCls} htmlFor="rule-pct">
                {t('propdev.pricing.adj_pct', 'Adjustment %')}
              </label>
              <input
                id="rule-pct"
                className={inputCls}
                inputMode="decimal"
                value={String(form.adjustment_pct)}
                onChange={(e) =>
                  setForm((f) => ({ ...f, adjustment_pct: e.target.value }))
                }
                placeholder="-5 = 5% off"
              />
            </div>
            <div>
              <label className={labelCls} htmlFor="rule-fixed">
                {t('propdev.pricing.adj_fixed', 'Fixed adjustment')}
              </label>
              <input
                id="rule-fixed"
                className={inputCls}
                inputMode="decimal"
                value={String(form.adjustment_fixed ?? '')}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    adjustment_fixed: e.target.value || null,
                  }))
                }
                placeholder="-2500"
              />
            </div>
            <div>
              <label className={labelCls} htmlFor="rule-prio">
                {t('propdev.pricing.priority', 'Priority (lower applies first)')}
              </label>
              <input
                id="rule-prio"
                type="number"
                className={inputCls}
                value={form.priority}
                onChange={(e) =>
                  setForm((f) => ({ ...f, priority: Number(e.target.value) }))
                }
              />
            </div>
            <div>
              <label className={labelCls} htmlFor="rule-max">
                {t('propdev.pricing.max_uses', 'Max uses (blank = unlimited)')}
              </label>
              <input
                id="rule-max"
                type="number"
                className={inputCls}
                value={form.max_uses ?? ''}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    max_uses: e.target.value ? Number(e.target.value) : null,
                  }))
                }
              />
            </div>
            <div className="sm:col-span-2">
              <label className={labelCls} htmlFor="rule-cond">
                {t(
                  'propdev.pricing.condition',
                  'Condition (JSON)',
                )}
              </label>
              <textarea
                id="rule-cond"
                className={clsx(inputCls, 'h-24 font-mono')}
                value={JSON.stringify(form.condition_json, null, 2)}
                onChange={(e) => {
                  try {
                    const parsed = JSON.parse(e.target.value);
                    setForm((f) => ({ ...f, condition_json: parsed }));
                  } catch {
                    /* swallow — user is still typing */
                  }
                }}
              />
            </div>
          </div>
          <div className="mt-3 flex justify-end">
            <Button
              variant="primary"
              onClick={() => createMutation.mutate()}
              disabled={!form.name.trim() || createMutation.isPending}
            >
              {t('common.create', 'Create')}
            </Button>
          </div>
        </Card>
      )}

      {rulesQuery.isLoading ? (
        <SkeletonTable rows={3} columns={5} />
      ) : rules.length === 0 ? (
        <EmptyState
          icon={<Settings2 className="h-8 w-8" />}
          title={t('propdev.pricing.empty_rules', 'No rules yet')}
          description={t(
            'propdev.pricing.empty_rules_desc',
            'Add a rule to apply discounts and premiums on top of the base price.',
          )}
        />
      ) : (
        <Card padding="none" className="overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-surface-secondary text-left text-xs uppercase tracking-wide text-content-secondary">
              <tr>
                <th className="px-3 py-2 w-12">
                  {t('propdev.pricing.priority_short', 'Pri')}
                </th>
                <th className="px-3 py-2">{t('propdev.pricing.rule_name', 'Name')}</th>
                <th className="px-3 py-2">{t('propdev.pricing.rule_type', 'Type')}</th>
                <th className="px-3 py-2">{t('propdev.pricing.adj_pct', 'Adj %')}</th>
                <th className="px-3 py-2">{t('propdev.pricing.adj_fixed', 'Fixed')}</th>
                <th className="px-3 py-2">{t('propdev.pricing.uses', 'Uses')}</th>
                <th className="px-3 py-2 text-right">
                  {t('common.actions', 'Actions')}
                </th>
              </tr>
            </thead>
            <tbody>
              {rules.map((r, idx) => (
                <tr key={r.id} className="border-t border-border">
                  <td className="px-3 py-2">
                    <div className="flex flex-col items-center">
                      <button
                        type="button"
                        aria-label="move up"
                        disabled={idx === 0}
                        onClick={() =>
                          reorderMutation.mutate({
                            ruleId: r.id,
                            priority: Math.max(0, r.priority - 10),
                          })
                        }
                        className="text-content-secondary hover:text-content-primary disabled:opacity-30"
                      >
                        <ChevronUp className="h-3 w-3" />
                      </button>
                      <span className="text-xs">{r.priority}</span>
                      <button
                        type="button"
                        aria-label="move down"
                        disabled={idx === rules.length - 1}
                        onClick={() =>
                          reorderMutation.mutate({
                            ruleId: r.id,
                            priority: r.priority + 10,
                          })
                        }
                        className="text-content-secondary hover:text-content-primary disabled:opacity-30"
                      >
                        <ChevronDown className="h-3 w-3" />
                      </button>
                    </div>
                  </td>
                  <td className="px-3 py-2 font-medium">{r.name}</td>
                  <td className="px-3 py-2 text-content-secondary">{r.rule_type}</td>
                  <td className="px-3 py-2">{r.adjustment_pct ?? '0'}</td>
                  <td className="px-3 py-2">{r.adjustment_fixed ?? '—'}</td>
                  <td className="px-3 py-2 text-content-secondary">
                    {r.times_used}
                    {r.max_uses ? `/${r.max_uses}` : ''}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      icon={<Trash2 className="h-3 w-3" />}
                      onClick={() => deleteMutation.mutate(r.id)}
                      aria-label="delete rule"
                    >
                      {t('common.delete', 'Delete')}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

// ── Simulator tab ────────────────────────────────────────────────────

function SimulatorTab({ devId }: { devId: string }): JSX.Element {
  const { t } = useTranslation();
  const [plotId, setPlotId] = useState<string>('');
  const [promo, setPromo] = useState('');
  const [quote, setQuote] = useState<PriceQuote | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const listsQuery = useQuery<PriceList[]>({
    queryKey: ['propdev', 'price-lists', devId],
    queryFn: () => listPriceLists(devId),
    enabled: Boolean(devId),
  });
  const active = useMemo(
    () => (listsQuery.data ?? []).find((p) => p.status === 'active') ?? null,
    [listsQuery.data],
  );
  const plotsQuery = useQuery<Plot[]>({
    queryKey: ['propdev', 'plots', devId, 'simulator'],
    queryFn: () => listPlots({ development_id: devId, limit: 500 }),
    enabled: Boolean(devId),
  });

  useEffect(() => {
    if (!plotId && (plotsQuery.data ?? []).length > 0) {
      setPlotId(plotsQuery.data![0].id);
    }
  }, [plotsQuery.data, plotId]);

  const runQuote = async (): Promise<void> => {
    if (!active || !plotId) return;
    setBusy(true);
    setErr(null);
    try {
      const q = await quotePrice({
        priceListId: active.id,
        plot_id: plotId,
        promo_code: promo || undefined,
      });
      setQuote(q);
    } catch (e) {
      setErr(getErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  if (!active) {
    return (
      <EmptyState
        icon={<Sparkles className="h-8 w-8" />}
        title={t('propdev.pricing.no_active', 'No active price list')}
        description={t(
          'propdev.pricing.sim_no_active_desc',
          'Activate a price list to use the simulator.',
        )}
      />
    );
  }

  const chartData = (quote?.lines ?? []).map((l, i) => {
    const value = Number(l.amount);
    return {
      idx: i,
      name: l.rule_name || l.rule_type,
      value,
      isBase: l.rule_type === 'base',
      isDiscount: value < 0,
    };
  });

  return (
    <div className="space-y-4">
      <Card padding="md">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div>
            <label className={labelCls} htmlFor="sim-plot">
              {t('propdev.pricing.sim_plot', 'Plot')}
            </label>
            <select
              id="sim-plot"
              className={inputCls}
              value={plotId}
              onChange={(e) => setPlotId(e.target.value)}
            >
              <option value="">
                {t('common.select', 'Select…')}
              </option>
              {(plotsQuery.data ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.plot_number}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelCls} htmlFor="sim-promo">
              {t('propdev.pricing.sim_promo', 'Promo code (optional)')}
            </label>
            <input
              id="sim-promo"
              className={inputCls}
              value={promo}
              onChange={(e) => setPromo(e.target.value)}
            />
          </div>
          <div className="flex items-end">
            <Button
              variant="primary"
              icon={
                busy ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <PlayCircle className="h-4 w-4" />
                )
              }
              onClick={runQuote}
              disabled={busy || !plotId}
            >
              {t('propdev.pricing.compute', 'Compute quote')}
            </Button>
          </div>
        </div>
        {err && (
          <p className="mt-3 text-sm text-rose-600 flex items-center gap-2">
            <AlertOctagon className="h-4 w-4" />
            {err}
          </p>
        )}
      </Card>

      {quote && (
        <Card padding="md">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-wide text-content-secondary">
                {t('propdev.pricing.final_price', 'Final price')}
              </p>
              <p className="text-2xl font-semibold">
                {fmtMoney(quote.total, quote.currency)}
              </p>
            </div>
            <CheckCircle2 className="h-6 w-6 text-emerald-500" />
          </div>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip
                  formatter={(value: number) => fmtMoney(value, quote.currency)}
                />
                <Bar dataKey="value">
                  {chartData.map((d) => (
                    <Cell
                      key={d.idx}
                      fill={
                        d.isBase
                          ? '#0070f3'
                          : d.isDiscount
                            ? '#ef4444'
                            : '#22c55e'
                      }
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <table className="mt-4 w-full text-sm">
            <thead className="bg-surface-secondary text-left text-xs uppercase tracking-wide text-content-secondary">
              <tr>
                <th className="px-3 py-2">
                  {t('propdev.pricing.line', 'Line')}
                </th>
                <th className="px-3 py-2">
                  {t('propdev.pricing.rule_type', 'Type')}
                </th>
                <th className="px-3 py-2 text-right">
                  {t('propdev.pricing.amount', 'Amount')}
                </th>
              </tr>
            </thead>
            <tbody>
              {quote.lines.map((l, i) => (
                <tr key={i} className="border-t border-border">
                  <td className="px-3 py-2">{l.rule_name || l.rule_type}</td>
                  <td className="px-3 py-2 text-content-secondary">
                    {l.rule_type}
                  </td>
                  <td
                    className={clsx(
                      'px-3 py-2 text-right tabular-nums',
                      Number(l.amount) < 0
                        ? 'text-rose-600'
                        : l.rule_type === 'base'
                          ? ''
                          : 'text-emerald-600',
                    )}
                  >
                    {fmtMoney(l.amount, quote.currency)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

// ── Quote History tab ────────────────────────────────────────────────

function QuoteHistoryTab({ devId }: { devId: string }): JSX.Element {
  const { t } = useTranslation();
  const reservationsQuery = useQuery<Reservation[]>({
    queryKey: ['propdev', 'reservations', devId, 'history'],
    queryFn: () =>
      listReservations({ development_id: devId, limit: 200 }) as Promise<
        Reservation[]
      >,
    enabled: Boolean(devId),
  });
  const rows = (reservationsQuery.data ?? []).filter(
    (r) =>
      r.price_breakdown_snapshot &&
      Object.keys(r.price_breakdown_snapshot).length > 0,
  );

  if (reservationsQuery.isLoading) return <SkeletonTable rows={4} columns={4} />;
  if (rows.length === 0) {
    return (
      <EmptyState
        icon={<History className="h-8 w-8" />}
        title={t(
          'propdev.pricing.empty_history',
          'No quote snapshots yet',
        )}
        description={t(
          'propdev.pricing.empty_history_desc',
          'Quote snapshots appear here automatically when reservations are created against an active price list.',
        )}
      />
    );
  }

  return (
    <Card padding="none" className="overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-surface-secondary text-left text-xs uppercase tracking-wide text-content-secondary">
          <tr>
            <th className="px-3 py-2">
              {t('propdev.pricing.reservation_no', 'Reservation #')}
            </th>
            <th className="px-3 py-2">
              {t('propdev.pricing.created_at', 'Created')}
            </th>
            <th className="px-3 py-2 text-right">
              {t('propdev.pricing.base_price', 'Base')}
            </th>
            <th className="px-3 py-2 text-right">
              {t('propdev.pricing.total', 'Total')}
            </th>
            <th className="px-3 py-2">
              {t('propdev.pricing.currency', 'Currency')}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const snap = (r.price_breakdown_snapshot ?? {}) as {
              base_price?: string;
              total?: string;
              currency?: string;
              lines?: { rule_name: string; amount: string }[];
            };
            return (
              <tr key={r.id} className="border-t border-border">
                <td className="px-3 py-2 font-medium">
                  {r.reservation_number}
                </td>
                <td className="px-3 py-2 text-content-secondary">
                  {r.created_at}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {snap.base_price ?? '—'}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {snap.total ?? '—'}
                </td>
                <td className="px-3 py-2 text-content-secondary">
                  {snap.currency ?? r.currency}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}

// ── Page ─────────────────────────────────────────────────────────────

export function PricingEnginePage(): JSX.Element {
  const { t } = useTranslation();
  const { devId = '' } = useParams<{ devId: string }>();
  const [tab, setTab] = useState<Tab>('lists');

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold">
          {t('propdev.pricing.title', 'Pricing engine')}
        </h1>
        <p className="text-sm text-content-secondary">
          {t(
            'propdev.pricing.subtitle',
            'Versioned, rule-driven sales pricing with simulator and audit history.',
          )}
        </p>
      </header>
      <Tabs tab={tab} setTab={setTab} />
      {tab === 'lists' && <PriceListsTab devId={devId} />}
      {tab === 'rules' && <RulesTab devId={devId} />}
      {tab === 'sim' && <SimulatorTab devId={devId} />}
      {tab === 'history' && <QuoteHistoryTab devId={devId} />}
    </div>
  );
}
