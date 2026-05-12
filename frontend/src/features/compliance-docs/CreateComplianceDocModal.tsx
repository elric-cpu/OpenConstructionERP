// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Create-compliance-doc modal.

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { X } from 'lucide-react';

import { Button, Input } from '@/shared/ui';
import { useToastStore } from '@/stores/useToastStore';
import { useFileList } from '@/features/file-manager/hooks';
import { ApiError } from '@/shared/lib/api';

import { createComplianceDoc } from './api';
import {
  COMPLIANCE_DOC_TYPES,
  type ComplianceDocCreate,
  type ComplianceDocType,
} from './types';

export interface CreateComplianceDocModalProps {
  projectId: string;
  onClose: () => void;
  onCreated?: () => void;
}

const TODAY_ISO = () => new Date().toISOString().slice(0, 10);
const ISO_PLUS_DAYS = (days: number) => {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
};

export function CreateComplianceDocModal({
  projectId,
  onClose,
  onCreated,
}: CreateComplianceDocModalProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const toast = useToastStore((s) => s.addToast);

  const [docType, setDocType] = useState<ComplianceDocType>(
    'insurance_general_liability',
  );
  const [name, setName] = useState('');
  const [issuer, setIssuer] = useState('');
  const [policyNumber, setPolicyNumber] = useState('');
  const [coverageAmount, setCoverageAmount] = useState('');
  const [currency, setCurrency] = useState('');
  const [effectiveDate, setEffectiveDate] = useState(TODAY_ISO());
  const [expiresAt, setExpiresAt] = useState(ISO_PLUS_DAYS(365));
  const [notifyDaysBefore, setNotifyDaysBefore] = useState(30);
  const [attachmentDocId, setAttachmentDocId] = useState<string>('');
  const [notes, setNotes] = useState('');

  const { data: files } = useFileList(projectId, { category: 'document' });
  const attachmentOptions = useMemo(
    () => (files?.items ?? []).map((f) => ({ id: f.id, name: f.name })),
    [files],
  );

  const mutation = useMutation({
    mutationFn: async () => {
      const body: ComplianceDocCreate = {
        project_id: projectId,
        doc_type: docType,
        name: name.trim(),
        issuer: issuer.trim() || null,
        policy_number: policyNumber.trim() || null,
        coverage_amount: coverageAmount.trim() || null,
        currency: currency.trim().toUpperCase(),
        effective_date: effectiveDate,
        expires_at: expiresAt,
        notify_days_before: notifyDaysBefore,
        attachment_document_id: attachmentDocId || null,
        notes: notes.trim(),
      };
      return createComplianceDoc(body);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['compliance-docs', projectId] });
      queryClient.invalidateQueries({
        queryKey: ['compliance-docs-expiring', projectId],
      });
      toast({
        title: t('compliance.toast.created', {
          defaultValue: 'Compliance document created.',
        }),
        type: 'success',
      });
      onCreated?.();
      onClose();
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof ApiError && err.message
          ? err.message
          : t('compliance.toast.create_failed', {
              defaultValue: 'Failed to create compliance document.',
            });
      toast({ title: msg, type: 'error' });
    },
  });

  const canSubmit = name.trim().length > 0 && effectiveDate <= expiresAt;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
      data-testid="create-compliance-modal-backdrop"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-compliance-title"
        className="w-full max-w-xl overflow-hidden rounded-lg border border-border-light bg-surface-primary shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        data-testid="create-compliance-modal"
      >
        <div className="flex items-center justify-between border-b border-border-light px-4 py-3">
          <div
            id="create-compliance-title"
            className="text-base font-semibold text-content-primary"
          >
            {t('compliance.modal.create_title', {
              defaultValue: 'New compliance document',
            })}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-content-tertiary hover:bg-surface-secondary hover:text-content-primary"
            aria-label={t('common.close', { defaultValue: 'Close' })}
          >
            <X size={18} />
          </button>
        </div>

        <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2">
          <label className="col-span-1 sm:col-span-2 flex flex-col gap-1 text-xs">
            <span className="text-content-secondary">
              {t('compliance.field.doc_type', { defaultValue: 'Document type' })}
            </span>
            <select
              value={docType}
              onChange={(e) => setDocType(e.target.value as ComplianceDocType)}
              className="rounded-md border border-border-light bg-surface-primary px-2 py-1.5 text-sm text-content-primary"
              data-testid="compliance-field-doc-type"
            >
              {COMPLIANCE_DOC_TYPES.map((dt) => (
                <option key={dt} value={dt}>
                  {t(`compliance.doc_type.${dt}`, { defaultValue: dt })}
                </option>
              ))}
            </select>
          </label>

          <label className="col-span-1 sm:col-span-2 flex flex-col gap-1 text-xs">
            <span className="text-content-secondary">
              {t('compliance.field.name', { defaultValue: 'Name' })}
            </span>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              data-testid="compliance-field-name"
            />
          </label>

          <label className="flex flex-col gap-1 text-xs">
            <span className="text-content-secondary">
              {t('compliance.field.issuer', { defaultValue: 'Issuer' })}
            </span>
            <Input
              value={issuer}
              onChange={(e) => setIssuer(e.target.value)}
              data-testid="compliance-field-issuer"
            />
          </label>

          <label className="flex flex-col gap-1 text-xs">
            <span className="text-content-secondary">
              {t('compliance.field.policy_number', {
                defaultValue: 'Policy / permit number',
              })}
            </span>
            <Input
              value={policyNumber}
              onChange={(e) => setPolicyNumber(e.target.value)}
              data-testid="compliance-field-policy"
            />
          </label>

          <label className="flex flex-col gap-1 text-xs">
            <span className="text-content-secondary">
              {t('compliance.field.coverage_amount', {
                defaultValue: 'Coverage amount',
              })}
            </span>
            <Input
              value={coverageAmount}
              onChange={(e) => setCoverageAmount(e.target.value)}
              inputMode="decimal"
              data-testid="compliance-field-coverage"
            />
          </label>

          <label className="flex flex-col gap-1 text-xs">
            <span className="text-content-secondary">
              {t('compliance.field.currency', { defaultValue: 'Currency' })}
            </span>
            <Input
              value={currency}
              maxLength={3}
              onChange={(e) => setCurrency(e.target.value.toUpperCase())}
              data-testid="compliance-field-currency"
            />
          </label>

          <label className="flex flex-col gap-1 text-xs">
            <span className="text-content-secondary">
              {t('compliance.field.effective_date', {
                defaultValue: 'Effective date',
              })}
            </span>
            <Input
              type="date"
              value={effectiveDate}
              onChange={(e) => setEffectiveDate(e.target.value)}
              data-testid="compliance-field-effective"
            />
          </label>

          <label className="flex flex-col gap-1 text-xs">
            <span className="text-content-secondary">
              {t('compliance.field.expires_at', { defaultValue: 'Expires on' })}
            </span>
            <Input
              type="date"
              value={expiresAt}
              onChange={(e) => setExpiresAt(e.target.value)}
              data-testid="compliance-field-expires"
            />
          </label>

          <label className="flex flex-col gap-1 text-xs">
            <span className="text-content-secondary">
              {t('compliance.field.notify_days', {
                defaultValue: 'Notify days before',
              })}
            </span>
            <Input
              type="number"
              min={0}
              max={365}
              value={notifyDaysBefore}
              onChange={(e) =>
                setNotifyDaysBefore(Number.parseInt(e.target.value, 10) || 0)
              }
              data-testid="compliance-field-notify"
            />
          </label>

          <label className="col-span-1 sm:col-span-2 flex flex-col gap-1 text-xs">
            <span className="text-content-secondary">
              {t('compliance.field.attachment', {
                defaultValue: 'Attachment document (optional)',
              })}
            </span>
            <select
              value={attachmentDocId}
              onChange={(e) => setAttachmentDocId(e.target.value)}
              className="rounded-md border border-border-light bg-surface-primary px-2 py-1.5 text-sm text-content-primary"
              data-testid="compliance-field-attachment"
            >
              <option value="">
                {t('compliance.field.attachment_none', {
                  defaultValue: 'No attachment',
                })}
              </option>
              {attachmentOptions.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>

          <label className="col-span-1 sm:col-span-2 flex flex-col gap-1 text-xs">
            <span className="text-content-secondary">
              {t('compliance.field.notes', { defaultValue: 'Notes' })}
            </span>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              className="rounded-md border border-border-light bg-surface-primary px-2 py-1.5 text-sm text-content-primary"
              data-testid="compliance-field-notes"
            />
          </label>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border-light px-4 py-3">
          <Button variant="ghost" onClick={onClose}>
            {t('common.cancel', { defaultValue: 'Cancel' })}
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={!canSubmit || mutation.isPending}
            data-testid="compliance-submit"
          >
            {mutation.isPending
              ? t('common.saving', { defaultValue: 'Saving…' })
              : t('compliance.modal.create_submit', {
                  defaultValue: 'Create document',
                })}
          </Button>
        </div>
      </div>
    </div>
  );
}
