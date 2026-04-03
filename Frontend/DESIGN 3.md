# Design System Specification: The Architectural Intelligence

## 1. Overview & Creative North Star

### Creative North Star: "The Data Cathedral"
In the world of enterprise data, we often fall into the trap of "functional clutter." This design system rejects the chaos of traditional dashboards in favor of **The Data Cathedral**: a space that feels expansive, authoritative, and impossibly precise. It is built on the philosophy that data is not just information—it is infrastructure.

This system moves beyond "standard" UI by employing **Atmospheric Density**. We prioritize high-information density through meticulous typography and spatial hierarchy rather than borders and boxes. By utilizing asymmetric layouts and intentional tonal layering, we create a digital environment that feels as reliable as a physical structure and as sophisticated as a high-end editorial piece.

---

## 2. Colors: Tonal Architecture

Our palette is anchored in deep, "intellectual" blues and teals, supported by a sophisticated range of neutral surfaces that define space without the need for visual noise.

### The "No-Line" Rule
**Explicit Instruction:** Designers are prohibited from using 1px solid borders for sectioning or containment. Boundaries must be defined solely through background color shifts or tonal transitions.
*   **The Technique:** Use `surface-container-low` for a sidebar, `surface` for the main canvas, and `surface-container-lowest` for cards. The eye perceives the edge through the shift in luminance, resulting in a cleaner, more premium interface.

### Surface Hierarchy & Nesting
Treat the UI as a series of physical layers. Each "inner" container should utilize the surface-container tiers to denote nesting:
*   **Base Canvas:** `surface` (#f8f9fb)
*   **Secondary Regions:** `surface-container` (#edeef0)
*   **Interactive Cards:** `surface-container-lowest` (#ffffff)
*   **Global Nav/Modals:** `surface-container-high` (#e7e8ea)

### The "Glass & Gradient" Rule
To elevate the experience above a generic "SaaS" look, use **Glassmorphism** for floating elements (e.g., Command Palettes, Popovers). 
*   **Token Usage:** Use `surface-container-lowest` at 80% opacity with a `24px` backdrop-blur.
*   **Signature Textures:** For Primary CTAs, apply a subtle linear gradient from `primary` (#25475c) to `primary-container` (#3e5f74) at a 135-degree angle. This adds "soul" and depth to critical action points.

---

## 3. Typography: The Editorial Scale

We use a dual-font strategy to balance character with raw utility.

*   **Display & Headlines (Manrope):** Chosen for its geometric precision and modern "tech-humanist" feel. Use `display-lg` and `headline-md` for high-level data summaries to establish an authoritative tone.
*   **Body & Labels (Inter):** The workhorse for dense data. Inter's tall x-height ensures readability at small scales (`body-sm`, `label-sm`).

**Hierarchy Principle:** 
Establish authority through contrast. Pair a `headline-sm` title in a dark `on-surface` (#191c1e) with a `label-md` uppercase subtitle in `outline` (#737685) to create an "Editorial Header" for data tables.

---

## 4. Elevation & Depth: Tonal Layering

Traditional shadows are often a crutch for poor spatial planning. In this system, depth is achieved through **Tonal Layering**.

### The Layering Principle
Stacking surface tiers creates a soft, natural lift. A card using `surface-container-lowest` sitting on a `surface-container-low` background provides enough contrast to be distinct without a single pixel of shadow.

### Ambient Shadows
When a "floating" effect is mandatory (e.g., a dragged element or a primary modal):
*   **Blur:** 32px to 64px.
*   **Opacity:** 4%–6%.
*   **Color Tint:** Use a tinted version of `on-surface` (#191c1e) rather than pure black to ensure the shadow feels like it belongs to the environment.

### The "Ghost Border" Fallback
If accessibility requirements demand a border (e.g., in high-contrast modes), use a **Ghost Border**:
*   **Token:** `outline-variant` (#c3c6d6) at **15% opacity**. 
*   *Forbid 100% opaque, high-contrast borders.*

---

## 5. Components: Precision Primitives

### Buttons
*   **Primary:** Gradient of `primary` to `primary-container`. Corner radius: `md` (0.375rem).
*   **Secondary:** Ghost style. No background, `outline` border at 20% opacity. Text in `primary`.
*   **Interactive State:** On hover, increase the surface brightness by 5% and expand the shadow slightly.

### Cards & Data Lists
*   **No Dividers:** Forbid the use of horizontal rules. Use vertical white space (`spacing-4` or `spacing-6`) to separate rows.
*   **Alternating Tones:** For complex tables, use a subtle shift between `surface` and `surface-container-low` for row zebra-striping.

### Input Fields
*   **Style:** Minimalist. No bottom border or full box. Use `surface-container-highest` as a subtle background fill with a `sm` (0.125rem) corner radius. 
*   **Focus State:** A 2px "glow" using `primary` at 30% opacity, utilizing the `xl` roundedness scale for the focus ring to soften the technical edge.

### Data Chips
*   **Visuals:** Use `tertiary_container` (#62528b) for status indicators. Chips should have a "pill" shape (`full` roundedness) but remain small and unobtrusive (`label-sm`).

### Custom Component: The "Intelligence Rail"
A vertical, high-density navigation element using `surface-dim` (#d9dadc). It houses core platform functions in a "collapsed" icon-only state to maximize the "Data Cathedral" workspace.

---

## 6. Do's and Don'ts

### Do
*   **Do** use white space as a structural element. If a layout feels cramped, increase spacing before adding a border.
*   **Do** use `tertiary` (#4a3a72) and `secondary` (#00687a) for data visualization to distinguish "Insights" from "Infrastructure."
*   **Do** align all elements to the 0.2rem/0.4rem spacing grid to maintain mathematical harmony.

### Don't
*   **Don't** use pure black (#000000) for text. Use `on-surface` (#191c1e) to maintain a soft, professional tone.
*   **Don't** use standard "Drop Shadows." Always prefer tonal shifts or ambient, low-opacity blurs.
*   **Don't** use "Alert Red" for everything. Reserve `error` (#ba1a1a) for critical data loss; use `amber/warning` tokens for non-breaking issues to reduce user fatigue.