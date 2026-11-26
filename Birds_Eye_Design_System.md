# Birds Eye --- Design System

**Purpose:** Define the visual language for the Birds Eye single-pass
drone-video-to-3D-reconstruction application. Antigravity must apply
these design tokens and component patterns consistently across all
screens.

**Reference aesthetic:** Muted graphite dashboard with a light cool-gray
working surface, deep charcoal navigation, lime-green primary actions,
and slate-blue secondary controls. The interface should feel like a
precise engineering workstation: compact, organized, high-contrast,
practical, and visually calm.

**Important reference rule:** The supplied image is a visual reference
only. Reuse its overall palette, typography character, spacing rhythm,
panel treatment, restrained icon style, and dashboard composition. Do
not reuse any text, labels, names, data, charts, photos, logos, or
subject matter from the reference image.

**Product context:** Birds Eye processes drone video into sparse/dense
point clouds, meshes, textured 3D models, quality reports, and exports.
This document defines the appearance of that application; the product
behavior and processing requirements remain defined in
`Birds_Eye_Single_Pass_Drone_3D_Reconstruction_Spec.md`.

------------------------------------------------------------------------

## 1. Visual Direction

  -----------------------------------------------------------------------
  Principle                           Meaning
  ----------------------------------- -----------------------------------
  **Graphite outer shell**            Use a medium graphite gray as the
                                      page surround/background, with
                                      clearly separated work panels.
                                      Avoid pure black or bright white as
                                      the dominant canvas.

  **Charcoal navigation**             Use a deep charcoal sidebar with
                                      white text and subtle separators.
                                      Navigation should feel anchored and
                                      compact.

  **Cool-gray work surface**          Main work panels use a light cool
                                      gray, giving dense technical
                                      content a readable background.

  **Lime means action or success**    Reserve the vivid lime accent for
                                      primary actions,
                                      selected/highlighted items,
                                      successful stages, and important
                                      positive states. Do not flood whole
                                      screens with lime.

  **Slate blue means secondary**      Use muted slate blue for secondary
                                      buttons, filters, selected
                                      date/month controls, and neutral
                                      information.

  **Compact, structured dashboard**   Use a strong column layout, clear
                                      panel boundaries, compact section
                                      labels, and predictable alignment.

  **Dark text on light panels; light  Maintain legibility through
  text on dark panels**               deliberate contrast. Do not place
                                      low-contrast gray body text on gray
                                      surfaces.

  **Engineering over decoration**     Use restrained icons, thin
                                      dividers, small status markers, and
                                      meaningful technical
                                      visualizations. Avoid decorative
                                      gradients, neon glows,
                                      glassmorphism, or oversized
                                      marketing typography.

  **Real results only**               Point clouds, meshes, processing
                                      charts, and previews must show
                                      actual project outputs. Never use
                                      decorative demo geometry as if it
                                      came from a user's video.

  **Responsive by design**            Desktop can use a multi-panel
                                      workspace; tablet and mobile should
                                      stack panels without clipping
                                      controls or hiding essential job
                                      status.
  -----------------------------------------------------------------------

### Layout character

-   Desktop application frame centered within a graphite background.
-   Left navigation rail for project navigation and workflow access.
-   Central working area for the current task.
-   Optional right-side details panel for project metadata, job status,
    quality metrics, or exports.
-   Panels should be square or only mildly rounded; avoid pill-shaped
    cards everywhere.
-   Use clear alignment and thin dividers rather than large shadows.

------------------------------------------------------------------------

## 2. Color Tokens

Use CSS custom properties for all recurring colors. Do not scatter
hard-coded hex values through components.

The values below are representative starting tokens sampled/estimated
from the supplied visual reference. Tune them slightly if needed for
accessibility, but keep the same overall palette.

