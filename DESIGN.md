---
name: GeoIssue
description: One civic issue dataset on a familiar map, table and dashboard. Quiet white surfaces, one blue accent, the map and the data doing the talking.
colors:
  # Light theme (default): :root in src/styles.css
  bg: "#f5f6f8"
  surface: "#ffffff"
  surface-2: "#f8f9fb"
  surface-3: "#eef0f3"
  border: "#e4e7eb"
  border-strong: "#cfd4da"
  text: "#111827"
  text-2: "#374151"
  text-3: "#545b67"
  text-4: "#6b7280"
  accent: "#2563eb"
  accent-hover: "#1d4ed8"
  accent-soft: "#eef3ff"
  accent-border: "#bfd2fd"
  accent-text: "#1d4ed8"
  danger: "#dc2626"
  danger-soft: "#fef2f2"
  danger-border: "#fcc9c9"
  danger-text: "#b91c1c"
  warning: "#d97706"
  warning-soft: "#fffbeb"
  warning-border: "#fce4a6"
  warning-text: "#a8520a"
  success: "#059669"
  success-soft: "#ecfdf5"
  success-border: "#a7f0cf"
  success-text: "#047857"
  purple: "#7c3aed"
  purple-soft: "#f5f3ff"
  purple-border: "#ddd5fe"
  purple-text: "#6d28d9"
  on-accent: "#ffffff"
  on-color: "#111827"
  on-danger: "#ffffff"
  overlay: "rgb(17 24 39 / .45)"
  # Dark theme: :root[data-theme="dark"] in src/styles.css
  dark-bg: "#0e0f11"
  dark-surface: "#17181b"
  dark-surface-2: "#1d1e22"
  dark-surface-3: "#25262b"
  dark-border: "#2b2d33"
  dark-border-strong: "#3c3f46"
  dark-text: "#ececef"
  dark-text-2: "#c5c8cf"
  dark-text-3: "#a0a4ad"
  dark-text-4: "#868a94"
  dark-accent: "#2563eb"
  dark-accent-hover: "#1e55d6"
  dark-accent-soft: "#172238"
  dark-accent-border: "#2c4a85"
  dark-accent-text: "#82aaff"
  dark-danger: "#e5484d"
  dark-danger-soft: "#2b1618"
  dark-danger-border: "#5e2529"
  dark-danger-text: "#ff8a8d"
  dark-warning: "#f5a524"
  dark-warning-soft: "#2a2110"
  dark-warning-border: "#5b4416"
  dark-warning-text: "#f7c065"
  dark-success: "#12a777"
  dark-success-soft: "#10261f"
  dark-success-border: "#1e5242"
  dark-success-text: "#4fd1a1"
  dark-purple: "#8b5cf6"
  dark-purple-soft: "#1f1a33"
  dark-purple-border: "#40336f"
  dark-purple-text: "#b39dfa"
  dark-on-accent: "#ffffff"
  dark-on-color: "#111827"
  dark-on-danger: "#1a0b0c"
  dark-overlay: "rgb(0 0 0 / .6)"
  # Map pin categories: categories in src/data.js, identical in both themes
  category-pothole: "#dc2626"
  category-sidewalk-damage: "#d97706"
  category-graffiti: "#7c3aed"
  category-litter: "#059669"
  category-flooding: "#2563eb"
  category-other: "#6b7280"
typography:
  brand:
    fontFamily: "Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "27px"
    fontWeight: 700
    letterSpacing: "-1.1px"
  headline:
    fontFamily: "Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "22px"
    fontWeight: 700
    letterSpacing: "-.5px"
  stat:
    fontFamily: "Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "24px"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-1px"
  title:
    fontFamily: "Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "17px"
    fontWeight: 650
    letterSpacing: "-.3px"
  subtitle:
    fontFamily: "Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "15px"
    fontWeight: 650
  body:
    fontFamily: "Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.65
    fontFeature: "'cv11', 'ss01'"
  control:
    fontFamily: "Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "13px"
    fontWeight: 500
  label:
    fontFamily: "Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "12px"
    fontWeight: 550
