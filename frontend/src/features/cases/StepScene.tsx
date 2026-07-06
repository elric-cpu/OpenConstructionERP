// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// StepScene - a small line-art illustration of WHAT a case/how-to step does.
//
// Keyed off the step's existing lucide `icon` name, so it needs no change to the
// 63 playbook data files. Icons without a bespoke scene fall back to a framed
// version of the step's own glyph, so every step gets a clean picture. Slate
// linework on an always-light tile (like CaseArt / RoleArt) so it reads the same
// in light and dark theme, with one accent colour per scene for a spot of life.

import { type ReactElement } from 'react';
import { type LucideIcon } from 'lucide-react';
import clsx from 'clsx';
import { iconFor } from './icons';

interface StepSceneProps {
  /** The step's lucide icon name; selects the scene. */
  icon?: string;
  /** Accent colour (hex) for the one highlight per scene. Defaults to oe-blue. */
  accent?: string;
  /** Extra classes for the tile (height / width / rounding). */
  className?: string;
  /** Fallback glyph when the icon has no bespoke scene (e.g. the how-to hub
   *  passes the module's own icon). Defaults to the cases icon resolver. */
  fallbackIcon?: LucideIcon;
  /** Accessible label; the scene is decorative when omitted. */
  title?: string;
}

const VB = '0 0 120 84';

/** Faint blueprint grid, shared by every scene for a cohesive feel. */
function Grid(): ReactElement {
  return (
    <g strokeWidth={0.6} opacity={0.16}>
      <path d="M0 21 H120 M0 42 H120 M0 63 H120" />
      <path d="M30 0 V84 M60 0 V84 M90 0 V84" />
    </g>
  );
}

type Scene = (accent: string) => ReactElement;

