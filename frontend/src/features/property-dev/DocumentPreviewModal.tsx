// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// DocumentPreviewModal — preview and download Property Development PDFs.
//
// Wraps the two backend endpoints exposed by
// ``app.modules.property_dev.router``:
//   * POST /api/v1/property-dev/documents/preview → base64 + page count
//   * GET  /api/v1/property-dev/documents/{doc_type} → application/pdf stream
//
// Used from the SalesContract / Reservation / Handover drawers (and from
// the inline action buttons on PropertyDevPage). Renders six different
// PDFs depending on ``docType``:
//   reservation_receipt   — issued at deposit time
//   sales_contract        — the SPA (multi-page, jurisdiction-aware)
//   payment_receipt       — per instalment
//   handover_certificate  — at completion
//   warranty_certificate  — structural + finishing warranty
//   noc                   — No Objection Certificate for resale
//
// Six locales are exposed (en / de / ru / fr / ar / es) — these are
// the locales shipped in
// ``backend/app/modules/property_dev/data/document_locales``. Unknown
// locales fall back to English on the server.

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Download, Loader2, Mail, X } from 'lucide-react';

import { Button } from '@/shared/ui';
import { WideModal } from '@/shared/ui/WideModal';
import { useToastStore } from '@/stores/useToastStore';

import {
  downloadPropDevDocument,
  previewPropDevDocument,
  type PropDevDocPreview,
  type PropDevDocType,
} from './api';

const SUPPORTED_LOCALES = ['en', 'de', 'ru', 'fr', 'ar', 'es'] as const;
type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];

const LOCALE_LABELS: Record<SupportedLocale, string> = {
  en: 'English',
  de: 'Deutsch',
  ru: 'Русский',
  fr: 'Français',
  ar: 'العربية',
  es: 'Español',
};

const DOC_TITLES: Record<PropDevDocType, { key: string; defaultValue: string }> = {
  reservation_receipt: {
    key: 'propdev.documents.reservation_receipt',
    defaultValue: 'Reservation Receipt',
  },
  sales_contract: {
    key: 'propdev.documents.sales_contract',
    defaultValue: 'Sales-Purchase Agreement',
  },
  payment_receipt: {
    key: 'propdev.documents.payment_receipt',
    defaultValue: 'Payment Receipt',
  },
  handover_certificate: {
    key: 'propdev.documents.handover_certificate',
    defaultValue: 'Handover Certificate',
  },
  warranty_certificate: {
    key: 'propdev.documents.warranty_certificate',
    defaultValue: 'Warranty Certificate',
  },
  noc: {
    key: 'propdev.documents.noc',
    defaultValue: 'No Objection Certificate',
  },
  tenant_lease_agreement: {
    key: 'propdev.documents.tenant_lease_agreement',
    defaultValue: 'Tenant Lease Agreement',
  },
  move_in_checklist: {
    key: 'propdev.documents.move_in_checklist',
    defaultValue: 'Move-In Checklist',
  },
  mortgage_clearance_letter: {
    key: 'propdev.documents.mortgage_clearance_letter',
    defaultValue: 'Mortgage Clearance Letter',
  },
  title_deed_transfer_request: {
    key: 'propdev.documents.title_deed_transfer_request',
    defaultValue: 'Title Deed Transfer Request',
  },
  escrow_release_authorization: {
    key: 'propdev.documents.escrow_release_authorization',
    defaultValue: 'Escrow Release Authorization',
  },
  refund_authorization: {
    key: 'propdev.documents.refund_authorization',
    defaultValue: 'Refund Authorization',
  },
};

export interface DocumentPreviewModalProps {
  open: boolean;
  onClose: () => void;
  docType: PropDevDocType;
  /** One of these must be set (the rest stay undefined). */
  contractId?: string;
  reservationId?: string;
  handoverId?: string;
  instalmentId?: string;
  /** Extra params forwarded to the backend (payment_method, etc.). */
  extraParams?: {
    payment_method?: string;
    payment_ref?: string;
    requested_by?: string;
    structural_warranty_years?: number;
    finishing_warranty_years?: number;
    noc_validity_days?: number;
  };
}