rounded:
  chip: "4px"
  badge: "5px"
  field: "6px"
  control: "7px"
  panel: "8px"
  card: "10px"
  canvas: "11px"
  dialog: "13px"
  pill: "20px"
  round: "50%"
spacing:
  map-inset: "15px"
  panel: "18px"
  dialog: "24px"
  page: "28px"
components:
  button:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "11px 15px"
  button-hover:
    backgroundColor: "{colors.surface-2}"
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "11px 15px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  button-small:
    padding: "8px 12px"
  icon-button:
    textColor: "{colors.text-3}"
    rounded: "{rounded.control}"
    size: "32px"
  icon-button-hover:
    backgroundColor: "{colors.surface-3}"
    textColor: "{colors.text}"
  text-button:
    textColor: "{colors.accent-text}"
  search-field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    height: "32px"
    padding: "0 11px"
  filter-select:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-2}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    height: "32px"
    padding: "0 10px"
  map-control:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-2}"
    rounded: "{rounded.field}"
    size: "37px"
  map-control-hover:
    backgroundColor: "{colors.surface-2}"
  map-control-active:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent-text}"
  segment-active:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent-text}"
    rounded: "{rounded.chip}"
  nav-item:
    textColor: "{colors.text-3}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "13px 14px"
    height: "45px"
  nav-item-hover:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text}"
  nav-item-active:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent-text}"
  badge:
    backgroundColor: "{colors.surface-3}"
    textColor: "{colors.text-2}"
    rounded: "{rounded.badge}"
    padding: "5px 8px"
  badge-high:
    backgroundColor: "{colors.danger-soft}"
    textColor: "{colors.danger-text}"
  badge-open:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent-text}"
  badge-in-review:
    backgroundColor: "{colors.surface-3}"
    textColor: "{colors.warning-text}"
  badge-verified:
    backgroundColor: "{colors.surface-3}"
    textColor: "{colors.success-text}"
  filter-chip:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent-text}"
    rounded: "{rounded.badge}"
    padding: "4px 7px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.card}"
  issue-panel:
    backgroundColor: "{colors.surface}"
    width: "360px"
  dialog:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.dialog}"
    width: "540px"
  map-pin:
    textColor: "{colors.on-accent}"
    width: "30px"
    height: "31px"
  map-cluster:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.round}"
    size: "34px"
  data-switch:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text-2}"
    rounded: "{rounded.pill}"
    padding: "5px 11px"
  toast:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.panel}"
    padding: "13px 19px"
---

# Design System: GeoIssue

## Overview

**Creative North Star: "The Quiet Civic Map"**

GeoIssue is the familiar civic map-and-data tool, built with care rather than novelty. White working surfaces sit on a cool grey ground, one blue carries every action and selection, Inter sets everything, and the map and the data do the talking. The bar is the category's best: Google Maps for the map, Linear and Stripe for panels and tables, city open-data portals and 311 tools for the civic register, Mapbox and Felt for overlays.

The density is that of a working tool. Controls read at 13px, filter fields are 32px tall, borders are neutral hairlines, and a single soft shadow lifts whatever floats over the map. Saturated colour belongs to the data: category pins on a muted basemap, tinted chips for severity, status and verification, and a blue-to-red density ramp. Light is the default theme; dark is the same system in neutral graphite.

The world was chosen against the dark neon command-centre look the app used to have. It carries no glows, no cyan halos, no gradient sheen, no backdrop blur and no gradient text, and nothing in it should read as AI-generated.

**Key Characteristics:**
- White surfaces on a cool grey ground, separated by neutral hairline borders.
- One blue for actions, selection, links and status chips; never for plain text.
- Inter only: 13px controls, and nothing a reader must read below 12px.
- Teardrop pins in category colours on a desaturated basemap; blue numbered clusters.
- One soft shadow for things that float; everything else is flat.
- Light by default; dark is neutral graphite, never navy.

## Colors

