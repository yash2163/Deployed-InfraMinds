# InfraMinds: Comprehensive Technical Documentation

## 1. Executive Summary
**InfraMinds** is an autonomous infrastructure agent that transforms natural language intent (or images) into a verified "Living State Graph" of cloud architecture. Unlike standard text-to-code tools, it employs a **multi-phase reasoning engine** (Intent -> Reasoned -> Implementation) to visualize, simulate, and verify infrastructure changes before generating Terraform code. It features a "Glass Box" approach, allowing users to see the "Blast Radius" of changes and relying on autonomous self-healing loops ensuring correctness.

## 2. Core Architecture & Tech Stack

### 2.1 Backend (`/backend`)
*   **Framework**: FastAPI (Python)
*   **AI Engine**: Google Gemini (via `google-genai` SDK), utilizing models like `gemini-2.0-flash`.
*   **Graph Engine**: `NetworkX` for maintaining the dependency graph and performing topological analysis (Blast Radius).
*   **Infrastructure Engine**: Terraform (via `tflocal` for LocalStack simulation).
*   **Pipeline**: A robust 5-stage pipeline for safe execution.

### 2.2 Frontend (`/frontend`)
*   **Framework**: Next.js (React 19)
*   **Visualization**: `React Flow` with `Dagre` for auto-layout.
*   **State Management**: Real-time streaming of agent thoughts and graph updates.
*   **Styling**: Tailwind CSS + Framer Motion.

## 3. The 4-Phase Generation Flow
InfraMinds does not jump straight to code. It evolves the architecture through 4 distinct phases to ensure semantically correct and improved infrastructure.

### Phase 1: Intent Generation (Abstract)
*   **Input**: Natural Language (e.g., "I need a scalable e-commerce app") or Architecture Diagrams (Images).
*   **Process**:
    *   **Text**: Uses `get_intent_text_prompt` to map request to **Semantic Types** only (e.g., `compute_service`, `relational_database`).
    *   **Image**: Uses `get_vision_prompt` to extract architecture from diagrams.
*   **Output**: `Intent Graph` (Method: `generate_intent_stream`).
*   **Goal**: Capture *what* the user wants without getting bogged down in *how* (AWS primitives).

### Phase 2: Reasoning & Policy Enforcement
*   **Input**: `Intent Graph`
*   **Process**:
    *   The **Policy Engine** (`apply_policies_gen`) acts as a "Cloud Architect".
    *   Enforces baseline policies:
        *   **Isolation**: DBs/Caches must not be public.
        *   **Least Privilege**: Strict connectivity.
        *   **Ingress Discipline**: Public compute must use Load Balancers.
    *   **Self-Healing Loop**: If violations are found, the graph is **mutated** (e.g., removing a direct public edge to a DB) and re-evaluated (up to 3 cycles).
*   **Output**: `Reasoned Graph` (still semantic, but policy-compliant).

### Phase 3: Cloud Expansion (Implementation)
*   **Input**: `Reasoned Graph`
*   **Process**:
    *   The **Platform Engineer** agent (`expand_architecture_gen`) maps semantic nodes to concrete **AWS Primitives**.
    *   *Examples*: `compute_service` -> `aws_instance`, `relational_database` -> `aws_db_instance`.
    *   **Materialization**: Adds necessary supporting infrastructure (VPCs, Subnets, Internet Gateways, Route Tables) that wasn't explicitly asked for but is required for a valid cloud setup.
    *   **Preservation Check**: Ensures all semantic nodes from Phase 2 exist in Phase 3.
*   **Output**: `Implementation Graph` (The "Living State Graph").

### Phase 4: Optimization & Cost
*   **Input**: `Implementation Graph`
*   **Process**:
    *   **Cost Estimator**: `CostEstimator` (in `cost.py`) analyzes resource types (`instance_type`, `volume_size`).
    *   Estimates monthly cost using AI knowledge of on-demand pricing.
