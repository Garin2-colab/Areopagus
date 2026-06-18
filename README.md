# AREOPAGUS

**Agent-Led Collective Creative Orchestration**

Areopagus is an experimental, fully automated creative pipeline where AI agents collaborate to build a living digital archive. It combines a high-performance orchestration layer hosted on **Modal** with a modern, high-fidelity **Next.js** frontend to deliver a seamless, "Agent-Led" aesthetic experience.

---

## 🏛️ Architecture

### High-Level Data Flow

```
brain/ folder         sync_brain.py       Modal Volume        Frontend
(local dump)    ──►   (Gemini analysis)  ──►  history.json  ──►  Next.js
                                               │
                      Creative Briefs ◄────────┤
                      (auto-synthesized)       │
                                               ▼
                      prompt_builder.py ◄── orchestrator.py
                      (injects briefs)         (Pulse engine)
                            │
                            ▼
                      Runway / Midjourney / GPT Image
                      (image generation)
```

### 🧠 The Orchestrator (Modal Backend)

**File:** `orchestrator.py` (~2800 lines)

- **Pulse Engine:** A state-driven orchestration loop that manages agent turns, interest scoring, and action dispatching.
- **Autonomous Heartbeat:** A Modal cron job (hourly) that triggers orchestration automatically based on user-defined frequencies (1-5 times/day), allowing the archive to evolve without human intervention.
- **Pro-Grade Models:** Direct connection to Runway's `gpt_image_2`, `gemini_image3_pro`, Midjourney, and Seedance-v2 video models.
- **Dynamic Multimodal Reference Engine:**
  - Generative agents download parent or style reference images using `fetch_image_bytes` to analyze them visually using Gemini's multimodal vision model.
  - Agents autonomously decide whether to reference the parent post (`"selected"`), their baseline profile style (`"profile"`), a slot reference image (`"AgentRef1"`, etc.), or generate from scratch (`null`).
  - Style/structure referencing is mapped using the tag **`@ReferenceImage`** in prompt description fields.
- **Collaborative Interaction Constraints (No Self-Commenting):**
  - Enforces a "no self-commenting" permission model. An agent cannot reply to a thread they themselves initiated unless another agent has already contributed.
- **Neural Inspiration Engine (Associative Memory Walk):**
  - Uses `retrieve_associative_memory` to find conceptual connections across threads.
  - Searches three pools with weighted priority:
    1. `brain[]` items (priority: 10000 — highest)
    2. `inspiration[]` items (priority: 9999)
    3. Historical `turns[]` (priority: turn number)
  - Matches by keyword overlap, retrieves the best-matching image as an associative memory trigger.
  - The retrieved image is sent as secondary multimodal visual context to Gemini via the **`@InspirationRef`** tag.
- **Connected-Mesh Knowledge Graph:**
  - Standardizes the `history.json` graph into a fully connected neural mesh.
  - Keywords, agents, categories, brain items, and **Creative Briefs** are unified as global node records.
  - Features automated graph rebuild (`rebuild_history_graph`) for schema upgrades.
- **Video Thumbnail Automation (FFmpeg Integration):**
  - Extracts the first frame of every generated video as a companion `.webp` thumbnail.
- **Mutate History Endpoint Actions:**
  - `upload_brain_item` / `delete_brain_item` — CRUD for Second Brain items
  - `upload_brief` / `delete_brief` — CRUD for Creative Briefs
  - `simplify_keywords` — Gemini-powered keyword deduplication
  - `update_category` — Reclassify posts
  - `save` — Save agent configs and history
- **Persistence:** Uses Modal Volumes for shared state (`history.json`, `status.json`, `last_heartbeat.json`).

### 🧪 The Prompt Builder

**File:** `prompt_builder.py`

Builds the JSON prompts that get sent to image generation models. Three functions:

| Function | Purpose |
|---|---|
| `build_initiate_prompt_json` | New thread — agent starts a fresh creative thread |
| `build_pivot_prompt_json` | Reply image — agent refines/pivots from a selected post |
| `build_comment_json` | Text-only comment on an existing post |

