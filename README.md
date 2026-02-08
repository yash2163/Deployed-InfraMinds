# 🧠 InfraMinds: The AI-Powered Cloud Architect

**InfraMinds** is an autonomous infrastructure agent that transforms natural language intent into a "Living State Graph" of cloud architecture. Unlike standard "Text-to-Code" tools, InfraMinds uses **Gemini 3's reasoning** to visualize, simulate, and verify infrastructure changes before a single line of Terraform is deployed.

It transforms the "Black Box" of AI coding into a transparent, interactive **"Glass Box"** where you can see the blast radius of every decision.

---

## ✨ Key Features

### 1. 🗣️ Intent-to-Blueprint
- **Natural Language Input:** "I need a scalable e-commerce app with high availability."
- **AI Reasoning:** Decomposes vague requests into strict technical invariants (e.g., Load Balancers, Multi-AZ Subnets, RDS).
- **JSON Blueprint:** Generates a structured intermediate representation, not just raw code.

### 2. 🕸️ Living State Graph (Visualization)
- **Interactive UI:** Built with **React Flow**, rendering infrastructure as a dynamic node-link diagram.
- **Cloud Blueprint Aesthetic:** High-fidelity visuals with "Blueprint" VPC containers, "Zone" subnets, and dark-mode resource cards.
- **Real-time Status:** Nodes visual states (Draft, Verifying, Deployed, Error).

### 3. 💥 Blast Radius Simulator ("Time Travel")
- **Impact Analysis:** Select any node (e.g., a NAT Gateway) and ask "What if I delete this?"
- **AI logic:** The backend traverses the dependency graph (NetworkX) and uses Gemini to predict cascading failures (e.g., "Database subnet loses internet access").
- **Visual Kill Chain:** Highlights the exact path of destruction in Red/Orange on the graph.

### 4. 🛡️ Autonomous Self-Correction
- **Constraint Enforcement:** Detects security violations (e.g., Security Group allowing `0.0.0.0/0`).
- **Self-Healing Loop:** Automatically generates fixes, updates the graph, and re-verifies until constraints are met.

---

## 🛠️ Tech Stack

### Frontend
- **Framework:** [Next.js](https://nextjs.org/) (React 19)
- **Visualization:** [React Flow](https://reactflow.dev/) + [Dagre](https://github.com/dagrejs/dagre) (Auto-Layout)
- **Styling:** [Tailwind CSS](https://tailwindcss.com/) + [Framer Motion](https://www.framer.com/motion/) (Animations)
- **Icons:** [Lucide React](https://lucide.dev/)

### Backend
- **Framework:** [FastAPI](https://fastapi.tiangolo.com/) (Python)
- **AI Engine:** [Google Gemini](https://ai.google.dev/) (via `google-genai` SDK)
- **Graph Engine:** [NetworkX](https://networkx.org/) (Dependency analysis)
- **Infrastructure:** [Terraform](https://www.terraform.io/) (HCL Generation)

---

## 🚀 Getting Started

### Prerequisites
- **Node.js** (v18+)
- **Python** (v3.10+)
- **Docker Desktop** (Optional, for LocalStack simulation)

### ⚡ Quick Start

The easiest way to run the entire stack is using the helper script:

```bash
chmod +x start_dev.sh
./start_dev.sh
```

This will launch:
- **Backend:** http://localhost:8000
- **Frontend:** http://localhost:3001

### 🔧 Manual Setup

#### 1. Backend Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Create a .env file with your Google API Key
echo "GOOGLE_API_KEY=your_api_key_here" > .env

# Run the server
uvicorn main:app --reload --port 8000
```

#### 2. Frontend Setup

```bash
cd frontend
npm install
npm run dev
# App runs on http://localhost:3000 (or 3001 if claimed)
```

---

## 📂 Project Structure

```
InfraMinds/
├── backend/                 # FastAPI Backend
│   ├── main.py              # Entry point & API Routes
│   ├── agent.py             # Agent Logic (Gemini Interface)
│   ├── prompts/             # System Prompts for AI Phases
│   └── requirements.txt     # Python Dependencies
├── frontend/                # Next.js Frontend
│   ├── app/                 # Page Layouts
│   ├── components/          # UI Components
│   │   ├── GraphVisualizer.tsx  # Main Graph View
│   │   └── AgentNeuralStream.tsx # AI Thought Log
│   └── lib/                 # API Clients & Utilities
├── start_dev.sh             # Startup Script
└── README.md                # Documentation
```

## 🤝 Contributing
1. Fork the repo.
2. Create a feature branch (`git checkout -b feature/amazing-feature`).
3. Commit your changes.
4. Open a Pull Request.

---

*Built with ❤️ for the Hackathon.*
