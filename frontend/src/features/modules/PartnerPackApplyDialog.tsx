// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
/**
 * PartnerPackApplyDialog - the "activate this pack" confirm + dry-run preview.
 *
 * The backend already exposes a dry-run (`GET /v1/partner-pack/apply-preview/
 * {slug}`) and the apply mutation (`POST /v1/partner-pack/apply`); the hooks
 * live in ./partnerPacks. This dialog wires them to a button so a user can
 * see exactly what a pack changes (currency, default language, validation
 * standards, which modules switch on or off, the demo project) before
 * committing. Disabling modules is the one destructive effect, so it is
 * gated behind an explicit opt-in checkbox.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  Boxes,
  Coins,
  Globe,
  Loader2,
  Power,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';

import { WideModal, Badge } from '@/shared/ui';
import { useToastStore } from '@/stores/useToastStore';

import { useApplyPack, useApplyPreview } from './partnerPacks';

interface PartnerPackApplyDialogProps {
  open: boolean;
  onClose: () => void;
  slug: string;
  partnerName: string;
}

function Row({
  icon,
  label,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-2.5 py-2">
      <span className="mt-0.5 shrink-0 text-content-tertiary">{icon}</span>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-semibold uppercase tracking-wide text-content-tertiary">
          {label}
        </p>
        <div className="mt-1 text-sm text-content-secondary">{children}</div>
      </div>
    </div>
  );
}

export function PartnerPackApplyDialog({
  open,
  onClose,
  slug,
  partnerName,
}: PartnerPackApplyDialogProps) {
  const { t } = useTranslation();
  const addToast = useToastStore((s) => s.addToast);

  const { data: preview, isLoading, isError } = useApplyPreview(open ? slug : null);
  const applyPack = useApplyPack();

  const [confirmDisables, setConfirmDisables] = useState(false);
  const [installDemo, setInstallDemo] = useState(true);

  // Reset the toggles whenever the dialog opens for a (possibly different) pack.
  useEffect(() => {
    if (open) {
      setConfirmDisables(false);
      setInstallDemo(true);
    }
  }, [open, slug]);

  const plan = preview?.plan;
  const willDisable = (plan?.modules_to_disable.length ?? 0) > 0;

  const handleApply = () => {
    applyPack.mutate(
      { slug, confirm_disables: confirmDisables, install_demo: installDemo },
      {
        onSuccess: () => {
          addToast({
            type: 'success',
            title: t('modules.pack_applied_title', { defaultValue: 'Pack activated' }),
            message: t('modules.pack_applied_msg', {
              defaultValue: '{{name}} is now the active partner pack.',
              name: partnerName,
            }),
          });
          onClose();
        },
        onError: () => {
          addToast({
            type: 'error',
            title: t('modules.pack_apply_failed', {
              defaultValue: 'Could not activate this pack',
            }),
          });
        },
      },
    );
  };

  return (
    <WideModal
      open={open}
      onClose={onClose}
      size="md"
      busy={applyPack.isPending}
      title={t('modules.pack_apply_title', {
        defaultValue: 'Activate {{name}}',
        name: partnerName,
      })}
      subtitle={t('modules.pack_apply_subtitle', {
        defaultValue: 'Review what this pack changes before you activate it.',
      })}
      footer={
        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={applyPack.isPending}
            className="rounded-md border border-border bg-surface-primary px-4 py-2 text-sm font-medium text-content-secondary transition hover:bg-surface-secondary disabled:opacity-60"
          >
            {t('common.cancel', { defaultValue: 'Cancel' })}
          </button>
          <button
            type="button"
            onClick={handleApply}
            disabled={applyPack.isPending || isLoading || isError}
            className="inline-flex items-center gap-1.5 rounded-md bg-oe-blue px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-oe-blue/90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {applyPack.isPending ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <Power size={15} />
            )}
            {t('modules.pack_activate', { defaultValue: 'Activate pack' })}
          </button>
        </div>
      }
    >
      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-10 text-sm text-content-tertiary">
          <Loader2 size={18} className="animate-spin" />
          {t('modules.pack_preview_loading', {
            defaultValue: 'Checking what will change...',
          })}
        </div>
      )}

      {isError && (
        <div className="flex items-start gap-2 rounded-lg border border-semantic-warning/40 bg-amber-50 px-3.5 py-3 text-sm text-amber-900 dark:bg-amber-900/20 dark:text-amber-100">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          {t('modules.pack_preview_failed', {
            defaultValue:
              'Could not load the preview for this pack. You can still activate it, but review the pack details first.',
          })}
        </div>
      )}

      {plan && (
        <div className="divide-y divide-border-light">
          <Row
            icon={<Sparkles size={15} />}
            label={t('modules.pack_branding', { defaultValue: 'Branding' })}
          >
            {plan.branding.powered_by}
          </Row>

          <Row
            icon={<Coins size={15} />}
            label={t('modules.pack_currency_locale', {
              defaultValue: 'Currency & language',
            })}
          >
            <span className="inline-flex flex-wrap items-center gap-1.5">
              <Badge variant="neutral" size="sm">
                {plan.default_currency}
              </Badge>
              <Badge variant="neutral" size="sm">
                {plan.default_locale}
              </Badge>
              {plan.additional_locales.map((l) => (
                <Badge key={l} variant="neutral" size="sm">
                  {l}
                </Badge>
              ))}
            </span>
          </Row>

          {plan.rule_packs_active.length > 0 && (
            <Row
              icon={<ShieldCheck size={15} />}
              label={t('modules.pack_standards', {
                defaultValue: 'Validation standards',
              })}
            >
              <span className="inline-flex flex-wrap items-center gap-1.5">
                {plan.rule_packs_active.map((r) => (
                  <Badge key={r} variant="blue" size="sm">
                    {r}
                  </Badge>
                ))}
              </span>
            </Row>
          )}

          {plan.modules_to_enable.length > 0 && (
            <Row
              icon={<Boxes size={15} />}
              label={t('modules.pack_modules_enable', {
                defaultValue: 'Modules switched on',
              })}
            >
              <span className="text-emerald-600 dark:text-emerald-400">
                {plan.modules_to_enable.join(', ')}
              </span>
            </Row>
          )}

          {willDisable && (
            <Row
              icon={<AlertTriangle size={15} className="text-amber-500" />}
              label={t('modules.pack_modules_disable', {
                defaultValue: 'Modules switched off',
              })}
            >
              <p className="text-amber-700 dark:text-amber-300">
                {plan.modules_to_disable.join(', ')}
              </p>
              <label className="mt-2 flex cursor-pointer items-start gap-2 rounded-md bg-amber-50 px-2.5 py-2 text-xs text-amber-900 dark:bg-amber-900/20 dark:text-amber-100">
                <input
                  type="checkbox"
                  checked={confirmDisables}
                  onChange={(e) => setConfirmDisables(e.target.checked)}
                  className="mt-0.5"
                />
                <span>
                  {t('modules.pack_confirm_disable', {
                    defaultValue:
                      'Yes, hide these modules from the menu. Leave unchecked to keep them on.',
                  })}
                </span>
              </label>
            </Row>
          )}

          {plan.demo_project && (
            <Row
              icon={<Globe size={15} />}
              label={t('modules.pack_demo', { defaultValue: 'Demo project' })}
            >
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={installDemo}
                  onChange={(e) => setInstallDemo(e.target.checked)}
                />
                <span>
                  {t('modules.pack_demo_install', {
                    defaultValue: 'Install the sample project "{{name}}"',
                    name: plan.demo_project.name ?? plan.demo_project.demo_id,
                  })}
                </span>
              </label>
            </Row>
          )}

          {plan.warnings.length > 0 && (
            <div className="pt-3">
              <ul className="space-y-1 text-xs text-amber-700 dark:text-amber-300">
                {plan.warnings.map((w, i) => (
                  <li key={i} className="flex items-start gap-1.5">
                    <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                    {w}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </WideModal>
  );
}

export default PartnerPackApplyDialog;
