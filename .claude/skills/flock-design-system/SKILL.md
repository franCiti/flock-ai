---
name: flock-design-system
description: "Trigger: building or styling any UI for Flock products, Flock branding, purple brand theme, dark mode, design tokens, Flock components. Apply the Flock Design System v1.1 tokens, type scale, spacing, components and patterns."
license: UNLICENSED
metadata:
  author: Flock
  version: "1.1"
---

## Activation Contract

Apply this skill when building or restyling any Flock product UI: components, pages, dashboards, tables, forms, modals, or when the user mentions Flock branding, the purple brand theme, or Flock design tokens. Skip for non-Flock projects with their own design system.

## Hard Rules

- NEVER invent colors, radii, shadows, or type sizes. Use only the tokens in `assets/tokens.css`.
- Reference colors via CSS variables (`var(--brand)`, `var(--text-soft)`), not raw hex, in generated code.
- Use the system font stack — no web fonts.
- Primary action = `--brand` (#7800C0). Reserve `--accent` (#F85000) for punctual emphasis only.
- Match the existing project's token setup if one is already present; extend, don't duplicate.
- Spacing is base-4. Respect the radius scale (8/9/12/16/18/20/50%).
- Surfaces MUST step in value. Cards/panels sit on `--panel` (#fff), NEVER on `--surface`/`--brand-softer` (the canvas tint) — same-tint-on-same-tint reads flat (the violet-on-violet trap). Adjacent layers must contrast: raise one to `--panel` or drop the nav to a dark surface (`--nav-gradient`). This is a learned fix, not a preference.
- Dark mode: enable via `html.dark`. On dark, `--brand` brightens to #9D2BD6 — never keep #7800C0 on dark surfaces. `--brand-dark` and `--accent` hold across themes.
- Data-dense numbers/tables use `.text-mono` (`--font-mono` + `tabular-nums`), not the sans stack.
- Gradient hero card brightens on hover (`brightness(1.07)`) — never flip to white.

## Decision Gates

| Need | Action |
|------|--------|
| Set up theme / colors | Paste `assets/tokens.css` into `:root`; use `var(--*)` after |
| Build a component (button, field, chip, card, modal, toast) | Read `references/design-system.md` §5 for exact specs |
| Build a pattern (tabs, filter bar, table, Gantt) | Read `references/design-system.md` §6 |
| Type scale, spacing, radii, elevation values | Read `references/design-system.md` §2–3 |
| State color (pending/in-progress/blocked/completed) | Use bg/fg/bar triplet in `assets/tokens.css` |
| Dark mode, mono for data, dark sidebar, gradient card | Read `references/design-system.md` §7 (v1.1 extensions) |

## Execution Steps

1. Confirm the target is a Flock UI; if unsure, ask.
2. Ensure tokens exist in the project — add `assets/tokens.css` to `:root` if missing.
3. For any component/pattern, open `references/design-system.md` and follow the exact spec instead of improvising.
4. Emit code using `var(--*)` tokens, system font, base-4 spacing, and the documented radius scale.

## Output Contract

Generated UI uses only documented tokens (via CSS variables), the system font stack, the base-4 spacing scale, and component/pattern specs from the reference. No ad-hoc colors or sizes.

## References

- `assets/tokens.css` — light `:root` + `html.dark` tokens, state colors, sans/mono stacks, brand/nav/stat gradients, `.text-mono` + `.stat-card-hero` helpers.
- `assets/flock-logo.svg` — full purple logo (light bg). `assets/flock-mark.svg` — purple mark. `assets/flock-mark-white.svg` — white mark (dark bg / topbar). Logo colors are brand-specific, not the `--brand`/`--accent` tokens.
- `references/design-system.md` — full v1.1 spec: foundations, typography, spacing, iconography, components, patterns, §7 extensions (dark mode, mono, dark sidebar, gradient card).
