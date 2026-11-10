# Editorial Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the generic "AI slop" look (indigo-600 glow buttons, lavender bg, rounded-xl everywhere) with a clean editorial light design (Linear/Notion/Stripe register) via a Tailwind v4 `@theme` design system + shared primitives, with zero logic changes.

**Architecture:** One `@theme` token block in `index.css` defines color/radius/shadow/type tokens that become Tailwind utilities automatically. A small `components/ui/` primitive set (Button, Card, SectionHeader, Badge, StatCard, ProgressRing) absorbs the recurring patterns; pages then compose primitives instead of hand-rolling classes. Restyle proceeds page-by-page most-seen-first with a build gate after each page.

**Tech Stack:** React 19 + TypeScript, Tailwind CSS v4.3.3 (via `@tailwindcss/vite`, tokens via `@theme`), Vite 8, Playwright e2e (55 tests, `data-testid`-based), oxlint.

## Global Constraints

- **Zero logic changes** — same routes, same API calls, same state, same handlers. Pure skin swap. The only logic edit allowed: deleting the duplicate Admin `<NavLink>` in AppHeader (lines 101–112).
- **Preserve every `data-testid`** attribute and every accessible label (`aria-label`, `role`, `aria-expanded`, etc.) — the 55 e2e tests depend on them.
- Accent color is used in **exactly 3 places**: primary CTAs, active nav/states, focus rings. Nowhere else. NO indigo-600 anywhere.
- Radius scale, 3 levels only: `rounded-md` (inputs/buttons), `rounded-lg` (cards/panels), `rounded-full` (pills/avatars). `rounded-xl` and `rounded-2xl` are banned in the final state (grep must return 0 in `src/`).
- Shadows, 2 levels only: `shadow-card` on elevated cards, none on flat surfaces.
- Type scale: `text-xs` labels, `text-sm` body-secondary, `text-base` body, `text-xl` section headers, `text-3xl` page titles. `text-2xl`/ad-hoc sizes are banned except stat numerals (`text-2xl tabular-nums` inside StatCard is allowed).
- Contrast: body text ≥ 4.5:1 (ink `#1c1917` on `#fafaf9` = 15.9:1 ✓; secondary `#57534e` on white = 7.4:1 ✓). Status never by color alone — Badge always carries a text label.
- Build gate after every page task: `npx tsc -b --noEmit && npx vite build` must pass.
- No new dependencies. No webfonts (system font stack).

## Design Tokens (single source of truth — Task 1)

| Token | Value | Role |
|---|---|---|
| `--color-page` | `#fafaf9` | page background (warm paper white) |
| `--color-surface` | `#ffffff` | cards, panels |
| `--color-ink` | `#1c1917` | primary text, headings |
| `--color-ink-soft` | `#57534e` | secondary text |
| `--color-ink-faint` | `#a8a29e` | hints, placeholders |
| `--color-line` | `#e7e5e4` | hairline borders |
| `--color-accent` | `#1d4ed8` | deep blue — CTAs, active, focus |
| `--color-accent-strong` | `#1e40af` | CTA hover |
| `--color-accent-soft` | `#eff6ff` | active nav bg, focus-tint bg |
| `--radius-*` | TW defaults (`md`=6px, `lg`=8px, `full`) | enforced usage only |
| `--shadow-card` | `0 1px 2px 0 rgb(28 25 23 / 0.05)` | the one elevation level |

Status colors (emerald/amber/red) are **semantic status**, not accent — used only inside Badge/coverage/level styling, always with text labels.

## File Structure

- Modify: `frontend/src/index.css` — `@theme` tokens + keep existing keyframes
- Create: `frontend/src/components/ui/Button.tsx`, `Card.tsx`, `SectionHeader.tsx`, `Badge.tsx`, `StatCard.tsx`, `ProgressRing.tsx`
- Create: `frontend/src/lib/status.ts` — move COVERAGE_STYLE/LEVEL_STYLE here as Badge variants (re-export from `lib/ui.ts` for backward compat during migration, delete re-export shim at the end)
- Modify: `frontend/src/components/AppHeader.tsx` (incl. duplicate Admin link fix)
- Modify: all 10 `pages/*.tsx`, `components/CodingWorkspace.tsx`, `components/EvaluationFeedback.tsx`, `components/DeleteTrackDialog.tsx`, `components/StartInterviewModal.tsx`, `components/LeaveInterviewModal.tsx`, `components/TrackOptionsMenu.tsx`, `components/TrackTypePicker.tsx`, `components/UserAvatar.tsx` (if needed)
- Modify: `frontend/src/lib/ui.ts` — final state: deleted, imports point to `lib/status.ts`

