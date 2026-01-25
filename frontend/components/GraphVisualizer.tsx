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

    const onNodeClick: NodeMouseHandler = async (_, node) => {
        try {
            console.log("Simulating blast radius for:", node.id);
            const result = await simulateBlastRadius(node.id);
            const impacted = new Set<string>(result.affected_nodes as string[]);
            impacted.add(node.id); // Highlight selected node too
            setAffectedNodeIds(impacted);

            // Notify parent to explain the blast radius
            if (onNodeSelected) {
                onNodeSelected(node.id);
            }

            // Trigger immediate refresh to show styling
            // refreshGraph will happen naturally on next poll, but we force updating nodes locally if we wanted
            // but relying on poll/effect is cleaner if we just update state.
        } catch (e) {
            console.error("Blast radius failed", e);
        }
    };

    return (
        <div style={{ width: '100%', height: '600px', border: '1px solid #ccc', borderRadius: '8px' }}>
            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onNodeClick={onNodeClick}
                fitView
            >
                <Background />
                <Controls />
            </ReactFlow>
        </div>
    );
}
