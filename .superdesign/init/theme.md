# Theme

## Compact token summary

Current baseline is a warm yellow light theme; the user authorizes three total redesign experiments, so these values are ground truth rather than mandatory constraints.

- Page #ffec9c; text #30291d; primary #453719; border #8b7846; focus #72551b.
- Input/card #fff8d9; panel/button #fff4c4; hover #fff9e3; disabled #f5eccb / #786e55.
- Muted workflow #82775e; track #d9ca92; errors #ffede5 / #8c3020.
- Evidence risks #ffd0d7; reach #cbe9ff; service #cef0c7; fallback #e4d6ff.
- Font system-ui, Segoe UI, Roboto, sans-serif. Root 18px. Home heading clamp(28px,3.5vw,44px), weight 600; results heading clamp(18px,2.5vw,30px); tag 14px.
- Spacing is literal CSS: 6/8/10/12/14/16/20/24/28/36/44/48px. No named spacing tokens.
- Radii 4px evidence, 8px menu item, 10px badge, 12px control, 16/18px row, 20/22px panel.
- Shadows: 0 8px 24px at brown 14%; 0 2px 4px at brown 8%. Borders mostly 2px.
- Responsive thresholds max-width 600px and max-height 500px; app 100dvh, home max 800px, analysis max 1200px; summary 1.3fr/1fr becomes vertically stacked.
- Motion: button hover 150ms, running spinner 900ms infinite; prefers-reduced-motion disables both.
- No Tailwind config, dark theme provider or third-party design system.

## Full raw source

### `frontend/src/colors.css`

```css
/* Edit these values to customize the homepage. All UI colors live here. */
:root {
  --primary-color: #453719;
  --page-background: #ffec9c;
  --text-color: #30291d;
  --border-color: #8b7846;
  --focus-color: #72551b;
  --widget-shadow-color: rgb(69 55 25 / 14%);
  --widget-shadow-edge-color: rgb(69 55 25 / 8%);
  --dialog-backdrop-color: rgb(69 55 25 / 35%);

  /* Event textbox */
  --textbox-background: #fff8d9;
  --textbox-text: var(--text-color);
  --textbox-placeholder: #75694f;

  /* Analyze button */
  --button-background: #fff4c4;
  --button-text: var(--primary-color);
  --button-border: var(--border-color);
  --button-hover-background: #fff9e3;
  --button-disabled-background: #f5eccb;
  --button-disabled-text: #786e55;

  /* Search */
  --search-background: #fff8d9;
  --search-text: var(--text-color);
  --search-placeholder: #75694f;

  /* Request feedback */
  --status-info-background: #fff8d9;
  --status-info-text: var(--primary-color);
  --status-error-background: #ffede5;
  --status-error-text: #8c3020;

  /* Workflow status and results */
  --workflow-muted-text: #82775e;
  --workflow-check-text: #fff8d9;
  --progress-track-color: #d9ca92;
  --results-panel-background: #fff4c4;
  --result-row-background: #fff8d9;
  /* Verified evidence: shared by passages and selected workflow rows */
  --evidence-risks-color: #ffd0d7;
  --evidence-reach-color: #cbe9ff;
  --evidence-service-color: #cef0c7;
  --evidence-fallback-color: #e4d6ff;
  --evidence-active-border: var(--primary-color);
}
```

### `frontend/src/index.css`

```css
:root {
  font-family: system-ui, 'Segoe UI', Roboto, sans-serif;
  font-size: 18px;
  color-scheme: light;
  color: var(--text-color);
  background: var(--page-background);
  font-synthesis: none;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  overflow: hidden;
}

input,
textarea,
button {
  font: inherit;
}

:focus-visible {
  outline: 3px solid var(--focus-color);
  outline-offset: 4px;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
  border: 0;
}
```

### `frontend/src/App.css`

