---
name: SetuHaul AI Visual Language
colors:
  surface: '#fff8f7'
  surface-dim: '#e8d6d4'
  surface-bright: '#fff8f7'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#fff0ef'
  surface-container: '#fdeae8'
  surface-container-high: '#f7e4e2'
  surface-container-highest: '#f1dedc'
  on-surface: '#231918'
  on-surface-variant: '#534434'
  inverse-surface: '#392e2d'
  inverse-on-surface: '#ffedeb'
  outline: '#867461'
  outline-variant: '#d8c3ad'
  surface-tint: '#855300'
  primary: '#855300'
  on-primary: '#ffffff'
  primary-container: '#f59e0b'
  on-primary-container: '#613b00'
  inverse-primary: '#ffb95f'
  secondary: '#ba0035'
  on-secondary: '#ffffff'
  secondary-container: '#e21e49'
  on-secondary-container: '#fffbff'
  tertiary: '#6d5a59'
  on-tertiary: '#ffffff'
  tertiary-container: '#c4abab'
  on-tertiary-container: '#513f3f'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#ffddb8'
  primary-fixed-dim: '#ffb95f'
  on-primary-fixed: '#2a1700'
  on-primary-fixed-variant: '#653e00'
  secondary-fixed: '#ffdada'
  secondary-fixed-dim: '#ffb3b6'
  on-secondary-fixed: '#40000c'
  on-secondary-fixed-variant: '#920028'
  tertiary-fixed: '#f7dcdc'
  tertiary-fixed-dim: '#dac1c0'
  on-tertiary-fixed: '#261818'
  on-tertiary-fixed-variant: '#554242'
  background: '#fff8f7'
  on-background: '#231918'
  surface-variant: '#f1dedc'
typography:
  display-lg:
    fontFamily: Geist
    fontSize: 48px
    fontWeight: '600'
    lineHeight: '1.1'
    letterSpacing: -0.04em
  headline-lg:
    fontFamily: Geist
    fontSize: 32px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '500'
    lineHeight: '1.3'
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Geist
    fontSize: 18px
    fontWeight: '400'
    lineHeight: '1.6'
    letterSpacing: '0'
  body-md:
    fontFamily: Geist
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
    letterSpacing: '0'
  label-md:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '500'
    lineHeight: '1.4'
    letterSpacing: 0.02em
  mono-sm:
    fontFamily: Geist Mono
    fontSize: 13px
    fontWeight: '400'
    lineHeight: '1.5'
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  unit: 4px
  container-max: 1440px
  gutter: 24px
  margin-mobile: 16px
  margin-desktop: 40px
  stack-sm: 8px
  stack-md: 16px
  stack-lg: 32px
---

## Brand & Style

The design system embodies "Elite Logistics Intelligence." It merges the precision of high-end enterprise software with the warmth of a luxury automotive cockpit. The aesthetic is a fusion of **Modern Corporate** and **Glassmorphism**, emphasizing high-fidelity clarity and rhythmic spatial density.

The target experience is one of effortless control. By utilizing a "Red-Yellow warm-tonal engine," the interface avoids the cold clinical nature of typical SaaS, instead offering a sophisticated, high-performance environment. The UI architecture follows a "Linear" style: high-contrast borders, rigorous grid alignment, and micro-interactions that feel expensive and intentional.

Key visual pillars:
- **Atmospheric Depth:** Multi-layered glass surfaces with varying blur intensities.
- **Volumetric Precision:** Use of subtle inner glows and ambient occlusion to define edges.
- **Warmth & Authority:** A rich palette that balances technical capability with premium hospitality.

## Colors

The palette is anchored in a "Sun-bleached Cream" and "Matte Obsidian-Terracotta" dichotomy. Unlike standard grayscale systems, every neutral in this design system contains a hint of red or yellow pigment to maintain the warm-tonal engine.

