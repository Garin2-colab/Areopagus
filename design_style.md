# Areopagus Design Style

## UI System
- **Framework:** Next.js 16 + React
- **Styling:** Tailwind CSS with a warm, off-white palette
- **Typography:** System font stack with `font-display` for headers (serif/display weight)

## Color Palette
- **Background:** `#F5F2EB` (warm off-white) — main page
- **Surface:** `#FAF9F6` — cards, panels, sidebar
- **Border:** `#D8D4CC` at 60% opacity — subtle dividers
- **Text Primary:** `#252422` — near-black warm tone
- **Text Secondary:** `#44423E` — medium gray
- **Text Muted:** `#858076` — light gray for metadata
- **Accent:** `#D45113` — Areopagus orange (brand color, buttons, highlights, agent accents)
- **Accent Light:** `#D45113/8` — keyword badges, subtle highlights

## Layout Architecture
- **Page:** `max-w-[1600px]` centered, `px-6 pt-8`
- **Grid:** 12-column responsive — `lg:col-span-9` for main content, `lg:col-span-3` for sidebar
- **Cards:** `rounded-2xl` with `border border-[#D8D4CC]/60`, `shadow-sm shadow-[#252422]/5`
- **Panels:** `rounded-[2rem]` for sidebar and major containers

## Tabs
- **Primary Navigation:** Micro | Macro | Brain | Table (top-center, pill-style)
- **Brain Tab replaces the former "Inspiration" tab**
- Filter tabs inside panels: `rounded-lg`, uppercase `text-[10px]`, `tracking-wider`

## Component Patterns
- **Icons:** Lucide React (`h-5 w-5` header, `h-3.5 w-3.5` inline, `h-3 w-3` micro)
- **Buttons:** Outlined style (`border border-[#D8D4CC]`) for secondary actions, solid `bg-[#D45113]` for primary
- **Badges:** `rounded-full bg-[#D45113]/8 px-1.5 py-0.5 text-[9px] font-semibold text-[#D45113]`
- **Expanded cards:** `col-span-2 row-span-2` with `border-[#D45113]/40 shadow-md shadow-[#D45113]/10`
- **Animations:** `animate-in fade-in slide-in-from-top-2 duration-200` for expanding sections

## Philosophy
- **Minimal, warm, premium:** Off-white surfaces with warm orange accents. No cold blues.
- **Information density over decoration:** Small type sizes (9px–12px), tight spacing, maximum data per viewport.
- **Agent-first identity:** Agent names are Greek philosopher names (auto-generated). No "Agent 1", "Agent 2" labels.
- **No placeholder text.** Every element serves a purpose.
- **Animations are subtle:** 200ms transitions, opacity-based reveals, no bouncing or sliding.

## Knowledge Web (D3 Graph)
- **Background:** Dark (`#1a1a1a`) with force-directed layout
- **Dots:** 25% opacity particles traveling along edges at constant speed, random start times
- **Active lines:** Turn orange when agents are working, dots inherit line color
- **Node types:** keyword (small), agent (medium), category (medium), brain/brief (small, distinct color)