const SCENES: Record<string, Scene> = {
  // Raise the request: an RFI sheet with a location crosshair and a question.
  HelpCircle: (accent) => (
    <>
      <rect x={12} y={20} width={52} height={50} rx={4} />
      <path d="M19 32 H55 M19 41 H50 M19 50 H44" strokeWidth={1.8} opacity={0.65} />
      <circle cx={50} cy={55} r={5} strokeWidth={1.8} opacity={0.8} />
      <path d="M50 47 v-3 M50 66 v-3 M42 55 h-3 M61 55 h-3" strokeWidth={1.8} opacity={0.8} />
      <path
        stroke={accent}
        strokeWidth={2.6}
        d="M78 15 h24 a6 6 0 0 1 6 6 v15 a6 6 0 0 1 -6 6 h-9 l-8 8 v-8 h-1 a6 6 0 0 1 -6 -6 v-15 a6 6 0 0 1 6 -6 z"
      />
      <path stroke={accent} strokeWidth={2.8} d="M87 25 a4.5 4.5 0 1 1 6.5 4 c-1.6 1 -2.2 2 -2.2 3.6" />
      <circle fill={accent} stroke="none" cx={91.3} cy={37} r={1.7} />
    </>
  ),

  // Route and chase it: an envelope travelling to a recipient, with a due clock.
  Send: (accent) => (
    <>
      <rect x={12} y={30} width={40} height={28} rx={3} />
      <path d="M12 33 l20 15 l20 -15" strokeWidth={1.9} opacity={0.8} />
      <path stroke={accent} strokeWidth={2.4} strokeDasharray="1 6" d="M55 34 C74 24 82 24 95 31" />
      <path stroke={accent} strokeWidth={2.4} d="M90 26 l6 4 l-5 5" />
      <circle cx={100} cy={47} r={8} />
      <path d="M96 48 a4 4 0 0 1 8 0" strokeWidth={1.8} opacity={0.8} />
      <circle cx={100} cy={44} r={2.4} strokeWidth={1.8} opacity={0.8} />
      <circle stroke={accent} strokeWidth={2.4} cx={29} cy={67} r={9} />
      <path stroke={accent} strokeWidth={2.4} d="M29 62 v5 l3 3" />
    </>
  ),

  // File the answer: a document dropping into an open folder, with a tick.
  FolderOpen: (accent) => (
    <>
      <rect x={28} y={10} width={40} height={30} rx={3} />
      <path d="M35 22 H61 M35 30 H55" strokeWidth={1.8} opacity={0.65} />
      <path d="M48 43 v7 M44 47 l4 4 l4 -4" strokeWidth={1.9} opacity={0.8} />
      <path d="M18 54 h20 l5 -6 h30 a3 3 0 0 1 3 3 v3" />
      <path d="M16 57 h66 l-8 20 a3 3 0 0 1 -3 2 H21 a3 3 0 0 1 -3 -2 z" />
      <circle fill={accent} stroke="none" cx={99} cy={63} r={10} />
      <path stroke="#fff" strokeWidth={2.6} d="M94 63 l3.5 3.5 l6 -7" />
    </>
  ),

  // Report / analytics: a sheet with a bar chart drawn on it.
  FileBarChart: (accent) => (
    <>
      <rect x={26} y={12} width={68} height={60} rx={4} />
      <path d="M33 21 H60" strokeWidth={1.6} opacity={0.5} />
      <path stroke={accent} strokeWidth={5} d="M41 63 V52 M53 63 V42 M65 63 V48 M77 63 V36" />
      <path d="M33 66 H86" strokeWidth={1.8} opacity={0.7} />
    </>
  ),

  // Validate / approve: a shield with a tick.
  ShieldCheck: (accent) => (
    <>
      <path d="M60 10 l26 9 v18 c0 17 -13 26 -26 32 c-13 -6 -26 -15 -26 -32 v-18 z" />
      <path stroke={accent} strokeWidth={3.6} d="M49 41 l8 8 l16 -18" />
    </>
  ),

  // Checklist: rows ticked off one by one.
  ListChecks: (accent) => (
    <>
      <rect x={28} y={18} width={10} height={10} rx={2.5} stroke={accent} />
      <path stroke={accent} strokeWidth={2} d="M30.5 23 l2 2 l4 -4.5" />
      <path d="M46 23 H94" strokeWidth={2.2} />
      <rect x={28} y={37} width={10} height={10} rx={2.5} stroke={accent} />
      <path stroke={accent} strokeWidth={2} d="M30.5 42 l2 2 l4 -4.5" />
      <path d="M46 42 H90" strokeWidth={2.2} />
      <rect x={28} y={56} width={10} height={10} rx={2.5} />
      <path d="M46 61 H84" strokeWidth={2.2} opacity={0.55} />
    </>
  ),

  // Schedule: a calendar with a due-date clock.
  CalendarClock: (accent) => (
    <>
      <rect x={22} y={18} width={52} height={48} rx={4} />
      <path d="M22 30 H74" strokeWidth={1.9} />
      <path d="M33 13 V22 M63 13 V22" strokeWidth={2.2} />
      <path d="M32 41 h.1 M45 41 h.1 M58 41 h.1 M32 52 h.1 M45 52 h.1" strokeWidth={3.5} opacity={0.5} />
      <circle cx={82} cy={58} r={13} fill="#fff" stroke={accent} strokeWidth={2.6} />
      <path stroke={accent} strokeWidth={2.4} d="M82 50 v8 l5 4" />
    </>
  ),

  // Inspection: a clipboard signed off with a tick.
  ClipboardCheck: (accent) => (
    <>
      <rect x={34} y={15} width={48} height={58} rx={4} />
      <rect x={48} y={10} width={20} height={10} rx={3} />
      <path d="M42 36 H74 M42 47 H68" strokeWidth={1.8} opacity={0.5} />
      <path stroke={accent} strokeWidth={3.4} d="M44 59 l6 6 l15 -17" />
    </>
  ),

  // Compare / adjudicate: a balance with two pans.
  Scale: (accent) => (
    <>
      <path d="M60 14 V62" strokeWidth={2.6} />
      <path d="M34 26 H86" strokeWidth={2.6} />
      <circle cx={60} cy={14} r={3} />
      <path stroke={accent} strokeWidth={2.3} d="M34 26 l-7 13 h14 z" />
      <path stroke={accent} strokeWidth={2.3} d="M86 26 l-7 13 h14 z" />
      <path d="M48 62 H72" strokeWidth={2.6} />
    </>
  ),

  // Models / layers: a stack of sheets, top one highlighted.
  Layers: (accent) => (
    <>
      <path stroke={accent} strokeWidth={2.6} d="M60 14 l30 13 l-30 13 l-30 -13 z" />
      <path d="M32 42 l28 12 l28 -12" strokeWidth={2.2} opacity={0.8} />
      <path d="M32 54 l28 12 l28 -12" strokeWidth={2.2} opacity={0.55} />
    </>
  ),

  // Sign a document: a sheet with a signature and pen.
  FileSignature: (accent) => (
    <>
      <rect x={26} y={12} width={58} height={60} rx={4} />
      <path d="M34 25 H72 M34 35 H66" strokeWidth={1.8} opacity={0.5} />
      <path stroke={accent} strokeWidth={2.4} d="M34 54 c5 -7 8 7 12 0 c3 -5 5 3 9 0 c2 -3 4 1 6 0" />
      <path stroke={accent} strokeWidth={2.3} d="M84 40 l8 8 l-20 20 l-10 2 l2 -10 z" />
    </>
  ),

  // Grid / BOQ table: rows and columns, header row highlighted.
  Table2: (accent) => (
    <>
      <rect x={24} y={16} width={72} height={52} rx={4} />
      <path d="M24 31 H96" stroke={accent} strokeWidth={2.6} />
      <path d="M24 45 H96 M24 57 H96" strokeWidth={1.7} opacity={0.55} />
      <path d="M48 16 V68 M72 16 V68" strokeWidth={1.7} opacity={0.55} />
    </>
  ),

  // Cost database: a data cylinder.
  Database: (accent) => (
    <>
      <ellipse cx={60} cy={20} rx={26} ry={8} stroke={accent} strokeWidth={2.5} />
      <path d="M34 20 V60 c0 4.4 11.6 8 26 8 s26 -3.6 26 -8 V20" strokeWidth={2.3} />
      <path d="M34 40 c0 4.4 11.6 8 26 8 s26 -3.6 26 -8" strokeWidth={1.9} opacity={0.6} />
    </>
  ),

  // Measure / takeoff: a ruler with a dimension line.
  Ruler: (accent) => (
    <>
      <rect x={20} y={32} width={80} height={15} rx={2} />
      <path
        d="M31 32 V41 M41 32 V37 M51 32 V41 M61 32 V37 M71 32 V41 M81 32 V37 M91 32 V41"
        strokeWidth={1.6}
        opacity={0.7}
      />
      <path stroke={accent} strokeWidth={2.3} d="M20 60 H100 M20 55 v10 M100 55 v10" />
    </>
  ),

  // Payment / rate: a banknote with a coin.
  Banknote: (accent) => (
    <>
      <rect x={20} y={24} width={62} height={34} rx={4} />
      <circle cx={51} cy={41} r={8} strokeWidth={1.8} opacity={0.7} />
      <circle cx={88} cy={52} r={13} fill={accent} stroke="none" />
      <path stroke="#fff" strokeWidth={2.4} d="M88 44 v16 M83 48 h7 a3.5 3.5 0 0 1 0 7 h-7" />
    </>
  ),

  // Checklist to fill in: a clipboard with a bulleted list.
  ClipboardList: (accent) => (
    <>
      <rect x={34} y={15} width={48} height={58} rx={4} />
      <rect x={48} y={10} width={20} height={10} rx={3} />
      <circle cx={43} cy={34} r={1.8} fill={accent} stroke="none" />
      <path stroke={accent} strokeWidth={2.3} d="M50 34 H75" />
      <circle cx={43} cy={46} r={1.8} fill="currentColor" stroke="none" opacity={0.5} />
      <path d="M50 46 H73" strokeWidth={1.8} opacity={0.5} />
      <circle cx={43} cy={58} r={1.8} fill="currentColor" stroke="none" opacity={0.5} />
      <path d="M50 58 H69" strokeWidth={1.8} opacity={0.5} />
    </>
  ),

  // Invoice / receipt: a torn-edge receipt with a total line.
  ReceiptText: (accent) => (
    <>
      <path d="M38 12 H82 V66 l-5.5 4 l-5.5 -4 l-5.5 4 l-5.5 -4 l-5.5 4 l-5.5 -4 l-5.5 4 z" />
      <path d="M46 26 H74 M46 36 H68" strokeWidth={1.8} opacity={0.55} />
      <path stroke={accent} strokeWidth={2.4} d="M46 48 H63 M69 48 H74" />
    </>
  ),

  // People / team: two figures, one highlighted.
  Users: (accent) => (
    <>
      <circle cx={47} cy={30} r={11} />
      <path d="M29 64 c0 -12 8 -19 18 -19 s18 7 18 19" />
      <circle cx={76} cy={35} r={8.5} stroke={accent} />
      <path stroke={accent} d="M65 64 c0 -10 6 -16 13 -16 s11 4 13 10" />
    </>
  ),

  // Risk / warning: a shield with an exclamation.
  ShieldAlert: (accent) => (
    <>
      <path d="M60 10 l26 9 v18 c0 17 -13 26 -26 32 c-13 -6 -26 -15 -26 -32 v-18 z" />
      <path stroke={accent} strokeWidth={3.4} d="M60 28 v16" />
      <circle cx={60} cy={54} r={1.9} fill={accent} stroke="none" />
    </>
  ),

  // Delivery accepted: a package with a check badge.
  PackageCheck: (accent) => (
    <>
      <path d="M56 14 l24 12 v20 l-24 12 l-24 -12 v-20 z" />
      <path d="M32 26 l24 12 l24 -12 M56 38 V70" strokeWidth={1.8} opacity={0.6} />
      <circle cx={86} cy={56} r={12} fill={accent} stroke="none" />
      <path stroke="#fff" strokeWidth={2.6} d="M81 56 l3.5 3.5 l6 -7" />
    </>
  ),

  // Site / safety: a hard hat.
  HardHat: (accent) => (
    <>
      <path d="M30 52 a30 26 0 0 1 60 0" strokeWidth={2.6} />
      <path d="M22 52 H98 a2.5 2.5 0 0 1 0 6 H22 a2.5 2.5 0 0 1 0 -6 z" />
      <path stroke={accent} strokeWidth={2.4} d="M48 52 V33 M60 52 V29 M72 52 V33" />
    </>
  ),

  // Document: a sheet of text with a folded corner.
  FileText: (accent) => (
    <>
      <path d="M40 10 h24 l16 16 v46 a2 2 0 0 1 -2 2 H40 a2 2 0 0 1 -2 -2 V12 a2 2 0 0 1 2 -2 z" />
      <path d="M64 10 v16 h16" strokeWidth={1.8} opacity={0.7} />
      <path stroke={accent} strokeWidth={2.3} d="M46 42 H74" />
      <path d="M46 52 H72 M46 61 H68" strokeWidth={1.8} opacity={0.55} />
    </>
  ),

  // Locate / pinpoint: a crosshair on a target.
  Crosshair: (accent) => (
    <>
      <circle cx={60} cy={42} r={25} />
      <circle cx={60} cy={42} r={9} stroke={accent} />
      <path stroke={accent} strokeWidth={2.4} d="M60 9 v13 M60 62 v13 M27 42 h13 M80 42 h13" />
      <circle cx={60} cy={42} r={2} fill={accent} stroke="none" />
    </>
  ),

  // Estimate / calculate: a calculator.
  Calculator: (accent) => (
    <>
      <rect x={40} y={10} width={40} height={64} rx={5} />
      <rect x={46} y={17} width={28} height={11} rx={2} stroke={accent} strokeWidth={2.2} />
      <path
        d="M50 41 h.1 M60 41 h.1 M70 41 h.1 M50 52 h.1 M60 52 h.1 M70 52 h.1 M50 63 h.1 M60 63 h.1 M70 63 h.1"
        strokeWidth={4.2}
        opacity={0.55}
      />
    </>
  ),

  // Materials / components: a stack of units, top one highlighted.
  Boxes: (accent) => (
    <>
      <path stroke={accent} strokeWidth={2.5} d="M42 32 l14 -7 l14 7 v14 l-14 7 l-14 -7 z" />
      <path d="M24 54 l14 -7 l14 7 v14 l-14 7 l-14 -7 z" />
      <path d="M52 54 l14 -7 l14 7 v14 l-14 7 l-14 -7 z" />
    </>
  ),

  // Trend / forecast: a rising line on axes.
  TrendingUp: (accent) => (
    <>
      <path d="M28 20 V64 H92" strokeWidth={2.2} opacity={0.6} />
      <path stroke={accent} strokeWidth={2.8} d="M34 56 l16 -14 l12 9 l22 -24" />
      <path stroke={accent} strokeWidth={2.6} d="M78 21 h11 v11" />
      <circle cx={50} cy={42} r={2.4} fill={accent} stroke="none" />
      <circle cx={62} cy={51} r={2.4} fill={accent} stroke="none" />
    </>
  ),

  // Discuss / comment: a speech bubble with text.
  MessageSquare: (accent) => (
    <>
      <path d="M26 18 h68 a4 4 0 0 1 4 4 v30 a4 4 0 0 1 -4 4 H52 l-14 12 v-12 h-12 a4 4 0 0 1 -4 -4 V22 a4 4 0 0 1 4 -4 z" />
      <path stroke={accent} strokeWidth={2.4} d="M36 31 H84" />
      <path d="M36 43 H70" strokeWidth={1.8} opacity={0.55} />
    </>
  ),

  // Time / deadline: a clock face.
  Clock: (accent) => (
    <>
      <circle cx={60} cy={42} r={27} />
      <path stroke={accent} strokeWidth={2.8} d="M60 24 V43 l13 8" />
      <path d="M60 17 v4 M60 63 v4 M35 42 h4 M81 42 h4" strokeWidth={2} opacity={0.6} />
    </>
  ),

  // Project / company: two buildings with windows.
  Building2: (accent) => (
    <>
      <rect x={32} y={16} width={34} height={56} rx={2} />
      <rect x={66} y={34} width={22} height={38} rx={2} />
      <path stroke={accent} strokeWidth={2.3} d="M39 27 h6 M53 27 h6 M39 39 h6 M53 39 h6 M39 51 h6 M53 51 h6" />
      <path d="M72 44 h9 M72 56 h9" strokeWidth={1.8} opacity={0.6} />
    </>
  ),
};

