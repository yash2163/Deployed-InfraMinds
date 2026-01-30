"use client";

import { useState, useRef, useEffect } from 'react';
import GraphVisualizer from '../components/GraphVisualizer';
import { api, simulateBlastRadius, explainBlastRadius } from '../lib/api';
import { Terminal, Play, Cpu, ShieldAlert, Info, CheckCircle2, Circle, Loader2, XCircle, FileCode } from 'lucide-react';

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
  const [deploymentPhase, setDeploymentPhase] = useState<'idle' | 'graph_pending' | 'code_pending' | 'deploying'>('idle');

  // Streaming State (The "Glass Box")
  const [executionLogs, setExecutionLogs] = useState<string[]>([]);
  const [thoughts, setThoughts] = useState<string[]>([]);
  const [pipelineStages, setPipelineStages] = useState<any[]>([]);
  const [resourceStatuses, setResourceStatuses] = useState<Record<string, string>>({});

  // Code Viewer State
  const [showCode, setShowCode] = useState(false);
  const [tfCode, setTfCode] = useState("");

  // Auto-scroll for logs
  const logsEndRef = useRef<HTMLDivElement>(null);
  const thoughtsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [executionLogs]);

  useEffect(() => {
    thoughtsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [thoughts]);

  const handleReset = async () => {
    if (!confirm("Reset entire graph?")) return;
    await api.post('/graph/reset');
    setResourceStatuses({});
    setExecutionLogs([]);
    setPipelineStages([]);
    setThoughts([]);
    setResponse(null);
    setDeploymentPhase('idle');
    window.location.reload();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    setLoading(true);
    setResponse(null);
    setExecutionLogs([]);
    setThoughts([]);

    try {
      // Stream "Thinking" Process
      await import('../lib/api').then(m => m.streamAgentThink(input, executionMode, (chunk) => {
        if (chunk.type === 'thought') {
          setThoughts(prev => [...prev, chunk.content]);
        } else if (chunk.type === 'result') {
          setResponse(chunk.payload);
        } else if (chunk.type === 'error') {
          setExecutionLogs(prev => [...prev, `❌ ${chunk.content}`]);
        }
      }));
    } catch (err) {
      console.error(err);
      setExecutionLogs(prev => [...prev, "❌ Error reaching agent"]);
    } finally {
      setLoading(false);
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

  const handleExecute = async () => {
    if (!input.trim()) return;
    const userInput = input.trim();

    // ---------------------------------------------------------
    // Phase 2: User Confirmed -> Run Deployment Pipeline
    // ---------------------------------------------------------
    if (userInput.toUpperCase() === "CONFIRM") {
      setLoading(true);
      setPipelineStages([]); // Reset stages
      setThoughts([]); // Clear previous thoughts
      setDeploymentPhase('deploying');

      try {
        await import('../lib/api').then(m => m.streamAgentDeploy("CONFIRM", executionMode, (chunk) => {

          if (chunk.type === 'log') {
            setExecutionLogs(prev => [...prev, chunk.content]);
          } else if (chunk.type === 'thought') {
            // Visualize Code Generation Thoughts (Drafting Phase)
            setThoughts(prev => [...prev, chunk.content]);
          } else if (chunk.type === 'stage') {
            // Update Pipeline Visualizer
            setPipelineStages(prev => {
              const existingIndex = prev.findIndex(s => s.name === chunk.content.name);
              if (existingIndex > -1) {
                const updated = [...prev];
                updated[existingIndex] = chunk.content;
                return updated;
              }
              return [...prev, chunk.content];
            });
          } else if (chunk.type === 'resource_update') {
            // ✨ REAL TIME GREEN LIGHTS ✨
            setResourceStatuses(prev => ({ ...prev, ...chunk.content }));
          } else if (chunk.type === 'result') {
            const result = chunk.content;
            if (result.success) {
              setDeploymentPhase('idle');
              setTfCode(result.hcl_code);
              setResponse({
                summary: "Deployment Complete!",
                explanation: result.final_message
              });
              setInput('');
            }
          } else if (chunk.type === 'error') {
            setExecutionLogs(prev => [...prev, `❌ ${chunk.content}`]);
          }
        }));
      } catch (e) {
        console.error(e);
        setExecutionLogs(prev => [...prev, "❌ Connection Error"]);
      } finally {
        setLoading(false);
      }
      return;
    }

    // ---------------------------------------------------------
    // Phase 1: Planning (Generate Graph) - STREAMING
    // ---------------------------------------------------------
    setLoading(true);
    setResponse(null);
    setExecutionLogs([]);
    setThoughts([]); // Clear old thoughts

    try {
      // Use streamPlanGraph instead of planGraph
      await import('../lib/api').then(m => m.streamPlanGraph(userInput, executionMode, (chunk) => {

        if (chunk.type === 'log') {
          // Stream logs to the terminal window
          setExecutionLogs(prev => [...prev, chunk.content]);
        }
        else if (chunk.type === 'thought') {
          // Stream AI reasoning to the "Brain" window
          setThoughts(prev => [...prev, chunk.content]);
        }
        else if (chunk.type === 'result') {
          // Final Plan Received
          const planResult = chunk.content;

          setDeploymentPhase('graph_pending');

          setResponse({
            summary: planResult.confirmation.message || "Graph Plan Generated",
            risks: planResult.confirmation.reasons?.map((r: any) => r.reason) || [],
            explanation: "Review the graph on the left. The infrastructure matches your request.",
            mitigation: planResult.confirmation.required
              ? "If this looks correct, type CONFIRM to generate Terraform code."
              : "Type CONFIRM to proceed with code generation."
          });
        }
        else if (chunk.type === 'error') {
          setExecutionLogs(prev => [...prev, `❌ ${chunk.content}`]);
        }
      }));

    } catch (e) {
      console.error(e);
      setExecutionLogs(["❌ Failed to generate plan"]);
      setDeploymentPhase('idle');
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
              <span className="text-[10px] text-slate-500">v0.9.2</span>
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
            <GraphVisualizer onNodeSelected={handleNodeSelected} nodeStatuses={resourceStatuses} />
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
                  REAL
                </button>
                <button
                  onClick={() => setExecutionMode('draft')}
                  className={`px-3 py-1 text-[10px] font-bold rounded-md transition-all ${executionMode === 'draft' ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/50' : 'text-slate-500 hover:text-slate-300'}`}
                >
                  DRAFT
                </button>
              </div>
            </div>

            <form onSubmit={handleSubmit} className="flex flex-col gap-3">
              <div className="relative">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={executionMode === 'deploy'
                    ? "e.g., Deploy a high availability web cluster with 2 t2.micro instances..."
                    : "e.g., Design a global architecture with EKS, RDS Aurora, and CloudFront..."}
                  className="w-full h-28 bg-slate-950 border border-slate-800 rounded-lg p-4 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500/50 focus:outline-none resize-none placeholder:text-slate-600 leading-relaxed"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSubmit(e);
                    }
                  }}
                />
                <div className="absolute bottom-3 right-3 text-[10px] text-slate-600">
                  {executionMode === 'deploy' ? 'LocalStack Mode' : 'Planning Mode'}
                </div>
              </div>

              <div className="flex gap-2">
                <button
                  disabled={loading}
                  type="submit"
                  className="flex-1 flex justify-center items-center gap-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 rounded-lg py-2.5 text-xs font-bold transition-all disabled:opacity-50"
                >
                  {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Terminal className="w-3 h-3" />}
                  ANALYZE
                </button>
                <button
                  type="button"
                  onClick={handleExecute}
                  disabled={loading}
                  className="flex-1 flex justify-center items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg py-2.5 text-xs font-bold transition-all shadow-lg shadow-blue-600/20 disabled:opacity-50"
                >
                  {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3 fill-current" />}
                  {deploymentPhase === 'idle' ? 'PLAN' :
                    deploymentPhase === 'graph_pending' ? 'CONFIRM' :
                      deploymentPhase === 'code_pending' ? 'DEPLOY' :
                        'DEPLOYING...'}
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

            {/* B. Internal Thoughts (The "Brain") */}
            {thoughts.length > 0 && (
              <div className="bg-slate-950 rounded-lg border border-slate-800 overflow-hidden shadow-sm animate-in fade-in duration-300">
                <div className="bg-slate-900/50 px-3 py-2 border-b border-slate-800 flex items-center gap-2">
                  <Cpu className="w-3 h-3 text-purple-400" />
                  <span className="text-[10px] font-bold text-purple-200 uppercase tracking-wider">Agent Reasoning</span>
                </div>
                <div className="p-3 text-[10px] text-slate-400 font-mono space-y-1.5 max-h-40 overflow-y-auto">
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

            {/* C. Response Card (Intent Analysis) */}
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

            {/* D. Execution Terminal Logs */}
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
      </div>
    </main>
  );
}