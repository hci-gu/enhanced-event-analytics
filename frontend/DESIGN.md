# Journal frontend experiment

Branch: `codex/design-editorial`. Based on `designprototype`.
Ivory and terracotta editorial.

Selected by the user after comparison. Decorative brand and perspective symbols removed; retain the editorial typography and palette. The canvas draft also removes decorative information/arrow icons and unsupported operational claims.

## Preview
From this worktree's `frontend` directory run `pnpm dev --port 5175`.
Use the existing backend for live analysis. The sample-text button fills the composer; submitting it uses the existing analysis endpoint.

[Superdesign alternative](https://p.superdesign.dev/draft/b8e9f1c2-f190-4080-bf9f-01e188454b94)
[Comparison canvas](https://superdesign.dev/teams/0952cbbb-3c10-48d2-b313-45fe598c7102/projects/e303c7c5-b1d1-4b65-8c75-241e559ba1cf)

Canvas alternatives and the local implementations explore the same brief; the canvas is a separate generated artifact, not an exact mirror of React.

## Changes
- Updated home layout, palette, typography and perspective widgets.
- Working sample input and live character count.
- Menu, button, card and progress transitions; all motion disabled with reduced-motion preference.
- Existing streaming status, navigation and evidence interactions retained.
- No new dependencies.

## Verification
- `pnpm build` and `pnpm lint` pass.
- `pnpm test`: all 32 tests pass.
- Existing Playwright smoke checks pass at desktop and mobile widths, using a mocked streaming API.
- Additional checks verify example text, submit enablement, horizontal overflow and reduced motion.
- Desktop and mobile screenshots inspected. Live model inference was not run.

