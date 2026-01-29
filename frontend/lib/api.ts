import axios from 'axios';

const API_URL = 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export interface GraphResource {
  id: string;
  type: string;
  properties: Record<string, any>;
  status: 'planned' | 'active' | 'deleted';
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
}

export interface GraphState {
  resources: GraphResource[];
  edges: GraphEdge[];
}

export interface IntentAnalysis {
  summary: string;
  risks: string[];
  suggested_actions: string[];
}

export const fetchGraph = async (): Promise<GraphState> => {
  const response = await api.get<GraphState>('/graph');
  return response.data;
};

export const sendPrompt = async (prompt: string, executionMode: string = "deploy"): Promise<IntentAnalysis> => {
  const response = await api.post<IntentAnalysis>('/agent/think', { prompt, execution_mode: executionMode });
  return response.data;
};

export const simulateBlastRadius = async (nodeId: string) => {
  const response = await api.post('/simulate/blast_radius', { target_node_id: nodeId });
  return response.data;
}

export interface BlastAnalysis {
  target_node: string;
  impact_level: "Low" | "Medium" | "High" | "Critical";
  affected_count: number;
  affected_node_ids: string[];
  explanation: string;
  mitigation_strategy: string;
}

export const explainBlastRadius = async (targetNodeId: string, affectedNodes: string[]): Promise<BlastAnalysis> => {
  const response = await api.post('/simulate/explain', { target_node_id: targetNodeId, affected_nodes: affectedNodes });
  return response.data;
}

export const generatePlan = async (prompt: string, executionMode: string = "deploy"): Promise<any> => {
  const response = await api.post('/agent/plan', { prompt, execution_mode: executionMode });
  return response.data;
}

export const applyPlan = async (diff: any): Promise<any> => {
  const response = await api.post('/agent/apply', diff);
  return response.data;
}

export const planGraph = async (prompt: string, executionMode: string = "deploy"): Promise<any> => {
  const response = await api.post('/agent/plan_graph', { prompt, execution_mode: executionMode });
  return response.data;
}




export interface PipelineStage {
  name: string;
  status: string;
  logs: string[];
  error?: string;
}

export interface PipelineResult {
  success: boolean;
  hcl_code: string;
  stages: PipelineStage[];
  final_message: string;
  session_phase?: string;
}

export const deployAgentic = async (prompt: string, executionMode: string = "deploy"): Promise<PipelineResult> => {
  const response = await api.post('/agent/deploy', { prompt, execution_mode: executionMode });
  return response.data;
}
