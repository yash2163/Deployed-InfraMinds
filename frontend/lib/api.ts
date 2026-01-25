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

export const sendPrompt = async (prompt: string): Promise<IntentAnalysis> => {
  const response = await api.post<IntentAnalysis>('/agent/think', { prompt });
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

export const generatePlan = async (prompt: string): Promise<any> => {
  const response = await api.post('/agent/plan', { prompt });
  return response.data;
}

export const applyPlan = async (diff: any): Promise<any> => {
  const response = await api.post('/agent/apply', diff);
  return response.data;
}

export const exportTerraform = async (): Promise<Record<string, string>> => {
  const response = await api.get('/agent/export');
  return response.data;
}

