import { useState, useEffect, useRef, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Mail, Check, X, Loader2, ExternalLink } from 'lucide-react';
import clsx from 'clsx';

/**
 * Newsletter Subscribe button + inline popover.
 *
 * Sits in the right-side header cluster next to Help/Support (was
 * previously absolutely-centred across the topbar). Sized to match the
 * Support pill — same ``h-8 px-3`` icon-with-label format on desktop,
 * icon-only on mobile. Sky-blue accent visually distinguishes it from
 * the neutral Help button and the amber Support pill so the three CTAs
 * don't all read as the same chrome.
 *
 * On click, opens a small popover (not a full modal) with a single
 * email field that POSTs JSON to ``/api/subscribe`` — the same endpoint
 * the marketing site exposes.
 *
 * Production: Caddy proxies ``/api/subscribe`` to the demo-register-api
 * Python service (per-deployment SMTP). Local dev: that path 404s
 * against the FastAPI backend on :9090. We detect dev mode and surface
 * a clearer "service offline" message + always offer a mailto fallback
 * so the user can still get their address to the team.
 *
 * Once the user has subscribed we persist a localStorage flag so the
 * trigger renders as a subtle "Subscribed" check pill instead of the
 * default Mail label. Re-clicking still opens the popover (so the user
 * can switch addresses or unsubscribe via the link in the confirmation
 * email).
 */

const STORAGE_KEY = 'oe.newsletter_subscribed';
const QUEUED_KEY = 'oe.newsletter_queued_emails';
const FALLBACK_MAILTO_RECIPIENT = 'info@datadrivenconstruction.io';

type Status = 'idle' | 'submitting' | 'success' | 'error';

interface SubscribeResponse {
  status?: string;
  message?: string;
}

function getInitialSubscribed(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

/** True if we appear to be running in a local dev environment.
 *  Used to swap the error copy from a scary "Couldn't subscribe" to a
 *  truthful "the subscribe service isn't running locally — production
 *  users can subscribe normally". */
function isLocalDev(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    // Vite injects ``import.meta.env.DEV`` at build time. In production
    // bundles this is ``false`` so this branch is dead-code-eliminated.
    if (import.meta.env?.DEV) return true;
  } catch {
    // ignore — older bundlers, SSR, etc.
  }
  const host = window.location.hostname;
  return (
    host === 'localhost' ||
    host === '127.0.0.1' ||
    host === '::1' ||
    host.endsWith('.local')
  );
}

/** Persist an attempted subscription so we don't lose it if the
 *  service is offline. Best-effort — localStorage may be unavailable
 *  in private-mode browsers. */
function queueEmailLocally(email: string): void {
  try {
    const raw = window.localStorage.getItem(QUEUED_KEY);
    const list = raw ? (JSON.parse(raw) as string[]) : [];
    if (!list.includes(email)) {
      list.push(email);
      window.localStorage.setItem(QUEUED_KEY, JSON.stringify(list));
    }
  } catch {
    /* ignore */
  }
}

/** Build the mailto fallback the user can hit when the backend isn't
 *  reachable. Pre-fills subject + body so a single click in the mail
 *  client sends a real signup request. */
function buildMailtoHref(email: string, lang: string): string {
  const subject = 'Newsletter signup — OpenConstructionERP';
  const bodyLines = [
    'Please add this email to the OpenConstructionERP newsletter:',
    '',
    `Email: ${email || '(your email here)'}`,
    lang ? `Language: ${lang}` : '',
    '',
    'Thanks!',
  ].filter(Boolean);
  return `mailto:${FALLBACK_MAILTO_RECIPIENT}?subject=${encodeURIComponent(
    subject,
  )}&body=${encodeURIComponent(bodyLines.join('\n'))}`;
}

