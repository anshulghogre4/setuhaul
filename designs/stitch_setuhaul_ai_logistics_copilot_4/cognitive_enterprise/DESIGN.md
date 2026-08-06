---
name: Cognitive Enterprise
colors:
  surface: '#f8f9ff'
  surface-dim: '#d0dbed'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e6eeff'
  surface-container-high: '#dee9fc'
  surface-container-highest: '#d9e3f6'
  on-surface: '#121c2a'
  on-surface-variant: '#434654'
  inverse-surface: '#27313f'
  inverse-on-surface: '#eaf1ff'
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
  tertiary: '#4f5c78'
  on-tertiary: '#ffffff'
  tertiary-container: '#687592'
  on-tertiary-container: '#fefcff'
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
  tertiary-fixed: '#d7e2ff'
  tertiary-fixed-dim: '#b9c6e7'
  on-tertiary-fixed: '#0d1b34'
  on-tertiary-fixed-variant: '#3a4761'
  background: '#f8f9ff'
  on-background: '#121c2a'
  surface-variant: '#d9e3f6'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Inter
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
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.05em
  code:
    fontFamily: jetbrainsMono
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
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
  xl: 32px
  xxl: 48px
  container-max: 1440px
  gutter: 24px
  margin-mobile: 16px
  margin-desktop: 32px
---

## Brand & Style

This design system is engineered for a premium, AI-first enterprise experience. It bridges the gap between high-utility productivity tools and sophisticated lifestyle aesthetics, drawing inspiration from the precision of developer-centric platforms and the elegance of consumer hardware interfaces.

The brand personality is **Intelligent, Reliable, and Forward-leaning**. It targets decision-makers and power users who require high information density without the cognitive load typically associated with enterprise software.

### Visual Style: "Prism Logic"
The aesthetic combines **Minimalism** with **Glassmorphism**. It utilizes a structured grid, vast whitespace, and subtle depth through translucent layers. The interface should feel "airy" yet grounded, using soft shadows and light-refractive properties to indicate hierarchy. Interaction patterns are fluid, mirroring the adaptive nature of AI.

## Colors

The palette is anchored by a deep professional navy (`#2D3A54`) and energized by a vibrant digital blue (`#4F7DFF`). 

- **Primary & Secondary Accents:** Use the Primary Blue for main actions and the Secondary Violet for AI-driven features or "magic" moments.
- **Surface Strategy:** The app background uses a cool grey-blue tint (`#EEF2F7`) to make the pure white (`#FFFFFF`) card surfaces pop with high perceived elevation.
- **Navigation:** The Sidebar and Top Nav use high-contrast dark values to frame the content area, focusing the user's attention on the data and workspace.
- **Gradients:** Subtle linear gradients (135°) transitioning from Primary to Secondary should be used sparingly for primary buttons and active AI states.

## Typography

This design system utilizes **Inter** for its neutral, systematic clarity and excellent legibility in high-density enterprise environments.

- **Weight Usage:** Reserve Bold (700) for display levels. Use Semi-Bold (600) for headlines and primary labels to maintain a professional, sturdy feel.
- **Hierarchy:** Maintain clear vertical rhythm by strictly adhering to the defined line-heights.
- **Labels:** Small labels (`label-md`) should use uppercase with slight letter spacing to differentiate from body text in dense data views.
- **AI Output:** Use **JetBrains Mono** for code snippets or raw data outputs generated by the AI to distinguish machine-generated content from the UI.

## Layout & Spacing

The design system follows a **Fluid Grid** model with fixed-width content containers for readability.

- **Grid System:** Use a 12-column grid for desktop with 24px gutters. Elements should align to a 4px/8px baseline shift.
- **Whitespace:** Prioritize "Generous Breathing Room." Enterprise data is often dense; use the `xxl` (48px) spacing between major sections to prevent user fatigue.
- **Responsive Behavior:** 
    - **Desktop (>1024px):** 12 columns, 32px side margins.
    - **Tablet (768px - 1023px):** 8 columns, 24px side margins.
    - **Mobile (<767px):** 4 columns, 16px side margins. Cards should typically stack vertically and take full width minus margins.

## Elevation & Depth

Depth is used to signal interactivity and focus, moving away from flat design toward a more tactile, layered environment.

- **Tonal Layers:** The primary app background is the lowest layer. The Sidebar and Top Nav sit on top with no shadow but high color contrast.
- **Glassmorphism:** Use for overlays, dropdowns, and modal backgrounds. Apply a `backdrop-filter: blur(12px)` and a white `opacity: 0.7` background. Add a 1px inner border with `white/20%` to simulate the edge of a glass pane.
- **Ambient Shadows:**
    - **Level 1 (Cards):** `0 4px 20px -2px rgba(45, 58, 84, 0.05)` — subtle, integrated.
    - **Level 2 (Dropdowns/Modals):** `0 12px 40px -4px rgba(45, 58, 84, 0.12)` — floating, distinct.
- **Active State:** When an item is dragged or hovered, increase the shadow spread and slightly scale the element (1.02x) to provide tactile feedback.

## Shapes

The shape language is approachable and modern, softening the traditional "sharpness" of enterprise software.

- **Base Components:** Buttons and input fields use `rounded-md` (0.5rem / 8px).
- **Container Elements:** Cards and main content areas use `rounded-xl` (1.5rem / 24px) for a soft, premium appearance.
- **Sidebar Elements:** Active states within the dark sidebar should use a `rounded-lg` (1rem / 16px) shape to contrast against the straight edges of the screen.
- **AI Elements:** Elements specifically related to AI features (like a chat bubble or a spark icon container) can use `rounded-3xl` (pill-shaped) to distinguish them from standard CRUD components.

## Components

### Buttons
- **Primary:** Linear gradient (`#4F7DFF` to `#7C5CFC`), white text, 8px corner radius. Subtle inner glow on top edge.
- **Secondary:** White background with a 1px border of `#E2E8F0`. Text uses Secondary Color.
- **Ghost:** No background or border. Primary color text. Use for low-priority actions.

### Cards
- **Standard:** White background, 24px corner radius, Level 1 shadow. 24px internal padding.
- **Interactive:** Level 1 shadow increases to Level 2 on hover with a 1px border transition to `#4F7DFF`.

### Input Fields
- **Default:** `#F8FAFC` background, 1px `#E2E8F0` border. On focus: border becomes `#4F7DFF` with a 3px soft blue glow (ring).
- **AI-Input:** A larger, pill-shaped input with a glassmorphic background and a "sparkle" icon as a suffix or prefix.

### Chips & Badges
- **Status Badges:** Use soft background tints (10% opacity of the semantic color) with high-contrast text of the same color. 
- **Filter Chips:** 100px roundedness (pill), neutral background, removable with an "X" icon.

### Sidebar & Navigation
- **Sidebar Items:** Clear separation between "System" navigation and "Workspace" navigation. Active state is a high-contrast white text with a subtle background highlight.
- **Top Nav:** Glassmorphic bar (blur) that stays sticky. Uses a subtle bottom border (`white/10%`) to separate from content.

### AI Interface Components
- **Message Bubbles:** User messages are simple and neutral. AI responses have a very subtle gradient border and a specific "AI" badge in the corner.
- **Loading States:** Use a pulsing shimmer effect (skeleton screens) rather than traditional spinners to maintain the premium feel.