```css
.homepage {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100dvh;
  padding: 28px 36px;
  background: var(--page-background);
  overflow: hidden;
}

.search-row {
  display: flex;
  justify-content: flex-end;
  flex-shrink: 0;
}

.search-widget {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 250px;
  max-width: 100%;
  padding: 10px 14px;
  background: var(--search-background);
  color: var(--search-text);
  border: 2px solid var(--border-color);
  border-radius: 12px;
  box-shadow: 0 4px 12px var(--widget-shadow-color),
    0 1px 2px var(--widget-shadow-edge-color);
}

.search-widget svg {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
}

.search-widget input {
  width: 100%;
  min-width: 0;
  border: 0;
  background: var(--search-background);
  color: var(--search-text);
}

.search-widget input::placeholder {
  color: var(--search-placeholder);
  opacity: 1;
}

/* Text inputs match :focus-visible even after a mouse click in browsers.
   Show their outline only when navigating with the keyboard. */
.search-widget input:focus,
.event-widget textarea:focus {
  outline: none;
}

.homepage[data-keyboard-focus='true'] input:focus-visible,
.homepage[data-keyboard-focus='true'] textarea:focus-visible {
  outline: 3px solid var(--focus-color);
  outline-offset: 4px;
}

.event-section {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  width: min(100%, 800px);
  margin: clamp(16px, 8dvh, 96px) auto 0;
}

.event-section form {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
}

h1 {
  flex-shrink: 0;
  margin: 0 0 44px;
  color: var(--primary-color);
  text-align: center;
  font-size: clamp(28px, 3.5vw, 44px);
  line-height: 1.25;
  font-weight: 600;
  letter-spacing: -0.025em;
  overflow-wrap: anywhere;
}

.event-widget {
  display: flex;
  flex-direction: column;
  flex: 0 1 auto;
  min-height: 0;
  max-height: 290px;
  padding: 16px 20px 10px;
  background: var(--textbox-background);
  border: 2px solid var(--border-color);
  border-radius: 22px;
  box-shadow: 0 8px 24px var(--widget-shadow-color),
    0 2px 4px var(--widget-shadow-edge-color);
}

.event-widget textarea {
  display: block;
  width: 100%;
  flex: 0 1 auto;
  min-height: 0;
  padding: 4px;
  resize: none;
  overflow-y: auto;
  border: 0;
  background: var(--textbox-background);
  color: var(--textbox-text);
  line-height: 1.6;
}

.event-widget textarea::placeholder {
  color: var(--textbox-placeholder);
  opacity: 1;
}

.event-actions {
  display: flex;
  flex-shrink: 0;
  justify-content: flex-end;
  margin-top: 6px;
}

.event-actions button,
.health-dialog button {
  min-height: 36px;
  padding: 6px 18px;
  border: 2px solid var(--button-border);
  border-radius: 12px;
  background: var(--button-background);
  color: var(--button-text);
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 3px 8px var(--widget-shadow-color),
    0 1px 2px var(--widget-shadow-edge-color);
  transition: background-color 150ms ease;
}

.event-actions button:hover:not(:disabled),
.health-dialog button:hover {
  background: var(--button-hover-background);
}

.event-actions button:disabled {
  background: var(--button-disabled-background);
  color: var(--button-disabled-text);
  cursor: not-allowed;
}

.feedback {
  flex-shrink: 0;
  max-height: 20dvh;
  overflow-y: auto;
  margin-top: 16px;
  color: var(--status-info-text);
  line-height: 1.5;
}

.feedback p {
  margin: 0;
  padding: 12px 16px;
  background: var(--status-info-background);
  border-radius: 12px;
}

.feedback .feedback-error {
  color: var(--status-error-text);
  background: var(--status-error-background);
}

.health-dialog {
  width: min(440px, calc(100% - 32px));
  max-height: calc(100dvh - 32px);
  padding: 24px;
  border: 2px solid var(--border-color);
  border-radius: 20px;
  background: var(--status-error-background);
  color: var(--status-error-text);
  box-shadow: 0 8px 24px var(--widget-shadow-color);
}

.health-dialog::backdrop {
  background: var(--dialog-backdrop-color);
}

.health-dialog h2 {
  margin: 0 0 12px;
  font-size: 22px;
}

.health-dialog p {
  margin: 0 0 20px;
  line-height: 1.5;
}

.health-dialog button {
  display: block;
  margin-left: auto;
}

@media (max-width: 600px) {
  .homepage {
    padding: 20px 16px;
  }

  .event-section {
    margin-top: clamp(16px, 6dvh, 48px);
  }

  h1 {
    margin-bottom: 28px;
  }

  .event-widget {
    padding: 14px 14px 8px;
    border-radius: 16px;
  }
}

@media (max-height: 500px) {
  .homepage {
    padding: 12px 16px;
  }

  .event-section {
    margin-top: 12px;
  }

  h1 {
    margin-bottom: 12px;
    font-size: 24px;
  }

  .event-widget {
    padding: 10px 10px 6px;
  }

  .event-actions {
    margin-top: 6px;
  }

  .event-actions button {
    min-height: 36px;
    padding: 6px 16px;
  }

  .feedback {
    margin-top: 8px;
    font-size: 14px;
  }

  .feedback p {
    padding: 8px 12px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .event-actions button {
    transition: none;
  }
}
```

### `frontend/src/PageMenu.css`

