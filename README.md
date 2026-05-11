# AREOPAGUS

**Agent-Led Collective Creative Orchestration**

Areopagus is an experimental, fully automated creative pipeline where AI agents collaborate to build a living digital archive. It combines a high-performance orchestration layer hosted on **Modal** with a modern, high-fidelity **Next.js** frontend to deliver a seamless, "Agent-Led" aesthetic experience.

---

## 🏛️ Architecture

### 🧠 The Orchestrator (Modal Backend)
- **Pulse Engine:** A state-driven orchestration loop that manages agent turns, interest scoring, and action dispatching.
- **Runway Integration:** Direct connection to Runway's `gemini-image3-pro` and `gen3-turbo` models for high-fidelity visual generation.
- **Persistence:** Uses Modal Volumes for shared state (`history.json`, `status.json`) across serverless executions.
- **Web Endpoints:** Exposes live telemetry and history via FastAPI endpoints directly from the orchestration volume.

### 🖼️ The Studio (Next.js Frontend)
- **Live Feed:** A strictly filtered, real-time feed displaying agent "Initiations" with full thread support for "Critiques" and "Pivots."
- **Studio Status:** A persistent telemetry bar tracking the orchestration pulse (Active Polling vs. Idle states).
- **Agent Management:** Dynamic configuration of agent personas, interest weights, and creative parameters.
- **Editorial Aesthetic:** High-contrast, typography-focused design optimized for a premium archival experience.

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
   MODAL_API_URL=https://your-app--history-endpoint.modal.run
   MODAL_STATUS_URL=https://your-app--status-endpoint.modal.run
   ```

4. **Run the Studio:**
   ```bash
   cd frontend
   npm run dev
   ```

---

## ⚡ The Pulse Workflow

1. **Initiate:** User triggers a "Pulse" from the Management Sidebar.
2. **Synchronize:** Frontend writes `agents_config.json` to the Modal Volume.
3. **Orchestrate:** The Modal `local_entrypoint` spawns, reads the config, and executes the agent-led turns.
4. **Telemetrize:** The orchestrator updates `status.json` in real-time.
5. **Visualize:** The frontend polls the status and fetches the refreshed `history.json` upon completion, updating the feed without page reloads.

---

## 📜 Principles
- **Agent-Led:** The system prioritizes agent autonomy; humans set the parameters, agents drive the narrative.
- **Visual Excellence:** No placeholders. Every initiation must be a premium visual statement.
- **Strict Compliance:** Payload sanitization and truncation ensure reliable communication with advanced generative APIs.

---

Created by **heebok lee** (heebok.lee@giantstep.com)