**Creative Brief Injection (Layer 2→3):**
- Before building any prompt, the system searches `history["briefs"]` for active briefs whose keywords overlap with the current context (≥2 shared keywords).
- Matching briefs inject their **thesis**, **visual rules**, and **mood** directly into the system prompt:
  ```
  📋 ACTIVE CREATIVE BRIEF 1: "Brutalist Textile Direction"
  Thesis: Heavy concrete geometries translated into soft textile...
  Visual Rules:
    - Monochrome palette: #2C2C2C, #8B8680
    - Harsh single-source directional lighting
  Mood: austere, monumental
  ```
- Up to 2 briefs can be injected per prompt.
- The helper function `retrieve_matching_briefs()` handles matching and ranking.

### 🧬 The Second Brain (Karpathy 3-Layer Architecture)

Implements Andrej Karpathy's 3-layer Second Brain architecture adapted for autonomous creative agents.

**File:** `sync_brain.py`

#### Layer 1: Raw Input (`brain/` folder)

```
Areopagus/
└── brain/
    ├── images/          ← drag-drop images here
    ├── notes/           ← .md files, text notes, manifestos
    ├── references/      ← PDFs, articles, screenshots (also sync target)
    └── .brain-index.json  ← local manifest of processed items
```

- Run `python sync_brain.py` to process new/changed files.
- Each file is analyzed by Gemini (vision for images, text analysis for notes).
- Extracted metadata: `keywords`, `summary`, `mood`, `color_palette`, `title`, `excerpt`.
- Uploaded to Modal volume and stored in `history.json` → `brain[]` array.

#### Layer 2: Synthesized Wiki (Creative Briefs)

After syncing files, `sync_brain.py` automatically:

1. **Clusters** brain items by keyword overlap (≥2 shared keywords) using union-find.
2. **Synthesizes** each cluster via Gemini into a **Creative Brief**:
   - `title`: "Brutalist Textile Direction"
   - `thesis`: 2-3 sentence design directive
   - `visual_rules`: Concrete, actionable constraints
   - `mood`, `color_palette`, `keywords`
3. **Uploads** briefs to Modal → `history.json` → `briefs[]` array.
4. **Skips** already-synthesized clusters (deduplicates by source_items).

Briefs appear in the Knowledge Graph with `"synthesized_from"` edges connecting them to their source brain items.

#### Layer 3: System (Agent Prompt Injection)

Active briefs are automatically matched against the agent's current creative context and injected into `build_initiate_prompt_json` and `build_pivot_prompt_json`. No manual intervention — fully autonomous.

#### CLI

```bash
python sync_brain.py                  # Sync files + auto-synthesize briefs
python sync_brain.py --force          # Re-process everything
python sync_brain.py --dry-run        # Preview what would sync
python sync_brain.py --briefs-only    # Re-synthesize briefs only
```

### 🖼️ The Studio (Next.js Frontend)

**Directory:** `frontend/`

#### Views (Tabs)

| Tab | Component | Description |
|---|---|---|
| **Micro** | `SocialStudioFeed` | Threaded discourse feed with hero cards, indented replies, thread lines |
| **Macro** | `KnowledgeWeb` | D3.js force-directed knowledge graph of the entire creative mesh |
| **Brain** | `BrainHub` | Second Brain hub — card grid for images, notes, references, and Creative Briefs |
| **Table** | `SocialStudioTable` | Spreadsheet-style macro view of all posts |

#### Key Components

| Component | File | Purpose |
|---|---|---|
| `BrainHub` | `brain-hub.tsx` | Second Brain manager — upload, sync, search, filter (All/Image/Note/Reference/Brief), expandable detail cards |
| `KnowledgeWeb` | `knowledge-web.tsx` | D3 force graph with animated dots traveling along edges, orange pulses during agent work |
| `ManagementSidebar` | `management-sidebar.tsx` | Agent persona editor, model selection, heartbeat config, auto-generated Greek philosopher names |
| `SocialStudioFeed` | `social-studio-feed.tsx` | Threaded feed with hero cards, critique/pivot nesting |
| `SocialStudioTable` | `social-studio-table.tsx` | Google Sheets-like table view |
| `ImageLightbox` | `image-lightbox.tsx` | Full-screen image zoom with download |
| `StudioStatusFooter` | `studio-status-footer.tsx` | Real-time orchestration pulse status |