``` css
:root {
  /* Application surround */
  --bg-outer:          #5E6368;  /* Graphite gray outside the main workspace */
  --bg-shell:          #4D5258;  /* Intermediate shell/background */
  --bg-sidebar:        #34383E;  /* Charcoal navigation */
  --bg-sidebar-raised: #292D32;  /* Selected rows, nested items, inset areas */

  /* Work surfaces */
  --bg-panel:          #C7CAD1;  /* Main cool-gray panel */
  --bg-panel-soft:     #D7D9DE;  /* Secondary/light panel */
  --bg-panel-inset:    #AEB3BD;  /* Charts, preview wells, inset regions */
  --bg-panel-white:    #F0F1F3;  /* Rare high-contrast content area */

  /* Accent colors */
  --accent-lime:       #A7ED79;  /* Primary actions, selected success state */
  --accent-lime-hover: #B9F49A;  /* Hover state */
  --accent-lime-dark:  #6DBB46;  /* Darker accent for text/icons on light surfaces */
  --accent-slate:      #6C7999;  /* Secondary buttons and selected controls */
  --accent-slate-dark: #53617F;  /* Hover/pressed secondary state */

  /* Text on dark surfaces */
  --text-on-dark:      #F7F8FA;
  --text-dark-muted:   #C2C6CC;
  --text-dark-subtle:  #9298A1;

  /* Text on light surfaces */
  --text-on-light:     #171A20;
  --text-light-muted:  #3D424B;
  --text-light-subtle: #606773;

  /* Borders and separators */
  --border-dark:       rgba(255, 255, 255, 0.14);
  --border-light:      rgba(20, 24, 31, 0.16);
  --border-strong:     rgba(20, 24, 31, 0.30);

  /* Semantic status colors */
  --status-success:    #4C8F35;
  --status-success-bg: rgba(167, 237, 121, 0.35);
  --status-warning:    #946414;
  --status-warning-bg: #F3DDAA;
  --status-error:      #A8323D;
  --status-error-bg:   #F2C7CB;
  --status-info:       #435B8A;
  --status-info-bg:    #D7DEED;

  /* Viewer-only background */
  --viewer-bg:         #242931;
  --viewer-grid:       rgba(255, 255, 255, 0.16);
}
```

### Usage rules

-   Application surround → `--bg-outer`.
-   Navigation sidebar → `--bg-sidebar`.
-   Main working panels → `--bg-panel`.
-   Secondary or nested panel → `--bg-panel-soft`.
-   Chart wells, processing preview wells, and inset surfaces →
    `--bg-panel-inset`.
-   Primary action → `--accent-lime` with `--text-on-light`.
-   Secondary action → `--accent-slate` with white text.
-   Selected navigation row → `--bg-sidebar-raised` plus a lime marker
    or icon.
-   Viewer canvas → `--viewer-bg`, because a dark viewport improves
    visibility of point clouds and meshes.
-   Use semantic status tokens for success/warning/error. Do not use
    lime for warnings or red for neutral processing.
-   Maintain readable text contrast on both light and dark panels.
-   Do not introduce a second vivid accent color without a clear
    semantic purpose.

------------------------------------------------------------------------

## 3. Typography

### Font direction

The reference uses a compact, modern sans-serif with clear bold headings
and highly readable small labels. Use **Inter** as the default family
because it closely matches the visual character and is robust across
environments. Use system sans-serif as a fallback.

``` css
:root {
  --font-heading: 'Inter', 'Segoe UI', Arial, sans-serif;
  --font-body:    'Inter', 'Segoe UI', Arial, sans-serif;
  --font-mono:   'JetBrains Mono', 'Consolas', monospace;
}
```

Do not add decorative display fonts. Keep headings bold and compact. Use
the monospace face only for technical values such as timestamps,
coordinates, file sizes, processing durations, IDs, and numeric metrics.