**Accent Usage:**
- **Amber-Gold (#F59E0B):** Used for "Active" states, primary calls to action, and positive data trends. It represents "Light" and "Energy."
- **Rich Crimson (#E11D48):** Reserved for high-priority alerts, critical status indicators, and secondary brand accents. It represents "Power" and "Urgency."
- **Glass Implementation:** In Dark Mode, surfaces utilize a 75% opacity maroon-espresso tint with a 20px backdrop blur to create depth without losing legibility.

## Typography

The design system utilizes **Geist** for its mathematical precision and developer-centric clarity. It provides a technical edge that complements the luxury aesthetic.

- **Scale:** High contrast between display types and body copy to emphasize hierarchy in data-heavy screens.
- **Tight Kerning:** Large headlines use negative letter spacing to create a "compact" and "premium" feel.
- **Monospace Integration:** For logistics coordinates, VIN numbers, and AI confidence scores, use the monospaced variant of Geist to maintain alignment and technical authenticity.

## Layout & Spacing

This design system employs a **Fixed-Fluid Hybrid Grid**. The primary dashboard content lives within a 1440px max-width container, while sidebars and command nodes remain fixed to the viewport edges.

- **Rhythm:** A strict 4px baseline grid ensures every element aligns perfectly.
- **Whitespace:** Emphasize "Immense Whitespace." Group related KPI blocks tightly, but allow for significant breathing room (40px+) between major sections to prevent cognitive overload.
- **Responsiveness:** On mobile, margins shrink to 16px and the 12-column desktop grid collapses into a single-column stack. Floating command nodes transition to a bottom-docked navigation bar.

## Elevation & Depth

Hierarchy is defined through **Ambient Occlusion** and **Tonal Layering** rather than traditional drop shadows.

- **Shadows:** Use ultra-diffused, multi-layered shadows with a slight warm tint (#2D1E1E at 5-10% opacity). Avoid harsh black shadows.
- **The "Glass" Effect:** Components should appear as if they are hovering 16px above the base layer. Apply a 1px inner border (stroke) with 10% white (light mode) or 10% amber (dark mode) to simulate the edge of a glass pane catching light.
- **Z-Index Strategy:** 
  - Level 0: Background (Cream/Obsidian)
  - Level 1: Main Content Cards (Solid White/Maroon Glass)
  - Level 2: Floating Command Nodes & Modals
  - Level 3: Tooltips and Context Menus

## Shapes

The shape language is "Micro-Rounded." It avoids the playfulness of fully rounded "bubble" UI, opting for a geometric, architectural feel.

- **Standard Radius:** 16px is the default for all primary containers and cards.
- **Interactive Elements:** Buttons and inputs use a tighter 8px-12px radius to feel more precise and "clickable."
- **Data Indicators:** Status chips and badges utilize a full pill-shape (999px) to contrast against the rigid rectangular grid.

## Components

### Floating Command Nodes
These are the primary interaction points. They should appear as small, glassmorphic bars floating at the bottom-center of the screen. They house global AI actions and search.

### KPI Blocks
High-density data containers. 
- **Header:** Label-md typography in clay-grey.
- **Value:** Headline-lg in Primary Amber.
- **Trend:** Small fluid vector area graphs using a linear gradient from Amber (#F59E0B) to Crimson (#E11D48).

### Buttons
- **Primary:** Solid Amber-Gold with black text for maximum contrast.
- **Secondary:** Transparent glass with a 1px border of the accent color.
- **Interaction:** On hover, a soft 4px "outer glow" in the primary color should appear (volumetric effect).

### Tables
Clean markdown-style tables. No vertical lines. Horizontal lines should be ultra-thin (0.5px) and low contrast. Header row uses the Sidebar color (#2D1E1E) with white text for a "weighted" feel.

### Input Fields
Minimalist design. No background in light mode (just a bottom border), or a 20% opacity dark fill in dark mode. Focus state triggers an Amber-Gold glow.