*   **Output**: Cost Report JSON (displayed in UI).

## 4. Self-Healing Loops
The system is designed to be autonomous and resilient through multiple feedback loops:

1.  **Graph Policy Loop (Phase 2)**:
    *   *Trigger*: Policy violation (e.g., "Database exposed to internet").
    *   *Action*: LLM modifies the graph structure (removes edge, adds attributes).
    *   *Retry*: Re-runs policy check until pure.

2.  **Architecture Expansion Loop (Phase 3)**:
    *   *Trigger*: Monotonicity failure (dropped nodes) or Hallucination (abstract nodes remaining).
    *   *Action*: Retries expansion prompt.

3.  **Terraform Pipeline Loop (Execution)**:
    *   *Trigger*: `terraform validate` or `terraform apply` failure.
    *   *Action*:
        *   Captures `stderr`.
        *   Calls `_fix_code` in `pipeline.py`.
        *   LLM analyzes the error ("X-ray vision"), proposes a fix, and generates patched HCL.
    *   *Retry*: Re-runs the failed stage (up to 3 times).

## 5. Usage of Knowledge Graph
The project relies heavily on `NetworkX` (`agent.py`) to maintain a "Living State":
*   **Dependency Tracking**: Knows that Subnet A is *inside* VPC B, and Instance C is *inside* Subnet A.
*   **Blast Radius Analysis**:
    *   Uses graph traversal (descendants/ancestors) to simulate failure impact.
    *   Prompts (`get_blast_radius_prompt`) combine structural graph data with AI reasoning (e.g., "Deleting this Security Group allows 0.0.0.0/0").
*   **Visual Layout**: The graph structure drives the `React Flow` visualization, grouping resources by Subnet/VPC (using `dagre` for auto-layout).

## 6. The 5-Stage Testing Plan (Pipeline)
To ensure the correctness of the generated Terraform code, `pipeline.py` executes a strict 5-stage plan:

1.  **Setup / Clean**:
    *   Removes `.terraform.lock.hcl`, state files, and provider overrides to ensure a clean slate.
    *   Runs `terraform init`.
2.  **Stage 1: Validate**:
    *   Runs `terraform validate`.
    *   Performs **Static Policy Check** (`_check_policy`): Scans HCL/Regex for forbidden patterns (e.g., inline ingress rules in SG).
3.  **Stage 2: Plan**:
    *   Runs `tflocal plan`.
    *   Verifies that the code is logically consistent and the provider can build a plan.
4.  **Stage 3: Apply**:
    *   Runs `tflocal apply -auto-approve`.
    *   Actually creates resources in the LocalStack simulation.
5.  **Stage 4: Verify**:
    *   Runs a Python test script (`test_infra.py`).
    *   **Logic**: The script (generated by AI) performs "Black Box" testing:
        *   Checks if resources exist (via Boto3).
        *   Checks connectivity (HTTP 200).
        *   Validates configuration (e.g., "Is port 80 open?").
    *   If this script fails, the pipeline is marked as failed even if Terraform applied successfully.

## 7. Blast Radius & Time Travel
*   **Concept**: Interactive impact analysis before deployment.
*   **Mechanism**:
    1.  User selects a node (e.g., "NAT Gateway").
    2.  Agent traverses the `NetworkX` graph to find all dependent downstream nodes.
    3.  AI Agent adds semantic reasoning (e.g., "Removing NAT Gateway breaks internet access for Private Subnets").
*   **Visualization**:
    *   **Target Node**: Pulsing Red.
    *   **Affected Nodes**: Orange Glow with dashed orange edges showing the "Kill Chain".

## 8. Cost Estimation
*   **Logic**: `backend/cost.py`.
*   **Method**: Extracts resource properties (`t2.micro`, `gp3`) -> Sends to LLM ("You are an AWS Pricing Expert") -> Returns JSON breakdown.
*   **Display**: Tablet in the UI showing Total Monthly Cost and itemized breakdown.
