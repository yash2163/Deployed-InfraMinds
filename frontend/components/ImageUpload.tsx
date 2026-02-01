import React, { useCallback, useState } from 'react';
import { ImagePlus, X, Upload } from 'lucide-react';

interface ImageUploadProps {
    onImageSelected: (file: File) => void;
    isProcessing: boolean;
}

export const ImageUpload: React.FC<ImageUploadProps> = ({ onImageSelected, isProcessing }) => {
    const [dragActive, setDragActive] = useState(false);
    const [preview, setPreview] = useState<string | null>(null);

    const handleDrag = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") {
            setDragActive(true);
        } else if (e.type === "dragleave") {
            setDragActive(false);
        }
    }, []);

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);

        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            const file = e.dataTransfer.files[0];
            handleFile(file);
        }
    }, []);

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        e.preventDefault();
        if (e.target.files && e.target.files[0]) {
            handleFile(e.target.files[0]);
        }
    };

    const handleFile = (file: File) => {
        // Basic validation
        if (!file.type.startsWith("image/")) {
            alert("Please upload an image file.");
            return;
        }

        // Set preview
        const reader = new FileReader();
        reader.onloadend = () => {
            setPreview(reader.result as string);
        };
        reader.readAsDataURL(file);

        // Notify parent
        onImageSelected(file);
    };

    const clearImage = () => {
        setPreview(null);
        // You might want to notify parent to clear selection?
        // For now, we assume this is just clearing the view before next upload
    };

    if (preview) {
        return (
            <div className="relative group w-full mb-4">
                <img
                    src={preview}
                    alt="Preview"
                    className="w-full h-32 object-cover rounded-md border border-neutral-700/50 opacity-80"
                />
                <button
                    onClick={clearImage}
                    disabled={isProcessing}
                    className="absolute top-1 right-1 bg-black/60 hover:bg-red-500/80 p-1 rounded-full text-white transition-colors backdrop-blur-sm"
                >
                    <X size={14} />
                </button>
                {isProcessing && (
                    <div className="absolute inset-0 bg-black/50 flex items-center justify-center rounded-md">
                        <div className="flex flex-col items-center gap-2">
                            <div className="w-5 h-5 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin"></div>
                            <span className="text-xs text-cyan-400 font-mono">Analyzing...</span>
                        </div>
                    </div>
                )}
            </div>
        )
    }

    return (
        <div
            className={`
            relative flex flex-col items-center justify-center p-4 
            border-2 border-dashed rounded-lg transition-all duration-200 ease-in-out cursor-pointer group mb-4
            ${dragActive ? 'border-cyan-400 bg-cyan-400/5' : 'border-neutral-700 hover:border-neutral-500 hover:bg-white/5'}
            ${isProcessing ? 'opacity-50 pointer-events-none' : ''}
        `}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            onClick={() => document.getElementById('image-upload-input')?.click()}
        >
            <input
                id="image-upload-input"
                type="file"
                className="hidden"
                multiple={false}
                accept="image/*"
                onChange={handleChange}
            />

            <div className="flex flex-col items-center gap-2 text-neutral-400 group-hover:text-neutral-200 transition-colors">
                <div className="p-2 rounded-full bg-neutral-800 group-hover:bg-neutral-700 transition-colors">
                    <ImagePlus size={20} />
                </div>
                <p className="text-xs font-mono text-center">
                    <span className="font-semibold text-cyan-400">Click to upload</span> or drag sketch
                </p>
            </div>
        </div>
    );
};
