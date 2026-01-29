"use client";

import { useState } from 'react';
import GraphVisualizer from '../components/GraphVisualizer';
import { sendPrompt, explainBlastRadius, simulateBlastRadius, api } from '../lib/api';
import { Terminal, Play, Cpu, ShieldAlert, Info } from 'lucide-react';

export default function Home() {
  const [input, setInput] = useState('');
  const [response, setResponse] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [executionLogs, setExecutionLogs] = useState<string[]>([]);
  const [deploymentPhase, setDeploymentPhase] = useState<'idle' | 'graph_pending' | 'code_pending' | 'deploying'>('idle');
  const [showCode, setShowCode] = useState(false);
  const [tfCode, setTfCode] = useState("");
  const [executionMode, setExecutionMode] = useState<'deploy' | 'draft'>('deploy');

  /* New Helper for Reset */
  const handleReset = async () => {
    if (!confirm("Reset entire graph?")) return;
    await api.post('/graph/reset');
    window.location.reload();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    setLoading(true);
    setResponse(null);
    setExecutionLogs([]);
    try {
      const res = await sendPrompt(input, executionMode);
      setResponse(res);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleNodeSelected = async (nodeId: string) => {
    setLoading(true);
    // Clear logs when selecting node to focus on analysis
    setExecutionLogs([]);
    try {
      // 1. Get affected IDs (redundant fetch but cleanest for separation of concerns)
      const blast = await simulateBlastRadius(nodeId);

      // 2. Get AI Explanation
      const explanation = await explainBlastRadius(nodeId, blast.affected_nodes);

      // 3. Update UI (Reuse the response format for now, or create a specific one)
      setResponse({
        summary: `Analysis of Deleting: ${nodeId}`,
        risks: [`High Impact: ${explanation.affected_count} resources affected`, `Severity: ${explanation.impact_level}`],
        explanation: explanation.explanation,
        mitigation: explanation.mitigation_strategy,
        suggested_actions: [] // Legacy field cleared
      });
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  /* Two-Stage Confirmation Deployment Handler */
  const handleExecute = async () => {
    if (!input.trim()) return;

    const userInput = input.trim();

    // Check if user is confirming
    if (userInput.toUpperCase() === "CONFIRM") {
      if (deploymentPhase === 'idle') {
        setResponse({
          summary: "No pending confirmation",
          risks: ["Please start with a deployment request first"],
          explanation: ""
        });
        return;
      }

      // User is confirming - proceed with next phase
      setLoading(true);
      setExecutionLogs([`Confirming phase: ${deploymentPhase}...`]);

      try {
        const pipelineResult = await import('../lib/api').then(m => m.deployAgentic("CONFIRM", executionMode));

        if (pipelineResult.session_phase === 'code_pending') {
          // Phase 2: Code generated and validated
          setTfCode(pipelineResult.hcl_code);
          setDeploymentPhase('code_pending');

          const logs: string[] = [];
          pipelineResult.stages?.forEach((stage: any) => {
            const symbol = stage.status === 'success' ? '✅' : '⚠️';
            logs.push(`${symbol} [STAGE: ${stage.name.toUpperCase()}]`);
            stage.logs?.forEach((l: string) => logs.push(`   > ${l}`));
          });
          logs.push(pipelineResult.final_message);
          setExecutionLogs(logs);

          setResponse({
            summary: "Terraform Code Generated",
            explanation: "Code has been validated. Review it using 'View Code' button.",
            mitigation: "Type CONFIRM to deploy to LocalStack for testing"
          });
        } else if (pipelineResult.success) {
          // Phase 3: Deployment complete
          setDeploymentPhase('idle');
          setTfCode(pipelineResult.hcl_code);

          const logs: string[] = [];
          pipelineResult.stages?.forEach((stage: any) => {
            const symbol = stage.status === 'success' ? '✅' : (stage.status === 'warning' ? '⚠️' : '❌');
            logs.push(`${symbol} [STAGE: ${stage.name.toUpperCase()}]`);
            stage.logs?.forEach((l: string) => logs.push(`   > ${l}`));
          });
          logs.push(`🎉 ${pipelineResult.final_message}`);
          setExecutionLogs(logs);

          setResponse({
            summary: "Deployment Complete!",
            explanation: pipelineResult.final_message
          });
          setInput(''); // Clear input
        } else {
          // Deployment failed
          const logs: string[] = ["❌ Deployment Failed"];
          pipelineResult.stages?.forEach((stage: any) => {
            logs.push(`[${stage.name}]: ${stage.status}`);
            stage.logs?.forEach((l: string) => logs.push(`   > ${l}`));
          });
          setExecutionLogs(logs);
          setDeploymentPhase('idle');
        }
      } catch (e) {
        console.error(e);
        setExecutionLogs(["❌ Error processing confirmation"]);
        setDeploymentPhase('idle');
      } finally {
        setLoading(false);
      }

      return;
    }

    // Phase 1: Generate graph plan
    setLoading(true);
    setResponse(null);
    setExecutionLogs(["Generating infrastructure plan..."]);

    try {
      // Send the input to generate the graph plan first
      const planResult = await import('../lib/api').then(m => m.planGraph(userInput, executionMode));

      setDeploymentPhase('graph_pending');
      setExecutionLogs(["✅ Graph plan generated. Review the visualization."]);

      setResponse({
        summary: planResult.confirmation.message || "Graph Plan Generated",
        risks: planResult.confirmation.reasons?.map((r: any) => r.reason) || [],
        explanation: "Review the graph on the left. The infrastructure matches your request.",
        mitigation: planResult.confirmation.required
          ? "If this looks correct, type CONFIRM to generate Terraform code."
          : "Type CONFIRM to proceed with code generation."
      });

    } catch (e) {
      console.error(e);
      setExecutionLogs(["❌ Failed to generate plan"]);
      setDeploymentPhase('idle');
    } finally {
      setLoading(false);
    }
  };

  const handleViewCode = async () => {
    try {
      if (tfCode) {
        // If we have code from the latest deployment, show it
        setShowCode(true);
        return;
      }
      // No code generated yet
      alert("No code generated yet. Run the Agent first!");
    } catch (e) {
      alert("Failed to fetch code");
    }
  };

  return (
    <main className="flex min-h-screen flex-col bg-slate-950 text-slate-100 font-mono relative">
      {/* Code Modal */}
      {showCode && (
        <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-10">
          <div className="bg-slate-900 border border-slate-700 rounded-lg w-full max-w-4xl h-full max-h-[80vh] flex flex-col shadow-2xl">
            <div className="flex justify-between items-center p-4 border-b border-slate-700 bg-slate-800">
              <h2 className="text-lg font-semibold text-blue-400">main.tf (Generated)</h2>
              <button onClick={() => setShowCode(false)} className="text-slate-400 hover:text-white">Close</button>
            </div>
            <div className="flex-1 overflow-auto p-4 bg-slate-950">
              <pre className="text-xs text-green-400 font-mono whitespace-pre-wrap">{tfCode}</pre>
            </div>
            <div className="p-4 border-t border-slate-700 flex justify-end">
              <button className="bg-blue-600 px-4 py-2 rounded text-sm text-white hover:bg-blue-500">Download .tf</button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <header className="flex items-center justify-between p-4 border-b border-slate-800 bg-slate-900/50 backdrop-blur">
        <div className="flex items-center gap-2 text-xl font-bold text-blue-400">
          <Cpu className="w-6 h-6" />
          InfraMinds <span className="text-xs bg-blue-900 text-blue-200 px-2 py-0.5 rounded">ALPHA</span>
        </div>
        <div className="flex gap-4 text-sm text-slate-400">
          <button onClick={handleViewCode} className="flex items-center gap-2 hover:text-blue-400 transition-colors border border-slate-700 px-3 py-1 rounded bg-slate-800">
            <Terminal className="w-3 h-3" />
            View Code
          </button>
          <button onClick={handleReset} className="hover:text-red-400 transition-colors">Reset Graph</button>
          <div className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500"></span> Agent Active</div>
          <div className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-yellow-500"></span> LocalStack Ready</div>
          <div className="flex items-center gap-1 border border-slate-700 rounded px-2 py-0.5 bg-slate-800 text-xs text-slate-400"><span className="w-1.5 h-1.5 rounded-full bg-purple-500"></span> Free Tier Mode</div>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Main Graph View */}
        <div className="flex-1 p-4 relative">
          <div className="absolute top-6 left-6 z-10 bg-slate-900/80 p-2 rounded border border-slate-700">
            <h2 className="text-xs uppercase tracking-widest text-slate-500 mb-1">Live Structure</h2>
            <div className="text-lg font-semibold">Production Environment</div>
          </div>
          <GraphVisualizer onNodeSelected={handleNodeSelected} />
        </div>

        {/* Right Command Panel */}
        <div className="w-96 border-l border-slate-800 bg-slate-900 flex flex-col">
          <div className="p-4 border-b border-slate-800 space-y-4">
            <h2 className="text-sm font-semibold flex items-center gap-2">
              <Terminal className="w-4 h-4 text-purple-400" />
              Agent Command
            </h2>

            {/* New Execution Mode Switch */}
            <div className="bg-slate-800 p-2 rounded flex flex-col gap-2 border border-slate-700">
              <div className="flex justify-between items-center">
                <span className="text-xs font-bold text-slate-300">Mode</span>
                <div className="flex bg-slate-900 rounded p-0.5">
                  <button
                    onClick={() => setExecutionMode('deploy')}
                    className={`px-2 py-0.5 text-xs rounded transition-colors ${executionMode === 'deploy' ? 'bg-green-600 text-white' : 'text-slate-500 hover:text-slate-300'}`}
                  >
                    Real
                  </button>
                  <button
                    onClick={() => setExecutionMode('draft')}
                    className={`px-2 py-0.5 text-xs rounded transition-colors ${executionMode === 'draft' ? 'bg-blue-600 text-white' : 'text-slate-500 hover:text-slate-300'}`}
                  >
                    Draft
                  </button>
                </div>
              </div>
              <div className="text-[10px] text-slate-500 leading-tight">
                {executionMode === 'deploy'
                  ? "Restricted to LocalStack Free Tier. Validates & Deploys."
                  : "Unrestricted AWS. Plans architecture only (No Deploy)."}
              </div>
            </div>

            <form onSubmit={handleSubmit} className="flex flex-col gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={executionMode === 'deploy' ? "Describe infrastructure (LocalStack Free Tier)..." : "Describe any AWS infrastructure..."}
                className="w-full h-24 bg-slate-950 border border-slate-700 rounded p-3 text-sm focus:border-blue-500 focus:outline-none resize-none"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSubmit(e);
                  }
                }}
              />
              <div className="flex gap-2">
                <button
                  disabled={loading}
                  type="submit"
                  className="flex-1 flex justify-center items-center gap-2 bg-slate-700 hover:bg-slate-600 text-white rounded py-2 text-sm font-medium transition-colors disabled:opacity-50"
                >
                  {loading ? "Thinking..." : <><Terminal className="w-3 h-3" /> Analyze</>}
                </button>
                <button
                  type="button"
                  onClick={handleExecute}
                  disabled={loading}
                  className="flex-1 flex justify-center items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white rounded py-2 text-sm font-medium transition-colors disabled:opacity-50"
                >
                  <Play className="w-3 h-3" />
                  {deploymentPhase === 'idle' ? 'Plan' :
                    deploymentPhase === 'graph_pending' ? 'Confirm' :
                      deploymentPhase === 'code_pending' ? 'Deploy' :
                        'Deploying...'}
                </button>
              </div>
            </form>
          </div>

          {/* Thought Stream */}
          <div className="flex-1 p-4 overflow-y-auto">
            <h3 className="text-xs uppercase text-slate-500 mb-3">Agent Thought Process</h3>
            {response ? (
              <div className="space-y-4">
                <div className="bg-slate-800/50 p-3 rounded border border-slate-700">
                  <div className="text-sm font-semibold text-green-400 mb-1">Intent Analyzed</div>
                  <p className="text-sm text-slate-300">{response.summary}</p>
                </div>

                {response.risks && response.risks.length > 0 && (
                  <div className="bg-red-900/20 p-3 rounded border border-red-900/50">
                    <div className="text-sm font-semibold text-red-400 mb-1 flex items-center gap-2">
                      <ShieldAlert className="w-3 h-3" />
                      Risks Detected
                    </div>
                    <ul className="list-disc list-inside text-xs text-red-200 space-y-1">
                      {response.risks.map((r: string, i: number) => <li key={i}>{r}</li>)}
                    </ul>
                  </div>
                )}

                {/* Dedicated Explanation Box */}
                {response.explanation && (
                  <div className="bg-blue-900/20 p-3 rounded border border-blue-900/50">
                    <div className="text-sm font-semibold text-blue-400 mb-1 flex items-center gap-2">
                      <Info className="w-3 h-3" />
                      Technical Explanation
                    </div>
                    <p className="text-xs text-blue-200 leading-relaxed">
                      {response.explanation}
                    </p>
                  </div>
                )}

                {/* Dedicated Mitigation Box */}
                {response.mitigation && (
                  <div className="bg-emerald-900/20 p-3 rounded border border-emerald-900/50">
                    <div className="text-sm font-semibold text-emerald-400 mb-1">
                      Recommended Mitigation
                    </div>
                    <p className="text-xs text-emerald-200 leading-relaxed">
                      {response.mitigation}
                    </p>
                  </div>
                )}

                {/* Legacy Fallback for simple Intent Analysis */}
                {(!response.explanation && !response.mitigation && response.suggested_actions) && (
                  <div className="bg-slate-800 p-3 rounded border border-slate-700">
                    <div className="text-sm font-semibold text-slate-400 mb-1">Suggested Actions</div>
                    <ul className="list-disc list-inside text-xs text-slate-300 space-y-1">
                      {response.suggested_actions.map((a: string, i: number) => <li key={i}>{a}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <>
                {executionLogs.length > 0 ? (
                  <div className="bg-slate-900 border border-slate-700 rounded p-3 font-mono text-xs">
                    <div className="text-slate-400 mb-2 uppercase tracking-wider">Self-Correction Logs</div>
                    <div className="space-y-1">
                      {executionLogs.map((log, i) => {
                        let color = "text-slate-300";
                        if (log.includes("FAILED") || log.includes("Error")) color = "text-red-400";
                        if (log.includes("PASSED") || log.includes("OK")) color = "text-green-400";
                        if (log.includes("Cycle") || log.includes(">>")) color = "text-blue-400 font-bold";
                        if (log.includes("Deploying")) color = "text-yellow-400";
                        return <div key={i} className={color}>{log}</div>
                      })}
                    </div>
                  </div>
                ) : (
                  <div className="text-slate-600 text-sm italic">Waiting for input...</div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
