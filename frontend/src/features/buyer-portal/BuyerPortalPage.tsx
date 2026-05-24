/**
 * Buyer self-service portal — public landing page (``/buyer-portal/:token``).
 *
 * Rendered for unauthenticated buyers who follow the magic link emailed
 * by the sales team. No bearer JWT — the token in the URL is the entire
 * auth surface (verified server-side against the revocation registry
 * stored in ``oe_propdev_portal_token``).
 *
 * Layout (top → bottom, ARIA-landmarks throughout):
 *   1. <header> — logo + "Welcome, {buyer_name}" + locale switcher.
 *   2. <main> with sections:
 *        a. Reservation card.
 *        b. Sales contract card.
 *        c. Payment schedule table.
 *        d. Documents library + KYC upload requests.
 *        e. "Contact your agent" form.
 *   3. <footer> — contact email + AGPL-3.0 link.
 *
 * States: loading / invalid-token / error / ready. We never leak a
 * login form when the token is bad — just a friendly "ask your agent
 * for a new link" message.
 */

import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  Clock,
  FileText,
  Loader2,
  Mail,
  ShieldX,
  Upload,
} from 'lucide-react';

import {
  contactPortalAgent,
  fetchPortalOverview,
  uploadPortalKyc,
  type PortalKycCode,
  type PortalOverviewResponse,
} from './api';

type PageState =
  | { kind: 'loading' }
  | { kind: 'invalid' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; data: PortalOverviewResponse };