export function SubscribeButton() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState('');
  const [honey, setHoney] = useState(''); // honeypot — bots fill it, humans don't
  const [status, setStatus] = useState<Status>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  // Distinguishes "real server said no" from "we never reached a server"
  // — the latter is what triggers the friendlier dev/offline copy.
  const [serviceOffline, setServiceOffline] = useState(false);
  const [subscribed, setSubscribed] = useState<boolean>(getInitialSubscribed);
  const ref = useRef<HTMLDivElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const successTimer = useRef<number | null>(null);
  const devMode = isLocalDev();

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  // Close on Esc.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open]);

  // Autofocus the email field once the popover opens (after the next
  // paint, otherwise the ref isn't attached yet).
  useEffect(() => {
    if (open && status === 'idle') {
      const id = window.setTimeout(() => emailRef.current?.focus(), 20);
      return () => window.clearTimeout(id);
    }
    return undefined;
  }, [open, status]);

  // Reset transient form state each time the popover closes so the next
  // open shows the form again (not a stale success/error banner).
  useEffect(() => {
    if (open) return;
    if (successTimer.current !== null) {
      window.clearTimeout(successTimer.current);
      successTimer.current = null;
    }
    // Defer one tick so the closing animation doesn't flash the reset form.
    const id = window.setTimeout(() => {
      setStatus('idle');
      setErrorMsg(null);
      setServiceOffline(false);
      // Keep the email field populated only if we failed — successful
      // submits and dismissals both clear it.
    }, 200);
    return () => window.clearTimeout(id);
  }, [open]);

  // Tidy up the success-auto-close timer on unmount.
  useEffect(() => {
    return () => {
      if (successTimer.current !== null) {
        window.clearTimeout(successTimer.current);
      }
    };
  }, []);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      // Honeypot tripped — pretend success silently so the bot doesn't
      // learn anything from a 4xx.
      if (honey.trim().length > 0) {
        setStatus('success');
        return;
      }
      const trimmed = email.trim();
      // Minimal sanity check — server does the real validation.
      if (trimmed.length === 0 || !trimmed.includes('@')) {
        setStatus('error');
        setServiceOffline(false);
        setErrorMsg(
          t('header.subscribe.error', { defaultValue: "Couldn't subscribe — try again." }),
        );
        return;
      }

      setStatus('submitting');
      setErrorMsg(null);
      setServiceOffline(false);

      const lang =
        typeof document !== 'undefined'
          ? document.documentElement.getAttribute('lang') ?? ''
          : '';

      try {
        const resp = await fetch('/api/subscribe', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
          },
          body: JSON.stringify({
            email: trimmed,
            source: 'header-popover',
            lang,
          }),
        });
        let body: SubscribeResponse | null = null;
        try {
          body = (await resp.json()) as SubscribeResponse;
        } catch {
          body = null;
        }
        if (resp.ok && body && body.status === 'subscribed') {
          setStatus('success');
          setEmail('');
          try {
            window.localStorage.setItem(STORAGE_KEY, '1');
          } catch {
            // Ignore — best-effort persistence.
          }
          setSubscribed(true);
          successTimer.current = window.setTimeout(() => {
            setOpen(false);
            successTimer.current = null;
          }, 3000);
          return;
        }
        // 404 from the FastAPI backend means the subscribe service
        // isn't proxied at this deployment (common in local dev — only
        // the production Caddy maps /api/subscribe to demo-register-api).
        // Treat that as "offline" so we surface the mailto fallback
        // instead of a generic "couldn't subscribe" error.
        if (resp.status === 404 || resp.status === 502 || resp.status === 503) {
          queueEmailLocally(trimmed);
          setStatus('error');
          setServiceOffline(true);
          setErrorMsg(
            devMode
              ? t('header.subscribe.dev_warning', {
                  defaultValue: 'Local dev — your address is queued.',
                })
              : t('header.subscribe.service_offline', {
                  defaultValue:
                    "The subscribe service isn't reachable right now — email us instead.",
                }),
          );
          return;
        }
        setStatus('error');
        setServiceOffline(false);
        setErrorMsg(
          (body && body.message) ||
            t('header.subscribe.error', { defaultValue: "Couldn't subscribe — try again." }),
        );
      } catch {
        // Network-level failure (DNS, CORS, offline). Queue the email
        // locally and offer the mailto fallback.
        queueEmailLocally(trimmed);
        setStatus('error');
        setServiceOffline(true);
        setErrorMsg(
          devMode
            ? t('header.subscribe.dev_warning', {
                defaultValue: 'Local dev — your address is queued.',
              })
            : t('header.subscribe.service_offline', {
                defaultValue:
                  "The subscribe service isn't reachable right now — email us instead.",
              }),
        );
      }
    },
    [email, honey, t, devMode],
  );

  const buttonLabel = subscribed
    ? t('header.subscribe.subscribed', { defaultValue: 'Subscribed' })
    : t('header.subscribe.button', { defaultValue: 'Subscribe to news' });
  const ariaLabel = subscribed
    ? t('header.subscribe.aria', { defaultValue: 'Subscribe to product news' })
    : t('header.subscribe.button_short', { defaultValue: 'Subscribe' });

  return (
    <div className="relative" ref={ref} data-testid="header-subscribe">
      {/* Desktop pill — sized to match SupportUsButton (h-8 px-3,
          icon+label). Sky-blue accent so it doesn't blend into the
          neutral Help button next to it. */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={ariaLabel}
        title={buttonLabel}
        data-testid="header-subscribe-trigger"
        className={clsx(
          'hidden md:inline-flex relative items-center gap-1.5 h-8 px-3 rounded-lg',
          'border transition-colors duration-fast ease-oe text-xs font-semibold',
          subscribed
            ? clsx(
                'border-emerald-400/50 bg-emerald-50/70 text-emerald-700',
                'dark:border-emerald-500/40 dark:bg-emerald-950/30 dark:text-emerald-300',
                'hover:bg-emerald-50 dark:hover:bg-emerald-950/50',
              )
            : clsx(
                'border-sky-400/50 bg-sky-50/70 text-sky-700',
                'dark:border-sky-500/40 dark:bg-sky-950/30 dark:text-sky-300',
                'hover:border-sky-500 hover:bg-sky-100/80',
                'dark:hover:border-sky-400/60 dark:hover:bg-sky-900/40',
              ),
          open && 'ring-1 ring-sky-400/40 ring-offset-0',
        )}
      >
        {subscribed ? (
          <Check size={14} strokeWidth={2} className="shrink-0" />
        ) : (
          <Mail size={14} strokeWidth={2} className="shrink-0" />
        )}
        <span className="whitespace-nowrap tracking-wide truncate max-w-[140px]">
          {buttonLabel}
        </span>
      </button>

      {/* Mobile fallback — icon-only square matching the Help button
          footprint on small screens. */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={t('header.subscribe.button_short', { defaultValue: 'Subscribe' })}
        title={buttonLabel}
        className={clsx(
          'md:hidden inline-flex h-8 w-8 items-center justify-center rounded-lg',
          'transition-colors',
          subscribed
            ? 'text-emerald-600 hover:bg-surface-secondary'
            : 'text-sky-600 hover:bg-surface-secondary',
        )}
      >
        {subscribed ? (
          <Check size={16} strokeWidth={1.75} />
        ) : (
          <Mail size={16} strokeWidth={1.75} />
        )}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label={t('header.subscribe.title', { defaultValue: 'Get release notes by email' })}
          className={clsx(
            // Anchored to the trigger's right edge so the popover
            // doesn't fall off the viewport on the right side of the
            // header (was previously centred on the trigger when the
            // button lived mid-header).
            'absolute top-full right-0 mt-1.5 w-72',
            'rounded-xl border border-border-light bg-surface-elevated shadow-lg',
            'animate-scale-in py-3 px-3 z-40',
          )}
        >
          <div className="flex items-start gap-2 mb-2">
            <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-sky-500/10">
              <Mail size={13} className="text-sky-600" />
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-content-primary leading-snug">
                {t('header.subscribe.title', { defaultValue: 'Get release notes by email' })}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label={t('header.subscribe.cancel', { defaultValue: 'Cancel' })}
              className="shrink-0 p-0.5 rounded text-content-quaternary hover:bg-surface-secondary hover:text-content-secondary transition-colors"
            >
              <X size={14} />
            </button>
          </div>

          {status === 'success' ? (
            <div
              role="status"
              className="flex items-start gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2.5"
            >
              <Check size={14} className="mt-0.5 text-emerald-600 dark:text-emerald-400 shrink-0" />
              <p className="text-xs text-emerald-700 dark:text-emerald-300 leading-snug">
                {t('header.subscribe.success', {
                  defaultValue: 'Thanks! Check your inbox to confirm.',
                })}
              </p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} noValidate>
              {/* Honeypot — bots fill any visible field, the user never
                  sees this one. Matches the marketing-site pattern. */}
              <input
                type="text"
                name="_honey"
                tabIndex={-1}
                autoComplete="off"
                value={honey}
                onChange={(e) => setHoney(e.target.value)}
                aria-hidden
                style={{
                  position: 'absolute',
                  left: '-9999px',
                  width: '1px',
                  height: '1px',
                  opacity: 0,
                  pointerEvents: 'none',
                }}
              />
              <label htmlFor="oe-subscribe-email" className="sr-only">
                {t('header.subscribe.email_placeholder', { defaultValue: 'you@example.com' })}
              </label>
              <input
                ref={emailRef}
                id="oe-subscribe-email"
                type="email"
                name="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={t('header.subscribe.email_placeholder', {
                  defaultValue: 'you@example.com',
                })}
                disabled={status === 'submitting'}
                className={clsx(
                  'w-full rounded-lg border border-border-light bg-surface-secondary',
                  'px-2.5 py-1.5 text-sm text-content-primary placeholder:text-content-quaternary',
                  'focus:outline-none focus:ring-2 focus:ring-sky-500/30 focus:border-sky-500',
                  'disabled:opacity-60',
                )}
              />

              {errorMsg && (
                <p
                  role="alert"
                  className={clsx(
                    'mt-1.5 text-2xs leading-snug',
                    serviceOffline
                      ? 'text-amber-700 dark:text-amber-400'
                      : 'text-semantic-error',
                  )}
                >
                  {errorMsg}
                </p>
              )}

              {/* Mailto fallback — always visible. Becomes the primary
                  action when the backend is offline; stays as a quiet
                  secondary link otherwise. Open-source users running
                  locally without a mailer service can still reach the
                  team this way. */}
              {serviceOffline && (
                <a
                  href={buildMailtoHref(email.trim(), lang())}
                  className={clsx(
                    'mt-2 inline-flex items-center gap-1.5 rounded-md',
                    'border border-amber-400/50 bg-amber-50/70 px-2.5 py-1.5',
                    'text-2xs font-semibold text-amber-700',
                    'dark:border-amber-500/40 dark:bg-amber-950/30 dark:text-amber-300',
                    'hover:bg-amber-100 dark:hover:bg-amber-900/40 transition-colors',
                  )}
                >
                  <Mail size={11} />
                  {t('header.subscribe.mailto_fallback', {
                    defaultValue: 'Email us instead →',
                  })}
                </a>
              )}

              <div className="mt-2 flex items-center gap-2">
                <button
                  type="submit"
                  disabled={status === 'submitting'}
                  className={clsx(
                    'flex h-8 flex-1 items-center justify-center gap-1.5 rounded-lg px-3',
                    'bg-sky-600 text-xs font-semibold text-white',
                    'shadow-[0_1px_2px_rgba(2,132,199,0.25)]',
                    'transition-colors hover:bg-sky-700',
                    'disabled:opacity-60 disabled:cursor-not-allowed',
                  )}
                >
                  {status === 'submitting' ? (
                    <>
                      <Loader2 size={12} className="animate-spin" />
                      <span>{t('common.loading', { defaultValue: 'Loading…' })}</span>
                    </>
                  ) : (
                    <span>{t('header.subscribe.cta', { defaultValue: 'Subscribe' })}</span>
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  disabled={status === 'submitting'}
                  className={clsx(
                    'flex h-8 items-center justify-center rounded-lg px-3',
                    'text-xs font-medium text-content-secondary',
                    'hover:bg-surface-secondary transition-colors',
                    'disabled:opacity-60',
                  )}
                >
                  {t('header.subscribe.cancel', { defaultValue: 'Cancel' })}
                </button>
              </div>

              {!serviceOffline && (
                <p className="mt-2 text-[10.5px] text-content-tertiary leading-snug">
                  {t('header.subscribe.privacy', {
                    defaultValue: 'No spam. Unsubscribe anytime.',
                  })}{' '}
                  <a
                    href={buildMailtoHref(email.trim(), lang())}
                    className="inline-flex items-center gap-0.5 text-content-secondary hover:text-sky-600 hover:underline"
                  >
                    {t('header.subscribe.mailto_fallback', {
                      defaultValue: 'Email us instead →',
                    })}
                    <ExternalLink size={9} />
                  </a>
                </p>
              )}
            </form>
          )}
        </div>
      )}
    </div>
  );
}

/** Pull the current ``lang`` attribute off the document so we can stamp
 *  the mailto body with the user's UI language. Returns an empty string
 *  during SSR — `buildMailtoHref` skips the field when blank. */
function lang(): string {
  if (typeof document === 'undefined') return '';
  return document.documentElement.getAttribute('lang') ?? '';
}
