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
import { fetchGraph, GraphState, simulateBlastRadius } from '../lib/api';

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
}

export default function GraphVisualizer({ onNodeSelected, nodeStatuses, terraformCode }: GraphVisualizerProps) {
    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
    const [showCode, setShowCode] = useState(false);

    const [affectedNodeIds, setAffectedNodeIds] = useState<Set<string>>(new Set());
    const [isPendingApproval, setIsPendingApproval] = useState(false);

    // Poll for graph updates (Phase 1 simplistic approach)
    // In real implementation, we might use WebSockets or just refresh on action
    const refreshGraph = useCallback(async () => {
        try {
            const state = await fetchGraph();
            if (!state) return;

            // 1. Create Raw Nodes (without position)
            const rawNodes: Node[] = state.resources.map((res) => {
                const isAffected = affectedNodeIds.has(res.id);
                // Check granular verification status
                const verificationStatus = nodeStatuses ? nodeStatuses[res.id] : undefined;

                let bgColor = res.status === 'planned' ? '#fff7ed' : '#fff';
                let borderColor = res.status === 'planned' ? '2px dashed #f59e0b' : '1px solid #777';

                if (isAffected) {
                    bgColor = '#fee2e2';
                    borderColor = '2px solid red';
                } else if (verificationStatus === 'success') {
                    bgColor = '#dcfce7'; // green-100
                    borderColor = '2px solid #22c55e'; // green-500
                } else if (verificationStatus === 'failed') {
                    bgColor = '#fee2e2'; // red-100
                    borderColor = '2px solid #ef4444'; // red-500
                }

                return {
                    id: res.id,
                    position: { x: 0, y: 0 }, // Placeholder
                    data: { label: `${res.type}\n${res.id}`, status: res.status },
                    style: {
                        background: bgColor,
                        border: borderColor,
                        width: 150,
                        color: isAffected ? 'red' : 'black',
                        fontSize: '12px',
                        fontWeight: 'bold',
                        boxShadow: '0px 4px 6px rgba(0,0,0,0.1)' // Add some depth
                    }
                };
            });

            const rawEdges: Edge[] = state.edges.map((edge, i) => {
                const isAffected = affectedNodeIds.has(edge.source) || affectedNodeIds.has(edge.target);
                return {
                    id: `e-${i}`,
                    source: edge.source,
                    target: edge.target,
                    animated: true,
                    label: edge.relation,
                    style: { stroke: isAffected ? 'red' : '#b1b1b7' },
                    labelStyle: { fill: isAffected ? 'red' : '#b1b1b7' }
                };
            });

            // 2. Apply Dagre Layout
            const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(rawNodes, rawEdges);

            setNodes(layoutedNodes);
            setEdges(layoutedEdges);

            // Check for pending changes
            const hasPlanned = state.resources.some(r => r.status === 'planned');
            setIsPendingApproval(hasPlanned);
        } catch (error) {
            console.error("Failed to fetch graph", error);
        }
    }, [setNodes, setEdges, affectedNodeIds, nodeStatuses]);

    useEffect(() => {
        refreshGraph();
        const interval = setInterval(refreshGraph, 5000); // Poll every 5s
        return () => clearInterval(interval);
    }, [refreshGraph]);

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
                if (node) alert(`Resource Details:\n\n${JSON.stringify(node.data, null, 2)}`);
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

            {/* Pending Approval Banner */}
            {
                isPendingApproval && (
                    <div style={{
                        position: 'absolute',
                        top: '10px',
                        left: '50%',
                        transform: 'translateX(-50%)',
                        backgroundColor: '#fff7ed', // orange-50
                        border: '1px solid #f97316', // orange-500
                        color: '#c2410c', // orange-700
                        padding: '8px 16px',
                        borderRadius: '20px',
                        fontWeight: 'bold',
                        fontSize: '14px',
                        zIndex: 10,
                        boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px'
                    }}>
                        <span style={{ fontSize: '18px' }}>⚠️</span> Plan Pending Approval
                    </div>
                )
            }

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
        </div >
    );
}
