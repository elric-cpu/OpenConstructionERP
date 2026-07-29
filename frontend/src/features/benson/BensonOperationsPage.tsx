import { Building2, Clock3, MapPin, ShieldCheck } from 'lucide-react';
import { editionConfig } from '@/editions/config';

const operatingFacts = [
  { icon: MapPin, label: 'Operating region', value: 'Eastern Oregon' },
  { icon: Building2, label: 'Project jurisdiction', value: 'County and local authority required' },
  { icon: Clock3, label: 'Project timezone', value: 'Project-specific IANA timezone required' },
  { icon: ShieldCheck, label: 'Runtime language', value: 'English only' },
];

export function BensonOperationsPage() {
  return (
    <main className="space-y-6" data-testid="benson-operations-page">
      <header>
        <p className="text-sm font-medium uppercase tracking-wide text-oe-blue">Benson edition</p>
        <h1 className="mt-1 text-2xl font-semibold text-slate-900">Integrated operations</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          Benson capabilities extend the complete OpenConstructionERP {__APP_VERSION__} application.
        </p>
      </header>

      <section className="grid gap-4 md:grid-cols-2" aria-label="Benson operating profile">
        {operatingFacts.map(({ icon: Icon, label, value }) => (
          <article key={label} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <Icon className="h-5 w-5 text-oe-blue" aria-hidden="true" />
            <h2 className="mt-3 text-sm font-semibold text-slate-900">{label}</h2>
            <p className="mt-1 text-sm text-slate-600">{value}</p>
          </article>
        ))}
      </section>

      <p className="text-xs text-slate-500">
        Region profile: {editionConfig.defaultRegion || 'not configured'}
      </p>
    </main>
  );
}

export default BensonOperationsPage;