// Semantic aliases: closely related icons reuse an existing scene.
SCENES.Box = SCENES.Boxes!;
SCENES.Combine = SCENES.Boxes!;
SCENES.LineChart = SCENES.TrendingUp!;

/**
 * Line-art illustration for a step. Renders a bespoke scene when one exists for
 * the step icon, otherwise a framed version of the step's own glyph on the grid.
 */
export function StepScene({
  icon,
  accent = '#2563eb',
  className,
  title,
  fallbackIcon,
}: StepSceneProps): ReactElement {
  const scene = icon ? SCENES[icon] : undefined;
  const Glyph = fallbackIcon ?? iconFor(icon);

  return (
    <div
      className={clsx(
        'relative flex items-center justify-center overflow-hidden rounded-2xl bg-gradient-to-br from-white to-slate-50 ring-1 ring-inset ring-slate-900/[0.06]',
        className,
      )}
      role={title ? 'img' : undefined}
      aria-label={title || undefined}
      aria-hidden={title ? undefined : true}
    >
      {scene ? (
        <svg
          viewBox={VB}
          className="h-full w-full p-3 text-slate-400"
          fill="none"
          stroke="currentColor"
          strokeWidth={2.4}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <Grid />
          {scene(accent)}
        </svg>
      ) : (
        <>
          <svg
            viewBox={VB}
            className="absolute inset-0 h-full w-full text-slate-400"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <Grid />
          </svg>
          <Glyph size={38} strokeWidth={1.5} className="relative text-slate-400" />
        </>
      )}
    </div>
  );
}
