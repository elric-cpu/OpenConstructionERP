import type { ModuleGuideContent } from '@/shared/ui';

/**
 * "How it works" guide content for the Dashboard module.
 *
 * Co-located with the feature. Consumed by <ModuleGuideButton content={dashboardGuide} />
 * rendered next to the Dashboard tour button in DashboardPage.tsx. Every key carries an
 * inline English defaultValue; none of these keys live in en.ts or any locale file.
 *
 * Key prefix: guide.dashboard.*
 * Spotlight selectors reuse the same data-testid hooks the Dashboard ProductTour uses.
 */
export const dashboardGuide: ModuleGuideContent = {
  titleKey: 'guide.dashboard.title',
  titleDefault: 'Dashboard',
  introKey: 'guide.dashboard.intro',
  introDefault:
    'The Dashboard is your home base. It rolls up every project into one view: headline numbers, budget health, open work for today, and shortcuts into the rest of the platform. You do not enter data here directly. Instead you read the rollups and click through to the page where the real work happens.',
  sections: [
    {
      icon: 'Rocket',
      titleKey: 'guide.dashboard.actions.title',
      titleDefault: 'Primary actions and quick start',
      bodyKey: 'guide.dashboard.actions.body',
      bodyDefault:
        'The buttons at the top start the most common jobs. New Estimate opens a fresh Bill of Quantities, Quick Start resumes your most recent estimate or creates one, and Customize lets you reorder, show or hide the widgets below. Pick an action to begin, the Dashboard itself stays read-only.',
      spotlightSelector: '[data-testid="dashboard-tour-hero-actions"]',
    },
    {
      icon: 'BookOpen',
      titleKey: 'guide.dashboard.kpi.title',
      titleDefault: 'Reading the KPI ribbon',
      bodyKey: 'guide.dashboard.kpi.body',
      bodyDefault:
        'Four tiles summarise your whole portfolio: Total Value, Active Estimates, Schedule Status and Priced positions. Total Value never blends currencies, so projects in different currencies show as separate chips side by side. Priced positions is the share of BOQ lines that already carry a unit rate, click it to run validation when no figure exists yet.',
      spotlightSelector: '[data-testid="dashboard-tour-kpi-ribbon"]',
    },
    {
      icon: 'Layers',
      titleKey: 'guide.dashboard.cost.title',
      titleDefault: 'Cost and portfolio widgets',
      bodyKey: 'guide.dashboard.cost.body',
      bodyDefault:
        'Portfolio Overview compares each project budget against actual cost and flags anything over budget. The Today panel scopes to your active project and lists open tasks, RFIs and safety incidents that need attention. These widgets read numbers entered elsewhere, so keep your BOQ rates and budgets current and the figures here stay accurate.',
    },
    {
      icon: 'Workflow',
      titleKey: 'guide.dashboard.projects.title',
      titleDefault: 'Project picker and drill-in',
      bodyKey: 'guide.dashboard.projects.body',
      bodyDefault:
        'The projects list shows every active project as a card. Click a card to set it as your active project and open its detail page. Setting an active project also narrows the Today panel and the project-scoped links so the dashboard and the next page always show the same data.',
      spotlightSelector: '[data-testid="dashboard-tour-projects-list"]',
    },
    {
      icon: 'ListChecks',
      titleKey: 'guide.dashboard.start.title',
      titleDefault: 'Getting started, step by step',
      bodyKey: 'guide.dashboard.start.body',
      bodyDefault:
        'New to the platform? Follow the Getting Started checklist below the ribbon: load a cost database, enable AI search, connect your AI keys, create a project, build a BOQ and set quantities. Each step turns green once done. Next Steps then suggests what to do next based on how far along your estimate is.',
    },
  ],
  ctaKey: 'guide.dashboard.cta',
  ctaDefault: 'Start a new estimate',
};