### Type scale

  --------------------------------------------------------------------------------
  Token                                  Size               Weight Usage
  ---------------------- -------------------- -------------------- ---------------
  `type-page-title`                      26px             750--800 Main screen
                                                                   heading

  `type-section-title`                   18px                  700 Panel and
                                                                   section
                                                                   headings

  `type-card-title`                      15px             650--700 Project and
                                                                   output card
                                                                   headings

  `type-body`                            14px             400--500 Default UI text

  `type-body-strong`                     14px             600--700 Important row
                                                                   labels and
                                                                   values

  `type-small`                           12px             400--500 Supporting
                                                                   details, table
                                                                   values

  `type-label`                           11px             600--700 Compact
                                                                   uppercase
                                                                   section labels

  `type-micro`                           10px                  600 Tiny status
                                                                   tags only

  `type-metric`                      24--32px             700--800 Primary metrics
                                                                   and stage
                                                                   counts

  `type-mono`                        12--13px             400--500 Technical
                                                                   identifiers and
                                                                   values
  --------------------------------------------------------------------------------

### Rules

-   Use sentence case for most labels and buttons; reserve uppercase for
    short section labels.
-   Keep paragraph copy concise. Technical help text should wrap
    naturally rather than become tiny.
-   Use tabular numerals for percentages, point counts, timestamps, and
    progress values.
-   Do not use tiny text for critical errors, warnings, or processing
    status.
-   Avoid very large hero typography. This is a working engineering
    dashboard, not a marketing landing page.
-   Use the same heading and body families throughout the app.

------------------------------------------------------------------------

## 4. Spacing Scale

Use a consistent 4px-based spacing system.

``` css
:root {
  --space-1:  4px;
  --space-2:  8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;
}
```

### Common applications

-   Icon-to-label gap: `--space-2`.
-   Compact table cell padding: 10--12px vertical, 12--16px horizontal.
-   Button padding: 10--12px vertical, 16--20px horizontal.
-   Standard panel padding: 20--24px.
-   Gap between dashboard panels: 12--16px.
-   Gap between major page sections: 20--24px.
-   Sidebar item height: 40--44px.
-   Form field gap: 14--16px.
-   Dense technical data may use tighter spacing, but controls must
    remain easy to click.

------------------------------------------------------------------------

## 5. Borders, Corners, and Elevation

The reference uses mostly rectangular surfaces with modest corner
rounding and thin separators.

``` css
:root {
  --radius-xs:  2px;
  --radius-sm:  4px;
  --radius-md:  6px;
  --radius-lg:  8px;
  --radius-xl: 10px;

  --shadow-panel: 0 1px 2px rgba(0, 0, 0, 0.10);
  --shadow-menu:  0 6px 18px rgba(0, 0, 0, 0.18);
}
```

### Rules

-   Main workspace panels: 0--4px radius.
-   Buttons and inputs: 2--4px radius.
-   Small status chips: 3--4px radius.
-   Modals/popovers: 6--8px radius.
-   Prefer borders and background separation to heavy shadows.
-   Do not make every container a rounded card.
-   Use subtle borders on light panels and slightly brighter dividers on
    dark panels.

------------------------------------------------------------------------

## 6. Buttons and Interactive States

### Primary action

``` css
.btn-primary {
  background: var(--accent-lime);
  color: var(--text-on-light);
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  min-height: 40px;
  padding: 10px 18px;
  font: 650 14px var(--font-body);
}
.btn-primary:hover {
  background: var(--accent-lime-hover);
}
.btn-primary:disabled {
  opacity: 0.48;
  cursor: not-allowed;
}
```

Use for the main next step: create project, start reconstruction, retry
stage, or export a selected result.

### Secondary action

``` css
.btn-secondary {
  background: var(--accent-slate);
  color: #FFFFFF;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  min-height: 38px;
  padding: 9px 16px;
  font: 600 13px var(--font-body);
}
.btn-secondary:hover {
  background: var(--accent-slate-dark);
}
```

Use for browse, filters, inspect logs, open settings, or other secondary
actions.

### Neutral action

-   Background: transparent or `--bg-panel-soft`.
-   Text: `--text-on-light`.
-   Border: `--border-light`.
-   Use for cancel, back, close, and low-priority actions.

### Destructive action

-   Use `--status-error` for text and a restrained border/background.
-   Confirm destructive actions such as deleting a project or removing
    generated files.
