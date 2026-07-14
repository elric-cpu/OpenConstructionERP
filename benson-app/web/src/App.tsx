import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { BriefcaseBusiness, CalendarDays, ClipboardCheck, Hammer, Home, Inbox, Menu, Search, Sparkles, Users, X } from 'lucide-react';

type Dashboard = { metrics: Record<string, number>; attention: unknown[]; schedule: unknown[]; jobs: unknown[] };
const empty: Dashboard = { metrics: { new_leads: 0, active_jobs: 0, open_tasks: 0, unbilled_work: 0 }, attention: [], schedule: [], jobs: [] };
const nav = [[Home,'Overview'],[Inbox,'Leads'],[BriefcaseBusiness,'Jobs'],[CalendarDays,'Schedule'],[ClipboardCheck,'Estimates'],[Users,'Customers']] as const;

export function App() {
  const [data, setData] = useState(empty), [online, setOnline] = useState(true), [menu, setMenu] = useState(false);
  useEffect(() => { fetch('/api/v1/dashboard').then(r => { if (!r.ok) throw Error(); return r.json(); }).then(setData).catch(() => setOnline(false)); }, []);
  const metrics: [string,string|number][] = [['New leads',data.metrics.new_leads],['Active jobs',data.metrics.active_jobs],['Open tasks',data.metrics.open_tasks],['Unbilled work',`$${data.metrics.unbilled_work.toLocaleString()}`]];
  const today = new Intl.DateTimeFormat('en-US', { weekday: 'long', month: 'long', day: 'numeric' }).format(new Date());
  return <div className="shell">
    <aside className={menu?'open':''}><div className="brand"><span>BH</span><div><b>Benson</b><small>Operations</small></div><button aria-label="Close menu" onClick={()=>setMenu(false)}><X/></button></div><nav>{nav.map(([Icon,label],i)=><a className={i===0?'active':''} href="#" key={label}><Icon/>{label}</a>)}</nav><div className="rail-foot"><div className="avatar">EB</div><div><b>Owner</b><small>Burns, Oregon</small></div></div></aside>
    <main><header><button className="menu" aria-label="Open menu" onClick={()=>setMenu(true)}><Menu/></button><div className="search"><Search/><input aria-label="Search" placeholder="Search jobs, customers, addresses…"/></div><span className={online?'status':'status offline'}>{online?'System ready':'Offline preview'}</span></header>
      <div className="content"><div className="headline"><div><p>{today}</p><h1>Good morning.</h1><span>Here’s what needs your attention today.</span></div><button className="primary">+ New lead</button></div>
        <section className="metrics">{metrics.map(([label,value])=><article key={label}><small>{label}</small><strong>{value}</strong><em>Live workspace total</em></article>)}</section>
        <div className="grid"><Panel title="Needs attention" subtitle="Items that could hold up work or cash flow." link="View all"><Empty icon={<ClipboardCheck/>} title="You’re caught up" body="New approvals, overdue tasks, and follow-ups will appear here."/></Panel>
          <section className="panel agent"><div className="agent-head"><Sparkles/><div><h2>Benson Assistant</h2><p>Powered through your private AI gateway</p></div></div><p>Ask for a summary, draft, or next-step list. Nothing external is sent without confirmation.</p><div className="prompts"><button>Summarize new leads</button><button>What needs attention?</button><button>Draft a follow-up</button></div><div className="ask"><input aria-label="Ask Benson Assistant" placeholder="Ask about your operations…"/><button>Ask</button></div></section>
          <Panel title="Today’s schedule" subtitle="Field visits and committed work." link="Open calendar"><Empty icon={<CalendarDays/>} title="No visits scheduled" body="Add work from a job or estimate." compact/></Panel>
          <Panel title="Active jobs" subtitle="Current residential work." link="View jobs"><Empty icon={<Hammer/>} title="No active jobs yet" body="Accepted estimates will appear here." compact/></Panel></div>
      </div></main></div>;
}
function Panel({title,subtitle,link,children}:{title:string;subtitle:string;link:string;children:ReactNode}){return <section className="panel"><div className="panel-title"><div><h2>{title}</h2><p>{subtitle}</p></div><a href="#">{link}</a></div>{children}</section>}
function Empty({icon,title,body,compact=false}:{icon:ReactNode;title:string;body:string;compact?:boolean}){return <div className={`empty ${compact?'compact':''}`}>{icon}<h3>{title}</h3><p>{body}</p></div>}
