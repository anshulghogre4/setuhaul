---
name: SetuHaul AI
colors:
  surface: '#0b1326'
  surface-dim: '#0b1326'
  surface-bright: '#31394d'
  surface-container-lowest: '#060e20'
  surface-container-low: '#131b2e'
  surface-container: '#171f33'
  surface-container-high: '#222a3d'
  surface-container-highest: '#2d3449'
  on-surface: '#dae2fd'
  on-surface-variant: '#c3c6d7'
  inverse-surface: '#dae2fd'
  inverse-on-surface: '#283044'
  outline: '#8d90a0'
  outline-variant: '#434655'
  surface-tint: '#b4c5ff'
  primary: '#b4c5ff'
  on-primary: '#002a78'
  primary-container: '#2563eb'
  on-primary-container: '#eeefff'
  inverse-primary: '#0053db'
  secondary: '#4edea3'
  on-secondary: '#003824'
  secondary-container: '#00a572'
  on-secondary-container: '#00311f'
  tertiary: '#ffb596'
  on-tertiary: '#581e00'
  tertiary-container: '#bc4800'
  on-tertiary-container: '#ffede6'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#dbe1ff'
  primary-fixed-dim: '#b4c5ff'
  on-primary-fixed: '#00174b'
  on-primary-fixed-variant: '#003ea8'
  secondary-fixed: '#6ffbbe'
  secondary-fixed-dim: '#4edea3'
  on-secondary-fixed: '#002113'
  on-secondary-fixed-variant: '#005236'
  tertiary-fixed: '#ffdbcd'
  tertiary-fixed-dim: '#ffb596'
  on-tertiary-fixed: '#360f00'
  on-tertiary-fixed-variant: '#7d2d00'
  background: '#0b1326'
  on-background: '#dae2fd'
  surface-variant: '#2d3449'
typography:
  display-lg:
    fontFamily: Hanken Grotesk
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Hanken Grotesk
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Hanken Grotesk
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  title-md:
    fontFamily: Hanken Grotesk
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.02em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 48px
  container-max: 1280px
  gutter: 24px
---

## Brand & Style
The design system embodies a premium, high-density SaaS aesthetic tailored for enterprise-grade AI workflows. It draws influence from modern developer-centric interfaces, prioritizing clarity, speed, and subtle depth. 

The visual narrative is "Technical Elegance." It combines a sophisticated dark environment with a precise, systematic layout. The UI utilizes **Glassmorphism** for navigational elements and **Minimalism** for content areas, ensuring the interface feels airy and expansive despite the dark palette. The emotional response should be one of absolute reliability, high-performance capability, and professional calm.

## Colors
The palette is built on a "Moderate Dark" foundation, avoiding pure blacks to maintain a softer, more premium contrast. 

- **Primary & Success**: The Blue (#2563EB) is used for primary actions, focus states, and active indicators. Emerald (#10B981) is reserved for success states, growth metrics, and "complete" status indicators.
- **Surfaces**: The base background uses Deep Navy (#0f172a). Nested containers and cards use Slate (#1e293b) to create a natural hierarchy of depth.
- **Accents**: Borders are kept extremely subtle using low-opacity white (8-10%) to define shapes without creating visual noise.

## Typography
The system employs a dual-font approach to balance character with utility. 

**Hanken Grotesk** is used for headlines and titles. Its sharp, contemporary geometry provides the "Fortune 500" professional edge. **Inter** is used for all functional body text, labels, and data inputs to ensure maximum legibility at high densities. 

Letter spacing is slightly tightened on larger headings to maintain a compact, premium feel. For data-heavy views, use `body-md` (14px) to maximize information density without sacrificing readability.

## Layout & Spacing
The layout follows a strict **Fluid Grid** model with a 12-column structure for desktop. 

- **Desktop (1440px+)**: 12 columns, 24px gutters, 48px side margins.
- **Tablet (768px - 1024px)**: 8 columns, 16px gutters, 24px side margins.
- **Mobile (<768px)**: 4 columns, 16px gutters, 16px side margins.

Spacing follows a 4px baseline. Use `lg` (24px) for section padding and `md` (16px) for internal component padding. High-density views should reduce vertical padding to `sm` (8px) between list items.

## Elevation & Depth
Depth is communicated through **Tonal Layering** and **Glassmorphism** rather than heavy shadows.

1.  **Level 0 (Floor)**: Deep Navy (#0f172a) - The canvas.
2.  **Level 1 (Card)**: Slate (#1e293b) - Primary content containers with a 1px border at 8% white opacity.
3.  **Level 2 (Overlay/Glass)**: Slate (#1e293b) at 70% opacity with a 12px backdrop blur. This is used for sidebars and top navigation bars.
4.  **Shadows**: Use a single, very soft ambient shadow for floating elements: `0 8px 32px rgba(0, 0, 0, 0.4)`.

## Shapes
The shape language is structured and modern. 

- **Base Components**: 8px (rounded) for buttons, inputs, and small cards.
- **Large Containers**: 12px (rounded-lg) for main dashboard panels and modals.
- **Pills**: Used exclusively for status chips and tags to provide visual contrast against the rectangular grid.

## Components
- **Buttons**: Primary buttons are solid Blue (#2563EB) with white text. Secondary buttons use a ghost style: transparent background with a 1px border (white at 10% opacity) and a subtle hover lift.
- **Inputs**: Backgrounds should be slightly darker than the card surface. Focus states must use a 2px Blue (#2563EB) outer ring with a 2px offset.
- **Cards**: Minimalist. No heavy shadows; use the 1px subtle border for definition.
- **Status Chips**: Small, high-contrast badges using secondary colors (Emerald for success) with a 10% background tint of the same color for a "glow" effect.
- **Glass Sidebar**: 70% opacity Slate with 12px backdrop-blur. The active menu item is indicated by a 2px vertical Blue line on the left edge.
- **Data Tables**: Remove vertical borders. Use thin horizontal separators at 5% white opacity. Header rows use `label-sm` in all-caps with 50% text opacity.