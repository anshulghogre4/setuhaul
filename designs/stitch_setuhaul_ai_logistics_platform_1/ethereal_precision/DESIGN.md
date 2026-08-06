---
name: Ethereal Precision
colors:
  surface: '#041428'
  surface-dim: '#041428'
  surface-bright: '#2b3a50'
  surface-container-lowest: '#000e22'
  surface-container-low: '#0c1c30'
  surface-container: '#112035'
  surface-container-high: '#1b2b40'
  surface-container-highest: '#27354b'
  on-surface: '#d4e3ff'
  on-surface-variant: '#c3c6d7'
  inverse-surface: '#d4e3ff'
  inverse-on-surface: '#223146'
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
  background: '#041428'
  on-background: '#d4e3ff'
  surface-variant: '#27354b'
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
  headline-md:
    fontFamily: Hanken Grotesk
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  headline-sm:
    fontFamily: Hanken Grotesk
    fontSize: 20px
    fontWeight: '500'
    lineHeight: 28px
  body-lg:
    fontFamily: Hanken Grotesk
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Hanken Grotesk
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Hanken Grotesk
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.05em
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.08em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  unit: 4px
  xs: 0.5rem
  sm: 1rem
  md: 1.5rem
  lg: 2rem
  xl: 3rem
  gutter: 24px
  margin-mobile: 16px
  margin-desktop: 40px
---

## Brand & Style

The design system is engineered for a high-end enterprise AI logistics platform. The brand personality is **authoritative, hyper-intelligent, and fluid**. It balances the industrial gravity of global logistics with the ethereal speed of artificial intelligence.

The visual style is a sophisticated blend of **Modern Corporate** and **Glassmorphism**. It utilizes deep atmospheric depth, subtle luminescence, and precision-engineered layouts to evoke a sense of "command and control." The UI should feel like a high-end flight deck—complex yet perfectly organized, providing users with the confidence that the AI is managing complexity behind a calm, premium interface.

## Colors

The palette is anchored in a multi-layered dark mode. 

- **Primary Canvas**: The deepest navy (#000e22) serves as the base background. 
- **Surface Elevation**: A slightly lighter navy (#00142b) is used for cards and containers to create structural separation.
- **Action & Focus**: The accent blue (#2563eb) is reserved for primary actions, progress indicators, and active states. 
- **System Health**: Emerald success (#10b981) represents optimized routes, completed tasks, and positive AI confidence intervals.

Use semi-transparent variants of the primary blue for hover states and subtle glow effects behind high-priority data visualizations.

## Typography

This design system uses **Hanken Grotesk** for all primary interfaces to maintain a modern, legible, and professional tone. The typeface's geometric clarity ensures high readability even in data-dense logistics dashboards.

For technical data, timestamps, and AI-generated IDs, **JetBrains Mono** (monospaced) is used to provide a "computational" aesthetic that distinguishes raw data from instructional text. Use uppercase for labels to enhance scannability in dense information environments.

## Layout & Spacing

The design system employs a **Fluid Grid** model with high-density capabilities. 

- **Desktop**: 12-column grid with 24px gutters. Use wide margins (40px) to allow the "Glassmorphism" effect to breathe against the deep background.
- **Tablet**: 8-column grid with 16px gutters.
- **Mobile**: 4-column grid with 16px margins.

Spacing follows a 4px baseline, but primary components should gravitate toward 16px (sm) and 24px (md) increments to ensure the UI feels expansive rather than cramped. Alignment should be rigorous and mathematical, reflecting the precision of logistics.

## Elevation & Depth

Depth is conveyed through **Glassmorphism and Tonal Layering** rather than traditional black shadows.

1.  **Level 0 (Base)**: #000e22.
2.  **Level 1 (Cards/Panels)**: #00142b with a 1px inner border (top-down) of `rgba(255, 255, 255, 0.05)` to catch the light.
3.  **Level 2 (Overlays/Modals)**: Semi-transparent #00142b (80% opacity) with a 20px Backdrop Blur. 
4.  **Luminescence**: Use soft, diffused primary blue glows (`box-shadow: 0 0 40px rgba(37, 99, 235, 0.1)`) for active AI-status indicators or critical path highlights.

Avoid heavy drop shadows; use "light-strokes" (thin, low-opacity borders) to define edges.

## Shapes

The shape language is defined by **Soft Precision**. 

The standard corner radius is **8px (0.5rem)**, providing a refined, approachable feel that isn't overly aggressive. 
- **Standard Cards/Inputs**: 8px.
- **Large Sections/Containers**: 16px (rounded-lg).
- **Control Chips/Badges**: Pill-shaped (Full round) to distinguish them from actionable buttons.

## Components

### Buttons
- **Primary**: Solid #2563eb with white text. Subtle outer glow on hover.
- **Secondary**: Ghost style with #2563eb border (1px) and subtle 5% blue fill on hover.
- **Tertiary**: Text-only, high-contrast white with blue icon accents.

### Cards
- Surfaces are #00142b. Must include an 8px corner radius and a subtle 1px border of `rgba(255, 255, 255, 0.08)`. 
- Header areas within cards should have a subtle bottom-border to separate metadata from content.

### Input Fields
- Darker than the card surface (#000e22) to create an "inset" feel. 
- Active state: 1px #2563eb border with a soft blue outer glow.

### Chips & Badges
- **Status Badges**: Small, semi-transparent backgrounds with high-saturation text (e.g., `rgba(16, 185, 129, 0.1)` background with #10b981 text).
- **AI-Suggestion Chips**: Distinguishable by a subtle gradient border from Blue to Emerald.

### Lists & Data Tables
- Row hover state: `rgba(255, 255, 255, 0.03)` background. 
- Use JetBrains Mono for all numerical data within tables for perfect alignment.