---

### Task 1: Design system tokens in index.css

**Files:**
- Modify: `frontend/src/index.css`

**Interfaces:**
- Produces: utilities `bg-page`, `bg-surface`, `text-ink`, `text-ink-soft`, `text-ink-faint`, `border-line`, `bg-accent`, `text-accent`, `bg-accent-soft`, `shadow-card` (Tailwind v4 generates these from `@theme` names)

- [ ] **Step 1: Replace the body rule and add `@theme` (keep all keyframes)**

```css
@import "tailwindcss";

@theme {
  --color-page: #fafaf9;
  --color-surface: #ffffff;
  --color-ink: #1c1917;
  --color-ink-soft: #57534e;
  --color-ink-faint: #a8a29e;
  --color-line: #e7e5e4;
  --color-accent: #1d4ed8;
  --color-accent-strong: #1e40af;
  --color-accent-soft: #eff6ff;
  --shadow-card: 0 1px 2px 0 rgb(28 25 23 / 0.05);
}

body {
  @apply bg-page text-ink antialiased;
}
```

- [ ] **Step 2: Build gate**

Run: `npx tsc -b --noEmit && npx vite build` — expected: pass.

- [ ] **Step 3: Commit** `feat(web): editorial design tokens via Tailwind v4 @theme`

### Task 2: UI primitives

**Files:**
- Create: `frontend/src/components/ui/Button.tsx`, `Card.tsx`, `SectionHeader.tsx`, `Badge.tsx`
- Create: `frontend/src/lib/status.ts` (Badge variants moved from `lib/ui.ts`; `lib/ui.ts` re-exports for now)

**Interfaces:**
- Produces: `<Button variant="primary|secondary|ghost" size="sm|md|lg" ...props>` (native button props, forwards ref), `<Card className padded?>`, `<SectionHeader title subtitle? actions?>` (renders `text-3xl font-semibold tracking-tight text-ink` + `text-sm text-ink-soft`), `<Badge tone="neutral|success|warn|danger|accent-soft" children>` (`rounded-full px-2 py-0.5 text-xs font-medium`, tone maps to emerald/amber/red/stone/accent-soft)

- [ ] **Step 1: Button.tsx**

```tsx
import { forwardRef, type ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-accent text-white hover:bg-accent-strong disabled:bg-accent/40",
  secondary:
    "border border-line bg-surface text-ink hover:bg-page disabled:opacity-50",
  ghost: "text-ink-soft hover:bg-page hover:text-ink disabled:opacity-50",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-xs",
  md: "h-9 px-4 text-sm",
  lg: "h-11 px-5 text-sm",
};

const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size }
>(function Button({ variant = "primary", size = "md", className = "", ...props }, ref) {
  return (
    <button
      ref={ref}
      className={`inline-flex items-center justify-center gap-1.5 rounded-md font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...props}
    />
  );
});
export default Button;
```

- [ ] **Step 2: Card.tsx, SectionHeader.tsx, Badge.tsx**

```tsx
// Card.tsx
import type { HTMLAttributes } from "react";

export default function Card({
  className = "",
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`rounded-lg border border-line bg-surface shadow-card ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
```

```tsx
// SectionHeader.tsx
export default function SectionHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-soft">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
```

```tsx
// Badge.tsx
import type { HTMLAttributes } from "react";

export type BadgeTone = "neutral" | "success" | "warn" | "danger" | "info";

const TONES: Record<BadgeTone, string> = {
  neutral: "bg-stone-100 text-stone-700",
  success: "bg-emerald-100 text-emerald-800",
  warn: "bg-amber-100 text-amber-800",
  danger: "bg-red-100 text-red-800",
  info: "bg-accent-soft text-accent-strong",
};

export default function Badge({
  tone = "neutral",
  className = "",
  children,
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: BadgeTone }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${TONES[tone]} ${className}`}
      {...props}
    >
      {children}
    </span>
  );
}
```

- [ ] **Step 3: lib/status.ts** — move the two maps from `lib/ui.ts`, remapped to Badge tones; keep `lib/ui.ts` as `export { COVERAGE_STYLE, LEVEL_STYLE } from "./status";`

```ts
export const COVERAGE_TONE: Record<string, "success" | "warn" | "danger"> = {
  excellent: "success",
  good: "success",
  partial: "warn",
  none: "danger",
};