-   Do not use red for ordinary cancel/back buttons.

### Focus and keyboard

-   Use a visible 2px outline in `--accent-slate-dark` or
    `--accent-lime-dark`, depending on surface.
-   Never remove focus indication without replacing it.
-   All controls must be keyboard accessible.

------------------------------------------------------------------------

## 7. Application Layout

### Breakpoints

-   Mobile: 360--767px.
-   Tablet: 768--1023px.
-   Desktop: 1024px and above.
-   Wide desktop: 1440px and above.

### Desktop frame

Use a three-zone composition inspired by the reference layout:

1.  **Left navigation:** fixed-width charcoal sidebar, approximately
    240--260px.
2.  **Main workspace:** flexible central area, light cool-gray surface.
3.  **Right inspector:** approximately 240--280px when relevant; hide or
    collapse it when the central task needs more room.

The main content should have consistent inner padding and clear panel
alignment. Avoid excessive empty space, but do not compress labels and
controls until they become hard to read.

### Sidebar

-   Dark charcoal background.
-   App logo/wordmark at the top; create a new Birds Eye mark or use a
    simple outlined icon. Do not reuse the reference image's logo.
-   Thin horizontal dividers between navigation groups.
-   White primary text, muted secondary labels.
-   Selected route uses a lime background or lime left marker. Prefer a
    contained selected item rather than making the entire sidebar
    bright.
-   Small outlined icons; use Lucide React.
-   Keep navigation compact and scannable.

### Main workspace

-   Light cool-gray background.
-   Dark text.
-   Panels and tool areas use slightly lighter/darker cool-gray
    variations.
-   Use a consistent grid and align panel edges.
-   Dense data tables may occupy full width.
-   Long processing logs should be placed in a dark inset terminal area
    with monospace text.

### Right inspector

Use for context-dependent details: - Selected project information. -
Processing stage status. - Reconstruction quality. - Available model
files. - Export options. - Warnings and limitations.

Do not show an empty inspector. If no item is selected, either collapse
it or show a concise project summary.

### Responsive behavior

-   Tablet: collapse the sidebar to a compact icon rail or a drawer;
    right inspector becomes collapsible.
-   Mobile: use a drawer or bottom navigation; stack all main panels
    vertically.
-   The 3D viewer should retain a useful minimum height and provide
    simplified controls on mobile.
-   Tables may scroll horizontally inside their own container; the full
    page must not overflow horizontally.
-   Important status and error messages must remain visible at narrow
    widths.

------------------------------------------------------------------------

## 8. Component Specifications

### 8.1 Sidebar navigation

**Structure** - Logo and application name. - Project selector or current
project summary. - Navigation groups for project overview,
reconstruction workflow, outputs, and settings. - Environment/dependency
status near the bottom. - Collapse control on wider layouts.

**Visual rules** - Background: `--bg-sidebar`. - Divider:
`--border-dark`. - Item height: 40--44px. - Label: 13--14px. - Icon:
18--20px, outlined. - Active item: `--bg-sidebar-raised` with a lime
marker or icon. - Hover: slightly lighter charcoal, no scale
transform. - Disabled items must have a clear disabled state and must
not appear clickable.

### 8.2 Workspace panels

``` css
.panel {
  background: var(--bg-panel);
  color: var(--text-on-light);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-panel);
  min-width: 0;
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px;
  border-bottom: 1px solid var(--border-light);
}
.panel-body {
  padding: 18px;
}
```

-   Keep panel headers short.
-   Use consistent header heights when panels sit side by side.
-   Do not nest many bordered panels inside one another.
-   Use an inset region for charts, logs, or the 3D viewport when
    contrast is needed.

### 8.3 Project cards and project rows

-   Show project name, source video name, created/updated time, and
    current status.
-   Include a compact progress indicator only when a job is active.
-   Use a neutral background and thin border.
-   Primary action: open/resume project.
-   Overflow menu: rename or delete, with confirmation for delete.
-   Do not show point counts, mesh status, or quality scores before
    those metrics are actually available.

