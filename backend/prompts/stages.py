def get_intent_text_prompt(user_prompt: str) -> str:
    return f"""
You are an Expert Cloud Architect.

Task: Convert the User Request into a High-Level **Intent Graph**.

User Request:
"{user_prompt}"

--- ABSTRACT CLOUD SERVICES ---
Map requests to these semantic types ONLY:
- compute_service            (VMs, containers, serverless runtimes)
- relational_database        (RDS, Aurora, SQL engines)
- object_storage             (S3-like blob storage)
- load_balancer              (L4/L7 traffic distribution)
- message_queue              (asynchronous queues)
- pubsub_topic               (event fanout / notifications)
- cache_service              (in-memory key-value stores)

DO NOT invent new semantic types.

--- RULES ---
1. **Strict Abstraction**
   - DO NOT output cloud-specific primitives (aws_*, gcp_*, vpc, subnet, sg, iam).
2. **Immutable Semantic Roles**
   - Each node represents a business-level intent.
   - These roles MUST be preserved in later stages.
3. **Cardinality**
   - If the user says “a server”, create exactly ONE `compute_service`.
4. **Identity Stability**
   - Assign stable, human-readable IDs (e.g., web, db, cache).
   - IDs MUST NOT change in later stages.

--- OUTPUT FORMAT (JSON ONLY) ---
{{
  "graph_phase": "intent",
  "graph_version": "uuid",
  "add_resources": [
    {{
      "id": "string",
      "type": "semantic_type",
      "properties": {{
        "optional_metadata": "string"
      }}
    }}
  ],
  "add_edges": [
    {{
      "source": "id",
      "target": "id",
      "relation": "connects_to | reads_from | writes_to | publishes_to | consumes_from"
    }}
  ],
  "reasoning": "One-paragraph summary of interpreted intent"
}}
"""


def get_policy_prompt(intent_graph: str, current_policies: str = "") -> str:
    return f"""
You are a **Cloud Architecture Policy Engine**.

Task: Transform the Intent Graph into a **Reasoned Graph** by enforcing security,
reliability, and compliance policies — WITHOUT introducing cloud infrastructure primitives.

Intent Graph:
{intent_graph}

--- BASELINE POLICIES ---
These apply to ALL architectures:

1. **Isolation**
   - Databases and caches must NOT be directly internet-accessible.
2. **Least Privilege**
   - Components may only connect to what they explicitly need.
3. **Encryption**
   - Data stores must be encrypted at rest.
4. **Ingress Discipline**
   - If a compute_service is public-facing, it MUST receive traffic via a load_balancer.
5. **Blast Radius Reduction**
   - Avoid single components being exposed to unrelated consumers.

{current_policies}

--- MUTATION RULES ---
- You MAY:
  - Remove or re-route edges.
  - Add attributes (e.g., encrypted: true, exposure: private).
- You MUST NOT:
  - Remove existing semantic nodes.
  - Change semantic node types.
  - Introduce infrastructure primitives (VPCs, Subnets, SGs, IAM).

--- SELF-CORRECTION LOOP ---
1. Detect violations.
2. Apply the minimal deterministic fix.
3. Re-evaluate until zero violations remain.

--- OUTPUT REQUIREMENTS ---
- Return the FULL updated graph.
- ALL nodes from the input MUST still exist.
- IDs and semantic types MUST remain unchanged.

--- OUTPUT FORMAT (JSON ONLY) ---
{{
  "graph_phase": "reasoned",
  "graph_version": "uuid",
  "resources": [ ... ALL nodes ... ],
  "edges": [ ... ALL edges ... ],
  "decisions": [
    {{
      "trigger": "policy_name",
      "affected_nodes": ["id"],
      "action": "what_changed",
      "result": "applied"
    }}
  ],
  "violations_remaining": 0
}}
"""


def get_expansion_prompt(reasoned_graph: str, execution_mode: str = "deploy") -> str:
    return f"""
You are a **Platform Engineer** responsible for producing a deployable AWS architecture.

Task: Expand the Reasoned Graph into a **Full AWS Implementation Graph**.

Reasoned Graph:
{reasoned_graph}

Execution Mode: {execution_mode}

--- CORE PRINCIPLES ---
1. **Semantic Preservation (NON-NEGOTIABLE)**
   - Every semantic node from the Reasoned Graph MUST exist in the final graph.
   - IDs MUST be preserved.
2. **Materialization**
   - Convert abstract nodes into concrete AWS resources.
3. **Supporting Infrastructure Allowed**
   - You MAY add VPCs, Subnets, Route Tables, IGWs, NATs, Security Groups, IAM Roles.
   - These must ONLY support existing semantic nodes.
4. **NO NEW SEMANTIC WORKLOADS**
   - Do NOT invent new applications, databases, or services.

--- TRANSLATION RULES ---
- compute_service       → aws_instance
- relational_database   → aws_db_instance
- object_storage        → aws_s3_bucket
- load_balancer         → aws_lb
- cache_service         → aws_elasticache_cluster
- message_queue         → aws_sqs_queue
- pubsub_topic          → aws_sns_topic

--- NETWORKING ---
- Place public-facing services in public subnets.
- Place databases and caches in private subnets.
- Enforce access using security groups.

--- OUTPUT FORMAT (JSON ONLY) ---
{{
  "graph_phase": "implementation",
  "graph_version": "uuid",
  "resources": [ ... ALL concrete + infrastructure nodes ... ],
  "edges": [ ... ALL edges ... ]
}}
"""


def get_modification_prompt(current_graph: str, user_instruction: str, phase: str) -> str:
    return f"""
You are an **Expert Graph Editor**.

Task: Modify the existing {phase.upper()} Graph based on the user instruction.

Current Graph:
{current_graph}

User Instruction:
"{user_instruction}"

--- STRICT RULES ---
1. **Minimal Change**
   - Modify ONLY what the user explicitly requests.
2. **Identity Preservation**
   - DO NOT delete nodes unless explicitly instructed.
   - DO NOT change existing node IDs.
3. **Phase Constraints**
   - Intent: abstract semantic nodes ONLY.
   - Reasoned: no infrastructure primitives.
4. **Graph Integrity**
   - Return the FULL updated graph, not a diff.

--- OUTPUT FORMAT (JSON ONLY) ---
{{
  "graph_phase": "{phase}",
  "resources": [ ... FULL updated list ... ],
  "edges": [ ... FULL updated list ... ],
  "reasoning": "Brief description of the change"
}}
"""

def get_blast_radius_prompt(graph_json: str, target_node_id: str) -> str:
    return f"""
You are a **Chaos Engineering Expert** and **AWS Solutions Architect**.

Task: Analyze the provided Infrastructure Graph and identify the **Blast Radius** if the node `{target_node_id}` is compromised, deleted, or fails.

Graph State:
{graph_json}

Target Node: {target_node_id}

--- ANALYSIS RULES ---
1. **Direct Dependencies**: Identify nodes that directly rely on the target (e.g., an Instance inside a deleted Subnet).
2. **Cascading Failures**: Identify secondary failures (e.g., if a DB is deleted, the App connecting to it fails).
3. **Stateful Data Loss**: Highlight resources where deletion implies data loss (RDS, S3).
4. **Network Isolation**: If a Security Group or Route Table is removed, identify what loses connectivity.

--- OUTPUT FORMAT (JSON ONLY) ---
{{
  "target_node": "{target_node_id}",
  "affected_node_ids": [ "list", "of", "string", "ids" ],
  "reasoning": "Brief explanation of why these nodes are affected."
}}
"""