export const LEVEL_TONE: Record<string, "success" | "warn" | "danger"> = {
  strong: "success",
  solid: "success",
  developing: "warn",
  weak: "danger",
};
```

- [ ] **Step 4: Build gate + commit** `feat(web): shared UI primitives (Button, Card, SectionHeader, Badge)`

### Task 3: Extract StatCard + ProgressRing from DashboardPage

**Files:**
- Create: `frontend/src/components/ui/StatCard.tsx`, `frontend/src/components/ui/ProgressRing.tsx`
- Modify: `frontend/src/pages/DashboardPage.tsx:820-889` (delete inline defs, import from ui/)

**Interfaces:**
- Produces: `<StatCard label value icon tone>` — tone prop REPLACED by neutral rendering (icon in `bg-page text-ink-soft rounded-lg`); `<ProgressRing value>` — track `stroke="#e7e5e4"`, arc `stroke="#1d4ed8"`, numeral `text-sm font-semibold tabular-nums text-ink`
- Consumes: Card primitive for the container

- [ ] **Step 1: Move both components into `components/ui/`, restyled per interfaces above; StatCard keeps the exact same props except `tone` is dropped — update the 4 call sites in DashboardPage to stop passing `tone`.**
- [ ] **Step 2: Build gate + commit** `refactor(web): extract StatCard and ProgressRing from DashboardPage`

### Task 4: AppHeader + SignInPage

**Files:**
- Modify: `frontend/src/components/AppHeader.tsx`, `frontend/src/pages/SignInPage.tsx`

- [ ] **Step 1: Delete the SECOND duplicate Admin NavLink block (lines 101–112, the `user?.is_admin` one).**
- [ ] **Step 2: Restyle header**: `border-b border-line bg-surface` (drop indigo tint + backdrop-blur); wordmark `<span className="text-accent">` instead of indigo; active nav pill = `bg-accent-soft text-accent-strong`, inactive = `text-ink-soft hover:bg-page`; Admin link loses amber, becomes a normal nav pill (admin-ness is conveyed by its label, per accent-only rule); avatar focus ring `focus-visible:ring-accent`; menu = `rounded-lg border-line shadow-card`, hover rows `hover:bg-page`, icon chips `bg-page text-ink-soft`.
- [ ] **Step 3: SignInPage**: white page, Card-centered Google button as `Button` secondary with logo, title via type scale. Keep all testids.
- [ ] **Step 4: Build gate + commit** `feat(web): restyle header + sign-in; drop duplicate admin link`

### Task 5: DashboardPage

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`

- [ ] **Step 1: Compose primitives.** Page title via SectionHeader; track cards = Card + internal `rounded-full` Badges (subject pill, question-count, best-score with `LEVEL_TONE`); CTAs = Button primary ("Start interview") / secondary; delete/restore menu = ghost. StatCard/ProgressRing already imported from Task 3. Empty state = centered `text-sm text-ink-soft` + Card.
- [ ] **Step 2: Kill every `rounded-xl/2xl`, `indigo-*`, `shadow-slate-*` in the file (grep must return 0 for this file).**
- [ ] **Step 3: Build gate + commit** `feat(web): dashboard in editorial system`

### Task 6: TrackDetailPage + track components

**Files:**
- Modify: `frontend/src/pages/TrackDetailPage.tsx`, `components/StartInterviewModal.tsx`, `components/DeleteTrackDialog.tsx`, `components/TrackOptionsMenu.tsx`, `components/TrackTypePicker.tsx`
- [ ] Same primitive composition: modals keep `.start-modal-panel` animation class (defined in index.css) but swap panel to `rounded-lg border-line bg-surface shadow-card`; duration pills = `rounded-full` with `data-[active]:bg-accent-soft data-[active]:text-accent-strong border-line`. Build gate + commit `feat(web): track detail + modals in editorial system`

### Task 7: InterviewPage + CodingWorkspace + EvaluationFeedback (the 45-minute room)

**Files:**
- Modify: `frontend/src/pages/InterviewPage.tsx`, `components/CodingWorkspace.tsx`, `components/EvaluationFeedback.tsx`, `components/LeaveInterviewModal.tsx`

