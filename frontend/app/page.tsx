"use client";

import Link from 'next/link';
import { useState, useRef, useEffect } from 'react';
import GraphVisualizer from '../components/GraphVisualizer';
import { ImageUpload } from '../components/ImageUpload';
import { api, simulateBlastRadius, explainBlastRadius, streamAgentVisualize, approveIntentStream, fetchSession, modifyGraphStream, confirmGraphModification } from '../lib/api';
import { Terminal, Play, Cpu, ShieldAlert, Info, CheckCircle2, Circle, Loader2, XCircle, FileCode, Check, RefreshCw, Scale, ThumbsUp, ThumbsDown } from 'lucide-react';

// --- UI Component: Pipeline Progress Bar ---
const PipelineProgress = ({ stages }: { stages: any[] }) => {
  // Define standard order for the deployment pipeline
  const standardStages = ['validate', 'plan', 'apply', 'verify'];

  return (
    <div className="flex items-center gap-2 text-[10px] bg-slate-900 border border-slate-800 p-2 rounded mb-2 overflow-x-auto scrollbar-hide">
      {standardStages.map((stageName) => {
        const stageState = stages.find(s => s.name === stageName);

        let icon = <Circle className="w-3 h-3 text-slate-700" />;
        let textColor = "text-slate-600";
        let bgColor = "";

        if (stageState?.status === 'success') {
          icon = <CheckCircle2 className="w-3 h-3 text-green-500" />;
          textColor = "text-green-400";
          bgColor = "bg-green-900/10";
        } else if (stageState?.status === 'failed') {
          icon = <XCircle className="w-3 h-3 text-red-500" />;
          textColor = "text-red-400";
          bgColor = "bg-red-900/10";
        } else if (stageState?.status === 'running') {
          icon = <Loader2 className="w-3 h-3 text-blue-400 animate-spin" />;
          textColor = "text-blue-400";
          bgColor = "bg-blue-900/10";
        }

        return (
          <div key={stageName} className={`flex items-center gap-1.5 px-2 py-1 rounded ${bgColor} ${textColor} uppercase font-bold tracking-wider transition-all duration-300`}>
            {icon} {stageName}
            {stageName !== 'verify' && <div className="w-3 h-[1px] bg-slate-800 ml-2" />}
          </div>
        );
      })}
    </div>
  );
};