export function BuyerPortalPage() {
  const { token } = useParams<{ token: string }>();
  const { t, i18n } = useTranslation();

  const [state, setState] = useState<PageState>({ kind: 'loading' });
  const [contactMessage, setContactMessage] = useState('');
  const [contactPhone, setContactPhone] = useState('');
  const [contactSending, setContactSending] = useState(false);
  const [contactSent, setContactSent] = useState(false);
  const [uploadBusy, setUploadBusy] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // 1. Initial overview fetch (verify happens implicitly).
  useEffect(() => {
    let cancelled = false;
    if (!token) {
      setState({ kind: 'invalid' });
      return;
    }
    (async () => {
      try {
        const data = await fetchPortalOverview(token);
        if (!cancelled) setState({ kind: 'ready', data });
      } catch (err) {
        if (cancelled) return;
        const msg = (err as Error).message;
        if (msg === 'INVALID') {
          setState({ kind: 'invalid' });
        } else {
          setState({ kind: 'error', message: msg });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  // 2. KYC upload handler. Re-fetches overview on success so the
  //    "Required documents" list updates without a page reload.
  async function handleKycUpload(
    e: ChangeEvent<HTMLInputElement>,
    code: PortalKycCode,
  ) {
    if (!token) return;
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadError(null);
    setUploadBusy(code);
    try {
      await uploadPortalKyc(token, code, file);
      const fresh = await fetchPortalOverview(token);
      setState({ kind: 'ready', data: fresh });
    } catch (err) {
      const msg = (err as Error).message;
      if (msg === 'UNSUPPORTED_MEDIA_TYPE') {
        setUploadError(
          t('buyer_portal.upload.unsupported', {
            defaultValue:
              'This file format is not accepted. Please upload a PDF or image (PNG/JPEG).',
          }),
        );
      } else if (msg === 'FILE_TOO_LARGE') {
        setUploadError(
          t('buyer_portal.upload.too_large', {
            defaultValue: 'File is too large. Maximum size is 20 MB.',
          }),
        );
      } else {
        setUploadError(msg);
      }
    } finally {
      setUploadBusy(null);
      // Clear the input so the same file can be retried.
      e.target.value = '';
    }
  }

  // 3. Contact-agent submission.
  async function handleContactSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!token || contactSending) return;
    const trimmed = contactMessage.trim();
    if (!trimmed) return;
    setContactSending(true);
    try {
      await contactPortalAgent(token, trimmed, contactPhone.trim() || undefined);
      setContactSent(true);
      setContactMessage('');
      setContactPhone('');
    } catch {
      // Soft error — keep form contents so the user can retry.
      setContactSent(false);
    } finally {
      setContactSending(false);
    }
  }

  // ── Render: invalid / error / loading shells ─────────────────────

  if (state.kind === 'invalid') {
    return (
      <ShellWrapper>
        <div
          data-testid="buyer-portal-invalid"
          className="rounded-2xl border border-semantic-error/30 bg-semantic-error/5 p-6 text-center space-y-3"
        >
          <ShieldX
            size={32}
            strokeWidth={1.5}
            className="mx-auto text-semantic-error"
          />
          <h2 className="text-base font-semibold text-content-primary">
            {t('buyer_portal.invalid.title', {
              defaultValue: 'Your access link has expired',
            })}
          </h2>
          <p className="text-sm text-content-secondary">
            {t('buyer_portal.invalid.body', {
              defaultValue:
                'Contact your sales agent to receive a new link. We never ask for a password to view your information.',
            })}
          </p>
        </div>
      </ShellWrapper>
    );
  }

  if (state.kind === 'error') {
    return (
      <ShellWrapper>
        <div
          data-testid="buyer-portal-error"
          className="rounded-2xl border border-amber-300/40 bg-amber-50 dark:bg-amber-900/20 p-6 text-center space-y-3"
        >
          <AlertTriangle
            size={28}
            strokeWidth={1.5}
            className="mx-auto text-amber-600 dark:text-amber-400"
          />
          <h2 className="text-base font-semibold text-content-primary">
            {t('buyer_portal.error.title', {
              defaultValue: 'Something went wrong',
            })}
          </h2>
          <p className="text-sm text-content-secondary">{state.message}</p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-2 inline-flex items-center justify-center gap-2 h-9 px-4 rounded-lg bg-oe-blue text-white text-sm font-medium hover:bg-oe-blue-hover"
          >
            {t('buyer_portal.error.retry', { defaultValue: 'Try again' })}
          </button>
        </div>
      </ShellWrapper>
    );
  }

  if (state.kind === 'loading') {
    return (
      <ShellWrapper>
        <div
          data-testid="buyer-portal-loading"
          className="rounded-2xl border border-border-light bg-surface-elevated p-8 text-center space-y-3"
        >
          <Loader2
            size={24}
            className="animate-spin mx-auto text-content-tertiary"
            aria-hidden
          />
          <p className="text-sm text-content-tertiary">
            {t('buyer_portal.loading', {
              defaultValue: 'Loading your portal…',
            })}
          </p>
        </div>
      </ShellWrapper>
    );
  }

  // ── Render: ready ────────────────────────────────────────────────

  const { data } = state;

  return (
    <ShellWrapper buyerName={data.buyer_full_name} locale={i18n.language}>
      <main className="w-full max-w-3xl mx-auto px-4 sm:px-6 py-6 space-y-6">
        {/* Welcome header */}
        <section
          aria-labelledby="welcome-heading"
          className="rounded-2xl border border-border-light bg-surface-elevated p-5 sm:p-6"
        >
          <h1
            id="welcome-heading"
            className="text-lg sm:text-xl font-semibold text-content-primary"
          >
            {t('buyer_portal.welcome', {
              defaultValue: 'Welcome, {{name}}',
              name: data.buyer_full_name,
            })}
          </h1>
          <p className="mt-1 text-sm text-content-secondary">
            {data.development_name ||
              t('buyer_portal.welcome.fallback', {
                defaultValue: 'Your buyer dashboard',
              })}
          </p>
        </section>

        {/* Reservation card */}
        {data.reservation && (
          <section
            aria-labelledby="reservation-heading"
            data-testid="reservation-card"
            className="rounded-2xl border border-border-light bg-surface-elevated p-5"
          >
            <h2
              id="reservation-heading"
              className="text-sm font-semibold text-content-primary flex items-center gap-2"
            >
              <Building2 size={16} aria-hidden />
              {t('buyer_portal.reservation.title', {
                defaultValue: 'Reservation',
              })}
            </h2>
            <dl className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-2xs uppercase tracking-wide text-content-tertiary">
                  {t('buyer_portal.reservation.number', {
                    defaultValue: 'Reservation #',
                  })}
                </dt>
                <dd className="text-content-primary font-medium">
                  {data.reservation.reservation_number}
                </dd>
              </div>
              <div>
                <dt className="text-2xs uppercase tracking-wide text-content-tertiary">
                  {t('buyer_portal.reservation.plot', { defaultValue: 'Plot' })}
                </dt>
                <dd className="text-content-primary font-medium">
                  {data.reservation.plot_number}
                </dd>
              </div>
              <div>
                <dt className="text-2xs uppercase tracking-wide text-content-tertiary">
                  {t('buyer_portal.reservation.address', {
                    defaultValue: 'Address',
                  })}
                </dt>
                <dd className="text-content-primary">
                  {data.reservation.plot_address ||
                    t('buyer_portal.na', { defaultValue: '—' })}
                </dd>
              </div>
              <div>
                <dt className="text-2xs uppercase tracking-wide text-content-tertiary">
                  {t('buyer_portal.reservation.status', {
                    defaultValue: 'Status',
                  })}
                </dt>
                <dd>
                  <StatusBadge status={data.reservation.status} />
                </dd>
              </div>
              <div>
                <dt className="text-2xs uppercase tracking-wide text-content-tertiary">
                  {t('buyer_portal.reservation.deposit', {
                    defaultValue: 'Deposit',
                  })}
                </dt>
                <dd className="text-content-primary font-medium tabular-nums">
                  {formatMoney(
                    data.reservation.deposit_amount,
                    data.reservation.currency,
                    i18n.language,
                  )}
                </dd>
              </div>
              {data.reservation.signed_on && (
                <div>
                  <dt className="text-2xs uppercase tracking-wide text-content-tertiary">
                    {t('buyer_portal.reservation.signed', {
                      defaultValue: 'Signed',
                    })}
                  </dt>
                  <dd className="text-content-primary">
                    {formatDate(data.reservation.signed_on, i18n.language)}
                  </dd>
                </div>
              )}
            </dl>
          </section>
        )}

        {/* Sales contract card */}
        {data.sales_contract && (
          <section
            aria-labelledby="contract-heading"
            data-testid="contract-card"
            className="rounded-2xl border border-border-light bg-surface-elevated p-5"
          >
            <h2
              id="contract-heading"
              className="text-sm font-semibold text-content-primary flex items-center gap-2"
            >
              <FileText size={16} aria-hidden />
              {t('buyer_portal.contract.title', {
                defaultValue: 'Sale & Purchase Agreement',
              })}
            </h2>
            <dl className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
              <div>
                <dt className="text-2xs uppercase tracking-wide text-content-tertiary">
                  {t('buyer_portal.contract.number', {
                    defaultValue: 'Contract #',
                  })}
                </dt>
                <dd className="text-content-primary font-medium">
                  {data.sales_contract.contract_number}
                </dd>
              </div>
              <div>
                <dt className="text-2xs uppercase tracking-wide text-content-tertiary">
                  {t('buyer_portal.contract.value', { defaultValue: 'Value' })}
                </dt>
                <dd className="text-content-primary font-medium tabular-nums">
                  {formatMoney(
                    data.sales_contract.total_value,
                    data.sales_contract.currency,
                    i18n.language,
                  )}
                </dd>
              </div>
              <div>
                <dt className="text-2xs uppercase tracking-wide text-content-tertiary">
                  {t('buyer_portal.contract.status', {
                    defaultValue: 'Status',
                  })}
                </dt>
                <dd>
                  <StatusBadge status={data.sales_contract.status} />
                </dd>
              </div>
            </dl>
          </section>
        )}

        {/* Payment schedule */}
        <section
          aria-labelledby="payments-heading"
          data-testid="payments-section"
          className="rounded-2xl border border-border-light bg-surface-elevated p-5"
        >
          <div className="flex items-baseline justify-between gap-3">
            <h2
              id="payments-heading"
              className="text-sm font-semibold text-content-primary"
            >
              {t('buyer_portal.payments.title', {
                defaultValue: 'Payment schedule',
              })}
            </h2>
            <div className="text-xs text-content-tertiary">
              {t('buyer_portal.payments.outstanding', {
                defaultValue: 'Outstanding: {{value}}',
                value: formatMoney(
                  data.payment_schedule_outstanding,
                  data.payment_schedule_currency,
                  i18n.language,
                ),
              })}
            </div>
          </div>
          {data.instalments.length === 0 ? (
            <p className="mt-3 text-xs text-content-tertiary">
              {t('buyer_portal.payments.empty', {
                defaultValue:
                  'No payment schedule has been issued yet. Your agent will share it once your contract is finalised.',
              })}
            </p>
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-2xs uppercase tracking-wide text-content-tertiary">
                    <th className="py-2 pr-3">#</th>
                    <th className="py-2 pr-3">
                      {t('buyer_portal.payments.milestone', {
                        defaultValue: 'Milestone',
                      })}
                    </th>
                    <th className="py-2 pr-3">
                      {t('buyer_portal.payments.due', { defaultValue: 'Due' })}
                    </th>
                    <th className="py-2 pr-3 text-right">
                      {t('buyer_portal.payments.amount', {
                        defaultValue: 'Amount',
                      })}
                    </th>
                    <th className="py-2 pr-3 text-right">
                      {t('buyer_portal.payments.paid', {
                        defaultValue: 'Paid',
                      })}
                    </th>
                    <th className="py-2 pr-1">
                      {t('buyer_portal.payments.status', {
                        defaultValue: 'Status',
                      })}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.instalments.map((row) => (
                    <tr
                      key={row.id}
                      data-testid={`installment-row-${row.sequence}`}
                      className="border-t border-border-light/50"
                    >
                      <td className="py-2 pr-3 tabular-nums text-content-tertiary">
                        {row.sequence}
                      </td>
                      <td className="py-2 pr-3 text-content-primary">
                        {row.milestone_label || '—'}
                      </td>
                      <td className="py-2 pr-3 text-content-secondary">
                        {row.due_date
                          ? formatDate(row.due_date, i18n.language)
                          : '—'}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums text-content-primary">
                        {formatMoney(row.amount, row.currency, i18n.language)}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums text-content-secondary">
                        {formatMoney(
                          row.amount_paid,
                          row.currency,
                          i18n.language,
                        )}
                      </td>
                      <td className="py-2 pr-1">
                        <InstalmentStatusPill status={row.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Documents + KYC */}
        <section
          aria-labelledby="documents-heading"
          data-testid="documents-section"
          className="rounded-2xl border border-border-light bg-surface-elevated p-5"
        >
          <h2
            id="documents-heading"
            className="text-sm font-semibold text-content-primary"
          >
            {t('buyer_portal.documents.title', {
              defaultValue: 'Documents',
            })}
          </h2>

          {/* Signed-doc downloads */}
          {data.documents.length === 0 ? (
            <p className="mt-3 text-xs text-content-tertiary">
              {t('buyer_portal.documents.empty', {
                defaultValue: 'No signed documents are available yet.',
              })}
            </p>
          ) : (
            <ul className="mt-3 space-y-2">
              {data.documents.map((doc) => (
                <li
                  key={doc.id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border-light/50 px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="text-sm text-content-primary truncate">
                      {doc.title}
                    </p>
                    <p className="text-2xs text-content-tertiary">
                      {doc.doc_type}
                      {doc.delivered_at
                        ? ` · ${formatDate(doc.delivered_at, i18n.language)}`
                        : ''}
                    </p>
                  </div>
                  <a
                    href={doc.download_url}
                    className="shrink-0 text-xs font-medium text-oe-blue hover:underline"
                    data-testid={`download-${doc.id}`}
                  >
                    {t('buyer_portal.documents.download', {
                      defaultValue: 'Download',
                    })}
                  </a>
                </li>
              ))}
            </ul>
          )}

          {/* KYC upload requests */}
          <div className="mt-5 pt-5 border-t border-border-light/50">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-content-tertiary">
              {t('buyer_portal.kyc.title', {
                defaultValue: 'Documents we need from you',
              })}
            </h3>
            <ul className="mt-3 space-y-2">
              {data.kyc_requests.map((req) => (
                <li
                  key={req.code}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border-light/50 px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="text-sm text-content-primary flex items-center gap-2">
                      {req.label}
                      {req.is_uploaded && (
                        <CheckCircle2
                          size={14}
                          className="text-semantic-success"
                          aria-label={t('buyer_portal.kyc.uploaded', {
                            defaultValue: 'Uploaded',
                          })}
                        />
                      )}
                    </p>
                    {req.description && (
                      <p className="text-2xs text-content-tertiary">
                        {req.description}
                      </p>
                    )}
                  </div>
                  <label
                    className="shrink-0 inline-flex items-center justify-center gap-1.5 h-8 px-3 rounded-md bg-surface-secondary border border-border-light text-xs font-medium text-content-primary hover:bg-surface-tertiary cursor-pointer"
                    data-testid={`kyc-upload-${req.code}`}
                  >
                    {uploadBusy === req.code ? (
                      <Loader2 size={12} className="animate-spin" />
                    ) : (
                      <Upload size={12} aria-hidden />
                    )}
                    {req.is_uploaded
                      ? t('buyer_portal.kyc.replace', {
                          defaultValue: 'Replace',
                        })
                      : t('buyer_portal.kyc.upload', {
                          defaultValue: 'Upload',
                        })}
                    <input
                      type="file"
                      accept="application/pdf,image/png,image/jpeg,image/heic,image/heif"
                      className="sr-only"
                      onChange={(e) =>
                        handleKycUpload(e, req.code as PortalKycCode)
                      }
                      disabled={uploadBusy !== null}
                    />
                  </label>
                </li>
              ))}
            </ul>
            {uploadError && (
              <p
                role="alert"
                className="mt-3 text-xs text-semantic-error"
                data-testid="kyc-upload-error"
              >
                {uploadError}
              </p>
            )}
          </div>
        </section>

        {/* Contact agent */}
        <section
          aria-labelledby="contact-heading"
          data-testid="contact-section"
          className="rounded-2xl border border-border-light bg-surface-elevated p-5"
        >
          <h2
            id="contact-heading"
            className="text-sm font-semibold text-content-primary flex items-center gap-2"
          >
            <Mail size={16} aria-hidden />
            {t('buyer_portal.contact.title', {
              defaultValue: 'Contact your agent',
            })}
          </h2>
          {contactSent ? (
            <div
              data-testid="contact-sent"
              className="mt-3 rounded-lg bg-semantic-success/10 text-semantic-success px-3 py-2 text-xs"
              role="status"
            >
              {t('buyer_portal.contact.sent', {
                defaultValue:
                  'Thank you — your agent will reply shortly.',
              })}
            </div>
          ) : (
            <form
              onSubmit={handleContactSubmit}
              className="mt-3 space-y-3"
              aria-label={t('buyer_portal.contact.form_label', {
                defaultValue: 'Contact agent form',
              })}
            >
              <label className="block">
                <span className="text-2xs uppercase tracking-wide text-content-tertiary">
                  {t('buyer_portal.contact.message', {
                    defaultValue: 'Your message',
                  })}
                </span>
                <textarea
                  required aria-required="true"
                  maxLength={2000}
                  rows={4}
                  value={contactMessage}
                  onChange={(e) => setContactMessage(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-border-light bg-surface-primary px-3 py-2 text-sm text-content-primary placeholder:text-content-quaternary focus:outline-none focus:ring-2 focus:ring-oe-blue/50"
                  placeholder={t('buyer_portal.contact.message_placeholder', {
                    defaultValue: 'Ask a question, request an update…',
                  })}
                  data-testid="contact-message"
                />
              </label>
              <label className="block">
                <span className="text-2xs uppercase tracking-wide text-content-tertiary">
                  {t('buyer_portal.contact.phone', {
                    defaultValue: 'Callback phone (optional)',
                  })}
                </span>
                <input
                  type="tel"
                  maxLength={40}
                  value={contactPhone}
                  onChange={(e) => setContactPhone(e.target.value)}
                  className="mt-1 w-full h-9 rounded-lg border border-border-light bg-surface-primary px-3 text-sm text-content-primary placeholder:text-content-quaternary focus:outline-none focus:ring-2 focus:ring-oe-blue/50"
                  placeholder="+49 30 12345678"
                  data-testid="contact-phone"
                />
              </label>
              <button
                type="submit"
                disabled={contactSending || contactMessage.trim().length === 0}
                className="inline-flex items-center justify-center gap-2 h-9 px-4 rounded-lg bg-oe-blue text-white text-sm font-medium hover:bg-oe-blue-hover disabled:opacity-50"
                data-testid="contact-submit"
              >
                {contactSending ? (
                  <Loader2 size={14} className="animate-spin" aria-hidden />
                ) : (
                  <Mail size={14} aria-hidden />
                )}
                {t('buyer_portal.contact.submit', {
                  defaultValue: 'Send message',
                })}
              </button>
            </form>
          )}
        </section>
      </main>
    </ShellWrapper>
  );
}

// ── Tiny helper components ────────────────────────────────────────────


function ShellWrapper({
  children,
  buyerName,
  locale,
}: {
  children: React.ReactNode;
  buyerName?: string;
  locale?: string;
}) {
  const { t, i18n } = useTranslation();

  // Bare-minimum top-3 locale switcher. We keep it minimal to stay
  // dependency-free — the production app's full LocaleSwitcher lives
  // behind the authenticated shell which we deliberately bypass here.
  const SUPPORTED: ReadonlyArray<{ code: string; label: string }> = [
    { code: 'en', label: 'EN' },
    { code: 'de', label: 'DE' },
    { code: 'ru', label: 'RU' },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-surface-secondary via-surface-primary to-surface-elevated">
      <header className="w-full border-b border-border-light bg-surface-primary/80 backdrop-blur supports-[backdrop-filter]:bg-surface-primary/60">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <div
              className="w-8 h-8 rounded-md bg-oe-blue text-white grid place-items-center text-sm font-bold"
              aria-hidden
            >
              OE
            </div>
            <span className="text-sm font-medium text-content-primary">
              {t('buyer_portal.brand', {
                defaultValue: 'Buyer portal',
              })}
            </span>
          </div>
          {buyerName && (
            <span className="hidden sm:block text-xs text-content-tertiary truncate max-w-[40ch]">
              {t('buyer_portal.header.greeting', {
                defaultValue: 'Welcome, {{name}}',
                name: buyerName,
              })}
            </span>
          )}
          <nav
            aria-label={t('buyer_portal.locale.label', {
              defaultValue: 'Language',
            })}
            className="flex items-center gap-1"
          >
            {SUPPORTED.map((loc) => (
              <button
                key={loc.code}
                type="button"
                onClick={() => i18n.changeLanguage(loc.code)}
                className={`text-2xs font-medium px-2 py-1 rounded ${
                  (locale || i18n.language).startsWith(loc.code)
                    ? 'bg-oe-blue text-white'
                    : 'text-content-tertiary hover:bg-surface-secondary'
                }`}
                data-testid={`locale-${loc.code}`}
                aria-pressed={(locale || i18n.language).startsWith(loc.code)}
              >
                {loc.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {children}

      <footer className="w-full border-t border-border-light mt-10">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 py-4 text-2xs text-content-tertiary flex items-center justify-between gap-3 flex-wrap">
          <span>
            {t('buyer_portal.footer.contact', {
              defaultValue: 'Questions? Email',
            })}{' '}
            <a
              href="mailto:info@datadrivenconstruction.io"
              className="text-oe-blue hover:underline"
            >
              info@datadrivenconstruction.io
            </a>
          </span>
          <a
            href="https://www.gnu.org/licenses/agpl-3.0.html"
            target="_blank"
            rel="noreferrer"
            className="hover:underline"
          >
            AGPL-3.0
          </a>
        </div>
      </footer>
    </div>
  );
}


function StatusBadge({ status }: { status: string }) {
  const tone =
    status === 'active' || status === 'signed' || status === 'countersigned'
      ? 'bg-semantic-success/10 text-semantic-success'
      : status === 'cancelled' || status === 'expired'
      ? 'bg-semantic-error/10 text-semantic-error'
      : 'bg-surface-secondary text-content-secondary';
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-2xs font-medium ${tone}`}
    >
      {status}
    </span>
  );
}


function InstalmentStatusPill({
  status,
}: {
  status: 'pending' | 'due' | 'overdue' | 'paid' | 'waived' | 'cancelled';
}) {
  const tone =
    status === 'paid'
      ? 'bg-semantic-success/10 text-semantic-success'
      : status === 'overdue'
      ? 'bg-semantic-error/10 text-semantic-error'
      : status === 'due'
      ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300'
      : status === 'waived' || status === 'cancelled'
      ? 'bg-surface-secondary text-content-tertiary'
      : 'bg-surface-secondary text-content-secondary';
  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-medium ${tone}`}
    >
      {status === 'overdue' && <Clock size={10} aria-hidden />}
      {status}
    </span>
  );
}


function formatMoney(amount: string, currency: string, locale: string): string {
  // Money is on the wire as a plain-decimal string (R7 convention).
  // We parse to Number for display — precision is fine at the
  // ≤12-digit values typical of property pricing. For pure
  // ledger-correctness we'd keep Decimal end-to-end, but the buyer
  // portal is a display surface.
  if (!amount) return '';
  const value = Number(amount);
  if (!isFinite(value)) return amount;
  try {
    return new Intl.NumberFormat(locale || 'en', {
      style: 'currency',
      currency: (currency || 'EUR').toUpperCase(),
      maximumFractionDigits: 2,
    }).format(value);
  } catch {
    return `${amount} ${currency}`.trim();
  }
}


function formatDate(iso: string, locale: string): string {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return new Intl.DateTimeFormat(locale || 'en', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    }).format(d);
  } catch {
    return iso;
  }
}