### 8.4 Status chips

Use compact square-ish chips rather than oversized pills.

Statuses: - **Ready / Completed:** lime-tinted background and dark green
text. - **Running:** slate-blue tint and dark blue text, with a subtle
animated indicator if appropriate. - **Warning:** pale amber background
and dark amber text. - **Failed:** pale red background and dark red
text. - **Queued / Skipped / Unknown:** neutral gray background and dark
gray text.

Status text must remain understandable without relying on color alone.
Include a short label or icon. Respect reduced-motion settings for any
animation.

### 8.5 Progress stepper

The reconstruction stages should be displayed in the actual processing
order:

1.  Video validation.
2.  Frame extraction and preprocessing.
3.  Feature detection and matching.
4.  Structure-from-Motion.
5.  Multi-View Stereo / dense reconstruction.
6.  Mesh generation and texturing.
7.  Scale/georeferencing and evaluation.
8.  3D viewer and export.

Visual states: - Completed: lime check icon and subtle lime tint. -
Active: slate-blue or lime outline with clear text. - Failed: red status
icon and a short error summary. - Skipped: neutral gray with the reason
available. - Pending: muted neutral state.

Do not mark a step complete until the backend confirms success and
validates its required outputs.

### 8.6 Video uploader

-   Large, clearly bounded drop zone inside a light panel.
-   Use a thin dashed border.
-   Upload icon and concise instruction.
-   Show accepted file types and configured size limit.
-   On selection, show filename, file size, duration, frame rate, and
    resolution when available.
-   Invalid files should show an inline error, not just a toast.
-   Primary action is disabled until validation passes.
-   Use lime for the validated/ready action; do not turn the whole drop
    zone lime.

### 8.7 Metrics and quality summary

-   Small label above each metric.
-   Bold value in 24--32px type for primary metrics.
-   Supporting description below in 12--13px type.
-   Use monospace/tabular numerals for counts and errors.
-   Metrics may include accepted frames, registered frames, registration
    percentage, sparse points, dense points, vertices, faces, and
    reprojection error where available.
-   Display `Not available` or `—` when a metric cannot be computed.
-   Do not display unknown metrics as `0`.
-   Keep metric color neutral unless the metric is a meaningful status.

### 8.8 Charts and technical plots

-   Use a light panel around charts with clear dark labels.
-   Use muted slate blue for primary lines, lime for
    highlighted/positive series, and gray for reference series.
-   Gridlines should be thin and low contrast.
-   Avoid decorative 3D charts.
-   A chart must explain a real metric or status; do not add charts
    solely to fill space.
-   For frame-quality plots, show actual values and a legend.
-   For stage duration charts, use measured durations from job logs.

### 8.9 Processing logs / terminal panel

-   Dark inset background: `--viewer-bg` or `--bg-sidebar-raised`.
-   Monospace font, 12--13px.
-   Light gray text; semantic colors for warnings and errors.
-   Include timestamps and stage labels.
-   Provide copy/download log action.
-   Keep raw logs separate from user-friendly error summaries.
-   Avoid displaying secrets, tokens, or sensitive machine paths.
-   Auto-scroll only while the user is already at the bottom; do not
    repeatedly pull them away from earlier log entries.

### 8.10 3D model viewer

-   Viewer canvas uses `--viewer-bg`.
-   Use a subtle grid/axes only when enabled.
-   Toolbar controls: orbit, pan, zoom, reset view, fit model, toggle
    grid/axes, and available display modes.
-   Toolbar buttons use compact dark or slate surfaces with accessible
    tooltips.
-   Use actual point clouds/meshes produced by the backend.
-   Show a loading overlay while assets load.
-   Show a useful empty state when no model is available.
-   If a model fails to load, show the error and offer log/details
    access.
-   Use lime sparingly for selected controls or successful loading
    state.
-   Avoid visual effects that obscure terrain detail.

### 8.11 File export list

