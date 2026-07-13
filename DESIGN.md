# PRLMAD Design System

This interface follows the warm editorial direction documented in
[VoltAgent/awesome-design-md's Claude analysis](https://github.com/VoltAgent/awesome-design-md/tree/main/design-md/claude).
It adapts that public design analysis to PRLMAD's learning workflow; it does not
reuse Anthropic names, logos, illustrations, or proprietary fonts.

## Visual direction

- Treat PRLMAD as a calm learning studio, not a generic blue SaaS dashboard.
- Use a warm cream canvas, warm-black text, and coral only for primary actions.
- Use dark ink surfaces for generated artifacts, technical previews, and strong
  contrast moments. Use cream cards for ordinary content.
- Prefer borders and surface contrast over shadows. Keep motion quiet.
- Display headings use a literary serif; interface copy uses a humanist sans.

## Tokens

| Role | Value |
| --- | --- |
| Canvas | `#faf9f5` |
| Soft surface | `#f5f0e8` |
| Card surface | `#efe9de` |
| Hairline | `#e6dfd8` |
| Ink | `#141413` |
| Body | `#3d3d3a` |
| Muted | `#6c6a64` |
| Primary coral | `#cc785c` |
| Primary active | `#a9583e` |
| Dark surface | `#181715` |
| Success | `#5db872` |
| Warning | `#d4a017` |
| Error | `#c64545` |

Use `Noto Serif SC` / `Cormorant Garamond` for display headings and `Inter` /
`Noto Sans SC` for interface text. Buttons and inputs use an 8px radius, content
cards 12px, and major containers 16px. Maintain minimum 40px control height.

## Component rules

- Primary buttons: coral fill, white label, no gradient, 8px radius.
- Secondary buttons and inputs: canvas fill with a warm hairline border.
- Cards: cream or canvas fill, warm hairline border, little to no shadow.
- Navigation: active items use a cream-card fill and coral marker.
- Page titles: regular-weight serif, never bold sans-serif.
- Status colors remain semantic; do not turn every positive state coral.
- On mobile, collapse the permanent sidebar into a compact top bar and keep all
  controls reachable without horizontal scrolling.
- Treat the left navigation and session context as a persistent application
  shell. Switching modules replaces only the main workspace, preserves browser
  history, and returns the workspace scroll position to the top.
- Prefer one intentional scroll container per module. Keep page context and
  primary actions visible; use responsive columns for paths and summaries to
  reduce unnecessary vertical travel.

## Guardrails

- Do not introduce cool blue/purple gradients as brand decoration.
- Do not use pure white as the page canvas or pure black for running text.
- Do not copy the Claude or Anthropic wordmark, spike mark, or product name.
- Do not trade readability for decorative styling; generated learning content is
  always the highest-priority visual layer.