A neutral grey-and-white workspace with a single civic blue, and saturated hues kept for the data.

### Primary
- **Civic Blue** (#2563eb): the accent fill. Primary buttons, the selected map tool's edge, clusters, the active table tab underline, ward outlines, the uncertainty circle, chart lines and breakdown bars, and the lens mark. It keeps the same fill in dark.
- **Pressed Blue** (#1d4ed8): hover and pressed state of a primary button; a selected cluster.
- **Link Blue** (#1d4ed8 light, #82aaff dark): blue at text level. Links, text buttons, the active nav item, active segments and legend items, and the label inside a blue status chip.
- **Selection Wash** (#eef3ff): the background of anything active or selected: the current nav item, active segment, active map tool, filter chips, selected or hovered table rows, sorted column headers, open and low-priority chips.
- **Selection Edge** (#bfd2fd): the edge of blue status chips (open, low priority, nav counts).

### Neutral
- **Civic Grey Ground** (#f5f6f8): the app ground behind every page and the splash.
- **Paper White** (#ffffff): every card, dialog, panel, input, filter, map control and the sidebar.
- **Faint Mist** (#f8f9fb): tone step inside white: table header, zebra rows, the legend strip under the map count, hover on buttons and nav items.
- **Quiet Fill** (#eef0f3): neutral chip fill, row hover in lists, callout blocks, KPI-strip separators, icon wells.
- **Hairline** (#e4e7eb): the border on containers (cards, panels, dialogs, rows, dividers).
- **Control Edge** (#cfd4da): the border on controls (buttons, fields, selects, map controls, segmented control) and on the surfaces that float on the map (the canvas frame, its count panel, the issue panel's edge).
- **Ink** (#111827): headings, values and primary text.
- **Slate Ink** (#374151): secondary text, select labels, table cells.
- **Muted Slate** (#545b67): body paragraphs, meta lines, placeholders, captions, idle nav labels and icons.
- **Icon Grey** (#6b7280): the quietest step. It reaches 4.83:1 on white and 4.59:1 on Faint Mist but only 4.47:1 on the ground and 4.23:1 on Quiet Fill, so the build uses it for icons; text in it stays on white.

### Status
Each status hue comes as a set: a fill for marks, a soft wash, an edge and a text tone. The text tone is the only one used for words.
- **Alert Red** (#dc2626, wash #fef2f2, edge #fcc9c9, ink #b91c1c): high severity, errors, the "!" severity badge.
- **Caution Amber** (#d97706, wash #fffbeb, edge #fce4a6, ink #a8520a): in review, pending correction, Street View person.
- **Crew Green** (#059669, wash #ecfdf5, edge #a7f0cf, ink #047857): verified and resolved, crew routes, success feedback.
- **Asset Violet** (#7c3aed, wash #f5f3ff, edge #ddd5fe, ink #6d28d9): infrastructure assets (schools, transit, roads) on the map.
- **On-colour inks**: white (#ffffff) on Civic Blue and on Alert Red in light; Ink (#111827) on the green route-stop numbers in both themes.
- **Scrim** (rgb(17 24 39 / .45)): behind dialogs.

### Map categories
Pins take a fixed colour per category from `src/data.js`; the same values serve both themes. Pothole (#dc2626), Sidewalk damage (#d97706), Graffiti (#7c3aed), Litter (#059669), Flooding (#2563eb), Other (#6b7280). Each pin carries its category icon as well, so the colour is never the only cue.

### Dark theme
Dark swaps every token above for a neutral graphite counterpart (the `dark-` keys in the frontmatter): ground #0e0f11, surfaces #17181b / #1d1e22 / #25262b, hairline #2b2d33, control edge #3c3f46, ink #ececef. Civic Blue keeps its fill (#2563eb) while text-level blue lifts to #82aaff; status hues brighten and their washes darken. The basemap is inverted to grey. On-red text turns dark (#1a0b0c).

### Contrast
`tests/theme.test.mjs` checks both palettes. It requires the same token names in light and dark, and 4.5:1 for text, text-2, text-3 and the five coloured text tones on the ground, Paper White and Faint Mist; text-3 on Quiet Fill; white on Civic Blue and Pressed Blue; on-danger on Alert Red; and each status text on its own wash. Every token pair it checks passes in both themes. Icon Grey is not part of the test.

### Named Rules
**The One Blue Rule.** Civic Blue (accent, accent-text) is only for actions, selection, links and status chips. Plain text uses the neutral ink ladder: text, text-2, text-3 and text-4.

**The Neutral Line Rule.** Containers take the hairline (border), controls take the control edge (border-strong). An accent border appears only on an active or selected state.

**The White-on-Grey Rule.** Cards, dialogs, inputs and filters are white (surface) on the grey ground (bg). Faint Mist and Quiet Fill are tone steps inside them: headers, zebra rows, legends, callouts.

**The Graphite Night Rule.** Dark is neutral graphite with no navy and no glow. Blue fills stay put; only text-level blue lifts.

**The Data Owns Colour Rule.** Saturated colour belongs to the data: category pins, status chips, the density ramp. Chrome stays neutral.

## Typography

**Display Font:** Inter (with system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif)
**Body Font:** Inter (same stack)

**Character:** One sturdy, neutral grotesque doing every job, from the wordmark down to table cells; hierarchy comes from size, weight and the ink ladder. Inter's alternate single-storey a and open digits are on globally (`font-feature-settings: 'cv11', 'ss01'`), synthesis is off, and coordinates and distances use tabular figures.

### Hierarchy
- **Brand** (700, 27px, -1.1px): the sidebar wordmark, "Civic" in Ink and "Lens" in Civic Blue. The splash sets it at 36px.
- **Headline** (700, 22px, -.5px): page titles (Data Explorer, Dashboard, workspace pages). The Map Explorer title steps down to 17px so the map keeps the room; dialog titles use 22px at 650 (-.6px), 20px on phones.
- **Stat** (700, 24px, 1.25, -1px): KPI numbers in the dashboard strip; 28px at 1600px and wider, 21px on phones.
- **Title** (650, 17px, -.3px): section headings. The issue detail title runs at 20px and the panel heading at 16px. Dashboard card headers are quieter: 12px at 500 beside an 18px Icon Grey icon (15px at 1600px and wider).
- **Subtitle** (650, 15px): subsection and card-level headings.
- **Body** (400, 13px, 1.65): paragraphs in Muted Slate.
- **Control** (500, 13px; 12px at 650px and below): buttons, selects, the search field, segmented control, legend, map count, list row titles.
- **Label** (550, 12px): the meta line under a heading, sidebar labels (section labels at 600), badges (at 400).

Google Fonts loads Inter at 400, 500, 600 and 700, so the declared 550 and 650 resolve to the 600 and 700 faces.

### Named Rules
**The One Face Rule.** Inter is the single typeface, pinned by the user. Never add a display or mono family.

**The Twelve-Pixel Floor Rule.** Controls read at 13px (12px on phones). Nothing a reader must read sits below 12px.

**The Heading-First Rule.** A heading comes first; its ID, type or date goes underneath as a 12px meta line in Muted Slate, 4px below. Never a kicker above it.

## Layout

The app shell is fixed: a white sidebar on the left, a one-row page header, and the content on the grey ground. The sidebar is 232px wide (250px at 1600px and wider, 205px at 1200px and narrower), becomes a 76px icon rail at 950px, and turns into a 58px bottom tab bar at 650px with a round upload button. The main area pads 28px (33px top and 35px sides at 1600px and wider, 24px top and 20px sides at 1200px and narrower, 12px sides on phones).

The Map Explorer gives the map everything below a compact 17px title. The map sits in a framed canvas (Control Edge border, 11px corners) and every control floats on it, inset 15px: search and filters across the top; the Pins/Density segment and the crew-route button below them on the left; map tools on the right; the live count and category legend sharing one panel bottom-left; Street View, zoom, fit and home bottom-right. Selecting an issue docks the white issue panel at the right edge (360px, 390px at 1600px) and the floating controls slide clear of it. On phones the panel becomes a bottom sheet over 58% of the height.

Filters sit in one row. Selects size to their label (`field-sizing: content`) and the search field takes the rest (it grows from 220px). On the map at 1360px and narrower, search takes its own row and the filters sit under it. When the map is narrow the filter row never wraps or clips: it scrolls sideways with a hidden scrollbar.

Data pages use white cards in grids with 16px to 18px gaps (20px at 1600px); the dashboard's KPIs form one bordered strip split by 1px tone steps. There is no spacing scale in tokens: panels pad 18px, dialogs 24px, control groups gap 6px to 12px. Breakpoints are 420px, 650px, 950px, 1200px, 1360px and 1600px.

### Named Rules
**The Sideways Filter Rule.** Selects size to their label. When the map is narrow its filter row scrolls sideways; labels are never clipped.

**The Clear Map Rule.** Map controls hug the canvas edges and slide aside when the issue panel opens, so the panel never covers a control.

## Elevation & Depth

The system is flat and tonal: white surfaces on a grey ground, separated by hairlines. One soft shadow lifts things that float or can be pressed: buttons, map controls, filter fields, the segmented control, the issue panel, dialogs, search suggestions, the hover preview and the sticky table header. Cards at rest have no shadow, and neither does the map's count and legend panel. Dialogs sit over a scrim, the photo viewer over near-black, and nothing uses backdrop blur. `--shadow-md`, `--shadow-lg` and `--focus-ring` exist in both palettes but nothing uses them.

### Shadow Vocabulary
- **Soft lift, light** (`box-shadow: 0 1px 2px rgb(16 24 40 / .06), 0 1px 3px rgb(16 24 40 / .08)`): the one elevation in light.
- **Soft lift, dark** (`box-shadow: 0 1px 2px rgb(0 0 0 / .4)`): the same role in dark.
- **Pin shadow** (`filter: drop-shadow(0 1px 1.5px rgb(16 24 40 / .35))`, hover `drop-shadow(0 2px 3px rgb(16 24 40 / .45))`): follows the teardrop's outline.
- **Focus** (`outline: 2px solid` Civic Blue, `outline-offset: 3px`): buttons and links. Fields show a Civic Blue border plus the soft lift instead.

### Named Rules
**The One Shadow Rule.** One soft shadow lifts whatever floats. No glows, no blur, no stacked elevations.

## Shapes

Corners are gently rounded and step up with the size of the thing: 4px for small chips, segments and keyboard hints; 5px for badges and filter chips; 6px for map tools and dialog fields; 7px for buttons, filters, nav items and the segmented control; 8px for the map's count panel, callouts, evidence photos and the toast; 10px for cards; 11px for the map canvas; 13px for dialogs (10px on phones); 20px pills for the data switch, priority and confidence. Circles mark clusters, avatars, stat icons and the severity badge.

The signature shape is the map pin: a teardrop (a square with three round corners, turned 45 degrees) whose tip sits exactly on the location. Dashed outlines mean "approximate" or "drop here": the location-uncertainty circle, the upload zone, blur boxes and the photo placeholder. Icons are inline 24×24 line icons with a 1.65 stroke and round caps, drawn mostly at 14px to 21px.

## Components

### Buttons
Plain, solid and quiet.
- **Shape:** gently rounded (7px).
- **Default:** Paper White with a Control Edge border, Ink text at 13px/500, the soft lift, 11px 15px padding, a 17px icon 8px from the label.
- **Primary:** Civic Blue fill and border with white text (5.17:1); hover Pressed Blue. Used for the main action of a region, such as the sidebar's "Upload new issue" or a panel footer's first action.
- **Hover / Focus:** hover steps to Faint Mist; press scales to .96; transitions run 180ms. Focus shows a 2px Civic Blue outline 3px out.
- **Small / icon-only / ghost:** small is 8px 12px at 12px; icon-only is 9px square padding around an 18px icon; the ghost icon button is a 32px square in Muted Slate that fills with Quiet Fill on hover. Text buttons are Link Blue with no fill.
- **Crew route:** "Plan crew route" is a default button with a Crew Green route icon.

### Chips and badges
- **Badge:** 5px corners, 12px text, 5px 8px padding, 1px edge. Neutral by default (Quiet Fill, Control Edge, Slate Ink). High severity: Alert wash, edge and ink. Open and low priority: Selection Wash, Selection Edge, Link Blue. In review: Quiet Fill with Caution ink. Verified and resolved: Quiet Fill, green edge, Crew Green ink.
- **Filter chip:** an applied filter. Selection Wash with a Control Edge border and Link Blue text; the border turns Civic Blue on hover; a 10px close icon removes it.
- **Pills:** the data switch, priority and confidence pills use 20px corners.

### Cards / Containers
- **Corner Style:** 10px.
- **Background:** Paper White on the grey ground.
- **Shadow Strategy:** none at rest (see Elevation & Depth); saved cards lift 3px with the soft shadow on hover.
- **Border:** 1px Hairline.
- **Internal Padding:** headers 18px 18px 16px; content 18px.
- **Tables:** live in a white records card. The header row is Faint Mist, rows are 47px with zebra striping in Faint Mist, hover and selection use Selection Wash, and a sorted column header turns Selection Wash with Link Blue text.
- **Callouts:** inside a panel, a location note, why-flagged or geolocation block is a flat tinted block (Quiet Fill or Faint Mist, Hairline edge, 7px to 8px corners), never a second white card.

### Inputs / Fields
- **Style:** Paper White, 1px Control Edge, 7px corners, 32px tall (34px for search over the map), 13px text, Muted Slate placeholder and icon. Selects are borderless inside their white shell and size to their current label.
- **Focus:** the border turns Civic Blue with the soft lift; the search icon turns Link Blue.
- **Dialog fields:** Paper White, Control Edge, 6px corners, 11px padding. Choice tiles (correction kinds) turn Selection Wash with a Civic Blue edge when checked.
- **Error:** Alert ink under the field. Valid location feedback is Crew Green ink.

### Navigation
- **Sidebar:** white with a Hairline right edge. The lens mark and wordmark, a 12px workspace label, then 45px nav items (13px/500 Muted Slate, 20px icons, 7px corners). Hover is Faint Mist with Ink text; the active item is Selection Wash with Link Blue text. The primary upload button sits under the nav and the account under a hairline at the bottom.
- **Phones:** a 58px bottom tab bar; the active tab is marked by a 2px Civic Blue bar along its top edge.
- **Segmented control:** a white track with a Control Edge and 3px inner padding; the active segment is Selection Wash with Link Blue text (4px corners).
- **Tabs:** the active table tab carries a 2px Civic Blue underline and Link Blue text.

### Map pins and clusters
The signature component.
- **Pin:** a 22px teardrop head in the category colour with a 2px white rim and a white 14px category icon (2.2 stroke), tip on the location, the pin shadow beneath. Selected pins scale to 1.25. Pins counter-scale with the camera so they hold their size while zooming.
- **Cluster:** a 34px Civic Blue circle with a 2px white rim and a white 13px/600 count. A selected cluster turns Pressed Blue.
- **High severity:** a 14px Alert Red "!" badge with a white rim at the pin's top-right.
- **Basemap:** OpenStreetMap tiles under `--tile-filter`: grayscale(.6) brightness(1.04) contrast(.92) in light, inverted to grey (brightness .78) in dark.
- **Uncertainty:** a dashed 1.5px Civic Blue circle with an 8% blue fill shows how far off an unverified pin may be.

**The Teardrop Rule.** An issue is a teardrop pin in its category colour with a white rim; a group of issues is a Civic Blue numbered circle. Severity is marked with the "!" badge, never by colour alone.

**The Muted Basemap Rule.** The basemap stays desaturated so the pins carry the colour.

### Map overlays
- **Floating controls:** white, Control Edge, the soft lift. Map tools are 37px with 6px corners, and the active tool is Selection Wash with a Civic Blue edge. The zoom stack shares one border with a divider between buttons.
- **Count and legend panel:** one 8px panel. The live count sits on Paper White; the legend strip below it is Faint Mist, with each category's coloured icon and its name in Slate Ink. The active legend item is Selection Wash with Link Blue at 600.
- **Density:** a heat surface replaces the pins. Its ramp runs transparent blue, then rgba(37,99,235,.32) at 12%, rgba(37,99,235,.55) at 35%, amber rgba(217,119,6,.72) at 60%, red rgba(220,38,38,.82) at 85% and rgba(185,28,28,.9) at the peak; the legend shows it as a 140px bar.
- **Wards:** Civic Blue outlines at 45% opacity, 1.2px, with a 5% fill; the active ward is 2.2px at 95% with a 12% fill. Ward labels are white pills (12px corners, Hairline edge) that turn Selection Wash with a Civic Blue edge when active.
- **Crew routes:** a 3.5px Crew Green dashed line (12 on, 9 off) flowing over an 8px hairline casing; stops are green numbered circles with Ink numerals.
- **Motion:** state changes run 150ms to 180ms; controls slide aside over 240ms on cubic-bezier(.2,.8,.2,1) when the panel opens; reduced motion removes every transition and animation.

### Issue panel and dialogs
- **Issue panel:** white, docked to the map's right edge with a Control Edge border and the soft lift. An 18px heading row over a hairline, a scrolling body, and a footer that keeps its actions on one row. On phones it becomes a bottom sheet with 13px top corners and a 32 × 3px grab handle.
- **Dialog:** white, 540px wide, 13px corners, Hairline border, the soft lift over the scrim. Heading, body and footer pad 24px across and are divided by rules; it enters with a 9px rise over 150ms.
- **Toast:** white, Hairline, 8px corners, 12px text, the soft lift, centred at the bottom.

### Loading mark
The lens draws itself: the inner ring strokes in over .65s, the blue core pops in, six category dots blink in around it like pins being found, and the wordmark rises in before the screen fades once the map is ready. Under reduced motion it shows the finished mark.

## Do's and Don'ts

### Do:
- **Do** keep Civic Blue (accent, accent-text) for actions, selection, links and status chips, and set plain text in text, text-2, text-3 and text-4.
- **Do** border containers with the hairline (border) and controls with the control edge (border-strong); use an accent border only on an active or selected state.
- **Do** make cards, dialogs, inputs and filters white (surface) on the grey ground (bg).
- **Do** set controls at 13px (12px at 650px and below) and keep anything a reader must read at 12px or larger.
- **Do** put the heading first and its ID, type or date underneath as a 12px meta line in text-3.
- **Do** draw issues as category-coloured teardrop pins with a white rim, clusters as Civic Blue numbered circles, and mark high severity with the "!" badge.
- **Do** let selects size to their label (`field-sizing: content`) and let the map's filter row scroll sideways when it is narrow.
- **Do** lift floating controls, panels and dialogs with the one soft shadow (--shadow-sm) and keep the basemap muted with --tile-filter.
- **Do** add every new colour token to both palettes and keep tests/theme.test.mjs passing at 4.5:1 for each text pair in both themes.
- **Do** keep light as the default theme and make dark neutral graphite.

### Don't:
- **Don't** use blue for headings, body copy or labels that are not links, selections or status chips.
- **Don't** put coloured side-accent stripes on cards, rows, callouts or alerts.
- **Don't** use glows, neon halos, backdrop blur, gradient text or decorative gradient sheen; the density ramp is a data encoding, not decoration.
- **Don't** nest a card inside a card.
- **Don't** put a kicker or eyebrow above a heading.
- **Don't** add a second typeface; Inter is pinned.
- **Don't** tint the dark theme navy or let anything glow in it.
- **Don't** let colour alone carry severity or status.
- **Don't** clip or wrap the map's filter labels; scroll the row instead.