-   One row per actual available output.
-   Show filename, format, file size, and brief description.
-   Use a download icon and clear download action.
-   Group point clouds, meshes/textures, camera/reconstruction data, and
    reports.
-   Missing optional outputs should be omitted or shown as unavailable
    with a reason, not as active download links.
-   Clearly explain that OBJ exports may require the associated MTL and
    texture files.
-   For large outputs, show preparation/loading feedback and handle
    download errors.

### 8.12 Forms and settings

-   Labels appear above fields.
-   Input height: 38--42px.
-   Background: `--bg-panel-white` or `--bg-panel-soft`.
-   Border: `--border-light`.
-   Focus border: `--accent-slate-dark` with visible focus ring.
-   Helper text: 12px dark-muted text.
-   Validation errors: dark red text with a pale red background where
    appropriate.
-   Group advanced reconstruction options under a collapsible "Advanced
    settings" section.
-   Explain settings that can increase memory use or change
    reconstruction quality.
-   Use safe defaults and never require optional camera/GCP metadata to
    start a basic run.

### 8.13 Dialogs and confirmations

-   Modal surface: `--bg-panel-soft`.
-   Dark text and thin border.
-   Width: up to 520px, constrained to viewport.
-   Clear title, concise explanation, and right-aligned actions.
-   Use confirmations for project deletion, cancellation of active work,
    or deleting generated outputs.
-   Do not require confirmation for harmless navigation or viewing logs.
-   Focus must remain within an open modal; Escape closes it where safe.

### 8.14 Toasts and inline alerts

-   Toasts are compact and placed consistently.
-   Use success, warning, and error icons with matching semantic colors.
-   Toasts should not be the only place a critical error appears.
-   Processing failures should also appear in the job panel and remain
    visible until dismissed or resolved.
-   Keep messages plain-language and actionable.

------------------------------------------------------------------------

## 9. Iconography

-   **Library:** Lucide React.
-   **Style:** Outlined icons only; consistent 1.75--2px stroke.
-   **Default size:** 18--20px; 16px for compact inline controls; 24px
    for major empty states.
-   **Color:** inherit from text or use semantic status tokens.
-   Avoid emoji as primary navigation icons.
-   Do not use filled icon packs mixed with outlined icons.

Suggested icon mapping for Birds Eye: - Projects → `FolderKanban` - New
project → `FolderPlus` - Video upload → `Upload` - Frame extraction →
`Images` - Feature matching → `GitCompare` - SfM / camera poses →
`Camera` - Dense reconstruction → `Layers3` - Mesh/model → `Box` -
Viewer → `Orbit` - Georeferencing → `MapPin` - Quality report →
`ClipboardCheck` - Export → `Download` - Logs → `ScrollText` - Settings
→ `Settings` - Warning → `TriangleAlert` - Failure → `CircleX` - Success
→ `CircleCheck` - Retry → `RotateCcw`

If an icon name is unavailable in the installed Lucide version, choose
the closest available outlined icon. Do not substitute an unrelated
filled icon.

------------------------------------------------------------------------

## 10. CSS Token Setup

Create a central token file, for example
`frontend/src/styles/tokens.css`, and import it once from the
application entry point.