export function DocumentPreviewModal({
  open,
  onClose,
  docType,
  contractId,
  reservationId,
  handoverId,
  instalmentId,
  extraParams,
}: DocumentPreviewModalProps) {
  const { t, i18n } = useTranslation();
  const addToast = useToastStore((s) => s.addToast);

  const defaultLocale: SupportedLocale = useMemo(() => {
    const base = (i18n.language || 'en').split('-')[0] as SupportedLocale;
    return SUPPORTED_LOCALES.includes(base) ? base : 'en';
  }, [i18n.language]);

  const [locale, setLocale] = useState<SupportedLocale>(defaultLocale);
  const [preview, setPreview] = useState<PropDevDocPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch on open + whenever locale changes.
  useEffect(() => {
    if (!open) {
      setPreview(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    previewPropDevDocument({
      doc_type: docType,
      contract_id: contractId,
      reservation_id: reservationId,
      handover_id: handoverId,
      instalment_id: instalmentId,
      locale,
      ...extraParams,
    })
      .then((result) => {
        if (!cancelled) setPreview(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : String(err);
          setError(message);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    open,
    docType,
    locale,
    contractId,
    reservationId,
    handoverId,
    instalmentId,
    extraParams,
  ]);

  const handleDownload = async () => {
    try {
      const blob = await downloadPropDevDocument({
        doc_type: docType,
        contract_id: contractId,
        reservation_id: reservationId,
        handover_id: handoverId,
        instalment_id: instalmentId,
        locale,
        ...extraParams,
      });
      const filename = preview?.filename ?? `${docType}.pdf`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }, 200);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      addToast({ type: 'error', title: 'Download failed', message });
    }
  };

  const handleEmail = () => {
    // TODO: wire to the buyer-email automation pipeline once the
    // notifications module exposes a templated-send endpoint. For now
    // this is intentionally a stub so we don't ship a fake button.
    addToast({
      type: 'info',
      title: t('propdev.documents.email_pending', {
        defaultValue: 'Email automation coming soon',
      }),
      message: t('propdev.documents.email_pending_detail', {
        defaultValue:
          'Email-to-buyer wiring is tracked separately. For now, please ' +
          'download the PDF and attach it manually.',
      }),
    });
  };

  const title = t(DOC_TITLES[docType].key, {
    defaultValue: DOC_TITLES[docType].defaultValue,
  });

  return (
    <WideModal
      open={open}
      onClose={onClose}
      title={title}
      subtitle={
        preview
          ? t('propdev.documents.size_pages', {
              defaultValue: '{{pages}} page(s) · {{kb}} KB',
              pages: preview.page_count,
              kb: Math.max(1, Math.round(preview.size_bytes / 1024)),
            })
          : undefined
      }
      size="xl"
      footer={
        <div className="flex items-center justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            {t('common.close', { defaultValue: 'Close' })}
          </Button>
          <Button
            variant="ghost"
            onClick={handleEmail}
            disabled={!preview || loading}
            icon={<Mail className="h-4 w-4" />}
          >
            {t('propdev.documents.email_to_buyer', {
              defaultValue: 'Email to buyer',
            })}
          </Button>
          <Button
            variant="primary"
            onClick={handleDownload}
            disabled={!preview || loading}
            icon={<Download className="h-4 w-4" />}
          >
            {t('propdev.documents.download', { defaultValue: 'Download' })}
          </Button>
        </div>
      }
    >
      <div className="space-y-3">
        {/* Locale picker */}
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-sm font-medium text-content-secondary">
            {t('propdev.documents.locale', { defaultValue: 'Locale' })}
          </label>
          <select
            value={locale}
            onChange={(e) => setLocale(e.target.value as SupportedLocale)}
            className="h-9 rounded-lg border border-border bg-surface-primary px-3 text-sm focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue"
            disabled={loading}
            aria-label={t('propdev.documents.locale', {
              defaultValue: 'Locale',
            })}
          >
            {SUPPORTED_LOCALES.map((code) => (
              <option key={code} value={code}>
                {LOCALE_LABELS[code]}
              </option>
            ))}
          </select>
          {loading && (
            <span className="flex items-center gap-1 text-sm text-content-tertiary">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {t('propdev.documents.rendering', {
                defaultValue: 'Rendering…',
              })}
            </span>
          )}
        </div>

        {/* Preview surface */}
        <div className="min-h-[60vh] rounded-lg border border-border bg-surface-secondary">
          {error ? (
            <div className="flex h-full min-h-[60vh] flex-col items-center justify-center gap-2 p-6 text-center">
              <X className="h-10 w-10 text-error" />
              <p className="text-sm font-medium text-content-primary">
                {t('propdev.documents.preview_failed', {
                  defaultValue: 'Could not generate preview',
                })}
              </p>
              <p className="text-xs text-content-tertiary">{error}</p>
            </div>
          ) : preview ? (
            <iframe
              key={`${docType}-${locale}-${preview.size_bytes}`}
              src={`data:application/pdf;base64,${preview.base64}`}
              title={title}
              className="h-[60vh] w-full rounded-lg"
            />
          ) : (
            <div className="flex h-[60vh] items-center justify-center">
              <Loader2 className="h-8 w-8 animate-spin text-content-tertiary" />
            </div>
          )}
        </div>
      </div>
    </WideModal>
  );
}