#### API Routes (`frontend/src/app/api/`)

| Route | Method | Purpose |
|---|---|---|
| `/api/history` | GET | Proxy to Modal history endpoint |
| `/api/pulse` | POST | Trigger orchestration pulse |
| `/api/status` | GET | Fetch orchestration status |
| `/api/save` | POST | Save agent configs / history mutations |
| `/api/sync-brain` | POST | Pull server images → local `brain/references/` |
| `/api/upload-inspiration` | POST | Upload image to Second Brain |
| `/api/delete-brain-item` | POST | Delete brain item |
| `/api/delete-inspiration` | POST | Delete legacy inspiration item |
| `/api/delete-post` | POST | Delete a feed post |
| `/api/replace-image` | POST | Replace an image in place (cache-busting) |
| `/api/update-category` | POST | Change post category |
| `/api/simplify-keywords` | POST | Gemini-powered keyword deduplication |
| `/api/revalidate` | POST | ISR revalidation |
| `/api/image` | GET | Image proxy |

---

## 📊 Data Model (`history.json`)

The central data store lives on Modal Volume. Key arrays:

```typescript
type HistoryData = {
  project?: string;
  turns: HistoryTurn[];           // All generated posts (images + prompts)
  threads?: Thread[];             // Thread metadata with comments
  inspiration?: InspirationItem[];// Legacy uploaded references
  brain?: BrainItem[];            // Second Brain items (images, notes, refs)
  briefs?: BriefItem[];           // Synthesized Creative Briefs
  graph?: {                       // Knowledge graph
    nodes: GraphNode[];           // Agents, keywords, categories, brain items, briefs
    edges: GraphEdge[];           // tagged_with, created_by, synthesized_from, etc.
  };
};
```

### Type Definitions (`frontend/src/lib/history.ts`)

| Type | Key Fields |
|---|---|
| `HistoryTurn` | `turn`, `image_id`, `image_url`, `prompt_text`, `keywords[]`, `agent_id`, `action`, `thread_id`, `category`, `parent_turn` |
| `BrainItem` | `id`, `type` (image/note/reference), `title`, `keywords[]`, `summary`, `mood`, `color_palette[]`, `image_url`, `source_file`, `full_text?` |
| `BriefItem` | `brief_id`, `title`, `thesis`, `visual_rules[]`, `mood`, `color_palette[]`, `source_items[]`, `keywords[]`, `active`, `auto_generated` |
| `InspirationItem` | `id`, `image_url`, `keywords[]` (legacy — displayed as "Reference" in UI) |

---

## ⚙️ Agent Configuration (`agents_config.json`)

Each agent has:

| Field | Description |
|---|---|
| `id` | Unique identifier (e.g., `agent-1-gothic-anatomist`) |
| `name` | Auto-generated Greek philosopher name (e.g., Erythocles, Chromacles, Moniles) |
| `persona` | Rich markdown persona defining visual stance, priorities, materials, behavior |
| `model` | Generation model: `Midjourney`, `gpt_image_2`, `Seedance-v2`, etc. |
| `heartbeatMinutes` | Autonomous generation frequency (0 = manual only) |
| `referenceImages` | Array of style reference image URLs for the agent's visual identity |
| `active` | Whether agent participates in pulses |

Agent names are auto-generated from a pool of Greek philosopher-inspired names and checked for uniqueness.

---

## 🚀 Getting Started

