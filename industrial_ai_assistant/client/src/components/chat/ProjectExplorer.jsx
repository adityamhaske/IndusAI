import React, { useEffect, useState } from 'react';
import { ChevronRight, ChevronDown, File, Folder, Database, Filter } from 'lucide-react';
import useAppStore from '../../store/useAppStore';
import { getProjectFiles } from '../../api/knowledgeApi';

// Recursive Tree Node
const TreeNode = ({ node, selectedFiles, selectedFolders, onToggleFile, onToggleFolder }) => {
    const [expanded, setExpanded] = useState(false);
    const isFolder = node.type === 'folder';
    const isSelected = isFolder
        ? selectedFolders.includes(node.path)
        : selectedFiles.includes(node.path);

    const handleToggle = () => {
        if (isFolder) {
            onToggleFolder(node.path);
        } else {
            onToggleFile(node.path);
        }
    };

    return (
        <div className="pl-4">
            <div className="flex items-center gap-1.5 py-1 hover:bg-industrial-50 rounded px-1 group">
                {isFolder ? (
                    <button
                        onClick={() => setExpanded(!expanded)}
                        className="text-industrial-400 hover:text-industrial-700"
                    >
                        {expanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                    </button>
                ) : (
                    <div className="w-3.5 h-3.5" /> // spacing helper
                )}

                <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={handleToggle}
                    className="w-3 h-3 text-primary-600 rounded border-industrial-300 focus:ring-primary-500 cursor-pointer"
                />

                {isFolder ? (
                    <Folder className="w-3.5 h-3.5 text-industrial-400" />
                ) : (
                    <File className="w-3.5 h-3.5 text-industrial-400" />
                )}

                <span className={`text-xs select-none cursor-default truncate ${isSelected ? 'text-primary-700 font-medium' : 'text-industrial-600'}`}>
                    {node.name}
                </span>
            </div>

            {isFolder && expanded && node.children && (
                <div>
                    {node.children.map(child => (
                        <TreeNode
                            key={child.path || child.name}
                            node={child}
                            selectedFiles={selectedFiles}
                            selectedFolders={selectedFolders}
                            onToggleFile={onToggleFile}
                            onToggleFolder={onToggleFolder}
                        />
                    ))}
                </div>
            )}
        </div>
    );
};

export default function ProjectExplorer() {
    const [tree, setTree] = useState([]);
    const [loading, setLoading] = useState(true);

    const [isOpen, setIsOpen] = useState(() => {
        // default collapsed on mobile
        if (typeof window !== 'undefined' && window.innerWidth < 768) return false;
        const saved = localStorage.getItem('explorerOpen');
        return saved ? saved === 'true' : true;
    });

    useEffect(() => {
        localStorage.setItem('explorerOpen', isOpen);
    }, [isOpen]);

    const selectedFiles = useAppStore(s => s.selectedFiles);
    const selectedFolders = useAppStore(s => s.selectedFolders);
    const setSelectedFiles = useAppStore(s => s.setSelectedFiles);
    const setSelectedFolders = useAppStore(s => s.setSelectedFolders);

    useEffect(() => {
        getProjectFiles('default')
            .then(data => {
                setTree(data);
                setLoading(false);
            })
            .catch(() => setLoading(false));
    }, []);

    const toggleFile = (path) => {
        if (selectedFiles.includes(path)) {
            setSelectedFiles(selectedFiles.filter(p => p !== path));
        } else {
            setSelectedFiles([...selectedFiles, path]);
        }
    };

    const toggleFolder = (path) => {
        if (selectedFolders.includes(path)) {
            setSelectedFolders(selectedFolders.filter(p => p !== path));
        } else {
            setSelectedFolders([...selectedFolders, path]);
        }
    };

    if (!isOpen) {
        return (
            <div className="w-12 bg-industrial-50 border-l border-industrial-200 flex flex-col items-center py-4 flex-shrink-0 transition-all duration-300">
                <button
                    onClick={() => setIsOpen(true)}
                    className="p-2 hover:bg-industrial-200 rounded text-industrial-500 transition-colors"
                    title="Open Project Explorer"
                >
                    <Filter className="w-5 h-5" />
                </button>
            </div>
        );
    }

    return (
        <div className="flex-shrink-0 w-[320px] bg-industrial-50 border-l border-industrial-200 flex flex-col h-full transition-all duration-300">
            <div className="p-4 border-b border-industrial-200 flex justify-between items-center bg-white">
                <h2 className="font-semibold text-industrial-800 text-sm flex items-center gap-2">
                    <Filter className="w-4 h-4 text-primary-600" />
                    Project Explorer
                </h2>
                <button
                    onClick={() => setIsOpen(false)}
                    className="text-industrial-400 hover:text-industrial-700 p-1"
                >
                    <ChevronRight className="w-4 h-4 block" />
                </button>
            </div>

            <div className="p-2 border-b border-industrial-200 flex justify-between items-center bg-white/50">
                <span className="text-[10px] uppercase tracking-wider text-industrial-500 font-bold px-2">
                    {selectedFiles.length + selectedFolders.length} selected
                </span>
                {(selectedFiles.length > 0 || selectedFolders.length > 0) && (
                    <button
                        onClick={() => { setSelectedFiles([]); setSelectedFolders([]); }}
                        className="text-[10px] uppercase font-bold text-primary-600 hover:text-primary-800 px-2"
                    >
                        Clear All
                    </button>
                )}
            </div>

            <div className="flex-1 overflow-y-auto p-2 pr-4 custom-scrollbar">
                {loading ? (
                    <div className="text-xs text-industrial-400 px-4 py-2">Loading indexed files...</div>
                ) : tree.length === 0 ? (
                    <div className="text-xs text-industrial-400 px-4 py-2">No files indexed.</div>
                ) : (
                    <div className="-ml-3">
                        {tree.map(node => (
                            <TreeNode
                                key={node.path || node.name}
                                node={node}
                                selectedFiles={selectedFiles}
                                selectedFolders={selectedFolders}
                                onToggleFile={toggleFile}
                                onToggleFolder={toggleFolder}
                            />
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
