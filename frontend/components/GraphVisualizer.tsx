"use client";

import React, { useCallback, useEffect, useState, useMemo } from 'react';
import ReactFlow, {
    Node,
    Edge,
    Controls,
    Background,
    useNodesState,
    useEdgesState,
    NodeMouseHandler,
    MarkerType,
    Handle,
    Position,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { fetchGraph, GraphState, simulateBlastRadius, fetchCost, CostReport, generateGraphLayout } from '../lib/api';
import { DollarSign, Layers, Box, Database, Globe, Shield, Activity, Archive, Cloud, Server, Router, Lock, Zap, Sparkles, Eye, EyeOff } from 'lucide-react';
import dagre from 'dagre';

/* -------------------------------------------------------------------------- */
/*                                CONSTANTS                                   */
/* -------------------------------------------------------------------------- */

const RESOURCE_WIDTH = 180;
const RESOURCE_HEIGHT = 60;
const SUBNET_PADDING = 30;
const VPC_PADDING = 40;
const GRID_GAP = 15;
const GRID_COLUMNS = 2; // For resources inside subnets

// AWS Architecture Colors
const COLORS = {
    VPC_BORDER: '#8c8c8c',
    VPC_BG: 'rgba(255, 255, 255, 0.05)',
    SUBNET_PUBLIC_BORDER: '#248814',
    SUBNET_PUBLIC_BG: 'rgba(240, 253, 244, 0.3)',
    SUBNET_PRIVATE_BORDER: '#0073bb',
    SUBNET_PRIVATE_BG: 'rgba(239, 246, 255, 0.3)',
    EDGE: '#5d5d5d',
    // Resource colors by type
    COMPUTE: '#FF9900', // Orange
    DATABASE: '#3B48CC', // Blue
    STORAGE: '#569A31', // Green
    NETWORKING: '#8C4FFF', // Purple
    DEFAULT: '#232F3E' // Dark
};

/* -------------------------------------------------------------------------- */
/*                          LAYOUT ENGINE                                     */
/* -------------------------------------------------------------------------- */

interface LayoutNode {
    id: string;
    type: string;
    data: any;
    position: { x: number; y: number };
    style?: any;
    parentNode?: string;
    extent?: 'parent';
    properties?: any;
    width?: number;
    height?: number;
}

interface DimensionInfo {
    width: number;
    height: number;
    children: LayoutNode[];
}

/**
 * Bottom-up dimension calculator:
 * 1. Resources have fixed dimensions
 * 2. Subnets are sized based on grid layout of resources
 * 3. VPCs are sized based on grid layout of subnets
 */
const calculateGroupDimensions = (
    resources: any[],
    subnets: any[],
    vpcs: any[],
    cleanRef: (ref: string) => string
): Map<string, DimensionInfo> => {
    const dimMap = new Map<string, DimensionInfo>();

    // 1. Calculate Subnet Dimensions
    subnets.forEach(subnet => {
        const subnetResources = resources.filter(
            r => cleanRef(r.properties?.subnet_id) === subnet.id
        );

        if (subnetResources.length === 0) {
            // Empty subnet
            dimMap.set(subnet.id, {
                width: RESOURCE_WIDTH + SUBNET_PADDING * 2,
                height: 100,
                children: []
            });
            return;
        }

        const rows = Math.ceil(subnetResources.length / GRID_COLUMNS);
        const cols = Math.min(subnetResources.length, GRID_COLUMNS);

        const contentWidth = cols * RESOURCE_WIDTH + (cols - 1) * GRID_GAP;
        const contentHeight = rows * RESOURCE_HEIGHT + (rows - 1) * GRID_GAP;

        dimMap.set(subnet.id, {
            width: contentWidth + SUBNET_PADDING * 2,
            height: contentHeight + SUBNET_PADDING * 2 + 20, // +20 for label
            children: subnetResources
        });
    });

    // 2. Calculate VPC Dimensions
    vpcs.forEach(vpc => {
        const vpcSubnets = subnets.filter(
            s => cleanRef(s.properties?.vpc_id) === vpc.id
        );

        if (vpcSubnets.length === 0) {
            dimMap.set(vpc.id, {
                width: 400,
                height: 300,
                children: []
            });
            return;
        }

        // Stack subnets vertically within VPC (by AZ)
        const azMap: Record<string, any[]> = {};
        vpcSubnets.forEach(subnet => {
            const az = subnet.properties?.availability_zone || 'unknown';
            if (!azMap[az]) azMap[az] = [];
            azMap[az].push(subnet);
        });

        const azCount = Object.keys(azMap).length;
        let maxWidth = 0;
        let totalHeight = 0;

        Object.values(azMap).forEach(azSubnets => {
            let azHeight = 0;
            let azWidth = 0;

            azSubnets.forEach(subnet => {
                const subnetDim = dimMap.get(subnet.id)!;
                azHeight += subnetDim.height + GRID_GAP;
                azWidth = Math.max(azWidth, subnetDim.width);
            });

            totalHeight = Math.max(totalHeight, azHeight);
            maxWidth += azWidth + GRID_GAP;
        });

        dimMap.set(vpc.id, {
            width: maxWidth + VPC_PADDING * 2,
            height: totalHeight + VPC_PADDING * 2 + 30, // +30 for header
            children: vpcSubnets
        });
    });

    return dimMap;
};

/**
 * Recursive Layout Engine using Dagre (LR) for top-level flow
 */
/**
 * Helper to clean HCL references like "${aws_vpc.main.id}" -> "main"
 * Also handles direct IDs.
 */
const cleanRef = (ref: string): string => {
    if (!ref) return '';
    if (ref.startsWith('${') && ref.endsWith('}')) {
        // format: ${type.id.attr}
        const parts = ref.slice(2, -1).split('.');
        if (parts.length >= 2) return parts[1];
    }
    return ref;
};

const calculateProfessionalLayout = (rawNodes: any[], rawEdges: any[]): LayoutNode[] => {
    const layoutNodes: LayoutNode[] = [];

    const vpcs = rawNodes.filter(n => n.type === 'aws_vpc');
    const subnets = rawNodes.filter(n => n.type === 'aws_subnet');
    const resources = rawNodes.filter(
        n => !['aws_vpc', 'aws_subnet'].includes(n.type)
    );

    // Categorize resources
    const subnetResources = resources.filter(r => r.properties?.subnet_id);
    const globalResources = resources.filter(
        r => !r.properties?.subnet_id &&
            !['aws_s3_bucket', 'aws_dynamodb_table', 'aws_cloudfront_distribution'].includes(r.type)
    );
    const edgeResources = resources.filter(r =>
        ['aws_s3_bucket', 'aws_dynamodb_table', 'aws_cloudfront_distribution'].includes(r.type)
    );

    // Calculate dimensions bottom-up
    // We need to pass a "resolver" or clean the references first
    // For simplicity, we'll just fix the comparison inside calculateGroupDimensions logic if needed
    // But calculateGroupDimensions is separate. Let's update it separately or move it inside if needed. 
    // Actually, let's just make cleanRef available to it or pass cleaned copies.

    // Better strategy: Fix the calculateGroupDimensions call by ensuring it can match.
    // BUT calculateGroupDimensions is OUTSIDE this function scope in the original file. 
    // I need to update calculateGroupDimensions as well.

    const dimMap = calculateGroupDimensions(
        subnetResources,
        subnets,
        vpcs,
        cleanRef // Pass the helper down
    );

    // --- TOP-LEVEL DAGRE LAYOUT ---
    const dagreGraph = new dagre.graphlib.Graph();
    dagreGraph.setDefaultEdgeLabel(() => ({}));
    dagreGraph.setGraph({ rankdir: 'LR', nodesep: 80, ranksep: 150 });

    // Add VPCs
    vpcs.forEach(vpc => {
        const dim = dimMap.get(vpc.id)!;
        dagreGraph.setNode(vpc.id, { width: dim.width, height: dim.height });
    });

    // Add Global
    globalResources.forEach(res => {
        dagreGraph.setNode(res.id, { width: RESOURCE_WIDTH, height: RESOURCE_HEIGHT });
    });

    // Add Edge Resources
    edgeResources.forEach(res => {
        dagreGraph.setNode(res.id, { width: RESOURCE_WIDTH, height: RESOURCE_HEIGHT });
    });

    const getTopLevelParent = (nodeId: string): string => {
        const node = rawNodes.find(n => n.id === nodeId);
        if (!node) return nodeId;

        if (node.type === 'aws_vpc') return nodeId;
        if (globalResources.find(r => r.id === nodeId)) return nodeId;
        if (edgeResources.find(r => r.id === nodeId)) return nodeId;

        if (node.properties?.subnet_id) {
            const cleanSubnetId = cleanRef(node.properties.subnet_id);
            const subnet = subnets.find(s => s.id === cleanSubnetId);
            if (subnet?.properties?.vpc_id) {
                return cleanRef(subnet.properties.vpc_id);
            }
        }

        return nodeId;
    };

    // Add edges to Dagre (mapped to top-level containers)
    const topLevelEdges = new Set<string>();
    rawEdges.forEach(edge => {
        const sourceTop = getTopLevelParent(edge.source);
        const targetTop = getTopLevelParent(edge.target);

        // Only add if both nodes exist in Dagre and it's not a self-loop
        if (sourceTop !== targetTop &&
            dagreGraph.hasNode(sourceTop) &&
            dagreGraph.hasNode(targetTop)) {
            const edgeKey = `${sourceTop}->${targetTop}`;
            if (!topLevelEdges.has(edgeKey)) {
                dagreGraph.setEdge(sourceTop, targetTop);
                topLevelEdges.add(edgeKey);
            }
        }
    });

    // Run Dagre layout
    dagre.layout(dagreGraph);

    // --- BUILD VPC NODES WITH CHILDREN ---
    vpcs.forEach(vpc => {
        const vpcDim = dimMap.get(vpc.id)!;
        const vpcDagreNode = dagreGraph.node(vpc.id);

        // VPC Group Node
        layoutNodes.push({
            id: vpc.id,
            type: 'group',
            data: {
                label: `VPC: ${vpc.properties?.tags?.Name || vpc.id}`,
                variant: 'vpc'
            },
            position: {
                x: vpcDagreNode.x - vpcDim.width / 2,
                y: vpcDagreNode.y - vpcDim.height / 2
            },
            style: {
                width: vpcDim.width,
                height: vpcDim.height,
                zIndex: 0
            }
        });

        // Get subnets in this VPC
        const vpcSubnets = subnets.filter(s => cleanRef(s.properties?.vpc_id) === vpc.id);

        // Group by AZ
        const azMap: Record<string, any[]> = {};
        vpcSubnets.forEach(subnet => {
            const az = subnet.properties?.availability_zone || 'unknown';
            if (!azMap[az]) azMap[az] = [];
            azMap[az].push(subnet);
        });

        let currentX = VPC_PADDING;
        Object.entries(azMap).forEach(([az, azSubnets]) => {
            let currentY = VPC_PADDING + 30; // Space for AZ label
            let maxWidth = 0;

            // AZ Header
            layoutNodes.push({
                id: `header-${vpc.id}-${az}`,
                type: 'group-label',
                data: { label: az },
                position: { x: currentX, y: VPC_PADDING },
                parentNode: vpc.id,
                extent: 'parent',
                style: { zIndex: 1 }
            } as any);

            azSubnets.forEach(subnet => {
                const subnetDim = dimMap.get(subnet.id)!;

                // Subnet Group Node
                layoutNodes.push({
                    id: subnet.id,
                    type: 'group',
                    data: {
                        label: subnet.properties?.tags?.Name || subnet.id,
                        subLabel: subnet.properties?.cidr_block,
                        variant: subnet.properties?.map_public_ip_on_launch ? 'public' : 'private'
                    },
                    position: { x: currentX, y: currentY },
                    parentNode: vpc.id,
                    extent: 'parent',
                    style: {
                        width: subnetDim.width,
                        height: subnetDim.height,
                        zIndex: 2
                    }
                } as any);

                // Resources inside Subnet (Grid Layout)
                const subnetResources = dimMap.get(subnet.id)!.children;
                subnetResources.forEach((res, idx) => {
                    const row = Math.floor(idx / GRID_COLUMNS);
                    const col = idx % GRID_COLUMNS;

                    layoutNodes.push({
                        ...res,
                        parentNode: subnet.id,
                        extent: 'parent',
                        position: {
                            x: SUBNET_PADDING + col * (RESOURCE_WIDTH + GRID_GAP),
                            y: SUBNET_PADDING + 20 + row * (RESOURCE_HEIGHT + GRID_GAP)
                        },
                        style: { ...res.style, zIndex: 10 }
                    });
                });

                currentY += subnetDim.height + GRID_GAP;
                maxWidth = Math.max(maxWidth, subnetDim.width);
            });

            currentX += maxWidth + GRID_GAP * 2;
        });
    });

    // --- GLOBAL RESOURCES (positioned by Dagre) ---
    globalResources.forEach(res => {
        const dagreNode = dagreGraph.node(res.id);
        if (dagreNode) {
            layoutNodes.push({
                ...res,
                position: {
                    x: dagreNode.x - RESOURCE_WIDTH / 2,
                    y: dagreNode.y - RESOURCE_HEIGHT / 2
                },
                style: { ...res.style, zIndex: 10 }
            });
        }
    });

    // --- EDGE RESOURCES (positioned by Dagre) ---
    edgeResources.forEach(res => {
        const dagreNode = dagreGraph.node(res.id);
        if (dagreNode) {
            layoutNodes.push({
                ...res,
                position: {
                    x: dagreNode.x - RESOURCE_WIDTH / 2,
                    y: dagreNode.y - RESOURCE_HEIGHT / 2
                },
                style: { ...res.style, zIndex: 10 }
            });
        }
    });

    return layoutNodes;
};

/* -------------------------------------------------------------------------- */
/*                              MAIN COMPONENT                                */
/* -------------------------------------------------------------------------- */

interface GraphVisualizerProps {
    onNodeSelected?: (nodeId: string) => void;
    nodeStatuses?: Record<string, string>;
    terraformCode?: string | null;
    overrideGraph?: GraphState | null;
}

export default function GraphVisualizer({ onNodeSelected, nodeStatuses, terraformCode, overrideGraph }: GraphVisualizerProps) {
    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState([]);

    // AI Layout State
    const [layoutMode, setLayoutMode] = useState<'default' | 'professional'>('default');
    const [layoutOverrides, setLayoutOverrides] = useState<Record<string, any>>({});
    const [isRefactoring, setIsRefactoring] = useState(false);
    const [showDetails, setShowDetails] = useState(false); // New State

    const [isInitialLoad, setIsInitialLoad] = useState(true);
    const [costReport, setCostReport] = useState<CostReport | null>(null);
    const [showCostModal, setShowCostModal] = useState(false);
    const [lastCostHash, setLastCostHash] = useState<string>("");
    const [affectedNodeIds, setAffectedNodeIds] = useState<Set<string>>(new Set());
    const [rawState, setRawState] = useState<GraphState | null>(null);
    const [showCode, setShowCode] = useState(false);
    const [contextMenu, setContextMenu] = useState<any>(null);
    const [selectedDetailNode, setSelectedDetailNode] = useState<any>(null);

    const refreshGraph = useCallback(async () => {
        try {
            let state = overrideGraph;
            if (!state) state = await fetchGraph();
            if (!state) return;
            setRawState(state);

            setRawState(state);

            // Manual Cost Calculation Only (as requested)
            if (isInitialLoad) {
                setIsInitialLoad(false);
            }
        } catch (error) {
            console.error("Failed to fetch graph", error);
        }
    }, [overrideGraph, isInitialLoad]);

    useEffect(() => {
        if (!rawState) return;

        // Prepare Nodes with styling and icons
        const allRawNodes = rawState.resources.map(res => {
            const isAffected = affectedNodeIds.has(res.id);

            // Determine color based on resource type
            let headerColor = COLORS.DEFAULT;
            if (res.type.includes('instance') || res.type.includes('ecs') || res.type.includes('lambda')) {
                headerColor = COLORS.COMPUTE;
            } else if (res.type.includes('rds') || res.type.includes('db') || res.type.includes('dynamodb')) {
                headerColor = COLORS.DATABASE;
            } else if (res.type.includes('s3') || res.type.includes('ebs')) {
                headerColor = COLORS.STORAGE;
            } else if (res.type.includes('vpc') || res.type.includes('subnet') || res.type.includes('lb') || res.type.includes('gateway')) {
                headerColor = COLORS.NETWORKING;
            }

            let Icon = Box;
            if (res.type.includes('ecs') || res.type.includes('instance')) Icon = Server;
            if (res.type.includes('rds') || res.type.includes('db')) Icon = Database;
            if (res.type.includes('s3')) Icon = Archive;
            if (res.type.includes('lb')) Icon = Activity;
            if (res.type.includes('cloudfront')) Icon = Globe;
            if (res.type.includes('vpc')) Icon = Cloud;
            if (res.type.includes('security')) Icon = Shield;
            if (res.type.includes('route') || res.type.includes('nat') || res.type.includes('gateway')) Icon = Router;
            if (res.type.includes('lambda')) Icon = Zap;

            return {
                id: res.id,
                type: res.type,
                data: {
                    label: res.id,
                    type: res.type,
                    icon: <Icon size={16} />,
                    headerColor,
                    status: res.status,
                    properties: res.properties,
                    isAffected
                },
                style: {
                    width: RESOURCE_WIDTH,
                    height: RESOURCE_HEIGHT
                },
                properties: res.properties,
                parent_id: res.parent_id
            };
        });

        // Calculate Default Layout
        let finalNodes = calculateProfessionalLayout(allRawNodes, rawState.edges);

        // AI Override Logic with Filtering
        if (layoutMode === 'professional' && Object.keys(layoutOverrides).length > 0) {
            finalNodes = finalNodes.map(node => {
                const override = layoutOverrides[node.id];
                if (override) {
                    // NEW: Filter Hidden Nodes unless Show Details is ON
                    if (override.hidden && !showDetails) return null;

                    // Sanitize Parent ID (Handle 'null' string or missing parent)
                    let parentId = override.parentId;
                    if (parentId === 'null') parentId = undefined;

                    // Safety: If parent is hidden/missing, detach to prevent crash
                    if (parentId && (!layoutOverrides[parentId] || (layoutOverrides[parentId].hidden && !showDetails))) {
                        parentId = undefined;
                    }

                    return {
                        ...node,
                        position: { x: override.x, y: override.y },
                        style: {
                            ...node.style,
                            width: override.width || node.style.width,
                            height: override.height || node.style.height
                        },
                        parentNode: parentId,
                        extent: parentId ? 'parent' : undefined,
                    };
                }
                return node;
            }).filter(Boolean) as any[]; // Important: Filter nulls
        }

        // Create a Set of valid node IDs for O(1) lookup
        const validNodeIds = new Set(finalNodes.map(n => n.id));

        const finalEdges = rawState.edges
            .filter(e => validNodeIds.has(e.source) && validNodeIds.has(e.target)) // NEW: Filter dangling edges
            .map(e => ({
                id: `e-${e.source}-${e.target}`,
                source: e.source,
                target: e.target,
                type: layoutMode === 'professional' ? 'step' : 'smoothstep', // Orthogonal for pro mode
                animated: false,
                style: { stroke: COLORS.EDGE, strokeWidth: 1.5, zIndex: 999 },
                markerEnd: { type: MarkerType.ArrowClosed, color: COLORS.EDGE },
                zIndex: 999
            }));

        setNodes(finalNodes);
        setEdges(finalEdges);
    }, [rawState, affectedNodeIds, layoutMode, layoutOverrides, showDetails]);

    useEffect(() => {
        refreshGraph();
        if (!overrideGraph) {
            const interval = setInterval(refreshGraph, 5000);
            return () => clearInterval(interval);
        }
    }, [refreshGraph, overrideGraph]);

    const handleRefactorLayout = async () => {
        if (layoutMode === 'professional') {
            setLayoutMode('default');
            return;
        }

        setIsRefactoring(true);
        try {
            const plan = await generateGraphLayout();
            if (plan && Object.keys(plan).length > 0) {
                setLayoutOverrides(plan);
                setLayoutMode('professional');
            }
        } catch (e) {
            console.error("Layout refactor failed", e);
        } finally {
            setIsRefactoring(false);
        }
    };

    const handleCalculateCost = async (e: React.MouseEvent) => {
        e.stopPropagation();
        if (!rawState) return;

        try {
            const report = await fetchCost();
            setCostReport(report);
            setShowCostModal(true);
        } catch (error) {
            console.error("Failed to calculate cost", error);
        }
    };



    const onNodeClick: NodeMouseHandler = (event, node) => {
        event.preventDefault(); event.stopPropagation();
        if (node.type === 'group' || node.type === 'group-label') return;
        setContextMenu({ x: event.clientX, y: event.clientY, id: node.id, type: 'node' });
    };

    const handleAction = (action: 'details' | 'delete') => {
        if (!contextMenu) return;
        if (action === 'delete') {
            simulateBlastRadius(contextMenu.id).then(result => {
                const impacted = new Set<string>(result.affected_nodes as string[]);
                impacted.add(contextMenu.id);
                setAffectedNodeIds(impacted);
                if (onNodeSelected) onNodeSelected(contextMenu.id);
            });
        } else if (action === 'details') {
            const node = rawState?.resources.find(n => n.id === contextMenu.id);
            if (node) setSelectedDetailNode(node);
        }
        setContextMenu(null);
    };

    // Custom Node Types
    const nodeTypes = useMemo(() => ({
        card: ({ data }: any) => {
            const bgColor = data.isAffected ? '#fee2e2' : '#ffffff';
            const borderColor = data.isAffected ? '#ef4444' : '#e5e7eb';
            const boxShadow = data.isAffected ? '0 0 0 2px #fecaca' : '0 1px 3px rgba(0,0,0,0.1)';

            return (
                <div style={{
                    width: RESOURCE_WIDTH,
                    height: RESOURCE_HEIGHT,
                    background: bgColor,
                    border: `1px solid ${borderColor}`,
                    borderRadius: '6px',
                    boxShadow,
                    overflow: 'hidden',
                    display: 'flex',
                    flexDirection: 'column'
                }}>
                    <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />

                    {/* Header Bar */}
                    <div style={{
                        background: data.headerColor,
                        height: '24px',
                        display: 'flex',
                        alignItems: 'center',
                        padding: '0 8px',
                        gap: '6px',
                        color: 'white'
                    }}>
                        {data.icon}
                        <span style={{
                            fontSize: '10px',
                            fontWeight: '600',
                            textTransform: 'uppercase',
                            letterSpacing: '0.5px'
                        }}>
                            {data.type.replace('aws_', '').replace(/_/g, ' ')}
                        </span>
                    </div>

                    {/* Body */}
                    <div style={{
                        flex: 1,
                        padding: '6px 8px',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'center'
                    }}>
                        <div style={{
                            fontSize: '13px',
                            fontWeight: '600',
                            color: '#1f2937',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap'
                        }} title={data.label}>
                            {data.label}
                        </div>
                    </div>

                    <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
                </div>
            );
        },
        group: ({ data }: any) => {
            const isVpc = data.variant === 'vpc';
            const isPublic = data.variant === 'public';

            let borderColor = isVpc ? COLORS.VPC_BORDER : (isPublic ? COLORS.SUBNET_PUBLIC_BORDER : COLORS.SUBNET_PRIVATE_BORDER);
            let bgColor = isVpc ? COLORS.VPC_BG : (isPublic ? COLORS.SUBNET_PUBLIC_BG : COLORS.SUBNET_PRIVATE_BG);

            return (
                <div style={{
                    width: '100%',
                    height: '100%',
                    border: `2px dashed ${borderColor}`,
                    backgroundColor: bgColor,
                    borderRadius: '8px',
                    position: 'relative'
                }}>
                    <div style={{
                        position: 'absolute',
                        top: '-12px',
                        left: '10px',
                        backgroundColor: '#ffffff',
                        padding: '2px 10px',
                        fontSize: '11px',
                        fontWeight: '700',
                        color: borderColor,
                        border: `1.5px solid ${borderColor}`,
                        borderRadius: '4px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px'
                    }}>
                        {isVpc ? <><Cloud size={12} />{data.label}</> :
                            isPublic ? <><Globe size={12} />{data.label}</> :
                                <><Lock size={12} />{data.label}</>}
                    </div>
                    {data.subLabel && (
                        <div style={{
                            position: 'absolute',
                            top: '8px',
                            right: '10px',
                            fontSize: '9px',
                            color: '#6b7280',
                            fontFamily: 'monospace'
                        }}>
                            {data.subLabel}
                        </div>
                    )}
                </div>
            );
        },
        'group-label': ({ data }: any) => (
            <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 8px'
            }}>
                <div style={{
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    background: '#94a3b8'
                }}></div>
                <span style={{
                    fontSize: '11px',
                    fontWeight: '700',
                    color: '#64748b',
                    textTransform: 'uppercase',
                    letterSpacing: '1px'
                }}>
                    {data.label.replace('az:', '')}
                </span>
            </div>
        )
    }), []);

    // Remap Types
    const renderNodes = nodes.map(n => {
        if (n.type === 'group') return { ...n, type: 'group' };
        if (n.type === 'group-label') return n;
        return { ...n, type: 'card' };
    });

    return (
        <div style={{ width: '100%', height: '600px', border: '1px solid #e2e8f0', borderRadius: '12px', position: 'relative', overflow: 'hidden', background: '#f8fafc' }} onClick={() => setContextMenu(null)}>

            <ReactFlow
                nodes={renderNodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onNodeClick={onNodeClick}
                nodeTypes={nodeTypes}
                fitView
                minZoom={0.1}
                maxZoom={1.5}
                attributionPosition="bottom-right"
            >
                <Background color="#cbd5e1" gap={20} size={1} />
                <Controls showInteractive={false} />
            </ReactFlow>

            {/* Toolbar: Refactor + Toggle Details */}
            <div className="absolute top-4 right-36 z-10 flex gap-2">
                <button
                    onClick={(e) => { e.stopPropagation(); handleRefactorLayout(); }}
                    disabled={isRefactoring}
                    className={`px-3 py-1.5 text-sm font-medium rounded-md shadow-sm flex items-center gap-2 transition-colors
                        ${layoutMode === 'professional'
                            ? 'bg-purple-600 text-white hover:bg-purple-700 border border-purple-500'
                            : 'bg-white text-slate-700 hover:bg-slate-50 border border-slate-200'
                        }
                        ${isRefactoring ? 'opacity-70 cursor-wait' : ''}
                    `}
                >
                    <Sparkles size={14} className={isRefactoring ? 'animate-spin' : ''} />
                    {isRefactoring ? 'Refactoring...' : (layoutMode === 'professional' ? 'Reset Layout' : 'Refactor Layout')}
                </button>

                {layoutMode === 'professional' && (
                    <button
                        onClick={(e) => { e.stopPropagation(); setShowDetails(!showDetails); }}
                        className="px-3 py-1.5 bg-slate-800 text-slate-300 rounded-md text-sm font-medium hover:bg-slate-700 shadow-sm flex items-center gap-2 border border-slate-600"
                        title={showDetails ? "Hide Details (SGs, Policies)" : "Show All Details"}
                    >
                        {showDetails ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                )}

                {/* Cost Calculation Button */}
                <button
                    onClick={handleCalculateCost}
                    className="px-3 py-1.5 text-sm font-medium bg-white text-slate-700 hover:bg-slate-50 border border-slate-200 rounded-md shadow-sm flex items-center gap-2 transition-colors"
                >
                    <DollarSign size={16} className="text-green-600" />
                    <span>Calculate Cost</span>
                </button>
            </div>

            {terraformCode && (
                <button onClick={(e) => { e.stopPropagation(); setShowCode(true); }} className="absolute top-4 right-4 z-10 px-3 py-1.5 bg-slate-800 text-white rounded-md text-sm font-medium hover:bg-slate-900 shadow-sm flex items-center gap-2">
                    <span>&lt;/&gt;</span> Terraform
                </button>
            )}

            {showCode && terraformCode && (
                <div className="absolute inset-0 bg-slate-900/90 z-50 p-6 flex flex-col" onClick={(e) => e.stopPropagation()}>
                    <div className="flex justify-between items-center text-white mb-4">
                        <h3 className="font-bold text-lg">Terraform Code</h3>
                        <button onClick={() => setShowCode(false)} className="text-slate-400 hover:text-white">✕</button>
                    </div>
                    <pre className="flex-1 bg-slate-950 p-4 rounded-lg overflow-auto text-sm font-mono text-emerald-400 border border-slate-800">{terraformCode}</pre>
                </div>
            )}

            {costReport && (
                <div onClick={() => setShowCostModal(true)} className="absolute bottom-4 left-4 z-10 bg-emerald-50 border border-emerald-200 text-emerald-700 px-3 py-1.5 rounded-md text-xs font-bold shadow-sm cursor-pointer flex items-center gap-1 hover:bg-emerald-100">
                    <DollarSign size={14} /> ${costReport.total_monthly_cost.toFixed(2)}/mo
                </div>
            )}

            {showCostModal && costReport && (
                <div className="fixed inset-0 bg-black/50 z-[60] flex items-center justify-center p-4" onClick={() => setShowCostModal(false)}>
                    <div className="bg-white rounded-xl max-w-lg w-full max-h-[80vh] overflow-hidden shadow-2xl" onClick={e => e.stopPropagation()}>
                        <div className="p-6 border-b border-slate-100 flex justify-between items-center">
                            <h3 className="font-bold text-slate-800">Cost Breakdown</h3>
                            <button onClick={() => setShowCostModal(false)} className="text-slate-400">✕</button>
                        </div>
                        <div className="p-6 overflow-y-auto max-h-[60vh]">
                            <div className="flex justify-between items-end mb-6">
                                <span className="text-sm text-slate-500">Total Monthly</span>
                                <span className="text-3xl font-bold text-emerald-600">${costReport.total_monthly_cost.toFixed(2)}</span>
                            </div>
                            <div className="space-y-3">
                                {costReport.breakdown.map((item, i) => (
                                    <div key={i} className="p-3 bg-slate-50 rounded-lg border border-slate-100">
                                        <div className="flex justify-between font-medium text-slate-700 mb-1">
                                            <span>{item.resource_type}</span>
                                            <span>${item.estimated_cost.toFixed(2)}</span>
                                        </div>
                                        <p className="text-xs text-slate-500">{item.explanation}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {selectedDetailNode && (
                <div className="fixed inset-0 bg-black/50 z-[60] flex items-center justify-center p-4" onClick={() => setSelectedDetailNode(null)}>
                    <div className="bg-white rounded-xl max-w-2xl w-full max-h-[80vh] overflow-hidden shadow-2xl flex flex-col" onClick={e => e.stopPropagation()}>
                        <div className="p-4 border-b border-slate-100 bg-slate-50 flex justify-between items-center">
                            <div>
                                <h3 className="font-bold text-slate-800">{selectedDetailNode.id}</h3>
                                <span className="text-xs font-mono text-slate-500">{selectedDetailNode.type}</span>
                            </div>
                            <button onClick={() => setSelectedDetailNode(null)} className="text-slate-400 hover:text-red-500">✕</button>
                        </div>
                        <div className="p-6 overflow-y-auto">
                            <div className="bg-slate-900 rounded-lg p-4 overflow-x-auto">
                                <pre className="text-xs font-mono text-blue-300">{JSON.stringify(selectedDetailNode.properties, null, 2)}</pre>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {contextMenu && (
                <div style={{ top: contextMenu.y, left: contextMenu.x }} className="fixed z-50 bg-white border border-slate-200 rounded-lg shadow-lg py-1 min-w-[160px]">
                    <button onClick={() => handleAction('details')} className="w-full text-left px-4 py-2 text-sm text-slate-700 hover:bg-slate-50">View Details</button>
                    <button onClick={() => handleAction('delete')} className="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50">Simulate Cut</button>
                </div>
            )}
        </div>
    );
}
