/**
 * The two touch rules `mockup.html`'s R6 fix added to `.btn, .row, .link-ctl, .field`, as one
 * class string so a new control on this surface cannot quietly omit them.
 *
 * Both come from the Web Interface Guidelines' Touch & Interaction section and both earn their
 * place specifically here: this is the most touch-dependent surface in the product -- every
 * interaction is a single gloved tap -- so the 300ms double-tap-zoom delay `touch-action:
 * manipulation` removes is felt on the one dominant button of every screen, and the browser's
 * default blue tap flash is a distraction under glare rather than press feedback (the pressed
 * colour step already provides that).
 *
 * `-webkit-tap-highlight-color` has no Tailwind utility, so it goes through v4's arbitrary-property
 * syntax rather than into `theme.css` -- it is a surface-specific rule, not a design token, and
 * `theme.css` is shared infrastructure this build does not own.
 */
export const TOUCH_CLASS = 'touch-manipulation [-webkit-tap-highlight-color:transparent]'