- [ ] **Question dominates**: question text → `text-lg sm:text-xl font-medium leading-relaxed text-ink` inside a borderless area (no card-in-card); area/mode meta via Badge.
- [ ] **Timer quiets down**: replace red/big countdown styling with a hairline progress bar (`h-1 rounded-full bg-line`, fill `bg-accent` width=%; only the final 5 min switches fill to `bg-red-500` — state change, not new logic) + `text-xs tabular-nums text-ink-soft` remaining-time text. **Reuse existing timer state/handlers; no logic edits.**
- [ ] **Answer area generous**: textarea `min-h-[10rem]` (up from current), `rounded-md border-line bg-surface focus:border-accent focus:ring-2 focus:ring-accent/20`, body text-base. Submit = Button lg primary.
- [ ] **Monaco embedded**: editor card keeps Card chrome; language tabs active state = `bg-accent-soft text-accent-strong` (NOT white-on-indigo); Monaco `theme="vs"` stays, add `renderLineHighlight: "none"` for calm; terminal panel keeps dark bg-stone-950 (it's a terminal, dark is semantic) but emerald text → `text-stone-300` and amber chip stays.
- [ ] **EvaluationFeedback = constructive notes**: Card, "Q{n} evaluation" `text-sm font-semibold text-ink`; coverage + AI-reviewed via Badge (uses COVERAGE_TONE); Strengths label `text-xs font-semibold uppercase tracking-wide text-emerald-700` (keep semantic), gaps → "To improve" label in amber; expected-answer box `bg-page border border-line` (NOT indigo-50); corrected-code `<pre>` keeps dark surface.
- [ ] Preserve every testid: `evaluation-feedback`, `ai-reviewed-badge`, `coding-workspace`, `run-disabled`, `assistance-panel`, plus all InterviewPage ones (grep file for `data-testid` before editing, keep the list).
- [ ] Build gate + commit `feat(web): interview room — calm exam surface, quiet timer, embedded editor`

### Task 8: ReportPage + ProfilePage

**Files:**
- Modify: `frontend/src/pages/ReportPage.tsx`, `frontend/src/pages/ProfilePage.tsx`
- [ ] **Report hierarchy**: overall score = `text-5xl font-semibold tabular-nums text-ink` top-left with `ProgressRing` companion; verdict line `text-sm text-ink-soft`; competency rows = Card with name + `Badge` (LEVEL_TONE) + one-line evidence, stacked list (scannable), not walls of text; strengths/improvement split into two Cards with semantic `text-xs uppercase` labels; coverage badges via COVERAGE_TONE. Build gate + commit `feat(web): report + profile in editorial system`

### Task 9: OnboardingPage + Admin pages

**Files:**
- Modify: `frontend/src/pages/OnboardingPage.tsx`, `pages/AdminOverviewPage.tsx`, `pages/AdminUsersPage.tsx`, `pages/AdminUserDetailPage.tsx`
- [ ] Onboarding: chat bubble surfaces — agent bubble `bg-surface border-line rounded-lg`, user bubble `bg-accent-soft text-ink rounded-lg` (soft, not solid accent — accent reserved); inputs `rounded-md`. Admin pages: tables with `border-line` hairlines, SectionHeader, Badge for status; costs in `tabular-nums`. Build gate + commit `feat(web): onboarding + admin in editorial system`

### Task 10: Sweep + delete shim + full verification

**Files:**
- Modify: `frontend/src/lib/ui.ts` (delete; point remaining imports at `lib/status.ts`), any stragglers

- [ ] **Sweep gates (must all be 0):**

```bash
grep -rn "rounded-xl\|rounded-2xl\|indigo-\|violet-\|shadow-slate\|bg-\[#f6f4fb\]" frontend/src/ | wc -l   # 0
```

- [ ] **Full verification:**

```bash
cd frontend && npx tsc -b --noEmit && npx vite build && npm run lint
cd backend && uv run pytest -q          # 174 pass (untouched, proves zero logic change)
cd e2e && npx playwright test           # 55 pass (testids preserved)
```

- [ ] **Rebuild frontend container:** `cd infra && docker compose up -d --build frontend`
- [ ] **Commit + push:** `feat(web): complete editorial redesign — sweep, delete legacy style shim` then `git push origin main`

## Self-Review

- Spec coverage: @theme tokens (T1), radius/type/shadow scales (T1 + global constraints), accent-in-3-places (global + T2 Button/active/focus), primitives (T2–T3), read-first done (AppHeader/CodingWorkspace/EvaluationFeedback/StatCard/ProgressRing all read), InterviewPage specifics (T7 all four points), ReportPage hierarchy (T8), build-after-each-page (every task), StatCard/ProgressRing extraction (T3), duplicate Admin link fix (T4), WCAG AA (constraints), color-not-alone (Badge always text-labeled) ✓
- No placeholders: all primitives given full code; page tasks specify exact target classes per pattern ✓
- Type consistency: Badge tones = `lib/status.ts` tone union; StatCard loses `tone` prop with call-site updates in T3 ✓