export default function Home() {
  // Input State
  const [input, setInput] = useState('');
  const [executionMode, setExecutionMode] = useState<'deploy' | 'draft'>('deploy');

  // Logic State
  const [response, setResponse] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [sessionPhase, setSessionPhase] = useState<'idle' | 'intent_review' | 'reasoned_review' | 'graph_pending' | 'deployed' | 'modification_review'>('idle');
  // const [deploymentPhase, setDeploymentPhase] = useState<'idle' | 'graph_pending' | 'code_pending' | 'deploying'>('idle'); // REPLACED by sessionPhase

  // Streaming State (The "Glass Box")
  const [executionLogs, setExecutionLogs] = useState<string[]>([]);
  const [thoughts, setThoughts] = useState<string[]>([]);
  const [decisions, setDecisions] = useState<any[]>([]); // New: Decisions Stream
  const [pipelineStages, setPipelineStages] = useState<any[]>([]);
  const [resourceStatuses, setResourceStatuses] = useState<Record<string, string>>({});

  // Graph Evolution State
  const [visualizedGraph, setVisualizedGraph] = useState<any>(null);
  const [graphPhase, setGraphPhase] = useState<'intent' | 'reasoned' | 'implementation' | null>(null);

  // Code Viewer State
  const [showCode, setShowCode] = useState(false);
  const [tfCode, setTfCode] = useState("");

  // Auto-scroll for logs
  const logsEndRef = useRef<HTMLDivElement>(null);
  const thoughtsEndRef = useRef<HTMLDivElement>(null);
  const decisionsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [executionLogs]);

  useEffect(() => {
    thoughtsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [thoughts]);

  useEffect(() => {
    decisionsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [decisions]);

  // --- RESTORE SESSION ON MOUNT ---
  useEffect(() => {
    const restore = async () => {
      try {
        const session = await fetchSession();
        if (session.phase !== 'idle') {
          setSessionPhase(session.phase);
          // Restore Graph
          if (session.implementation_graph) {
            setVisualizedGraph(session.implementation_graph);
            setGraphPhase("implementation"); // If implementation exists, show it
          } else if (session.reasoned_graph) {
            setVisualizedGraph(session.reasoned_graph);
            setGraphPhase("reasoned");
          } else if (session.intent_graph) {
            setVisualizedGraph(session.intent_graph);
            setGraphPhase("intent");
          }

          if (session.execution_mode) {
            setExecutionMode(session.execution_mode as 'deploy' | 'draft');
          }
          setExecutionLogs(["System: Session restored."]);
        }
      } catch (e) {
        console.error("Failed to restore session", e);
      }
    };
    restore();
  }, []);

  const handleReset = async () => {
    if (!confirm("Reset entire graph?")) return;
    await api.post('/graph/reset');
    setResourceStatuses({});
    setExecutionLogs([]);
    setPipelineStages([]);
    setThoughts([]);
    setDecisions([]);
    setResponse(null);
    setSessionPhase('idle');
    window.location.reload();
  };

  const commonStreamHandler = (chunk: any) => {
    if (chunk.type === 'log') {
      setExecutionLogs(prev => [...prev, chunk.content]);
    } else if (chunk.type === 'graph_snapshot') {
      setVisualizedGraph(chunk.content);
      setGraphPhase(chunk.content.graph_phase || 'implementation');
    } else if (chunk.type === 'thought') {
      setThoughts(prev => [...prev, chunk.content]);
    } else if (chunk.type === 'decision') {
      // New Decision Stream
      setDecisions(prev => [...prev, chunk.content]);
    } else if (chunk.type === 'control') {
      // Backend tells us phase changed
      if (chunk.content.next_phase === 'reasoning') setSessionPhase('intent_review');
      if (chunk.content.next_phase === 'deployment') setSessionPhase('reasoned_review'); // Architecture Ready
      if (chunk.content.next_phase === 'confirm_change') setSessionPhase('modification_review'); // HITL
      setLoading(false);
    } else if (chunk.type === 'result') {
      const planResult = chunk.content;
      if (planResult.session_phase === 'graph_pending') setSessionPhase('graph_pending');

      setResponse({
        summary: planResult.confirmation?.message || "Operation Complete",
        risks: planResult.confirmation?.reasons?.map((r: any) => r.reason) || [],
        explanation: "Process finished successfully.",
        mitigation: "Ready for next step."
      });
    } else if (chunk.type === 'error') {
      setExecutionLogs(prev => [...prev, `❌ ${chunk.content}`]);
    } else if (chunk.type === 'stage') {
      // Pipeline Stage
      setPipelineStages(prev => {
        const existingIndex = prev.findIndex(s => s.name === chunk.content.name);
        if (existingIndex > -1) {
          const updated = [...prev];
          updated[existingIndex] = chunk.content;
          return updated;
        }
        return [...prev, chunk.content];
      });
    }
  };

  const handleImageUpload = async (file: File) => {
    setLoading(true);
    setResponse(null);
    setExecutionLogs([]);
    setThoughts([]);
    setDecisions([]);
    setExecutionLogs(["🚀 Uploading Sketch for Analysis (Unified Phase 1)..."]);

    try {
      // Unified Stream Call
      await streamAgentVisualize(file, commonStreamHandler);
    } catch (e) {
      console.error(e);
      setExecutionLogs(prev => [...prev, "❌ Visualization Failed"]);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    setLoading(true);
    setResponse(null);
    setThoughts([]);
    setDecisions([]); // Clear decisions on new request

    try {
      // --- INTERACTIVE ROUTING ---
      // If we are in a review phase, this is a REFINEMENT request
      if (sessionPhase === 'intent_review' || sessionPhase === 'reasoned_review') {
        setExecutionLogs(prev => [...prev, `🛠️ Refining Graph: "${input}"`]);
        await modifyGraphStream(input, commonStreamHandler);
      }
      // Else if idle, it's a new Intent
      else if (sessionPhase === 'idle') {
        setExecutionLogs(prev => [...prev, `💡 New Intent: "${input}"`]);
        await import('../lib/api').then(m => m.streamAgentThink(input, executionMode, commonStreamHandler));
      }
      // Else (graph_pending/deployed), maybe treat as new intent or context?
      else {
        alert("Please Reset or Deploy before starting a new intent.");
      }
    } catch (err) {
      console.error(err);
      setExecutionLogs(prev => [...prev, "❌ Error reaching agent"]);
    } finally {
      setLoading(false);
      setInput(''); // Clear input after submit
    }
  };

  const handleNodeSelected = async (nodeId: string) => {
    setLoading(true);
    setExecutionLogs([`Analyzing Blast Radius for ${nodeId}...`]);
    try {
      const blast = await simulateBlastRadius(nodeId);
      const explanation = await explainBlastRadius(nodeId, blast.affected_nodes);

      setResponse({
        summary: `Analysis of Deleting: ${nodeId}`,
        risks: [`High Impact: ${explanation.affected_count} resources affected`, `Severity: ${explanation.impact_level}`],
        explanation: explanation.explanation,
        mitigation: explanation.mitigation_strategy,
        suggested_actions: []
      });
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  // --- TRANSITION HANDLERS ---
  const handleApprove = async () => {
    setLoading(true);
    try {
      if (sessionPhase === 'intent_review') {
        await approveIntentStream(executionMode, commonStreamHandler);
      } else if (sessionPhase === 'reasoned_review') {
        // UNIFIED DEPLOYMENT FLOW: Architecture -> Code
        // User approved the Architecture. Now we generate code & deploy.
        setPipelineStages([]);
        setDecisions([]); // Clear decisions as we might get Terraform Validation Decisions

        await import('../lib/api').then(m => m.streamAgentDeploy("DEPLOY", executionMode, (chunk) => {
          // Custom handler for Deploy as it returns different "result" shape
          if (chunk.type === 'result' && chunk.content.success) {
            setTfCode(chunk.content.hcl_code);
            setSessionPhase('deployed');
            setResponse({ summary: "Deployment Complete!", explanation: chunk.content.final_message });
          }
          commonStreamHandler(chunk);
        }));
      } else if (sessionPhase === 'graph_pending') {
        // This case might be skipped now as we go directly to code, but kept for safety
        setPipelineStages([]);
        await import('../lib/api').then(m => m.streamAgentDeploy("DEPLOY", executionMode, (chunk) => {
          if (chunk.type === 'result' && chunk.content.success) {
            setTfCode(chunk.content.hcl_code);
            setSessionPhase('deployed');
          }
          commonStreamHandler(chunk);
        }));
      }
    } catch (e) {
      console.error(e);
      setExecutionLogs(prev => [...prev, "❌ Approval Failed"]);
    } finally {
      setLoading(false);
    }
  };

  // --- NEW: MODIFICATION CONFIRMATION (HITL) ---
  const handleConfirmModification = async (accept: boolean) => {
    setLoading(true);
    try {
      // Stream the result of the confirmation (which runs stabilization)
      await confirmGraphModification(accept, commonStreamHandler);
      // If discarded, we should probably reset phase to 'reasoned_review'
      // If accepted, we also go to 'reasoned_review' (after stabilization)
      // The commonStreamHandler logic handles the actual "reasoned_review" state transition via Control messages?
      // Actually backend sends: Phase 2: Architecture -> success -> control.next_phase = deployment
      // So commonStreamHandler will set 'reasoned_review' automatically if accepted.
      // If discarded, we revert. The backend just sends snapshot. We manually need to set phase back.
      if (!accept) {
        setSessionPhase('reasoned_review'); // Go back to review
      }
    } catch (e) {
      console.error(e);
      setExecutionLogs(prev => [...prev, "❌ Confirmation Error"]);
    } finally {
      setLoading(false);
    }
  };


  const handleViewCode = async () => {
    if (tfCode) {
      setShowCode(true);
    } else {
      alert("No code generated yet. Run a deployment first!");
    }
  };

  return (
    <main className="flex min-h-screen flex-col bg-slate-950 text-slate-100 font-mono relative overflow-hidden">

      {/* --- MODAL: Terraform Code Viewer --- */}
      {showCode && (
        <div className="fixed inset-0 z-50 bg-black/90 backdrop-blur-sm flex items-center justify-center p-4 md:p-10">
          <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-5xl h-full max-h-[85vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200">
            <div className="flex justify-between items-center p-4 border-b border-slate-800 bg-slate-950">
              <div className="flex items-center gap-3">
                <FileCode className="w-5 h-5 text-blue-400" />
                <h2 className="text-md font-semibold text-slate-200">main.tf (Generated)</h2>
              </div>
              <button onClick={() => setShowCode(false)} className="px-3 py-1 text-xs hover:bg-slate-800 rounded transition-colors text-slate-400 hover:text-white">Close</button>
            </div>
            <div className="flex-1 overflow-auto p-6 bg-[#0d1117]">
              <pre className="text-xs md:text-sm text-green-400 font-mono whitespace-pre-wrap leading-relaxed">{tfCode}</pre>
            </div>
            <div className="p-4 border-t border-slate-800 bg-slate-900 flex justify-end">
              <button className="bg-blue-600 px-6 py-2 rounded-lg text-sm font-semibold text-white hover:bg-blue-500 shadow-lg shadow-blue-500/20 transition-all">Download .tf</button>
            </div>
          </div>
        </div>
      )}

      {/* --- HEADER --- */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/80 backdrop-blur-md sticky top-0 z-40">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-500/10 rounded-lg">
            <Cpu className="w-6 h-6 text-blue-400" />
          </div>
          <div>
            <h1 className="text-lg font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">InfraMinds</h1>
            <div className="flex items-center gap-2">
              <span className="text-[10px] bg-blue-900/50 text-blue-200 px-2 py-0.5 rounded border border-blue-800">ALPHA</span>
              <span className="text-[10px] text-slate-500">v0.9.5 Hardened</span>
            </div>
          </div>
        </div>

        <div className="flex gap-4 text-xs font-medium">
          <button onClick={handleViewCode} className="flex items-center gap-2 hover:text-blue-400 transition-colors border border-slate-800 hover:border-slate-600 px-3 py-1.5 rounded-md bg-slate-900">
            <Terminal className="w-3.5 h-3.5" />
            View Code
          </button>
          <button onClick={handleReset} className="hover:text-red-400 transition-colors px-2">Reset</button>

          <div className="h-6 w-[1px] bg-slate-800 mx-2"></div>

          <div className="flex items-center gap-1.5 text-slate-400">
            <span className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"></span>
            Agent Active
          </div>
          <div className="flex items-center gap-1.5 text-slate-400">
            <span className="w-2 h-2 rounded-full bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.5)]"></span>
            LocalStack
          </div>
        </div>
      </header>

      {/* --- MAIN LAYOUT --- */}
      <div className="flex flex-1 overflow-hidden">

        {/* LEFT: GRAPH CANVAS */}
        <div className="flex-1 relative bg-[radial-gradient(#1e293b_1px,transparent_1px)] [background-size:20px_20px]">
          <div className="absolute inset-0 bg-slate-950/50 pointer-events-none"></div>

          <div className="absolute top-6 left-6 z-10 bg-slate-900/90 backdrop-blur p-3 rounded-lg border border-slate-700 shadow-xl">
            <h2 className="text-[10px] uppercase tracking-widest text-slate-500 font-bold mb-1">Architecture View</h2>
            <div className="text-sm font-semibold text-slate-200 flex items-center gap-2">
              Production Environment
              <span className="flex h-2 w-2 relative">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
            </div>
          </div>

          <div className="w-full h-full p-4">
            {/* Graph Visualizer gets the live statuses to update colors */}
            <GraphVisualizer
              onNodeSelected={handleNodeSelected}
              nodeStatuses={resourceStatuses}
              overrideGraph={visualizedGraph}
            />

            {/* Phase Indicator Overlay */}
            {graphPhase && (
              <div className="absolute top-24 left-6 z-10 bg-slate-900 shadow-2xl p-3 rounded-lg border border-slate-800 flex flex-col gap-1 items-start">
                <span className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Evolution Phase</span>
                <span className={`text-sm font-bold capitalize ${graphPhase === 'intent' ? 'text-purple-400' :
                  graphPhase === 'reasoned' ? 'text-blue-400' :
                    'text-emerald-400'
                  }`}>
                  {graphPhase}
                </span>
                {sessionPhase.includes("review") && <span className="text-[10px] text-amber-500 animate-pulse">Waiting for Approval / Refinement</span>}
              </div>
            )}

            {/* APPROVAL OVERLAY - PRIMARY ACTION */}
            {(sessionPhase === 'intent_review' || sessionPhase === 'reasoned_review' || sessionPhase === 'graph_pending') && (
              <div className="absolute bottom-6 left-1/2 transform -translate-x-1/2 z-50 animate-in slide-in-from-bottom-4 zoom-in-95 duration-300">
                <button
                  onClick={handleApprove}
                  disabled={loading}
                  className="bg-emerald-600 hover:bg-emerald-500 text-white px-6 py-3 rounded-full font-bold shadow-xl shadow-emerald-500/20 flex items-center gap-2 border border-emerald-400/50 hover:scale-105 transition-all text-sm disabled:opacity-50 disabled:grayscale disabled:cursor-not-allowed"
                >
                  {loading ? <Loader2 className="animate-spin w-4 h-4" /> : <CheckCircle2 size={18} />}

                  {sessionPhase === 'intent_review' && "Approve Intent → Architecture"}
                  {sessionPhase === 'reasoned_review' && "Approve Architecture → Deploy"}
                  {(sessionPhase === 'graph_pending') && "Deploy to Cloud 🚀"}
                </button>
              </div>
            )}

            {/* CONFIRMATION OVERLAY (HITL) */}
            {sessionPhase === 'modification_review' && (
              <div className="absolute bottom-6 left-1/2 transform -translate-x-1/2 z-50 animate-in slide-in-from-bottom-4 zoom-in-95 duration-300 flex gap-4">
                <button
                  onClick={() => handleConfirmModification(true)}
                  disabled={loading}
                  className="bg-emerald-600 hover:bg-emerald-500 text-white px-6 py-3 rounded-full font-bold shadow-xl flex items-center gap-2 border border-emerald-400/50 hover:scale-105 transition-all text-sm"
                >
                  {loading ? <Loader2 className="animate-spin w-4 h-4" /> : <ThumbsUp size={18} />}
                  Confirm Changes
                </button>
                <button
                  onClick={() => handleConfirmModification(false)}
                  disabled={loading}
                  className="bg-slate-700 hover:bg-red-900/50 hover:text-red-400 text-slate-200 px-6 py-3 rounded-full font-bold shadow-xl flex items-center gap-2 border border-slate-600 hover:scale-105 transition-all text-sm"
                >
                  <ThumbsDown size={18} />
                  Discard
                </button>
              </div>
            )}
          </div>
        </div>

        {/* RIGHT: COMMAND CENTER */}
        <div className="w-[450px] border-l border-slate-800 bg-slate-900 flex flex-col shadow-2xl z-20">

          {/* 1. Input Area */}
          <div className="p-5 border-b border-slate-800 space-y-4 bg-slate-900">
            <div className="flex justify-between items-center">
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-2">
                <Terminal className="w-4 h-4 text-purple-400" />
                Instruction
              </h2>

              {/* Mode Toggle */}
              <div className="flex bg-slate-950 rounded-lg p-1 border border-slate-800">
                <button
                  onClick={() => setExecutionMode('deploy')}
                  className={`px-3 py-1 text-[10px] font-bold rounded-md transition-all ${executionMode === 'deploy' ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-900/50' : 'text-slate-500 hover:text-slate-300'}`}
                >
                  LocalStack
                </button>
                <button
                  onClick={() => setExecutionMode('draft')}
                  className={`px-3 py-1 text-[10px] font-bold rounded-md transition-all ${executionMode === 'draft' ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/50' : 'text-slate-500 hover:text-slate-300'}`}
                >
                  AWS Cloud
                </button>
              </div>
            </div>

            {/* Visual Input */}
            <ImageUpload onImageSelected={handleImageUpload} isProcessing={loading} />

            <form onSubmit={handleSubmit} className="flex flex-col gap-3">
              <div className="relative">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={
                    sessionPhase === 'idle' ? "Design a cloud system (e.g. 'Highly available VPC')..." :
                      sessionPhase.includes('review') ? "Refine the design (e.g. 'Add a Redis cache')..." :
                        sessionPhase === 'modification_review' ? "Review proposed changes..." :
                          "System deployed."
                  }
                  className="w-full h-28 bg-slate-950 border border-slate-800 rounded-lg p-4 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500/50 focus:outline-none resize-none placeholder:text-slate-600 leading-relaxed"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSubmit(e);
                    }
                  }}
                  disabled={loading || sessionPhase === 'deployed' || sessionPhase === 'modification_review'}
                />

                {sessionPhase.includes('review') && (
                  <div className="absolute top-2 right-2 flex items-center gap-1 bg-amber-500/10 text-amber-500 text-[10px] px-2 py-0.5 rounded border border-amber-500/20">
                    <RefreshCw className="w-3 h-3" /> Refinement Mode
                  </div>
                )}

                {sessionPhase === 'modification_review' && (
                  <div className="absolute inset-0 bg-slate-900/80 backdrop-blur-[1px] rounded-lg flex items-center justify-center">
                    <span className="text-xs font-bold text-amber-400 bg-amber-900/20 px-3 py-1 rounded-full border border-amber-500/30 animate-pulse">
                      Waiting for Confirmation
                    </span>
                  </div>
                )}

                <div className="absolute bottom-3 right-3 text-[10px] text-slate-600">
                  {executionMode === 'deploy' ? 'LocalStack Mode' : 'AWS Cloud Planning Mode'}
                </div>
              </div>

              <div className="flex gap-2">
                <button
                  disabled={loading || sessionPhase === 'deployed' || sessionPhase === 'modification_review'}
                  type="submit"
                  className="w-full flex justify-center items-center gap-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 rounded-lg py-2.5 text-xs font-bold transition-all disabled:opacity-50"
                >
                  {loading ? <Loader2 className="w-3 h-3 animate-spin" /> :
                    sessionPhase.includes('review') ? <RefreshCw className="w-3 h-3" /> :
                      <Terminal className="w-3 h-3" />
                  }
                  {loading ? "PROCESSING..." :
                    sessionPhase === 'idle' ? "START DESIGN" :
                      sessionPhase.includes('review') ? "REFINE GRAPH" :
                        "SEND"
                  }
                </button>
              </div>
            </form>
          </div>

          {/* 2. Output & Logs Area */}
          <div className="flex-1 p-5 overflow-y-auto space-y-5 custom-scrollbar">

            {/* A. Live Pipeline Progress */}
            {pipelineStages.length > 0 && (
              <div className="animate-in slide-in-from-top-2 duration-300">
                <div className="flex justify-between items-center mb-2">
                  <h3 className="text-[10px] uppercase font-bold text-slate-500">Pipeline Status</h3>
                  <span className="text-[10px] text-blue-400 animate-pulse">● Live</span>
                </div>
                <PipelineProgress stages={pipelineStages} />
              </div>
            )}

            {/* B. Decisions Stream (Pinned) */}
            {decisions.length > 0 && (
              <div className="bg-slate-900/80 rounded-lg border border-indigo-500/30 overflow-hidden shadow-lg animate-in zoom-in-95 duration-300">
                <div className="bg-indigo-900/20 px-3 py-2 border-b border-indigo-500/20 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Scale className="w-3 h-3 text-indigo-400" />
                    <span className="text-[10px] font-bold text-indigo-200 uppercase tracking-wider">Policy Decisions</span>
                  </div>
                  <span className="text-[10px] text-indigo-400 font-mono">{decisions.length}</span>
                </div>
                <div className="p-2 max-h-48 overflow-y-auto space-y-2 bg-[#0a0c10]">
                  {decisions.map((d, i) => (
                    <div key={i} className="flex flex-col gap-1 p-2 bg-slate-900 rounded border border-slate-800 text-[10px]">
                      <div className="flex justify-between items-center">
                        <span className="text-slate-400 font-bold">{d.trigger || d.rule}</span>
                        <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${d.action === 'allowed' ? 'bg-emerald-900/30 text-emerald-400' :
                          d.action === 'modified' ? 'bg-amber-900/30 text-amber-400' : 'bg-red-900/30 text-red-400'
                          }`}>
                          {d.action}
                        </span>
                      </div>
                      <div className="text-slate-500">{d.result || d.modification}</div>
                    </div>
                  ))}
                  <div ref={decisionsEndRef} />
                </div>
              </div>
            )}

            {/* C. Internal Thoughts (The "Brain") */}
            {thoughts.length > 0 && (
              <div className="bg-slate-950 rounded-lg border border-slate-800 overflow-hidden shadow-sm animate-in fade-in duration-300">
                <div className="bg-slate-900/50 px-3 py-2 border-b border-slate-800 flex items-center gap-2">
                  <Cpu className="w-3 h-3 text-purple-400" />
                  <span className="text-[10px] font-bold text-purple-200 uppercase tracking-wider">Agent Reasoning</span>
                </div>
                <div className="p-3 text-[10px] text-slate-400 font-mono space-y-1.5 max-h-32 overflow-y-auto">
                  {thoughts.map((t, i) => (
                    <div key={i} className="flex gap-2 animate-in slide-in-from-left-2 duration-100">
                      <span className="text-slate-600 shrink-0 select-none">›</span>
                      <span className="text-slate-300">{t}</span>
                    </div>
                  ))}
                  <div ref={thoughtsEndRef} />
                </div>
              </div>
            )}

            {/* D. Response Card (Intent Analysis) */}
            {response && !loading && (
              <div className="space-y-3 animate-in zoom-in-95 duration-200">
                <div className="bg-slate-800/40 p-4 rounded-lg border border-slate-700/50">
                  <div className="text-xs font-bold text-emerald-400 mb-2 flex items-center gap-2">
                    <CheckCircle2 className="w-3 h-3" />
                    Objective
                  </div>
                  <p className="text-sm text-slate-300 leading-relaxed">{response.summary}</p>
                </div>

                {response.risks && response.risks.length > 0 && (
                  <div className="bg-red-900/10 p-4 rounded-lg border border-red-900/30">
                    <div className="text-xs font-bold text-red-400 mb-2 flex items-center gap-2">
                      <ShieldAlert className="w-3 h-3" />
                      Risk Assessment
                    </div>
                    <ul className="list-disc list-inside text-xs text-red-200/80 space-y-1.5">
                      {response.risks.map((r: string, i: number) => <li key={i}>{r}</li>)}
                    </ul>
                  </div>
                )}

                {(response.explanation || response.mitigation) && (
                  <div className="bg-blue-900/10 p-4 rounded-lg border border-blue-900/30">
                    <div className="text-xs font-bold text-blue-400 mb-2 flex items-center gap-2">
                      <Info className="w-3 h-3" />
                      Technical Strategy
                    </div>
                    {response.explanation && <p className="text-xs text-blue-200/80 mb-2">{response.explanation}</p>}
                    {response.mitigation && <p className="text-xs text-emerald-200/80 italic border-l-2 border-emerald-500/30 pl-2">{response.mitigation}</p>}
                  </div>
                )}
              </div>
            )}

            {/* E. Execution Terminal Logs */}
            {executionLogs.length > 0 && (
              <div>
                <h3 className="text-[10px] uppercase font-bold text-slate-500 mb-2">System Logs</h3>
                <div className="bg-[#0d1117] border border-slate-800 rounded-lg p-3 font-mono text-[10px] h-48 overflow-y-auto shadow-inner">
                  {executionLogs.map((log, i) => {
                    let color = "text-slate-400";
                    if (log.includes("FAILED") || log.includes("Error") || log.includes("❌")) color = "text-red-400";
                    if (log.includes("PASSED") || log.includes("OK") || log.includes("✅")) color = "text-emerald-400";
                    if (log.includes("Cycle") || log.includes("Stage")) color = "text-blue-400 font-bold";
                    if (log.includes("Deploying")) color = "text-amber-400";

                    return (
                      <div key={i} className={`${color} py-0.5 whitespace-pre-wrap break-all border-b border-white/5 last:border-0`}>
                        {log}
                      </div>
                    );
                  })}
                  <div ref={logsEndRef} />
                </div>
              </div>
            )}

            {!response && executionLogs.length === 0 && !loading && (
              <div className="h-full flex flex-col items-center justify-center text-slate-700 gap-3 opacity-50">
                <Terminal className="w-8 h-8" />
                <p className="text-xs">System Idle. Waiting for instructions.</p>
              </div>
            )}

          </div>
        </div>
      </div >
    </main >
  );
}