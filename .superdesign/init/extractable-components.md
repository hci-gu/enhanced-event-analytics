# Extractable components

## PageMenu
- Source: `frontend/src/PageMenu.tsx`
- Category: layout
- Description: Shared popover navigation across home, status and summary states.
- Extractable props: page (home/status/summary active state); analysis availability and completed state (navigation eligibility).
- Hardcoded: Swedish labels Hem, Status, Sammanfattning; menu SVG; classes and keyboard behavior. Callback onNavigate belongs to implementation.

## WorkflowRow
- Source: `frontend/src/WorkflowRow.tsx`
- Category: basic
- Description: Native disclosure card with workflow state, completed-category tags and verbatim evidence quotes.
- Extractable props: showTags (false); showStatus (false); selected (false); workflow state and dynamic result count.
- Hardcoded: Swedish state labels, chevron SVG, ✓ and ! status symbols, CSS classes and disclosure semantics. Actual dynamic workflow/result content is implementation data.

## AppShell (candidate extraction)
- Source: `frontend/src/App.tsx`
- Category: layout
- Description: Viewport shell and toolbar shared by three local page states, currently inline in App.
- Extractable props: page (active state); showSearch (home only).
- Hardcoded: search label Sök händelser and placeholder Sök, toolbar classes, dialog structure.

There is no existing independent Card/Button/Input/Badge/Avatar library. Do not invent repository components or claim unused assets are brand logos.