```css
.app-toolbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
  min-height: 48px;
}

.page-menu { position: relative; flex-shrink: 0; z-index: 10; }
.menu-trigger {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  padding: 10px;
  border: 2px solid var(--button-border);
  border-radius: 12px;
  color: var(--button-text);
  background: var(--button-background);
  cursor: pointer;
}
.menu-trigger svg { width: 24px; height: 24px; stroke: currentColor; stroke-width: 2; stroke-linecap: round; }
.menu-trigger:hover { background: var(--button-hover-background); }
.page-navigation {
  position: absolute;
  right: 0;
  top: calc(100% + 8px);
  min-width: 200px;
  padding: 6px;
  border: 2px solid var(--border-color);
  border-radius: 12px;
  background: var(--textbox-background);
  box-shadow: 0 8px 24px var(--widget-shadow-color);
}
.page-navigation button {
  display: block;
  width: 100%;
  padding: 12px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-color);
  text-align: left;
  font: inherit;
  cursor: pointer;
}
.page-navigation button:hover:not(:disabled), .page-navigation button[aria-current] {
  background: var(--button-hover-background);
}
.page-navigation button:disabled { color: var(--button-disabled-text); cursor: default; opacity: .6; }
.page-navigation button:focus-visible, .menu-trigger:focus-visible { outline: 3px solid var(--focus-color); outline-offset: 2px; }
@media (max-width: 600px) {
  .app-toolbar .search-row { min-width: 0; }
  .app-toolbar .search-widget { width: min(250px, 100%); }
}
```

### `frontend/src/AnalysisScreen.css`

```css
.analysis-screen {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  width: min(100%, 1200px);
  margin: 0 auto;
}

.analysis-screen h1 {
  margin: 12px 0 24px;
  height: 2.5em;
  flex-shrink: 0;
  line-height: 1.25;
  overflow: auto;
  overflow-wrap: anywhere;
  font-size: clamp(18px, 2.5vw, 30px);
}

.workflow-status-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.workflow-status-list {
  list-style: none;
  padding: 8px 0;
  margin: 0;
  overflow-y: auto;
  min-height: 0;
}

.workflow-running,
.workflow-completed {
  color: var(--primary-color);
}

.workflow-failed {
  color: var(--status-error-text);
}

.workflow-symbol {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  border: 2px solid var(--workflow-muted-text);
  border-radius: 50%;
  font-size: 22px;
}

.workflow-completed .workflow-symbol {
  background: var(--primary-color);
  color: var(--workflow-check-text);
  border-color: var(--primary-color);
}

.workflow-failed .workflow-symbol {
  border-color: var(--status-error-text);
}

.workflow-spinner {
  border-color: var(--progress-track-color);
  border-top-color: var(--primary-color);
  animation: workflow-spin 900ms linear infinite;
}

.analysis-progress {
  position: relative;
  width: 88px;
  height: 88px;
  align-self: center;
  margin: auto 0 48px;
  flex-shrink: 0;
}

.analysis-progress svg {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}

.analysis-progress circle {
  fill: none;
  stroke-width: 4px;
}

.progress-track {
  stroke: var(--progress-track-color);
}

.progress-value {
  stroke: var(--primary-color);
  stroke-linecap: round;
}

.analysis-progress span {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: var(--primary-color);
  font-weight: 600;
}

.workflow-result {
  margin-bottom: 12px;
  border: 2px solid var(--border-color);
  border-radius: 12px;
  background: var(--result-row-background);
  color: var(--text-color);
  box-shadow: 0 3px 8px var(--widget-shadow-edge-color);
}

.workflow-result summary {
  padding: 12px 16px;
  cursor: pointer;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.workflow-result p,
.workflow-result ul {
  margin: 0;
  padding: 0 16px 16px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.workflow-result ul {
  padding-left: 36px;
}

.analysis-error {
  flex-shrink: 0;
  max-height: 20dvh;
  overflow-y: auto;
  margin: 16px 0 0;
  padding: 12px 16px;
  border-radius: 12px;
  background: var(--status-error-background);
  color: var(--status-error-text);
}

@keyframes workflow-spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 600px) {
  .analysis-progress {
    width: 56px;
    height: 56px;
    margin: auto 0 0;
    font-size: 14px;
  }

}

@media (max-height: 500px) {
  .analysis-screen h1 { font-size: 24px; margin: 0 0 8px; }
  .analysis-progress { width: 48px; height: 48px; margin: auto 0 0; font-size: 12px; }
}

@media (prefers-reduced-motion: reduce) {
  .workflow-spinner { animation: none; }
}

/* Shared expandable workflow rows, used on status and summary pages. */
.workflow-status-panel {
  flex: 1;
  padding: 24px;
  border: 2px solid var(--border-color);
  border-radius: 22px;
  background: var(--results-panel-background);
  box-shadow: 0 8px 24px var(--widget-shadow-color);
}
.workflow-status-list {
  flex: 1;
  padding: 0 6px 0 0;
  scrollbar-gutter: stable;
  overflow-anchor: none;
}
.workflow-result { margin-bottom: 16px; border-radius: 18px; }
.workflow-result .workflow-row-header {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 76px;
  padding: 16px 20px;
  list-style: none;
  font-size: clamp(16px, 1.8vw, 22px);
  font-weight: 600;
}
.workflow-row-header::-webkit-details-marker { display: none; }
.workflow-label { overflow-wrap: anywhere; }
.workflow-unavailable { cursor: default; }
.workflow-queued, .workflow-skipped { color: var(--workflow-muted-text); border-color: var(--progress-track-color); box-shadow: none; }
.workflow-failed { color: var(--status-error-text); border-color: var(--status-error-text); }
.workflow-row-header small { font-size: 12px; }
.workflow-chevron {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  margin-left: auto;
  border: 1px solid currentColor;
  border-radius: 50%;
  font-size: 24px;
  line-height: 1;
}
.workflow-chevron svg { width: 20px; height: 20px; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; }
details[open] > .workflow-row-header .workflow-chevron { transform: rotate(180deg); }
.workflow-row-header:focus-visible { outline: 3px solid var(--focus-color); outline-offset: 3px; border-radius: 16px; }
.workflow-symbol { width: 28px; height: 28px; font-size: 18px; }
.workflow-tags { display: flex; flex-wrap: wrap; flex: 1; gap: 8px; min-width: 0; margin-left: 12px; }
.workflow-tag { padding: 6px 12px; border: 1px solid var(--border-color); border-radius: 10px; font-size: 14px; font-weight: 500; overflow-wrap: anywhere; max-width: 100%; }
.workflow-no-matches { font-size: 14px; font-weight: 400; }
.workflow-row-content { padding: 0 20px 20px; line-height: 1.6; overflow-wrap: anywhere; }
.workflow-row-content ul { margin: 0; padding: 0 0 0 20px; }
.workflow-row-content p { margin: 6px 0 0; padding: 0; }
.workflow-row-content .evidence-quotes { white-space: pre-wrap; margin: 6px 0 12px; }
.workflow-result[data-active] { border-color: var(--evidence-active-border); background: var(--workflow-evidence-color); box-shadow: 0 0 0 2px var(--workflow-evidence-color); }
.analysis-progress { margin: 20px 0 0; }
@media (max-width: 600px) {
  .workflow-status-panel { padding: 14px; }
  .workflow-result .workflow-row-header { flex-wrap: wrap; padding: 12px; gap: 8px; }
  .workflow-tags { order: 1; flex-basis: 100%; margin-left: 0; }
  .workflow-label { max-width: calc(100% - 80px); }
  .workflow-row-content { padding: 0 12px 12px; }
  .analysis-progress { width: 64px; height: 64px; margin-top: 12px; font-size: 14px; }
}
@media (max-height: 500px) {
  .analysis-progress { width: 48px; height: 48px; margin-top: 8px; font-size: 12px; }
  .workflow-result .workflow-row-header { min-height: 56px; padding: 8px 12px; }
}
```

