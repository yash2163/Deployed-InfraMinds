import axios from 'axios';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const streamPlanGraph = async (
  prompt: string,
  executionMode: string,
  onChunk: (chunk: any) => void
) => {
  const response = await fetch(`${API_URL}/agent/plan_stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, execution_mode: executionMode }),
  });

  const reader = response.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    const lines = chunk.split('\n').filter(line => line.trim() !== '');
    for (const line of lines) {
      try {
        const data = JSON.parse(line);
        onChunk(data);
      } catch (e) {
        console.error('Error parsing chunk', e);
      }
    }
  }
};

export const approvePlan = async () => {
  const response = await api.post('/agent/approve');
  return response.data;
};

export const approveIntentStream = async (executionMode: string, onChunk: (chunk: any) => void) => {
  const response = await fetch(`${API_URL}/agent/approve/intent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt: "APPROVE", execution_mode: executionMode }),
  });
  handleStream(response, onChunk);
};

// Obsolete approveReasonedStream removed.


// Helper to avoid duplication
const handleStream = async (response: Response, onChunk: (chunk: any) => void) => {
  const reader = response.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    const lines = chunk.split('\n').filter(line => line.trim() !== '');
    for (const line of lines) {
      try {
        const data = JSON.parse(line);
        onChunk(data);
      } catch (e) {
        console.error('Error parsing chunk', e);
      }
    }
  }
};

export const rejectPlan = async () => {
  const response = await api.post('/agent/reject');
  return response.data;
};

export interface CostItem {
  resource_id: string;
  resource_type: string;
  estimated_cost: number;
  explanation: string;
}

export interface CostReport {
  total_monthly_cost: number;
  currency: string;
  breakdown: CostItem[];
  disclaimer: string;
}

export const fetchCost = async (phase: string = "implementation"): Promise<CostReport> => {
  const response = await api.get(`/cost?phase=${phase}`);
  return response.data;
};

export interface Resource {
  id: string;
  type: string;
  properties: Record<string, any>;
  status: 'planned' | 'active' | 'deleted' | 'proposed';
  description?: string;
  parent_id?: string;
}

export interface Edge {
  source: string;
  target: string;
  relation: string;
}

export interface GraphState {
  graph_phase?: 'intent' | 'reasoned' | 'implementation'; // Added for Evolution Demo
  resources: Resource[];
  edges: Edge[];
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

export const fetchDemoData = async () => {
  const response = await api.get('/agent/demo_data');
  return response.data;
};

export const generateGraphLayout = async (): Promise<any> => {
  const response = await api.post('/agent/layout', { prompt: "LAYOUT", execution_mode: "deploy" });
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
  resource_statuses?: Record<string, string>;
}

export const deployAgentic = async (prompt: string, executionMode: string = "deploy"): Promise<PipelineResult> => {
  const response = await api.post('/agent/deploy', { prompt, execution_mode: executionMode });
  return response.data;
}

export const streamAgentThink = async (
  prompt: string,
  executionMode: string,
  onChunk: (chunk: any) => void
) => {
  const response = await fetch(`${API_URL}/agent/think`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, execution_mode: executionMode }),
  });

  const reader = response.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    const lines = chunk.split('\n').filter(line => line.trim() !== '');
    for (const line of lines) {
      try {
        const data = JSON.parse(line);
        onChunk(data);
      } catch (e) {
        console.error('Error parsing chunk', e);
      }
    }
  }
};

export const streamAgentDeploy = async (
  prompt: string,
  executionMode: string,
  onChunk: (chunk: any) => void
) => {
  const response = await fetch(`${API_URL}/agent/deploy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, execution_mode: executionMode }),
  });

  const reader = response.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    const lines = chunk.split('\n').filter(line => line.trim() !== '');
    for (const line of lines) {
      try {
        const data = JSON.parse(line);
        onChunk(data);
      } catch (e) {
        console.error('Error parsing chunk', e);
      }
    }
  }
};

export const streamAgentVisualize = async (
  file: File,
  onChunk: (chunk: any) => void
) => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_URL}/agent/visualize`, {
    method: 'POST',
    body: formData, // fetch automatically sets Content-Type to multipart/form-data
  });

  const reader = response.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    const lines = chunk.split('\n').filter(line => line.trim() !== '');
    for (const line of lines) {
      try {
        const data = JSON.parse(line);
        onChunk(data);
      } catch (e) {
        console.error('Error parsing chunk', e);
      }
    }
  }
};

export const fetchSession = async (): Promise<any> => {
  const response = await api.get('/agent/session');
  return response.data;
};

export const modifyGraphStream = async (
  prompt: string,
  onChunk: (chunk: any) => void
) => {
  const response = await fetch(`${API_URL}/agent/modify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  });

  const reader = response.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    const lines = chunk.split('\n').filter(line => line.trim() !== '');
    for (const line of lines) {
      try {
        const data = JSON.parse(line);
        onChunk(data);
      } catch (e) {
        console.error('Error parsing chunk', e);
      }
    }
  }
};

export const confirmGraphModification = async (
  accept: boolean,
  onChunk: (chunk: any) => void
) => {
  const response = await fetch(`${API_URL}/graph/confirm_change`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ accept }),
  });

  const reader = response.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    const lines = chunk.split('\n').filter(line => line.trim() !== '');
    for (const line of lines) {
      try {
        const data = JSON.parse(line);
        onChunk(data);
      } catch (e) {
        console.error('Error parsing chunk', e);
      }
    }
  }
};