``` css
:root {
  --bg-outer: #5E6368;
  --bg-shell: #4D5258;
  --bg-sidebar: #34383E;
  --bg-sidebar-raised: #292D32;

  --bg-panel: #C7CAD1;
  --bg-panel-soft: #D7D9DE;
  --bg-panel-inset: #AEB3BD;
  --bg-panel-white: #F0F1F3;

  --accent-lime: #A7ED79;
  --accent-lime-hover: #B9F49A;
  --accent-lime-dark: #6DBB46;
  --accent-slate: #6C7999;
  --accent-slate-dark: #53617F;

  --text-on-dark: #F7F8FA;
  --text-dark-muted: #C2C6CC;
  --text-dark-subtle: #9298A1;

  --text-on-light: #171A20;
  --text-light-muted: #3D424B;
  --text-light-subtle: #606773;

  --border-dark: rgba(255,255,255,0.14);
  --border-light: rgba(20,24,31,0.16);
  --border-strong: rgba(20,24,31,0.30);

  --status-success: #4C8F35;
  --status-success-bg: rgba(167,237,121,0.35);
  --status-warning: #946414;
  --status-warning-bg: #F3DDAA;
  --status-error: #A8323D;
  --status-error-bg: #F2C7CB;
  --status-info: #435B8A;
  --status-info-bg: #D7DEED;

  --viewer-bg: #242931;

  --font-heading: 'Inter', 'Segoe UI', Arial, sans-serif;
  --font-body: 'Inter', 'Segoe UI', Arial, sans-serif;
  --font-mono: 'JetBrains Mono', Consolas, monospace;

  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;

  --radius-xs: 2px;
  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 8px;

  --shadow-panel: 0 1px 2px rgba(0,0,0,0.10);
  --shadow-menu: 0 6px 18px rgba(0,0,0,0.18);
}
```

### Global base styles

``` css
html, body, #root {
  min-height: 100%;
  margin: 0;
}

body {
  background: var(--bg-outer);
  color: var(--text-on-light);
  font-family: var(--font-body);
  font-size: 14px;
  line-height: 1.45;
}

button, input, select, textarea {
  font: inherit;
}

button {
  cursor: pointer;
}

button:disabled {
  cursor: not-allowed;
}

:focus-visible {
  outline: 2px solid var(--accent-slate-dark);
  outline-offset: 2px;
}

* {
  box-sizing: border-box;
}
```

Use these tokens throughout components. If Tailwind is used, map the
tokens to theme utilities or use CSS variables directly. Do not
duplicate the palette in multiple configuration files.

------------------------------------------------------------------------

## 11. Screen-Specific Application

### 11.1 Projects / Home

-   Charcoal sidebar on the left.
-   Main area on cool-gray surface.
-   Page title and a lime primary button for creating a project.
-   Recent projects shown as compact rows or cards with project name,
    source video, last updated time, and actual status.
-   A small environment-readiness panel may show backend, COLMAP, and
    GPU capability.
-   Avoid marketing copy and decorative charts.
-   If no projects exist, show a simple empty state with an
    upload/create action.

### 11.2 New Project / Video Upload

-   Use a wide upload panel in the main column.
-   Use a bordered drop zone with upload icon and short instruction.
-   Show file type/size constraints.
-   After selection, show actual video metadata in a compact grid.
-   Optional camera/GPS/GCP settings appear below or in a collapsible
    section.
-   Keep "Start Reconstruction" as the lime primary action.
-   Disable the action until validation passes.
-   Show input errors inline.

### 11.3 Processing Workspace

-   Main column: stage stepper and current stage.
-   Secondary panel: job metadata, elapsed time, available progress, and
    current warnings.
-   Bottom or tabbed region: logs and outputs from completed stages.
-   Use a muted slate-blue indicator for active work and lime for
    confirmed completed stages.
-   Use red only for failed stages and errors.
-   If a command does not expose reliable percentage progress, show
    "Running" and elapsed time rather than inventing a percentage.
-   Provide a clear cancel action with confirmation if cancellation
    could interrupt expensive work.

### 11.4 Frame Review

-   Show the contact sheet and a grid of extracted frames.
-   Each frame can display timestamp/frame index and quality score.
-   Use small neutral tags for accepted/rejected status.
-   Make rejected-frame reasons inspectable.
-   Keep filtering settings in a side panel or collapsible controls.
-   Use actual extracted frames only.

### 11.5 Reconstruction Results

-   Give the 3D viewer the largest area on this screen.
-   Place model mode controls and camera controls above the viewport.
-   Place quality metrics and warnings in a right-side inspector or a
    panel below the viewer.
-   Separate sparse cloud, dense cloud, mesh, and textured mesh states.
-   Do not show tabs for outputs that do not exist unless disabled with
    a clear explanation.
-   Use the viewer's dark background for geometry contrast; keep
    surrounding panels in the light palette.

