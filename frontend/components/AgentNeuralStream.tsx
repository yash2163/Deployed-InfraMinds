import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Terminal, Cpu, Activity, Zap } from 'lucide-react';

interface AgentNeuralStreamProps {
    isActive: boolean;
    phase: string; // 'plan', 'apply', 'idle', etc.
}

const MOCK_LOGS = [
    "analyzing_spatial_relationships...",
    "detecting_trust_boundaries...",
    "simulating_packet_loss_for_sg_deletion...",
    "optimizing_subnet_allocation...",
    "verifying_iam_policy_attachment...",
    "calculating_blast_radius_probability...",
    "checking_resource_dependencies...",
    "validating_security_group_rules...",
    "scanning_for_orphaned_resources...",
    "synthesizing_terraform_module_structure..."
];

export const AgentNeuralStream: React.FC<AgentNeuralStreamProps> = ({ isActive, phase }) => {
    const [logs, setLogs] = useState<string[]>([]);
    const [currentLogIndex, setCurrentLogIndex] = useState(0);
    const scrollRef = useRef<HTMLDivElement>(null);

    // Reset logs when activation changes
    useEffect(() => {
        if (isActive) {
            setLogs([]);
            setCurrentLogIndex(0);
        }
    }, [isActive]);

    // Stream logs effect
    useEffect(() => {
        if (!isActive) return;

        const interval = setInterval(() => {
            if (currentLogIndex < MOCK_LOGS.length) {
                // Add next log
                setLogs(prev => [...prev.slice(-4), MOCK_LOGS[currentLogIndex]]); // Keep last 5
                setCurrentLogIndex(prev => (prev + 1) % MOCK_LOGS.length);
            }
        }, 1500); // New log every 1.5s

        return () => clearInterval(interval);
    }, [isActive, currentLogIndex]);

    // Auto-scroll
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [logs]);

    return (
        <AnimatePresence>
            {isActive && (
                <motion.div
                    initial={{ opacity: 0, y: 20, scale: 0.95 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 20, scale: 0.95 }}
                    transition={{ duration: 0.3 }}
                    className="absolute bottom-4 right-4 z-50 w-80 overflow-hidden rounded-lg border border-emerald-500/30 bg-slate-900/90 shadow-[0_0_15px_rgba(16,185,129,0.2)] backdrop-blur-md font-mono"
                >
                    {/* Header */}
                    <div className="flex items-center justify-between border-b border-white/10 bg-white/5 px-4 py-2">
                        <div className="flex items-center gap-2">
                            <Activity size={14} className="text-emerald-400 animate-pulse" />
                            <span className="text-xs font-bold uppercase tracking-wider text-emerald-100">
                                Neural Stream
                            </span>
                        </div>
                        <div className="flex items-center gap-2">
                            <span className="flex h-2 w-2">
                                <span className="absolute inline-flex h-2 w-2 animate-ping rounded-full bg-emerald-400 opacity-75"></span>
                                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
                            </span>
                            <span className="text-[10px] font-medium text-emerald-500/80">
                                LIVE
                            </span>
                        </div>
                    </div>

                    {/* Content */}
                    <div
                        ref={scrollRef}
                        className="h-32 flex flex-col justify-end p-4 space-y-1 overflow-y-hidden"
                    >
                        {logs.map((log, i) => (
                            <motion.div
                                key={`${log}-${i}`}
                                initial={{ opacity: 0, x: -10 }}
                                animate={{ opacity: 1, x: 0 }}
                                className="flex items-center gap-2 text-xs"
                            >
                                <span className="text-emerald-500/50">➜</span>
                                <TypewriterText text={log} />
                            </motion.div>
                        ))}
                        {logs.length === 0 && (
                            <div className="text-xs text-slate-500 italic">Initializing agent process...</div>
                        )}
                    </div>

                    {/* Footer Status */}
                    <div className="bg-emerald-500/5 px-4 py-1.5 border-t border-emerald-500/10 flex justify-between items-center">
                        <span className="text-[10px] text-emerald-400/60 uppercase">
                            Phase: <span className="text-emerald-300 font-bold">{phase}</span>
                        </span>
                        <Zap size={10} className="text-emerald-500/40" />
                    </div>
                </motion.div>
            )}
        </AnimatePresence>
    );
};

const TypewriterText = ({ text }: { text: string }) => {
    const [displayedText, setDisplayedText] = useState('');

    useEffect(() => {
        let i = 0;
        const timer = setInterval(() => {
            if (i < text.length) {
                setDisplayedText(prev => prev + text.charAt(i));
                i++;
            } else {
                clearInterval(timer);
            }
        }, 30); // Speed of typing

        return () => clearInterval(timer);
    }, [text]);

    return <span className="text-emerald-400">{displayedText}</span>;
};
