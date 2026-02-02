"use client";

import React, { useCallback, useEffect, useState } from 'react';
import ReactFlow, {
    Node,
    Edge,
    Controls,
    Background,
    useNodesState,
    useEdgesState,
    Connection,
    addEdge,
    NodeMouseHandler,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { fetchGraph, GraphState, simulateBlastRadius, approvePlan, rejectPlan, fetchCost, CostReport } from '../lib/api';
import { Check, X, DollarSign } from 'lucide-react';

import dagre from 'dagre';

const initialNodes: Node[] = [];
const initialEdges: Edge[] = [];

// Helper to calculate layout
const getLayoutedElements = (nodes: Node[], edges: Edge[]) => {
    const dagreGraph = new dagre.graphlib.Graph();
    dagreGraph.setDefaultEdgeLabel(() => ({}));
    dagreGraph.setGraph({ rankdir: 'TB' }); // TB = Top to Bottom

    nodes.forEach((node) => {
        // Set generic width/height for layout calculation
        dagreGraph.setNode(node.id, { width: 150, height: 50 });
    });

    edges.forEach((edge) => {
        dagreGraph.setEdge(edge.source, edge.target);
    });

    dagre.layout(dagreGraph);

    const layoutedNodes = nodes.map((node) => {
        const nodeWithPosition = dagreGraph.node(node.id);
        node.position = {
            x: nodeWithPosition.x - 75, // Center offset
            y: nodeWithPosition.y - 25,
        };
        return node;
    });

    return { nodes: layoutedNodes, edges };
};

interface GraphVisualizerProps {
    onNodeSelected?: (nodeId: string) => void;
    nodeStatuses?: Record<string, string>;
    terraformCode?: string | null;
    overrideGraph?: GraphState | null; // For Streaming Visualization
}

export default function GraphVisualizer({ onNodeSelected, nodeStatuses, terraformCode, overrideGraph }: GraphVisualizerProps) {
    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
    const [showCode, setShowCode] = useState(false);

    const [isInitialLoad, setIsInitialLoad] = useState(true);
    const [costReport, setCostReport] = useState<CostReport | null>(null);
    const [showCostModal, setShowCostModal] = useState(false);
    const [lastCostHash, setLastCostHash] = useState<string>("");

    // Missing state variables restore
    const [affectedNodeIds, setAffectedNodeIds] = useState<Set<string>>(new Set());
    const [isPendingApproval, setIsPendingApproval] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);

    // Poll for graph updates
    const refreshGraph = useCallback(async () => {
        try {
            let state = overrideGraph; // Default to override if exists

            if (!state) {
                state = await fetchGraph();
            }

            if (!state) return;

            // Check for pending approval (proposed status only)
            const hasProposed = state.resources.some(r => r.status === 'proposed');
            setIsPendingApproval(hasProposed);

            // Fetch Cost
            // Calculate Hash for Cost Trigger
            const currentHash = state.resources.map(r => r.id).sort().join(',');

            if (currentHash !== lastCostHash || isInitialLoad) {
                console.log("Architecture changed (or initial load), fetching cost...");
                fetchCost().then(setCostReport).catch(e => console.error(e));
                setLastCostHash(currentHash);
                setIsInitialLoad(false);
            }

            // Process Data
            const rawNodes: Node[] = state.resources.map((res) => {
                const isAffected = affectedNodeIds.has(res.id);
                const verificationStatus = nodeStatuses ? nodeStatuses[res.id] : undefined;

                // Group Detection
                const isGroup = ['aws_vpc', 'network_container', 'aws_subnet', 'network_zone', 'aws_security_group'].includes(res.type);

                let bgColor = res.status === 'planned' ? '#fff7ed' : '#fff';
                let borderColor = res.status === 'planned' ? '2px dashed #f59e0b' : '1px solid #777';

                if (isAffected) {
                    bgColor = '#fee2e2';
                    borderColor = '2px solid red';
                } else if (verificationStatus === 'success') {
                    bgColor = '#dcfce7';
                    borderColor = '2px solid #22c55e';
                } else if (verificationStatus === 'failed') {
                    bgColor = '#fee2e2';
                    borderColor = '2px solid #ef4444';
                }

                // Phase-based Styling
                if (state.graph_phase === 'intent') {
                    bgColor = '#f3e8ff';
                    borderColor = '2px dashed #a855f7';
                } else if (state.graph_phase === 'reasoned') {
                    bgColor = '#e0f2fe';
                    borderColor = '2px solid #0ea5e9';
                }

                if (res.status === 'proposed') {
                    bgColor = '#eff6ff';
                    borderColor = '2px dashed #3b82f6';
                }

                // Group Styling Overrides
                if (isGroup) {
                    bgColor = 'rgba(240, 249, 255, 0.05)'; // Very transparent blue
                    borderColor = '2px dashed rgba(59, 130, 246, 0.3)';
                }

                return {
                    id: res.id,
                    // --- PARENT MAPPING ---
                    // REVERTED: User reported issue with nodes merging/getting stuck.
                    // parentNode: res.parent_id ? res.parent_id : undefined,
                    // extent: 'parent',
                    // ----------------------
                    data: {
                        label: isGroup ? res.id : `${res.type}\n${res.id}`,
                        status: res.status,
                        type: res.type,
                        id: res.id,
                        description: res.description || "No description available.",
                        properties: res.properties
                    },
                    style: {
                        background: bgColor,
                        border: borderColor,
                        width: isGroup ? undefined : 150, // Let groups auto-size or be handled by layout
                        minWidth: isGroup ? 400 : 150,
                        minHeight: isGroup ? 300 : 80,
                        opacity: isGroup ? 0.9 : 1, // Groups slightly transparent
                        color: isAffected ? 'red' : ((isGroup) ? '#64748b' : 'black'),
                        fontSize: isGroup ? '14px' : '12px',
                        fontWeight: 'bold',
                        boxShadow: isGroup ? 'none' : '0px 4px 6px rgba(0,0,0,0.1)',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        padding: '10px',
                        zIndex: isGroup ? -1 : 1, // Groups behind
                    },
                    position: { x: 0, y: 0 }
                };
            });

            const rawEdges: Edge[] = state.edges.map((edge) => {
                const isAffected = affectedNodeIds.has(edge.source) || affectedNodeIds.has(edge.target);
                const isProposed = edge.relation === 'proposed' || (rawNodes.find(n => n.id === edge.source)?.data.status === 'proposed');

                return {
                    id: `e-${edge.source}-${edge.target}`,
                    source: edge.source,
                    target: edge.target,
                    animated: true,
                    label: edge.relation,
                    style: { stroke: isAffected ? 'red' : (isProposed ? '#3b82f6' : '#b1b1b7'), strokeDasharray: isProposed ? '5,5' : '0' },
                    labelStyle: { fill: isAffected ? 'red' : '#b1b1b7' }
                };
            });

            // Update Edges
            setEdges(rawEdges);

            // Update Nodes with Layout Logic
            setNodes((currentNodes) => {
                const nodeCountChanged = currentNodes.length !== state.resources.length;

                // Merge positions
                const nodesWithPositions = rawNodes.map(node => {
                    const existing = currentNodes.find(n => n.id === node.id);
                    if (existing) {
                        return { ...node, position: existing.position };
                    }
                    return node;
                });

                if (isInitialLoad || nodeCountChanged) {
                    const { nodes: layoutedNodes } = getLayoutedElements(nodesWithPositions, rawEdges);
                    return layoutedNodes;
                }

                return nodesWithPositions;
            });

        } catch (error) {
            console.error("Failed to fetch graph", error);
        }
    }, [affectedNodeIds, nodeStatuses, isInitialLoad, lastCostHash, setNodes, setEdges, overrideGraph]);

    useEffect(() => {
        refreshGraph();

        // Only poll if NOT in override mode
        if (!overrideGraph) {
            const interval = setInterval(refreshGraph, 5000); // Poll every 5s
            return () => clearInterval(interval);
        }
    }, [refreshGraph, overrideGraph]);

    // Context Menu State
    const [contextMenu, setContextMenu] = useState<{ x: number, y: number, id: string, type: 'node' | 'edge' } | null>(null);

    const onNodeClick: NodeMouseHandler = (event, node) => {
        event.preventDefault();
        event.stopPropagation(); // Prevent container click from closing menu
        setContextMenu({
            x: event.clientX,
            y: event.clientY,
            id: node.id,
            type: 'node'
        });
    };

    const onEdgeClick = (event: React.MouseEvent, edge: Edge) => {
        event.preventDefault();
        event.stopPropagation(); // Prevent container click from closing menu
        setContextMenu({
            x: event.clientX,
            y: event.clientY,
            id: edge.id,
            type: 'edge'
        });
    }

    const [selectedDetailNode, setSelectedDetailNode] = useState<any>(null);

    const handleAction = (action: 'details' | 'delete') => {
        if (!contextMenu) return;

        if (action === 'delete') {
            if (contextMenu.type === 'node') {
                console.log("Simulating blast radius for:", contextMenu.id);
                simulateBlastRadius(contextMenu.id).then(result => {
                    const impacted = new Set<string>(result.affected_nodes as string[]);
                    impacted.add(contextMenu.id);
                    setAffectedNodeIds(impacted);

                    if (onNodeSelected) {
                        onNodeSelected(contextMenu.id);
                    }
                });
            } else {
                alert("Impact Analysis for Edge Deletion is coming in v2.0!");
            }
        } else if (action === 'details') {
            if (contextMenu.type === 'node') {
                const node = nodes.find(n => n.id === contextMenu.id);
                if (node) setSelectedDetailNode(node.data);
            } else {
                const edge = edges.find(e => e.id === contextMenu.id);
                if (edge) alert(`Connection Details:\n\nSource: ${edge.source}\nTarget: ${edge.target}\nRelation: ${edge.label}`);
            }
        }
        setContextMenu(null);
    };

    return (
        <div style={{ width: '100%', height: '600px', border: '1px solid #ccc', borderRadius: '8px', position: 'relative' }} onClick={() => setContextMenu(null)}>
            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onNodeClick={onNodeClick}
                onEdgeClick={onEdgeClick}
                fitView
            >
                <Background />
                <Controls />
            </ReactFlow>

            {/* View Code Button */}
            {terraformCode && (
                <button
                    onClick={(e) => { e.stopPropagation(); setShowCode(true); }}
                    style={{
                        position: 'absolute',
                        top: '10px',
                        right: '10px',
                        zIndex: 10,
                        backgroundColor: '#3b82f6',
                        color: 'white',
                        padding: '6px 12px',
                        borderRadius: '6px',
                        fontSize: '12px',
                        fontWeight: 'bold',
                        cursor: 'pointer',
                        border: 'none',
                        boxShadow: '0 2px 4px rgba(0,0,0,0.2)'
                    }}
                >
                    &lt;/&gt; View Code
                </button>
            )}

            {/* Code Modal */}
            {showCode && terraformCode && (
                <div style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: '100%',
                    backgroundColor: 'rgba(0,0,0,0.85)',
                    zIndex: 2000,
                    padding: '20px',
                    display: 'flex',
                    flexDirection: 'column',
                    backdropFilter: 'blur(4px)'
                }} onClick={(e) => e.stopPropagation()}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px', color: 'white' }}>
                        <span style={{ fontWeight: 'bold' }}>Generated Terraform Code</span>
                        <button
                            onClick={() => setShowCode(false)}
                            style={{ background: 'none', border: 'none', color: '#cbd5e1', cursor: 'pointer', fontSize: '14px' }}
                        >
                            ✕ Close
                        </button>
                    </div>
                    <div style={{
                        flex: 1,
                        overflow: 'auto',
                        backgroundColor: '#1e293b',
                        color: '#e2e8f0',
                        padding: '16px',
                        borderRadius: '8px',
                        fontSize: '12px',
                        fontFamily: 'monospace',
                        border: '1px solid #334155'
                    }}>
                        <pre>{terraformCode}</pre>
                    </div>
                </div>
            )}

            {/* Pending Approval Banner (Legacy - Disabled for Unified Workflow) */}
            {/*
                isPendingApproval && (
                    <div style={{
                        position: 'absolute',
                        top: '10px',
                        left: '50%',
                        transform: 'translateX(-50%)',
                        backgroundColor: '#eff6ff',
                        border: '1px solid #3b82f6',
                        color: '#1e40af',
                        padding: '8px 16px',
                        borderRadius: '20px',
                        fontWeight: 'bold',
                        fontSize: '14px',
                        zIndex: 10,
                        boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '12px'
                    }}>
                        <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span style={{ fontSize: '18px' }}>🤖</span> AI Proposed Changes
                        </span>
                        <div style={{ display: 'flex', gap: '8px' }}>
                            <button
                                onClick={async (e) => {
                                    e.stopPropagation();
                                    setIsProcessing(true);
                                    try {
                                        await approvePlan();
                                        await refreshGraph();
                                    } finally {
                                        setIsProcessing(false);
                                    }
                                }}
                                disabled={isProcessing}
                                className={`flex items-center gap-1 px-3 py-1 bg-green-600 text-white rounded-full text-xs transition-colors ${isProcessing ? 'opacity-50 cursor-not-allowed' : 'hover:bg-green-700'}`}
                            >
                                <Check size={14} /> {isProcessing ? 'Saving...' : 'Accept'}
                            </button>
                            <button
                                onClick={async (e) => {
                                    e.stopPropagation();
                                    setIsProcessing(true);
                                    try {
                                        await rejectPlan();
                                        await refreshGraph();
                                    } finally {
                                        setIsProcessing(false);
                                    }
                                }}
                                disabled={isProcessing}
                                className={`flex items-center gap-1 px-3 py-1 bg-red-600 text-white rounded-full text-xs transition-colors ${isProcessing ? 'opacity-50 cursor-not-allowed' : 'hover:bg-red-700'}`}
                            >
                                <X size={14} /> {isProcessing ? 'Reverting...' : 'Reject'}
                            </button>
                        </div>
                    </div>
                )
            */}

            {/* Cost Badge */}
            {costReport && (
                <div
                    onClick={() => setShowCostModal(true)}
                    style={{
                        position: 'absolute',
                        top: '10px',
                        left: '10px', // Top Left to balance View Code which is Top Right
                        zIndex: 10,
                        backgroundColor: '#ecfdf5', // emerald-50
                        border: '1px solid #10b981', // emerald-500
                        color: '#047857', // emerald-700
                        padding: '6px 12px',
                        borderRadius: '6px',
                        fontSize: '12px',
                        fontWeight: 'bold',
                        cursor: 'pointer',
                        boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px'
                    }}
                >
                    <DollarSign size={14} /> Est. ${costReport.total_monthly_cost.toFixed(2)}/mo
                </div>
            )}

            {/* Cost Breakdown Modal */}
            {showCostModal && costReport && (
                <div style={{
                    position: 'fixed',
                    top: 0,
                    left: 0,
                    width: '100vw',
                    height: '100vh',
                    backgroundColor: 'rgba(0,0,0,0.5)',
                    zIndex: 3000, // Higher than code modal
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    backdropFilter: 'blur(2px)'
                }} onClick={() => setShowCostModal(false)}>
                    <div style={{
                        backgroundColor: '#fff',
                        borderRadius: '12px',
                        width: '500px',
                        maxHeight: '80vh',
                        display: 'flex',
                        flexDirection: 'column',
                        overflow: 'hidden',
                        boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)'
                    }} onClick={e => e.stopPropagation()}>
                        <div style={{ padding: '20px', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <h3 style={{ fontSize: '18px', fontWeight: 'bold', color: '#1e293b' }}>Monthly Cost Estimate</h3>
                            <button onClick={() => setShowCostModal(false)} style={{ color: '#64748b' }}>✕</button>
                        </div>
                        <div style={{ padding: '20px', overflowY: 'auto' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px', fontSize: '24px', fontWeight: 'bold', color: '#10b981' }}>
                                <span>Total</span>
                                <span>${costReport.total_monthly_cost.toFixed(2)}</span>
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                                {costReport.breakdown.map((item, i) => (
                                    <div key={i} style={{ padding: '12px', backgroundColor: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 'bold', marginBottom: '4px', color: '#334155' }}>
                                            <span>{item.resource_type} ({item.resource_id})</span>
                                            <span>${item.estimated_cost.toFixed(2)}</span>
                                        </div>
                                        <div style={{ fontSize: '12px', color: '#64748b' }}>{item.explanation}</div>
                                    </div>
                                ))}
                            </div>
                            <div style={{ marginTop: '20px', fontSize: '10px', color: '#94a3b8', textAlign: 'center' }}>
                                {costReport.disclaimer}
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Context Menu Overlay */}
            {
                contextMenu && (
                    <div
                        style={{
                            position: 'fixed',
                            top: contextMenu.y,
                            left: contextMenu.x,
                            zIndex: 1000,
                            backgroundColor: '#1e293b',
                            border: '1px solid #475569',
                            borderRadius: '6px',
                            padding: '4px',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '2px',
                            boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)'
                        }}
                        onClick={(e) => e.stopPropagation()}
                    >
                        <button
                            onClick={() => handleAction('details')}
                            className="px-4 py-2 text-sm text-slate-200 hover:bg-slate-700 rounded text-left"
                        >
                            View {contextMenu.type === 'node' ? 'Resource' : 'Connection'} Details
                        </button>
                        <button
                            onClick={() => handleAction('delete')}
                            className="px-4 py-2 text-sm text-red-400 hover:bg-red-900/30 rounded text-left"
                        >
                            Simulate {contextMenu.type === 'node' ? 'Deletion' : 'One Cut'}
                        </button>
                    </div>
                )
            }
            {/* Resource Details Modal */}
            {selectedDetailNode && (
                <div style={{
                    position: 'fixed',
                    top: 0,
                    left: 0,
                    width: '100vw',
                    height: '100vh',
                    backgroundColor: 'rgba(0,0,0,0.5)',
                    zIndex: 3000,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    backdropFilter: 'blur(2px)'
                }} onClick={() => setSelectedDetailNode(null)}>
                    <div style={{
                        backgroundColor: '#1e293b',
                        color: '#f8fafc',
                        borderRadius: '12px',
                        width: '600px',
                        maxHeight: '80vh',
                        display: 'flex',
                        flexDirection: 'column',
                        overflow: 'hidden',
                        border: '1px solid #334155',
                        boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)'
                    }} onClick={e => e.stopPropagation()}>
                        <div style={{ padding: '20px', borderBottom: '1px solid #334155', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#0f172a' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <div style={{ padding: '8px', backgroundColor: 'rgba(59, 130, 246, 0.2)', borderRadius: '8px' }}>
                                    <span style={{ fontSize: '20px' }}>📦</span>
                                </div>
                                <div>
                                    <h3 style={{ fontSize: '16px', fontWeight: 'bold' }}>{selectedDetailNode.id}</h3>
                                    <div style={{ fontSize: '12px', color: '#94a3b8', fontFamily: 'monospace' }}>{selectedDetailNode.type}</div>
                                </div>
                            </div>
                            <button onClick={() => setSelectedDetailNode(null)} style={{ color: '#94a3b8', background: 'none', border: 'none', cursor: 'pointer', fontSize: '18px' }}>✕</button>
                        </div>

                        <div style={{ padding: '24px', overflowY: 'auto' }}>
                            {/* Description Section */}
                            <div style={{ marginBottom: '24px' }}>
                                <h4 style={{ fontSize: '12px', textTransform: 'uppercase', fontWeight: 'bold', color: '#64748b', marginBottom: '8px', letterSpacing: '0.05em' }}>Description</h4>
                                <p style={{ fontSize: '14px', color: '#cbd5e1', lineHeight: '1.6', backgroundColor: 'rgba(30, 41, 59, 0.5)', padding: '12px', borderRadius: '8px', border: '1px solid #334155' }}>
                                    {selectedDetailNode.description}
                                </p>
                            </div>

                            {/* Configuration Table */}
                            <div>
                                <h4 style={{ fontSize: '12px', textTransform: 'uppercase', fontWeight: 'bold', color: '#64748b', marginBottom: '8px', letterSpacing: '0.05em' }}>Configuration</h4>
                                <div style={{ border: '1px solid #334155', borderRadius: '8px', overflow: 'hidden' }}>
                                    <table style={{ width: '100%', fontSize: '14px', borderCollapse: 'collapse' }}>
                                        <thead style={{ backgroundColor: '#1e293b', color: '#94a3b8', textTransform: 'uppercase', fontSize: '12px' }}>
                                            <tr>
                                                <th style={{ padding: '8px 16px', borderBottom: '1px solid #334155', textAlign: 'left' }}>Property</th>
                                                <th style={{ padding: '8px 16px', borderBottom: '1px solid #334155', textAlign: 'left' }}>Value</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {selectedDetailNode.properties && Object.entries(selectedDetailNode.properties).map(([key, value], i) => (
                                                <tr key={key} style={{ borderBottom: '1px solid #334155', backgroundColor: i % 2 === 0 ? '#0f172a' : '#1e293b' }}>
                                                    <td style={{ padding: '8px 16px', fontFamily: 'monospace', color: '#93c5fd' }}>{key}</td>
                                                    <td style={{ padding: '8px 16px', color: '#cbd5e1', fontFamily: 'monospace', wordBreak: 'break-all' }}>
                                                        {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                                                    </td>
                                                </tr>
                                            ))}
                                            {(!selectedDetailNode.properties || Object.keys(selectedDetailNode.properties).length === 0) && (
                                                <tr>
                                                    <td colSpan={2} style={{ padding: '16px', textAlign: 'center', color: '#64748b', fontStyle: 'italic' }}>No specific configuration properties.</td>
                                                </tr>
                                            )}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            )}

        </div >
    );
}