### 11.6 Quality Report

-   Start with a compact status summary.
-   Show registered images, point counts, mesh statistics, and
    reprojection error only when available.
-   Clearly label unknown scale/georeferencing.
-   Use tables with restrained dividers and right-aligned numeric
    values.
-   Warnings and limitations should be visible, not hidden behind a tiny
    icon.
-   Export/download the report using a secondary action.

### 11.7 Export Panel

-   Group outputs by point cloud, mesh/texture, reconstruction data, and
    reports.
-   Each file row shows name, format, file size, and download action.
-   Use a lime button only for the primary export action; secondary
    formats use neutral/slate buttons.
-   Explain related files for formats such as OBJ + MTL + textures.
-   Show clear states for unavailable exports.

### 11.8 Settings / Environment

-   Use compact forms with labels above fields.
-   Group video limits, frame sampling, COLMAP path, compute settings,
    mesh options, and optional georeferencing settings.
-   Use an advanced section for risky/high-cost settings.
-   Show dependency checks with text plus semantic status chips.
-   Do not reveal secrets or environment variables containing
    credentials.

------------------------------------------------------------------------

## 12. Do / Don't

  -----------------------------------------------------------------------
  Do                                  Don't
  ----------------------------------- -----------------------------------
  Use graphite, charcoal, cool gray,  Introduce unrelated bright colors
  lime, and slate blue consistently   or gradients

  Use dark navigation and readable    Make every panel the same shade
  light work panels                   

  Reserve lime for primary actions    Paint entire pages lime
  and successful states               

  Use compact, bold headings and      Use oversized marketing typography
  readable small labels               

  Use modest corner rounding and thin Make every card heavily rounded or
  dividers                            shadowed

  Use Inter with a monospace face for Add decorative fonts or multiple
  technical values                    unrelated font families

  Use real frame previews, geometry,  Use the reference image's photos,
  and metrics                         text, chart, or data

  Show actual job progress and stage  Simulate processing progress or
  status                              success

  Mark unknown metrics as unavailable Replace unknown values with zero or
                                      fabricated numbers

  Use a dark viewer canvas for point  Use a light viewer that washes out
  clouds and meshes                   sparse geometry

  Provide inline validation and clear Rely on disappearing toasts for
  failure states                      critical errors

  Keep layouts responsive and         Allow horizontal overflow or tiny
  controls accessible                 touch targets
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 13. Implementation Checklist for Antigravity

Before shipping any screen, verify:

-   [ ] The reference image is used only for visual direction, not for
    content.
-   [ ] Main palette uses graphite, charcoal, cool gray, lime, and slate
    blue.
-   [ ] The left navigation uses charcoal with clear active-state
    treatment.
-   [ ] Main panels use light cool-gray surfaces with dark readable
    text.
-   [ ] The 3D viewport uses a dark canvas for geometry visibility.
-   [ ] Typography uses Inter and a consistent type scale.
-   [ ] Technical values use tabular numerals or monospace where
    appropriate.
-   [ ] Borders are thin and corners are modest.
-   [ ] Lime is reserved for primary actions and meaningful successful
    states.
-   [ ] Active, pending, failed, skipped, and completed stages are
    distinguishable.
-   [ ] Every progress/status label reflects actual backend state.
-   [ ] The UI never presents fake geometry or fake metrics as real
    output.
-   [ ] Empty, loading, error, and partial-result states are
    implemented.
-   [ ] Keyboard focus and accessible labels are present.
-   [ ] Mobile layout has no page-level horizontal overflow.
-   [ ] Colors are centralized in tokens rather than duplicated across
    components.
-   [ ] The final design stays consistent across projects, processing,
    results, and export screens.

------------------------------------------------------------------------

**End of design system.** Load alongside
`Birds_Eye_Single_Pass_Drone_3D_Reconstruction_Spec.md` and
`SKILL_build_birds_eye_3d_reconstruction.md` in every Antigravity
session that creates or modifies the Birds Eye UI.
