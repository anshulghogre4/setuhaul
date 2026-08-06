---
name: SetuHaul AI Design System
colors:
  surface: '#faf8ff'
  surface-dim: '#d9d9e4'
  surface-bright: '#faf8ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f3f3fe'
  surface-container: '#ededf8'
  surface-container-high: '#e7e7f2'
  surface-container-highest: '#e2e1ed'
  on-surface: '#191b23'
  on-surface-variant: '#434654'
  inverse-surface: '#2e3038'
  inverse-on-surface: '#f0f0fb'
  outline: '#737686'
  outline-variant: '#c3c5d7'
  surface-tint: '#1953d5'
  primary: '#1351d3'
  on-primary: '#ffffff'
  primary-container: '#3b6bed'
  on-primary-container: '#fefbff'
  inverse-primary: '#b5c4ff'
  secondary: '#5f3add'
  on-secondary: '#ffffff'
  secondary-container: '#7857f8'
  on-secondary-container: '#fffbff'
  tertiary: '#924700'
  on-tertiary: '#ffffff'
  tertiary-container: '#b75b00'
  on-tertiary-container: '#fffbff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dbe1ff'
  primary-fixed-dim: '#b5c4ff'
  on-primary-fixed: '#00174d'
  on-primary-fixed-variant: '#003dab'
  secondary-fixed: '#e6deff'
  secondary-fixed-dim: '#cabeff'
  on-secondary-fixed: '#1c0062'
  on-secondary-fixed-variant: '#4918c8'
  tertiary-fixed: '#ffdcc6'
  tertiary-fixed-dim: '#ffb786'
  on-tertiary-fixed: '#311400'
  on-tertiary-fixed-variant: '#723600'
  background: '#faf8ff'
  on-background: '#191b23'
  surface-variant: '#e2e1ed'
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
    fontWeight: '500'
    lineHeight: 28px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-mono:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.05em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  unit: 4px
  container-padding: 32px
  gutter: 24px
  sidebar-width: 280px
  stack-sm: 8px
  stack-md: 16px
  stack-lg: 24px
---

## Brand & Style

The design system is engineered to evoke a sense of "High-Performance Intelligence." It targets enterprise decision-makers and high-stakes operators who require the clarity of a premium productivity suite (like Apple Keynote) combined with the information density of a modern developer dashboard (like Stripe). 

The visual style merges **Modern Corporate** structure with **Glassmorphism**. It utilizes semi-transparent layers, subtle backdrop blurs, and volumetric ambient occlusion to create a multi-dimensional interface that feels physical yet digital. The atmosphere is professional, sleek, and authoritative, emphasizing precision through micro-rounded corners and high-fidelity typography.

## Colors

This design system utilizes a sophisticated dual-token engine to maintain a premium feel across environments. 

- **Primary & Secondary:** Corporate Cobalt Blue and Electric Violet are used exclusively for interactive actions, data visualizations, and highlighting AI-driven insights. 
- **Light Mode:** Focuses on high-contrast legibility with a soft blue-grey foundation. Navigational elements (Sidebar/Navbar) remain dark to provide a structural frame.
- **Dark Mode:** Employs a "Midnight Glass" aesthetic. Surfaces use high-transparency overlays with a 20px backdrop blur to maintain depth without clutter.
- **Gradients:** Primary gradients should flow from Cobalt Blue (#4F7DFF) to Electric Violet (#7C5CFC) at a 135-degree angle.

## Typography

The typography strategy balances executive-level clarity with technical precision. 

- **Headlines:** Use **Hanken Grotesk** for its contemporary, sharp terminals. Large displays should use tight letter spacing to mirror high-end editorial design.
- **Body:** **Inter** provides maximum legibility for data-heavy sections and long-form AI analysis.
- **Data & Labels:** **Geist** is reserved for monospaced data points, status labels, and "command node" text to emphasize the software's technical AI core.

## Layout & Spacing

The layout follows a **Fixed-Fluid Hybrid** model. The sidebar and navigation are fixed, while the primary content area uses a 12-column fluid grid.

- **Margins:** Desktop views require generous 32px external margins to prevent the UI from feeling cramped.
- **Rhythm:** All spacing must be multiples of 4px. Use 24px gutters between grid cards to allow "ambient occlusion" shadows to breathe.
- **Mobile Adaptivity:** On mobile, the 12-column grid collapses to a single column. The sidebar transforms into a full-screen drawer, and internal card padding reduces from 24px to 16px.

## Elevation & Depth

This system utilizes **Volumetric Layering** to define hierarchy.

1.  **Level 0 (Background):** Flat color (#EEF2F7 or #0F172A).
2.  **Level 1 (Cards/Nodes):** Frosted glass surfaces. In light mode, use a subtle 1px white border (20% opacity). In dark mode, use a 1px border (10% white) to define edges.
3.  **Shadows:** Shadows are "Ambient Occlusion" style—extremely wide, soft, and low-opacity.
    - *Light Mode:* `0 20px 50px rgba(0,0,0,0.05)`.
    - *Dark Mode:* `0 20px 50px rgba(0,0,0,0.3)`.
4.  **Blur:** All elevated surfaces must apply a `backdrop-filter: blur(20px)`.

## Shapes

The shape language is defined as **Micro-Rounded**. While corners are soft, they are not "bubbly."

- **Standard Elements:** (Buttons, Inputs, Small Cards) use 0.5rem (8px).
- **Large Containers:** (Dashboard Cards, Modal Windows) use 1rem (16px).
- **Floating Command Nodes:** Use 1.5rem (24px) or full pill-shape to distinguish them from standard structural elements.

## Components

- **Midnight Navbars:** Fixed to the top or side. Use `#34445F` (Light) or `#111827` (Dark). Icons should be stroke-based (1.5px weight) using the secondary text color, shifting to Primary Blue on active state.
- **Glassmorphic Cards:** Content containers must have a semi-transparent background and blur. No solid fills for cards in Dark Mode.
- **Floating Message Consoles:** AI chat or log interfaces should appear as "Command Nodes"—floating above the content with higher elevation and pill-shaped headers.
- **High-Density Data Tables:** Use zero-border layouts. Distinguish rows with very subtle zebra striping (`rgba(255,255,255,0.02)`) and use the `label-mono` typography for numeric data.
- **Vibrant Area Graphs:** Data visualizations must use the Cobalt-to-Violet gradient. The area fill should be a 10% opacity version of the stroke color, fading to 0% at the X-axis.
- **Buttons:** Primary buttons use the 135° gradient fill with white text. Secondary buttons use a ghost style with a 1px border.