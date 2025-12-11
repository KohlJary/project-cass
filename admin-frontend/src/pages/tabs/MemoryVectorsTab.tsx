import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { memoryApi } from '../../api/client';

interface VectorPoint {
  id: string;
  x: number;
  y: number;
  type: string;
  preview: string;
}

const typeColors: Record<string, string> = {
  summary: '#89ddff',
  journal: '#c792ea',
  observation: '#ffcb6b',
  self_observation: '#c3e88d',
  user_observation: '#f78c6c',
  per_user_journal: '#82aaff',
  cass_self_observation: '#c3e88d',
  attractor_marker: '#ff9cac',
  project_document: '#ffd580',
};

export function MemoryVectorsTab() {
  const [limit, setLimit] = useState(200);
  const [filterType, setFilterType] = useState<string>('');
  const [hoveredPoint, setHoveredPoint] = useState<VectorPoint | null>(null);
  const [selectedPoint, setSelectedPoint] = useState<VectorPoint | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ['vectors', limit, filterType],
    queryFn: () => memoryApi.getVectors({ limit, type: filterType || undefined }).then((r) => r.data),
    retry: false,
  });

  const vectors = data?.vectors || [];

  // Group by type for legend
  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    vectors.forEach((v: VectorPoint) => {
      counts[v.type] = (counts[v.type] || 0) + 1;
    });
    return counts;
  }, [vectors]);

  return (
    <div className="vectors-tab">
      <div className="tab-description">
        2D projection of memory embeddings using PCA
      </div>

      <div className="vectors-layout">
        {/* Controls panel */}
        <div className="controls-panel">
          <div className="control-section">
            <h3>Display Options</h3>
            <div className="control-group">
              <label>Points</label>
              <select value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
                <option value={50}>50</option>
                <option value={100}>100</option>
                <option value={200}>200</option>
                <option value={500}>500</option>
              </select>
            </div>
            <div className="control-group">
              <label>Filter Type</label>
              <select value={filterType} onChange={(e) => setFilterType(e.target.value)}>
                <option value="">All Types</option>
                <option value="summary">Summary</option>
                <option value="journal">Journal</option>
                <option value="observation">Observation</option>
                <option value="self_observation">Self Observation</option>
                <option value="user_observation">User Observation</option>
                <option value="per_user_journal">Per-User Journal</option>
              </select>
            </div>
          </div>

          <div className="control-section">
            <h3>Legend</h3>
            <div className="legend">
              {Object.entries(typeCounts).map(([type, count]) => (
                <div key={type} className="legend-item">
                  <span
                    className="legend-dot"
                    style={{ backgroundColor: typeColors[type] || '#888' }}
                  />
                  <span className="legend-label">{type.replace(/_/g, ' ')}</span>
                  <span className="legend-count">{count}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Selected point info */}
          {selectedPoint && (
            <div className="control-section selected-info">
              <h3>Selected Memory</h3>
              <div className="selected-type" style={{ color: typeColors[selectedPoint.type] || '#888' }}>
                {selectedPoint.type}
              </div>
              <div className="selected-preview">{selectedPoint.preview}</div>
              <div className="selected-id">
                <code>{selectedPoint.id}</code>
              </div>
            </div>
          )}
        </div>

        {/* Visualization canvas */}
        <div className="canvas-panel">
          {isLoading ? (
            <div className="loading-state">Loading vectors...</div>
          ) : error ? (
            <div className="error-state">Failed to load vectors</div>
          ) : vectors.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">o</div>
              <p>No vectors to display</p>
              <p className="hint">Add more memories or adjust filters</p>
            </div>
          ) : (
            <div className="vector-canvas">
              <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet">
                {/* Grid lines */}
                <defs>
                  <pattern id="grid" width="10" height="10" patternUnits="userSpaceOnUse">
                    <path d="M 10 0 L 0 0 0 10" fill="none" stroke="#1a1a1a" strokeWidth="0.2" />
                  </pattern>
                </defs>
                <rect width="100" height="100" fill="url(#grid)" />

                {/* Points */}
                {vectors.map((point: VectorPoint) => (
                  <circle
                    key={point.id}
                    cx={point.x * 90 + 5}
                    cy={(1 - point.y) * 90 + 5}
                    r={selectedPoint?.id === point.id ? 1.5 : hoveredPoint?.id === point.id ? 1.2 : 0.8}
                    fill={typeColors[point.type] || '#888'}
                    opacity={selectedPoint && selectedPoint.id !== point.id ? 0.3 : 0.8}
                    className="vector-point"
                    onMouseEnter={() => setHoveredPoint(point)}
                    onMouseLeave={() => setHoveredPoint(null)}
                    onClick={() => setSelectedPoint(selectedPoint?.id === point.id ? null : point)}
                  />
                ))}
              </svg>

              {/* Hover tooltip */}
              {hoveredPoint && !selectedPoint && (
                <div className="tooltip">
                  <div className="tooltip-type" style={{ color: typeColors[hoveredPoint.type] || '#888' }}>
                    {hoveredPoint.type}
                  </div>
                  <div className="tooltip-preview">{hoveredPoint.preview.slice(0, 80)}...</div>
                </div>
              )}
            </div>
          )}

          <div className="canvas-footer">
            <span>{vectors.length} points displayed</span>
            <span>PCA projection of {vectors.length > 0 ? '1536' : '0'}-dim embeddings</span>
          </div>
        </div>
      </div>
    </div>
  );
}
