# InfraMinds System Architecture

This document details the architectural components and data flow of the InfraMinds system.

## High-Level Overview

InfraMinds is designed as a "Glass Box" system where every decision is transparent and verifiable. The core architecture revolves around a **Living State Graph** maintained by NetworkX, which evolves through 4 reasoning phases before being deployed.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontFamily': 'arial', 'fontSize': '14px'}, 'flowchart': {'curve': 'basis', 'nodeSpacing': 60, 'rankSpacing': 80}}}%%
flowchart TD
    %% --- Styling Definitions ---
    classDef input fill:#FFF8E1,stroke:#FFC107,stroke-width:2px,rx:10,ry:10,color:#444;
    classDef api fill:#E3F2FD,stroke:#2196F3,stroke-width:2px,rx:5,ry:5,color:#0D47A1;
    classDef ai fill:#F3E5F5,stroke:#9C27B0,stroke-width:3px,rx:5,ry:5,color:#4A148C,stroke-dasharray: 5 5;
    classDef graphNode fill:#E0F2F1,stroke:#009688,stroke-width:2px,rx:5,ry:5,color:#004D40;
    classDef infra fill:#ECEFF1,stroke:#546E7A,stroke-width:2px,rx:5,ry:5,color:#263238;
    classDef ui fill:#F3E5F5,stroke:#673AB7,stroke-width:2px,rx:10,ry:10,color:#311B92;
    
    %% --- Components ---
    User((User)):::input
    NL[Natural Language Prompt]:::input --> API
    Image[Architecture Diagram]:::input --> API
    
    subgraph Backend[Backend - FastAPI]
        direction TB
        API[Orchestration API]:::api
        
        subgraph AICore[AI Core]
            Gemini[Google Gemini 3.0 Flash/Pro]:::ai
        end
        
        subgraph GraphEngine[Graph Engine]
            Note1[Semantic -> Concrete]:::graphNode
            NX[NetworkX Dependency Graph]:::graphNode
            Blast[Blast Radius Calculator]:::graphNode
        end
        
        subgraph PolicyEngine[Policy Engine]
            Policy[Policy Enforcer]:::graphNode
            SelfHeal[Self-Healing Loop]:::graphNode
        end
        
        subgraph InfraEngine[Infrastructure Engine]
            TF[Terraform Generator]:::infra
            LocalStack[LocalStack Simulation]:::infra
            Cost[Cost Estimator]:::infra
        end
    end

    subgraph Frontend[Frontend - Next.js]
        UI[React Flow Visualization]:::ui
        Stream[Agent Thought Stream]:::ui
    end

    %% --- Connections ---
    User --> NL
    User --> Image
    
    API -->|1. Generate Intent| Gemini
    Gemini -->|Intent Graph JSON| NX
    
    NX -->|2. Reasoning| Policy
    Policy -->|Violations?| SelfHeal
    SelfHeal -->|Fix Graph| NX
    
    Policy -->|Validated Graph| Gemini
    Gemini -->|3. Expand to AWS| NX
    
    NX -->|Implementation Graph| Cost
    Cost -->|Cost Report| UI
    
    NX -->|4. Generate HCL| TF
    TF -->|Plan/Apply| LocalStack
    LocalStack -->|State| API
    LocalStack -.->|Error/Feedback| TF
    
    NX -.->|Real-time Updates| UI
    Blast -.->|Impact Analysis| UI
    Stream -.->|Thought Logs| API

    %% --- Feedback Loops ---
    LocalStack -.->|Error/Feedback| Gemini
    linkStyle 17 stroke:#D32F2F,stroke-width:2px,stroke-dasharray: 5 5;
    Gemini -.->|x-Ray Fix| TF
    linkStyle 18 stroke:#388E3C,stroke-width:2px,stroke-dasharray: 5 5;
```

## The 4-Phase Logic Flow

The system does not jump straight to code. It follows a rigorous 4-phase process to ensure correctness and policy compliance.

```mermaid
sequenceDiagram
    participant U as User
    participant A as Agent (FastAPI)
    participant G as Gemini AI
    participant N as NetworkX Graph
    participant T as Terraform/LocalStack

    U->>A: "I need a scalable web app"
    
    rect rgb(240, 248, 255)
        Note over A, N: Phase 1: Intent Generation
        A->>G: Parse Intent (Semantic Nodes)
        G->>N: Create Intent Graph
    end

    rect rgb(255, 240, 245)
        Note over A, N: Phase 2: Reasoning & Policy
        loop Self-Healing Policy Loop
            A->>N: Check Policies (Isolation, Least Privilege)
            alt Violation Found
                N->>G: Request Fix
                G->>N: Mutate Graph
            else Validated
                N->>A: Reasoned Graph Ready
            end
        end
    end

    rect rgb(240, 255, 240)
        Note over A, N: Phase 3: Cloud Expansion
        A->>G: Map to AWS Primitives (Concrete Nodes)
        G->>N: Add VPCs, Subnets, Gateways
        N->>A: Implementation Graph (Living State)
    end

    rect rgb(255, 250, 240)
        Note over A, T: Phase 4: Execution & Verification
        A->>T: Generate & Validate Terraform
        T->>T: Plan & Apply (LocalStack)
        
        opt Validation Failure
            T->>G: Analyze Error (X-Ray)
            G->>T: Patch HCL
            T->>T: Retry Apply
        end
        
        T->>U: Deployment Successful
    end
```

## Component Details

### 1. Intent Generator
- **Role**: Parses user input (text/image) into semantic infrastructure nodes.
- **Output**: Abstract Intent Graph (e.g., `Compute`, `Database`).

### 2. Policy & Reasoning Engine
- **Role**: Validates the graph against security and architectural best practices.
- **Mechanism**: Iterative self-healing. If a policy fails (e.g., public DB), the AI modifies the graph until it passes.

### 3. Graph Engine (NetworkX)
- **Role**: The source of truth. Maintains the dependency graph, handles topological sorts for deployment order, and calculates blast radius.

### 4. Expansion Agent
- **Role**: Converts semantic nodes to concrete provider resources (e.g., `AWS EC2`, `AWS RDS`), adding necessary scaffolding (VPC, IGW) that the user didn't explicitly request.

### 5. Execution Pipeline
- **Role**: Generates, validates, and applies Terraform code.
- **Features**: Includes a "Self-Correction Loop" where Terraform errors are fed back to the AI to generate fixes automatically.
