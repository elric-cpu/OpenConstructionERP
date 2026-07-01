/**
 * ModuleDeveloperGuide - in-app, readable guide for building your own module.
 * The body is authored as Markdown (moduleDeveloperGuide.md) and rendered with
 * the shared <Markdown> component, so the content stays clear and easy to edit
 * and reads the same here as it does on GitHub. Mirrors the repo's MODULES.md.
 */

import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { Breadcrumb, Card, Markdown } from '@/shared/ui';
import { PageHeader } from '@/shared/ui/PageHeader';
import guideMarkdown from './moduleDeveloperGuide.md?raw';

export function ModuleDeveloperGuide() {
  const { t } = useTranslation();

  // Deep-link support: when opened with a #hash (e.g. the Partner Packs tab
  // links to #partner-packs), scroll that section into view after render. The
  // Markdown heading ids are slugs of the heading text, so "## Partner Packs"
  // becomes #partner-packs.
  useEffect(() => {
    if (typeof window === 'undefined' || !window.location.hash) return;
    try {
      const el = document.querySelector(window.location.hash);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch {
      // Ignore an invalid selector from a malformed hash.
    }
  }, []);

  return (
    <div className="space-y-5 animate-fade-in">
      <Breadcrumb
        items={[
          { label: t('nav.modules', 'Modules'), to: '/modules' },
          { label: t('modules.dev_guide', 'Developer guide') },
        ]}
      />

      <PageHeader
        srTitle={t('modules.dev_guide_title', { defaultValue: 'Build your own module' })}
        subtitle={t('modules.dev_guide_subtitle', {
          defaultValue:
            'A practical, 10-minute walkthrough for adding business features to OpenConstructionERP.',
        })}
        actions={
          <Link
            to="/modules"
            className="inline-flex items-center gap-1 text-xs text-content-tertiary hover:text-oe-blue transition-colors"
          >
            <ArrowLeft size={12} />
            {t('modules.back_to_modules', { defaultValue: 'Back to Modules & Marketplace' })}
          </Link>
        }
      />

      <Card>
        <div className="p-6 md:p-8">
          <Markdown source={guideMarkdown} className="max-w-3xl" />
        </div>
      </Card>
    </div>
  );
}

export default ModuleDeveloperGuide;