### `frontend/src/SummaryScreen.css`

```css
.summary-screen {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  width: min(100%, 1200px);
  margin: 0 auto;
}

.summary-screen h1 {
  margin: 12px 0 24px;
  font-size: clamp(18px, 2.5vw, 30px);
  overflow-wrap: anywhere;
}

.summary-columns {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr);
  gap: 24px;
  flex: 1;
  min-height: 0;
  padding: 24px;
  border: 2px solid var(--border-color);
  border-radius: 22px;
  background: var(--results-panel-background);
  box-shadow: 0 8px 24px var(--widget-shadow-color);
}

.summary-text,
.summary-results {
  min-height: 0;
  overflow-y: auto;
  overflow-wrap: anywhere;
  scrollbar-gutter: stable;
}

.summary-text {
  white-space: pre-wrap;
  line-height: 1.8;
  padding: 20px;
}

.summary-results {
  border-left: 2px solid var(--border-color);
  padding-left: 24px;
}

.evidence-highlight {
  color: var(--text-color);
  border-radius: 4px;
  cursor: pointer;
  box-decoration-break: clone;
  -webkit-box-decoration-break: clone;
}

.evidence-highlight[data-active] {
  outline: 2px solid var(--evidence-active-border);
  outline-offset: 1px;
}

@media (max-width: 600px) {
  .summary-columns {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: minmax(0, 1.3fr) minmax(0, 1fr);
    padding: 14px;
    gap: 14px;
  }
  .summary-results {
    border-left: 0;
    border-top: 2px solid var(--border-color);
    padding: 14px 0 0;
  }
  .summary-text { padding: 14px; }
}
```

