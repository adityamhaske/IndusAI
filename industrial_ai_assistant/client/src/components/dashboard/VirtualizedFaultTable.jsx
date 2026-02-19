import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
    useReactTable,
    getCoreRowModel,
    getSortedRowModel,
    flexRender,
} from '@tanstack/react-table';
import { useVirtualizer } from '@tanstack/react-virtual';
import { ArrowUpDown, ArrowUp, ArrowDown, Search } from 'lucide-react';

const SEVERITY_COLORS = {
    HIGH: 'bg-red-100 text-red-800',
    MEDIUM: 'bg-yellow-100 text-yellow-800',
    LOW: 'bg-green-100 text-green-800',
};

const columns = [
    { accessorKey: 'row_id', header: '#', size: 60 },
    { accessorKey: 'fault_code', header: 'Fault Code', size: 110 },
    { accessorKey: 'timestamp', header: 'Timestamp', size: 190 },
    { accessorKey: 'device', header: 'Device', size: 120 },
    { accessorKey: 'severity', header: 'Severity', size: 90 },
    { accessorKey: 'message', header: 'Message', size: 300 },
];

const VirtualizedFaultTable = ({ totalRows, onRowSelect, selectedRowId, fetchPage }) => {
    const [rows, setRows] = useState([]);
    const [sorting, setSorting] = useState([]);
    const [filterCode, setFilterCode] = useState('');
    const [loading, setLoading] = useState(false);
    const [page, setPage] = useState(1);
    const [totalPages, setTotalPages] = useState(1);
    const PAGE_SIZE = 200;

    const load = useCallback(async (p = 1) => {
        setLoading(true);
        try {
            const data = await fetchPage(p, PAGE_SIZE);
            setRows(data.rows);
            setTotalPages(data.total_pages);
            setPage(p);
        } finally {
            setLoading(false);
        }
    }, [fetchPage]);

    useEffect(() => { load(1); }, [load]);

    // Client-side filter on loaded page
    const filtered = filterCode
        ? rows.filter(r => r.fault_code?.toLowerCase().includes(filterCode.toLowerCase()))
        : rows;

    const table = useReactTable({
        data: filtered,
        columns,
        state: { sorting },
        onSortingChange: setSorting,
        getCoreRowModel: getCoreRowModel(),
        getSortedRowModel: getSortedRowModel(),
        manualPagination: true,
    });

    const parentRef = useRef(null);
    const tableRows = table.getRowModel().rows;

    const virtualizer = useVirtualizer({
        count: tableRows.length,
        getScrollElement: () => parentRef.current,
        estimateSize: () => 40,
        overscan: 20,
    });

    return (
        <div className="flex flex-col gap-3">
            {/* Toolbar */}
            <div className="flex items-center gap-3">
                <div className="relative flex-1 max-w-xs">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-industrial-400" />
                    <input
                        type="text"
                        placeholder="Filter by fault code…"
                        value={filterCode}
                        onChange={e => setFilterCode(e.target.value)}
                        className="pl-9 pr-3 py-2 w-full text-sm border border-industrial-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-primary-500"
                    />
                </div>
                <div className="text-xs text-industrial-500 ml-auto">
                    {loading ? 'Loading…' : `${filtered.length.toLocaleString()} rows (page ${page}/${totalPages})`}
                </div>
                <button disabled={page <= 1} onClick={() => load(page - 1)}
                    className="px-3 py-1.5 text-xs border rounded-md disabled:opacity-40 hover:bg-industrial-50 transition-colors">
                    ← Prev
                </button>
                <button disabled={page >= totalPages} onClick={() => load(page + 1)}
                    className="px-3 py-1.5 text-xs border rounded-md disabled:opacity-40 hover:bg-industrial-50 transition-colors">
                    Next →
                </button>
            </div>

            {/* Table */}
            <div className="border border-industrial-200 rounded-lg overflow-hidden bg-white shadow-sm">
                {/* Sticky Header */}
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead className="sticky top-0 z-10 bg-industrial-100 border-b border-industrial-200">
                            {table.getHeaderGroups().map(hg => (
                                <tr key={hg.id}>
                                    {hg.headers.map(h => (
                                        <th
                                            key={h.id}
                                            style={{ width: h.column.getSize() }}
                                            className="px-3 py-2.5 text-left text-xs font-semibold text-industrial-600 uppercase tracking-wider whitespace-nowrap select-none cursor-pointer hover:bg-industrial-200 transition-colors"
                                            onClick={h.column.getToggleSortingHandler?.()}
                                        >
                                            <div className="flex items-center gap-1">
                                                {flexRender(h.column.columnDef.header, h.getContext())}
                                                {h.column.getIsSorted() === 'asc' && <ArrowUp className="w-3 h-3" />}
                                                {h.column.getIsSorted() === 'desc' && <ArrowDown className="w-3 h-3" />}
                                                {!h.column.getIsSorted() && <ArrowUpDown className="w-3 h-3 opacity-30" />}
                                            </div>
                                        </th>
                                    ))}
                                </tr>
                            ))}
                        </thead>
                    </table>
                </div>

                {/* Virtualized Body */}
                <div ref={parentRef} className="overflow-auto" style={{ height: '460px' }}>
                    <table className="w-full text-sm">
                        <tbody style={{ height: `${virtualizer.getTotalSize()}px`, position: 'relative' }}>
                            {virtualizer.getVirtualItems().map(vi => {
                                const row = tableRows[vi.index];
                                const isSelected = row?.original?.row_id === selectedRowId;
                                return (
                                    <tr
                                        key={vi.key}
                                        data-index={vi.index}
                                        ref={virtualizer.measureElement}
                                        style={{ position: 'absolute', top: 0, left: 0, width: '100%', transform: `translateY(${vi.start}px)` }}
                                        onClick={() => onRowSelect(row.original)}
                                        className={`border-b border-industrial-100 cursor-pointer transition-colors
                      ${isSelected ? 'bg-primary-50 border-primary-200' : 'hover:bg-industrial-50'}`}
                                    >
                                        {row.getVisibleCells().map(cell => (
                                            <td
                                                key={cell.id}
                                                style={{ width: cell.column.getSize() }}
                                                className="px-3 py-2 whitespace-nowrap overflow-hidden text-ellipsis"
                                            >
                                                {cell.column.id === 'severity' ? (
                                                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${SEVERITY_COLORS[cell.getValue()?.toUpperCase()] || 'bg-industrial-100 text-industrial-600'}`}>
                                                        {cell.getValue() || '—'}
                                                    </span>
                                                ) : (
                                                    <span className="text-industrial-800">
                                                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                                                    </span>
                                                )}
                                            </td>
                                        ))}
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};

export default VirtualizedFaultTable;
