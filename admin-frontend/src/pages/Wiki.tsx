import { useState, useEffect, useRef, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { wikiApi } from '../api/client';
import './Wiki.css';

interface WikiPage {
  name: string;
  title: string;
  page_type: string;
  link_count: number;
  modified_at: string;
}

interface GraphNode {
  id: string;
  name: string;
  type: string;
  linkCount: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
}

interface GraphLink {
  source: string;
  target: string;
}

export function Wiki() {
  const [selectedPage, setSelectedPage] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'graph' | 'list'>('graph');
  const [searchQuery, setSearchQuery] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [newPageName, setNewPageName] = useState('');
  const [newPageType, setNewPageType] = useState('concept');
  const [newPageContent, setNewPageContent] = useState('');
  const queryClient = useQueryClient();

  const { data: pagesData, isLoading } = useQuery({
    queryKey: ['wiki-pages'],
    queryFn: () => wikiApi.getPages().then(r => r.data),
  });

  const { data: selectedPageData } = useQuery({
    queryKey: ['wiki-page', selectedPage],
    queryFn: () => selectedPage ? wikiApi.getPage(selectedPage).then(r => r.data) : null,
    enabled: !!selectedPage,
  });

  const pages: WikiPage[] = pagesData?.pages || [];

  // Mutations
  const updateMutation = useMutation({
    mutationFn: ({ name, content }: { name: string; content: string }) =>
      wikiApi.updatePage(name, content),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wiki-pages'] });
      queryClient.invalidateQueries({ queryKey: ['wiki-page', selectedPage] });
      setIsEditing(false);
    },
  });

  const createMutation = useMutation({
    mutationFn: (data: { name: string; content: string; page_type?: string }) =>
      wikiApi.createPage(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wiki-pages'] });
      setIsCreating(false);
      setNewPageName('');
      setNewPageType('concept');
      setNewPageContent('');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (name: string) => wikiApi.deletePage(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wiki-pages'] });
      setSelectedPage(null);
    },
  });

  // Calculate stats
  const stats = useMemo(() => {
    const totalPages = pages.length;
    const totalLinks = pages.reduce((sum, p) => sum + p.link_count, 0);
    const types: Record<string, number> = {};
    const orphaned: WikiPage[] = [];

    for (const page of pages) {
      types[page.page_type] = (types[page.page_type] || 0) + 1;
      if (page.link_count === 0) {
        orphaned.push(page);
      }
    }

    // Find central concepts (most linked)
    const central = [...pages]
      .sort((a, b) => b.link_count - a.link_count)
      .slice(0, 5);

    return { totalPages, totalLinks, types, orphaned, central };
  }, [pages]);

  // Filter pages for list view
  const filteredPages = useMemo(() => {
    if (!searchQuery) return pages;
    const query = searchQuery.toLowerCase();
    return pages.filter(p =>
      p.name.toLowerCase().includes(query) ||
      p.title.toLowerCase().includes(query)
    );
  }, [pages, searchQuery]);

  return (
    <div className="wiki-page">
      <header className="page-header">
        <h1>Wiki Graph</h1>
        <p className="subtitle">
          Cass's self-knowledge network - {stats.totalPages} pages, {stats.totalLinks} links
        </p>
      </header>

      <div className="wiki-controls">
        <div className="view-toggle">
          <button
            className={viewMode === 'graph' ? 'active' : ''}
            onClick={() => setViewMode('graph')}
          >
            Graph
          </button>
          <button
            className={viewMode === 'list' ? 'active' : ''}
            onClick={() => setViewMode('list')}
          >
            List
          </button>
        </div>

        <button
          className="new-page-btn"
          onClick={() => setIsCreating(true)}
        >
          + New Page
        </button>

        <div className="search-box">
          <input
            type="text"
            placeholder="Search pages..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      <div className="wiki-layout">
        <div className="wiki-main">
          {isLoading ? (
            <div className="loading-state">Loading wiki...</div>
          ) : viewMode === 'graph' ? (
            <WikiGraph
              pages={pages}
              selectedPage={selectedPage}
              onSelectPage={setSelectedPage}
            />
          ) : (
            <div className="wiki-list">
              {filteredPages.map(page => (
                <div
                  key={page.name}
                  className={`wiki-list-item ${selectedPage === page.name ? 'selected' : ''}`}
                  onClick={() => setSelectedPage(page.name)}
                >
                  <span className={`type-badge type-${page.page_type}`}>
                    {page.page_type.slice(0, 3)}
                  </span>
                  <span className="page-name">{page.name}</span>
                  <span className="link-count">{page.link_count} links</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="wiki-sidebar">
          {isCreating ? (
            <div className="page-details create-form">
              <h3>Create New Page</h3>
              <div className="form-group">
                <label>Page Name</label>
                <input
                  type="text"
                  value={newPageName}
                  onChange={(e) => setNewPageName(e.target.value)}
                  placeholder="e.g., Temple-Codex"
                />
              </div>
              <div className="form-group">
                <label>Type</label>
                <select
                  value={newPageType}
                  onChange={(e) => setNewPageType(e.target.value)}
                >
                  <option value="entity">Entity</option>
                  <option value="concept">Concept</option>
                  <option value="relationship">Relationship</option>
                  <option value="journal">Journal</option>
                  <option value="meta">Meta</option>
                </select>
              </div>
              <div className="form-group">
                <label>Content</label>
                <textarea
                  value={newPageContent}
                  onChange={(e) => setNewPageContent(e.target.value)}
                  placeholder="Wiki content with [[links]]..."
                  rows={10}
                />
              </div>
              <div className="form-actions">
                <button
                  className="btn-primary"
                  onClick={() => createMutation.mutate({
                    name: newPageName,
                    content: newPageContent,
                    page_type: newPageType,
                  })}
                  disabled={!newPageName || createMutation.isPending}
                >
                  {createMutation.isPending ? 'Creating...' : 'Create'}
                </button>
                <button
                  className="btn-secondary"
                  onClick={() => {
                    setIsCreating(false);
                    setNewPageName('');
                    setNewPageType('concept');
                    setNewPageContent('');
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : selectedPage && selectedPageData ? (
            <div className="page-details">
              <div className="page-header-row">
                <h3>{selectedPageData.page?.title || selectedPage}</h3>
                <div className="page-actions">
                  {!isEditing && (
                    <>
                      <button
                        className="btn-icon"
                        onClick={() => {
                          setEditContent(selectedPageData.page?.content || '');
                          setIsEditing(true);
                        }}
                        title="Edit"
                      >
                        Edit
                      </button>
                      <button
                        className="btn-icon btn-danger"
                        onClick={() => {
                          if (confirm(`Delete "${selectedPage}"?`)) {
                            deleteMutation.mutate(selectedPage);
                          }
                        }}
                        title="Delete"
                      >
                        Del
                      </button>
                    </>
                  )}
                </div>
              </div>
              <div className="page-meta">
                <span className={`type-badge type-${selectedPageData.page?.page_type}`}>
                  {selectedPageData.page?.page_type}
                </span>
              </div>
              {isEditing ? (
                <div className="edit-form">
                  <textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    rows={15}
                  />
                  <div className="form-actions">
                    <button
                      className="btn-primary"
                      onClick={() => updateMutation.mutate({
                        name: selectedPage,
                        content: editContent,
                      })}
                      disabled={updateMutation.isPending}
                    >
                      {updateMutation.isPending ? 'Saving...' : 'Save'}
                    </button>
                    <button
                      className="btn-secondary"
                      onClick={() => setIsEditing(false)}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="page-content">
                    <pre>{selectedPageData.page?.content}</pre>
                  </div>
                  {selectedPageData.page?.links?.length > 0 && (
                    <div className="page-links">
                      <h4>Links to:</h4>
                      <div className="link-list">
                        {selectedPageData.page.links.map((link: string) => (
                          <button
                            key={link}
                            className="link-chip"
                            onClick={() => setSelectedPage(link)}
                          >
                            {link}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          ) : (
            <div className="stats-panel">
              <h3>Wiki Stats</h3>

              <div className="stat-section">
                <h4>By Type</h4>
                {Object.entries(stats.types).map(([type, count]) => (
                  <div key={type} className="stat-row">
                    <span className={`type-badge type-${type}`}>{type}</span>
                    <span className="stat-value">{count}</span>
                  </div>
                ))}
              </div>

              <div className="stat-section">
                <h4>Central Concepts</h4>
                {stats.central.map(page => (
                  <div
                    key={page.name}
                    className="stat-row clickable"
                    onClick={() => setSelectedPage(page.name)}
                  >
                    <span>{page.name}</span>
                    <span className="stat-value">{page.link_count} links</span>
                  </div>
                ))}
              </div>

              {stats.orphaned.length > 0 && (
                <div className="stat-section orphaned">
                  <h4>Orphaned Pages</h4>
                  {stats.orphaned.slice(0, 5).map(page => (
                    <div
                      key={page.name}
                      className="stat-row clickable"
                      onClick={() => setSelectedPage(page.name)}
                    >
                      <span>{page.name}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function WikiGraph({
  pages,
  selectedPage,
  onSelectPage
}: {
  pages: WikiPage[];
  selectedPage: string | null;
  onSelectPage: (name: string | null) => void;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  // Load links for all pages to build graph
  const { data: linksData } = useQuery({
    queryKey: ['wiki-all-links'],
    queryFn: async () => {
      // Fetch links for each page
      const links: GraphLink[] = [];
      for (const page of pages) {
        try {
          const resp = await wikiApi.getPage(page.name);
          const pageLinks = resp.data?.page?.links || [];
          for (const target of pageLinks) {
            // Only add if target exists in our pages
            if (pages.some(p => p.name === target)) {
              links.push({ source: page.name, target });
            }
          }
        } catch {
          // Skip pages that fail to load
        }
      }
      return links;
    },
    enabled: pages.length > 0,
  });

  const links = linksData || [];

  // Initialize nodes with positions
  const [nodes, setNodes] = useState<GraphNode[]>([]);

  useEffect(() => {
    if (pages.length === 0) return;

    // Initialize nodes in a circle
    const centerX = dimensions.width / 2;
    const centerY = dimensions.height / 2;
    const radius = Math.min(centerX, centerY) * 0.8;

    const newNodes: GraphNode[] = pages.map((page, i) => {
      const angle = (i / pages.length) * 2 * Math.PI;
      return {
        id: page.name,
        name: page.name,
        type: page.page_type,
        linkCount: page.link_count,
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle),
        vx: 0,
        vy: 0,
      };
    });

    setNodes(newNodes);
  }, [pages, dimensions]);

  // Simple force simulation
  useEffect(() => {
    if (nodes.length === 0 || links.length === 0) return;

    let animationId: number;
    let iterations = 0;
    const maxIterations = 200;

    const simulate = () => {
      if (iterations >= maxIterations) return;
      iterations++;

      const nodeMap = new Map(nodes.map(n => [n.id, n]));
      const newNodes = nodes.map(node => ({ ...node }));

      // Apply forces
      for (const node of newNodes) {
        // Repulsion from all other nodes
        for (const other of newNodes) {
          if (node.id === other.id) continue;
          const dx = node.x - other.x;
          const dy = node.y - other.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = 500 / (dist * dist);
          node.vx += (dx / dist) * force;
          node.vy += (dy / dist) * force;
        }

        // Attraction along links
        for (const link of links) {
          let other: GraphNode | undefined;
          if (link.source === node.id) {
            other = nodeMap.get(link.target);
          } else if (link.target === node.id) {
            other = nodeMap.get(link.source);
          }
          if (other) {
            const dx = other.x - node.x;
            const dy = other.y - node.y;
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            const force = dist * 0.01;
            node.vx += dx * force;
            node.vy += dy * force;
          }
        }

        // Center gravity
        const dx = dimensions.width / 2 - node.x;
        const dy = dimensions.height / 2 - node.y;
        node.vx += dx * 0.001;
        node.vy += dy * 0.001;

        // Apply velocity with damping
        node.x += node.vx * 0.1;
        node.y += node.vy * 0.1;
        node.vx *= 0.9;
        node.vy *= 0.9;

        // Boundary constraints
        node.x = Math.max(50, Math.min(dimensions.width - 50, node.x));
        node.y = Math.max(50, Math.min(dimensions.height - 50, node.y));
      }

      setNodes(newNodes);
      animationId = requestAnimationFrame(simulate);
    };

    simulate();

    return () => {
      if (animationId) cancelAnimationFrame(animationId);
    };
  }, [nodes.length, links.length, dimensions]);

  // Resize handler
  useEffect(() => {
    const updateDimensions = () => {
      if (svgRef.current?.parentElement) {
        const { width, height } = svgRef.current.parentElement.getBoundingClientRect();
        setDimensions({ width: width || 800, height: height || 600 });
      }
    };

    updateDimensions();
    window.addEventListener('resize', updateDimensions);
    return () => window.removeEventListener('resize', updateDimensions);
  }, []);

  const nodeMap = useMemo(() => new Map(nodes.map(n => [n.id, n])), [nodes]);

  const typeColors: Record<string, string> = {
    entity: '#c792ea',
    concept: '#89ddff',
    relationship: '#c3e88d',
    journal: '#ffcb6b',
    meta: '#f78c6c',
  };

  return (
    <div className="graph-container">
      <svg ref={svgRef} width={dimensions.width} height={dimensions.height}>
        {/* Links */}
        <g className="links">
          {links.map((link, i) => {
            const source = nodeMap.get(link.source);
            const target = nodeMap.get(link.target);
            if (!source || !target) return null;
            return (
              <line
                key={i}
                x1={source.x}
                y1={source.y}
                x2={target.x}
                y2={target.y}
                stroke="#333"
                strokeWidth={1}
                strokeOpacity={0.5}
              />
            );
          })}
        </g>

        {/* Nodes */}
        <g className="nodes">
          {nodes.map(node => {
            const isSelected = node.id === selectedPage;
            const radius = Math.max(8, Math.min(20, 5 + node.linkCount * 2));
            return (
              <g
                key={node.id}
                transform={`translate(${node.x}, ${node.y})`}
                onClick={() => onSelectPage(isSelected ? null : node.id)}
                style={{ cursor: 'pointer' }}
              >
                <circle
                  r={radius}
                  fill={typeColors[node.type] || '#888'}
                  stroke={isSelected ? '#fff' : 'none'}
                  strokeWidth={isSelected ? 3 : 0}
                  opacity={isSelected ? 1 : 0.8}
                />
                <text
                  dy={radius + 12}
                  textAnchor="middle"
                  fill="#ccc"
                  fontSize={10}
                  opacity={isSelected ? 1 : 0.7}
                >
                  {node.name.length > 15 ? node.name.slice(0, 12) + '...' : node.name}
                </text>
              </g>
            );
          })}
        </g>
      </svg>

      <div className="graph-legend">
        {Object.entries(typeColors).map(([type, color]) => (
          <div key={type} className="legend-item">
            <span className="legend-color" style={{ backgroundColor: color }} />
            <span>{type}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
