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
}

export default function GraphVisualizer({ onNodeSelected }: GraphVisualizerProps) {
    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
    const [affectedNodeIds, setAffectedNodeIds] = useState<Set<string>>(new Set());

    // Poll for graph updates (Phase 1 simplistic approach)
    // In real implementation, we might use WebSockets or just refresh on action
    const refreshGraph = useCallback(async () => {
        try {
            const state = await fetchGraph();
            if (!state) return;

            // 1. Create Raw Nodes (without position)
            const rawNodes: Node[] = state.resources.map((res) => {
                const isAffected = affectedNodeIds.has(res.id);
                return {
                    id: res.id,
                    position: { x: 0, y: 0 }, // Placeholder
                    data: { label: `${res.type}\n${res.id}` },
                    style: {
                        background: isAffected ? '#fee2e2' : (res.status === 'planned' ? '#f0f9ff' : '#fff'),
                        border: isAffected ? '2px solid red' : (res.status === 'deleted' ? '2px solid red' : (res.status === 'planned' ? '2px dashed #3b82f6' : '1px solid #777')),
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
        } catch (error) {
            console.error("Failed to fetch graph", error);
        }
    }, [setNodes, setEdges, affectedNodeIds]);

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

            {/* Context Menu Overlay */}
            {contextMenu && (
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
            )}
        </div>
    );
}
