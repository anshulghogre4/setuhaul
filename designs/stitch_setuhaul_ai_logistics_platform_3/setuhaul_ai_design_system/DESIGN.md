---
name: SetuHaul AI Design System
colors:
  surface: '#faf8ff'
  surface-dim: '#d2d9f4'
  surface-bright: '#faf8ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f3ff'
  surface-container: '#eaedff'
  surface-container-high: '#e2e7ff'
  surface-container-highest: '#dae2fd'
  on-surface: '#131b2e'
  on-surface-variant: '#434655'
  inverse-surface: '#283044'
  inverse-on-surface: '#eef0ff'
  outline: '#737686'
  outline-variant: '#c3c6d7'
  surface-tint: '#0053db'
  primary: '#004ac6'
  on-primary: '#ffffff'
  primary-container: '#2563eb'
  on-primary-container: '#eeefff'
  inverse-primary: '#b4c5ff'
  secondary: '#5c5f61'
  on-secondary: '#ffffff'
  secondary-container: '#e0e3e5'
  on-secondary-container: '#626567'
  tertiary: '#006242'
  on-tertiary: '#ffffff'
  tertiary-container: '#007d55'
  on-tertiary-container: '#bdffdb'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dbe1ff'
  primary-fixed-dim: '#b4c5ff'
  on-primary-fixed: '#00174b'
  on-primary-fixed-variant: '#003ea8'
  secondary-fixed: '#e0e3e5'
  secondary-fixed-dim: '#c4c7c9'
  on-secondary-fixed: '#191c1e'
  on-secondary-fixed-variant: '#444749'
  tertiary-fixed: '#6ffbbe'
  tertiary-fixed-dim: '#4edea3'
  on-tertiary-fixed: '#002113'
  on-tertiary-fixed-variant: '#005236'
  background: '#faf8ff'
  on-background: '#131b2e'
  surface-variant: '#dae2fd'
typography:
  display:
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
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Hanken Grotesk
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.01em
  code-sm:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '450'
    lineHeight: 18px
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
  margin-desktop: 40px
  margin-tablet: 24px
  margin-mobile: 16px
  stack-xs: 4px
  stack-sm: 8px
  stack-md: 16px
  stack-lg: 32px
---

## Brand & Style
The design system embodies a premium enterprise aesthetic tailored for high-stakes AI decision-making. The visual narrative is defined by "Technical Sophistication"—a blend of high-end Swiss minimalism and modern developer-centric interfaces. 

The strategy prioritizes clarity, extreme precision, and an "airy" spatial model to reduce cognitive load in data-dense environments. Drawing inspiration from industry leaders like Linear and Vercel, the system utilizes a "Glass-on-Canvas" approach: structured, light-gray layouts serving as a high-contrast foundation for translucent, interactive layers. The goal is to evoke a sense of institutional trust and cutting-edge intelligence, positioning the product as the "operating system" for enterprise AI.

## Colors
This design system utilizes a high-key palette to maintain an expansive, clean feel. 

- **Foundation:** The primary background is pure white (#FFFFFF), providing maximum contrast. Sectioning is handled via the "Surface" color (#F8FAFC), used for sidebars, secondary panels, and layout nesting.
- **Action:** Primary Blue (#2563EB) is reserved for high-intent actions and critical status indicators.
- **Semantic:** Success, Warning, and Error colors are used sparingly. To maintain the premium feel, use these colors with low-saturation backgrounds (e.g., Error Red text on a 5% opacity Red background) for alerts and badges.
- **Grayscale:** Text should range from #0F172A (Headings) to #64748B (Secondary/Captions) to ensure professional legibility without the harshness of pure black.

## Typography
The typographic system pairs the sharp, contemporary geometry of **Hanken Grotesk** for display and headings with the utilitarian precision of **Inter** for body copy.

- **Display & Headlines:** Use Hanken Grotesk with tight letter-spacing for a modern, "engineered" look. 
- **Body Text:** Inter handles all long-form reading and UI labels. 
- **Data & AI Metadata:** **JetBrains Mono** is introduced as a tertiary font for AI-generated logs, technical IDs, and data values to emphasize the system's analytical nature.
- **Hierarchy:** Maintain a clear vertical rhythm by strictly adhering to the defined line heights. Use `body-sm` for most enterprise dashboard data cells.

## Layout & Spacing
This design system employs a **Fluid-Fixed Hybrid** model. Navigation and sidebars are fixed-width, while the primary content area scales with the viewport up to a maximum width of 1440px to prevent excessive line lengths.

- **Grid:** A 12-column grid is used for primary layouts, transitioning to a single-column layout on mobile.
- **Rhythm:** All spacing is based on a 4px baseline. Use 16px (`stack-md`) for standard component spacing and 32px (`stack-lg`) for section separation to maintain an "airy" feel.
- **Density:** While the overall brand is "airy," data tables should allow for a "compact" mode where vertical padding is halved to 8px to accommodate enterprise-scale data sets.

## Elevation & Depth
Depth is created through a combination of light-tinted borders and multi-layered shadows rather than heavy color shifts.

- **The Layering Logic:** 
  - **Level 0 (Base):** #FFFFFF background.
  - **Level 1 (Sub-section):** #F8FAFC with a 1px solid #E2E8F0 border. No shadow.
  - **Level 2 (Cards/Inputs):** White surface, 1px #E2E8F0 border, and a "Soft Ambient" shadow (0 1px 3px rgba(0,0,0,0.05), 0 10px 15px -5px rgba(0,0,0,0.03)).
  - **Level 3 (Modals/Overlays):** White surface with a "Deep Focus" shadow and a 12px backdrop-blur (Glassmorphism) applied to the layer immediately beneath.
- **Borders:** Use a subtle primary-tinted border (e.g., 10% Primary Blue) for active states to signify focus without adding visual bulk.

## Shapes
The shape language is "Generous & Modern." 

A standard **16px (1rem) corner radius** is applied to all primary cards, modal containers, and input fields. This softened geometry balances the technical nature of the AI data.
- **Small Elements:** Buttons and tags use a slightly reduced `rounded-lg` (8px) to maintain a crisp appearance at smaller scales.
- **Interactive States:** On hover, cards should not change their corner radius but may slightly increase their shadow depth to simulate physical lift.

## Components
- **Buttons:** Primary buttons use a solid Primary Blue background with white text. Ghost buttons use a 1px #E2E8F0 border and clear background, shifting to a #F8FAFC background on hover.
- **Inputs:** 16px rounded corners with a 1px #E2E8F0 border. The focus state uses a 1px Primary Blue border with a 3px soft blue outer glow (ring).
- **Cards:** Use the Level 2 elevation. Padding should be generous (24px or 32px) to support the "Fortune 500" quality.
- **Glass Chips:** For AI-specific tags or status indicators, use a semi-transparent white background (opacity 70%) with a backdrop-blur of 8px and a thin 1px border.
- **Data Tables:** Row lines should be #F1F5F9. Header cells use `label-md` typography with a subtle background tint of #F8FAFC.
- **AI Feedback:** Use a subtle gradient border (Primary Blue to Success Emerald) for components that represent active AI computation or live-updating data.