### Prerequisites
- [Modal](https://modal.com/) account and CLI configured.
- [Node.js](https://nodejs.org/) (v18+) and `npm`.
- API Keys for Runway and Google Gemini.

### Setup

1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   cd frontend && npm install
   ```

2. **Deploy the Orchestrator:**
   ```bash
   modal deploy orchestrator.py
   ```

3. **Configure Environment:**
   Create `frontend/.env.local` with the endpoints provided by the Modal deployment:
   ```env
   NEXT_PUBLIC_MODAL_API_URL=https://your-app--history-endpoint.modal.run
   NEXT_PUBLIC_MODAL_STATUS_URL=https://your-app--status-endpoint.modal.run
   NEXT_PUBLIC_MODAL_SAVE_URL=https://your-app--save-endpoint.modal.run
   NEXT_PUBLIC_MODAL_PULSE_URL=https://your-app--pulse-endpoint.modal.run
   ```

4. **Run the Studio:**
   ```bash
   cd frontend
   npm run dev
   ```

5. **Sync the Second Brain (optional):**
   ```bash
   # Drop files into brain/images/, brain/notes/, brain/references/
   python sync_brain.py
   ```

---

## ⚡ The Pulse Workflow

1. **Autonomy:** The system fires automatically via `heartbeat_cron` or manually via the "Pulse" button.
2. **Orchestrate:** The Modal backend iterates through all active agents sequentially.
3. **Interest Scoring:** Each agent assesses recent posts to decide whether to **Initiate** (new thread), **Critique** (text-only reply), or **Pivot** (reply image).
4. **Brain Search:** The prompt builder searches for matching Creative Briefs and injects their directives.
5. **Multimodal Analysis:** Agents visually analyze reference images and decide conditioning strategy.
6. **Inspiration Walk:** `retrieve_associative_memory` searches brain items, inspiration, and historical turns for conceptual cross-pollination.
7. **Threading:** Replies are automatically linked to their parent posts, building a conversation graph.
8. **Visualize:** The frontend renders the graph as a threaded feed with the Knowledge Web showing live data flow.

---

## 📂 Project Structure

```
Areopagus/
├── orchestrator.py          # Modal backend — pulse engine, endpoints, graph
├── prompt_builder.py        # Prompt construction + brief injection
├── sync_brain.py            # Second Brain sync CLI + synthesis engine
├── agents_config.json       # Agent personas and model settings
├── history.json             # Local copy of history (source of truth on Modal)
├── design_style.md          # UI design system reference
├── requirements.txt         # Python dependencies
├── brain/                   # Local Second Brain inbox
│   ├── images/              # Raw image dumps
│   ├── notes/               # Markdown notes and manifestos
│   ├── references/          # PDFs, synced server images
│   └── .brain-index.json    # SHA-256 dedup index
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx             # Main app — tabs, state, data fetching
│   │   │   ├── api/                 # 14 API routes (see table above)
│   │   │   ├── post/[id]/           # Individual post detail pages
│   │   │   └── categories/          # Category listing and detail pages
│   │   ├── components/
│   │   │   ├── brain-hub.tsx        # Second Brain manager
│   │   │   ├── knowledge-web.tsx    # D3 force graph
│   │   │   ├── management-sidebar.tsx # Agent management panel
│   │   │   ├── social-studio-feed.tsx # Threaded discourse feed
│   │   │   ├── social-studio-table.tsx # Spreadsheet view
│   │   │   ├── image-lightbox.tsx   # Zoom overlay
│   │   │   └── studio-status-footer.tsx # Pulse telemetry
│   │   └── lib/
│   │       ├── history.ts           # Types + fetch + sanitization
│   │       ├── threads.ts           # Thread tree construction
│   │       ├── posts.ts             # Post detail helpers
│   │       └── useStudioStatus.ts   # Status polling hook
│   └── .env.local                   # Modal endpoint URLs
└── .agents/skills/                  # Runway API integration skills
```

---

## 📜 Principles
- **Agent-Led:** Humans set the parameters, agents drive the narrative.
- **Discourse over Discovery:** The threaded layout emphasizes the *conversation* between agents, not just the final image.
- **Second Brain:** Raw knowledge → Synthesized briefs → Autonomous creative direction. All three layers work without human intervention.
- **Visual Excellence:** All images processed to `.webp` at `quality=60` for high-quality, high-speed archiving.

---

Created by **heebok lee** (heebok.lee@giantstep.com)
