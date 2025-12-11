import { useState, useEffect, useRef, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { wikiApi } from '../../api/client';
import { WikiReader, type WikiPage } from '../../components/WikiReader';
import '../Wiki.css';

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

interface RetrievalPage {
  name: string;
  title: string;
  type: string;
  relevance: number;
  depth: number;
  path: string[];
}

interface RetrievalResult {
  synthesis: string;
  entry_points: string[];
  pages: RetrievalPage[];
  stats: {
    total_pages: number;
    retrieval_time_ms: number;
    stopped_early: boolean;
    avg_novelty: number;
  };
}

interface PopulationSuggestion {
  action: string;
  page: string;
  type: string | null;
  confidence: number;
  reason: string;
}

interface PopulationResult {
  conversations_analyzed: number;
  entities_found: number;
  concepts_found: number;
  top_entities: [string, number][];
  top_concepts: [string, number][];
  suggestions: PopulationSuggestion[];
  pages_created: string[];
  pages_updated: string[];
  links_created: [string, string][];
  errors: string[];
  elapsed_seconds: number;
  auto_applied: boolean;
}

interface ResearchQueueItem {
  name: string;
  reference_count: number;
  referenced_by: string[];
}

export function WikiTab() {
  const [selectedPage, setSelectedPage] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'reader' | 'graph' | 'list' | 'replay' | 'populate' | 'research'>('reader');
  const [searchQuery, setSearchQuery] = useState('');
  const [replayQuery, setReplayQuery] = useState('');
  const [replayResult, setReplayResult] = useState<RetrievalResult | null>(null);
  const [replayLoading, setReplayLoading] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [newPageName, setNewPageName] = useState('');
  const [newPageType, setNewPageType] = useState('concept');
  const [newPageContent, setNewPageContent] = useState('');
  const [populateResult, setPopulateResult] = useState<PopulationResult | null>(null);
  const [populateLoading, setPopulateLoading] = useState(false);
  const [populateAutoApply, setPopulateAutoApply] = useState(false);
  const [populateMinConfidence, setPopulateMinConfidence] = useState(0.6);
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

  const { data: backlinksData } = useQuery({
    queryKey: ['wiki-backlinks', selectedPage],
    queryFn: () => selectedPage ? wikiApi.getBacklinks(selectedPage).then(r => r.data) : null,
    enabled: !!selectedPage && viewMode === 'reader',
  });

  const { data: maturityData } = useQuery({
    queryKey: ['wiki-maturity', selectedPage],
    queryFn: () => selectedPage ? wikiApi.getPageMaturity(selectedPage).then(r => r.data) : null,
    enabled: !!selectedPage && viewMode === 'reader',
  });

  const pages: WikiPage[] = pagesData?.pages || [];
  const backlinks = backlinksData?.backlinks || [];
  const maturity = maturityData;

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

  // Run traversal replay
  const runReplay = async () => {
    if (!replayQuery.trim()) return;
    setReplayLoading(true);
    try {
      const response = await wikiApi.retrieveContext(replayQuery);
      setReplayResult(response.data);
    } catch (error) {
      console.error('Replay failed:', error);
      setReplayResult(null);
    } finally {
      setReplayLoading(false);
    }
  };

  const runPopulate = async () => {
    setPopulateLoading(true);
    try {
      const response = await wikiApi.populateFromConversations({
        auto_apply: populateAutoApply,
        min_confidence: populateMinConfidence,
      });
      setPopulateResult(response.data);
      if (populateAutoApply) {
        queryClient.invalidateQueries({ queryKey: ['wiki-pages'] });
      }
    } catch (error) {
      console.error('Population failed:', error);
      setPopulateResult(null);
    } finally {
      setPopulateLoading(false);
    }
  };

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
            className={viewMode === 'reader' ? 'active' : ''}
            onClick={() => setViewMode('reader')}
          >
            Reader
          </button>
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
          <button
            className={viewMode === 'replay' ? 'active' : ''}
            onClick={() => setViewMode('replay')}
          >
            Replay
          </button>
          <button
            className={viewMode === 'populate' ? 'active' : ''}
            onClick={() => setViewMode('populate')}
          >
            Populate
          </button>
          <button
            className={viewMode === 'research' ? 'active' : ''}
            onClick={() => setViewMode('research')}
          >
            Research
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
          ) : viewMode === 'reader' ? (
            <WikiReader
              pages={pages}
              selectedPage={selectedPage}
              pageData={selectedPageData?.page}
              backlinks={backlinks}
              maturity={maturity}
              onSelectPage={setSelectedPage}
              onEdit={() => {
                setEditContent(selectedPageData?.page?.content || '');
                setIsEditing(true);
              }}
              isEditing={isEditing}
              editContent={editContent}
              onEditChange={setEditContent}
              onSave={() => {
                if (selectedPage) {
                  updateMutation.mutate({ name: selectedPage, content: editContent });
                }
              }}
              onCancelEdit={() => setIsEditing(false)}
              isSaving={updateMutation.isPending}
            />
          ) : viewMode === 'graph' ? (
            <WikiGraph
              pages={pages}
              selectedPage={selectedPage}
              onSelectPage={setSelectedPage}
            />
          ) : viewMode === 'replay' ? (
            <TraversalReplay
              query={replayQuery}
              onQueryChange={setReplayQuery}
              onRun={runReplay}
              result={replayResult}
              loading={replayLoading}
              onSelectPage={setSelectedPage}
            />
          ) : viewMode === 'populate' ? (
            <WikiPopulate
              onRun={runPopulate}
              result={populateResult}
              loading={populateLoading}
              autoApply={populateAutoApply}
              onAutoApplyChange={setPopulateAutoApply}
              minConfidence={populateMinConfidence}
              onMinConfidenceChange={setPopulateMinConfidence}
              onSelectPage={setSelectedPage}
              onCreatePage={async (name, type) => {
                await wikiApi.createFromSuggestion(name, type);
                queryClient.invalidateQueries({ queryKey: ['wiki-pages'] });
              }}
              onEnrichPages={async () => {
                const response = await wikiApi.enrichPages({ limit: 10 });
                queryClient.invalidateQueries({ queryKey: ['wiki-pages'] });
                return response.data;
              }}
            />
          ) : viewMode === 'research' ? (
            <ResearchQueue
              onSelectPage={setSelectedPage}
              onResearchPage={async (name) => {
                await wikiApi.researchPage(name);
                queryClient.invalidateQueries({ queryKey: ['wiki-pages'] });
              }}
              onResearchBatch={async (limit) => {
                const response = await wikiApi.researchBatch({ limit });
                queryClient.invalidateQueries({ queryKey: ['wiki-pages'] });
                return response.data;
              }}
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

// Traversal Replay Component - visualizes wiki context retrieval
function TraversalReplay({
  query,
  onQueryChange,
  onRun,
  result,
  loading,
  onSelectPage,
}: {
  query: string;
  onQueryChange: (q: string) => void;
  onRun: () => void;
  result: RetrievalResult | null;
  loading: boolean;
  onSelectPage: (name: string | null) => void;
}) {
  const typeColors: Record<string, string> = {
    entity: '#89ddff',
    concept: '#c792ea',
    relationship: '#c3e88d',
    journal: '#ffcb6b',
    meta: '#f78c6c',
  };

  return (
    <div className="traversal-replay">
      <div className="replay-controls">
        <input
          type="text"
          className="replay-query"
          placeholder="Enter a query to see how Cass retrieves wiki context..."
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && onRun()}
        />
        <button
          className="btn-primary"
          onClick={onRun}
          disabled={loading || !query.trim()}
        >
          {loading ? 'Traversing...' : 'Run Retrieval'}
        </button>
      </div>

      {result && (
        <div className="replay-results">
          <div className="replay-stats">
            <span className="stat">
              <strong>{result.stats.total_pages}</strong> pages retrieved
            </span>
            <span className="stat">
              <strong>{result.stats.retrieval_time_ms.toFixed(0)}ms</strong>
            </span>
            <span className="stat">
              avg novelty: <strong>{(result.stats.avg_novelty * 100).toFixed(0)}%</strong>
            </span>
            {result.stats.stopped_early && (
              <span className="stat stat-warning">stopped early (low novelty)</span>
            )}
          </div>

          <div className="replay-section">
            <h4>Entry Points</h4>
            <div className="entry-points">
              {result.entry_points.map((ep, i) => (
                <span
                  key={i}
                  className="entry-point"
                  onClick={() => onSelectPage(ep)}
                >
                  {ep}
                </span>
              ))}
            </div>
          </div>

          <div className="replay-section">
            <h4>Traversal Path</h4>
            <div className="traversal-tree">
              {result.pages.map((page, i) => (
                <div
                  key={i}
                  className="traversal-node"
                  style={{ marginLeft: page.depth * 20 }}
                  onClick={() => onSelectPage(page.name)}
                >
                  <div className="node-connector">
                    {page.depth > 0 && (
                      <span className="connector-line" />
                    )}
                  </div>
                  <div className="node-content">
                    <span
                      className="node-dot"
                      style={{ backgroundColor: typeColors[page.type] || '#888' }}
                    />
                    <span className="node-name">{page.name}</span>
                    <span className="node-relevance" style={{
                      opacity: 0.3 + page.relevance * 0.7
                    }}>
                      {(page.relevance * 100).toFixed(0)}%
                    </span>
                  </div>
                  {page.path.length > 1 && (
                    <div className="node-path">
                      via: {page.path.slice(0, -1).join(' → ')}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="replay-section">
            <h4>Synthesized Context</h4>
            <div className="synthesis-preview">
              {result.synthesis}
            </div>
          </div>
        </div>
      )}

      {!result && !loading && (
        <div className="replay-empty">
          <p>Enter a query to see how Cass traverses the wiki graph to gather context.</p>
          <p className="hint">The retrieval algorithm:</p>
          <ol>
            <li>Finds semantic entry points via embedding search</li>
            <li>Traverses outgoing [[wikilinks]] breadth-first</li>
            <li>Scores each page for relevance and novelty</li>
            <li>Stops when novelty drops or limits are reached</li>
            <li>Synthesizes context from collected pages</li>
          </ol>
        </div>
      )}
    </div>
  );
}

interface EnrichResult {
  stub_pages_found: number;
  enriched: number;
  errors: number;
  results: Array<{
    name: string;
    status: string;
    context_snippets: number;
    error?: string;
  }>;
}

// Wiki Population Component - analyze conversations to seed wiki
function WikiPopulate({
  onRun,
  result,
  loading,
  autoApply,
  onAutoApplyChange,
  minConfidence,
  onMinConfidenceChange,
  onSelectPage,
  onCreatePage,
  onEnrichPages,
}: {
  onRun: () => void;
  result: PopulationResult | null;
  loading: boolean;
  autoApply: boolean;
  onAutoApplyChange: (v: boolean) => void;
  minConfidence: number;
  onMinConfidenceChange: (v: number) => void;
  onSelectPage: (name: string | null) => void;
  onCreatePage: (name: string, type: string) => Promise<void>;
  onEnrichPages: () => Promise<EnrichResult>;
}) {
  const [createdPages, setCreatedPages] = useState<Set<string>>(new Set());
  const [creating, setCreating] = useState<string | null>(null);
  const [enriching, setEnriching] = useState(false);
  const [enrichResult, setEnrichResult] = useState<EnrichResult | null>(null);

  const handleCreate = async (name: string, type: string) => {
    setCreating(name);
    try {
      await onCreatePage(name, type);
      setCreatedPages(prev => new Set([...prev, name]));
    } catch (error) {
      console.error('Failed to create page:', error);
    } finally {
      setCreating(null);
    }
  };

  const handleEnrich = async () => {
    setEnriching(true);
    try {
      const result = await onEnrichPages();
      setEnrichResult(result);
    } catch (error) {
      console.error('Failed to enrich pages:', error);
    } finally {
      setEnriching(false);
    }
  };

  const typeColors: Record<string, string> = {
    entity: '#89ddff',
    concept: '#c792ea',
    relationship: '#c3e88d',
    journal: '#ffcb6b',
    meta: '#f78c6c',
  };

  return (
    <div className="wiki-populate">
      <div className="populate-controls">
        <div className="populate-options">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={autoApply}
              onChange={(e) => onAutoApplyChange(e.target.checked)}
            />
            Auto-apply suggestions
          </label>
          <label className="slider-label">
            Min confidence: {Math.round(minConfidence * 100)}%
            <input
              type="range"
              min="0.3"
              max="0.9"
              step="0.1"
              value={minConfidence}
              onChange={(e) => onMinConfidenceChange(parseFloat(e.target.value))}
            />
          </label>
        </div>
        <div className="populate-buttons">
          <button
            className="btn-primary btn-large"
            onClick={onRun}
            disabled={loading || enriching}
          >
            {loading ? 'Analyzing Conversations...' : 'Analyze Conversations'}
          </button>
          <button
            className="btn-secondary btn-large"
            onClick={handleEnrich}
            disabled={loading || enriching}
          >
            {enriching ? 'Enriching...' : 'Enrich Stub Pages'}
          </button>
        </div>
      </div>

      {enrichResult && (
        <div className="enrich-results">
          <h4>Enrichment Results</h4>
          <div className="enrich-summary">
            <span className="stat">Found <strong>{enrichResult.stub_pages_found}</strong> stub pages</span>
            <span className="stat">Enriched <strong>{enrichResult.enriched}</strong></span>
            {enrichResult.errors > 0 && (
              <span className="stat stat-error">Errors: {enrichResult.errors}</span>
            )}
          </div>
          <div className="enrich-list">
            {enrichResult.results.map((r, i) => (
              <div
                key={i}
                className={`enrich-item ${r.status === 'enriched' ? 'success' : 'error'}`}
                onClick={() => onSelectPage(r.name)}
              >
                <span className="enrich-name">{r.name}</span>
                <span className="enrich-status">{r.status}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {result && (
        <div className="populate-results">
          <div className="populate-summary">
            <div className="summary-stat">
              <span className="stat-value">{result.conversations_analyzed}</span>
              <span className="stat-label">Conversations</span>
            </div>
            <div className="summary-stat">
              <span className="stat-value">{result.entities_found}</span>
              <span className="stat-label">Entities</span>
            </div>
            <div className="summary-stat">
              <span className="stat-value">{result.concepts_found}</span>
              <span className="stat-label">Concepts</span>
            </div>
            <div className="summary-stat">
              <span className="stat-value">{result.elapsed_seconds}s</span>
              <span className="stat-label">Time</span>
            </div>
          </div>

          {result.pages_created.length > 0 && (
            <div className="populate-section created-pages">
              <h4>Pages Created ({result.pages_created.length})</h4>
              <div className="created-list">
                {result.pages_created.map((name, i) => (
                  <span
                    key={i}
                    className="created-page"
                    onClick={() => onSelectPage(name)}
                  >
                    {name}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="populate-section">
            <h4>Top Entities</h4>
            <div className="entity-list">
              {result.top_entities.map(([name, count], i) => (
                <div key={i} className="entity-item">
                  <span className="entity-name">{name}</span>
                  <span className="entity-count">{count} mentions</span>
                </div>
              ))}
            </div>
          </div>

          <div className="populate-section">
            <h4>Top Concepts</h4>
            <div className="concept-list">
              {result.top_concepts.map(([name, count], i) => (
                <div key={i} className="concept-item">
                  <span className="concept-name">{name}</span>
                  <span className="concept-count">{count} mentions</span>
                </div>
              ))}
            </div>
          </div>

          <div className="populate-section">
            <h4>Suggestions ({result.suggestions.length})</h4>
            <div className="suggestions-list">
              {result.suggestions.map((s, i) => {
                const isCreated = createdPages.has(s.page);
                const isCreating = creating === s.page;
                return (
                  <div
                    key={i}
                    className={`suggestion-item ${isCreated ? 'created' : ''}`}
                  >
                    <span
                      className="suggestion-type"
                      style={{ backgroundColor: typeColors[s.type || 'concept'] + '33', color: typeColors[s.type || 'concept'] }}
                    >
                      {s.type || 'page'}
                    </span>
                    <span className="suggestion-page">{s.page}</span>
                    <span className="suggestion-confidence" style={{ opacity: 0.4 + s.confidence * 0.6 }}>
                      {Math.round(s.confidence * 100)}%
                    </span>
                    <span className="suggestion-reason">{s.reason}</span>
                    {isCreated ? (
                      <span className="suggestion-created">Created</span>
                    ) : (
                      <button
                        className="suggestion-create-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleCreate(s.page, s.type || 'entity');
                        }}
                        disabled={isCreating}
                      >
                        {isCreating ? '...' : '+'}
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {result.errors.length > 0 && (
            <div className="populate-section errors">
              <h4>Errors ({result.errors.length})</h4>
              <div className="error-list">
                {result.errors.map((err, i) => (
                  <div key={i} className="error-item">{err}</div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {!result && !loading && (
        <div className="populate-empty">
          <h3>Populate Wiki from Conversations</h3>
          <p>
            Analyze all historical conversations to extract entities and concepts
            that Cass has discussed. This helps build out the wiki with relevant pages.
          </p>
          <div className="populate-info">
            <h4>How it works:</h4>
            <ol>
              <li>Scans all conversation history</li>
              <li>Extracts named entities (people, places, projects)</li>
              <li>Identifies discussed concepts</li>
              <li>Ranks by mention frequency across conversations</li>
              <li>Suggests new wiki pages with confidence scores</li>
            </ol>
            <p className="note">
              Enable "Auto-apply" to automatically create pages above the confidence threshold.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// Research Queue Component - manage red links and web research
function ResearchQueue({
  onSelectPage,
  onResearchPage,
  onResearchBatch,
}: {
  onSelectPage: (name: string | null) => void;
  onResearchPage: (name: string) => Promise<void>;
  onResearchBatch: (limit: number) => Promise<{
    total_red_links: number;
    processed: number;
    created: number;
    errors: number;
    results: Array<{ name: string; status: string; references?: number; web_sources?: number; error?: string }>;
  }>;
}) {
  const [researching, setResearching] = useState<string | null>(null);
  const [researchedPages, setResearchedPages] = useState<Set<string>>(new Set());
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchResult, setBatchResult] = useState<{
    total_red_links: number;
    processed: number;
    created: number;
    errors: number;
    results: Array<{ name: string; status: string; references?: number; web_sources?: number; error?: string }>;
  } | null>(null);

  const { data: queueData, isLoading, refetch } = useQuery({
    queryKey: ['research-queue'],
    queryFn: () => wikiApi.getResearchQueue(50).then(r => r.data),
  });

  const handleResearch = async (name: string) => {
    setResearching(name);
    try {
      await onResearchPage(name);
      setResearchedPages(prev => new Set([...prev, name]));
      refetch();
    } catch (error) {
      console.error('Research failed:', error);
    } finally {
      setResearching(null);
    }
  };

  const handleBatchResearch = async () => {
    setBatchRunning(true);
    try {
      const result = await onResearchBatch(5);
      setBatchResult(result);
      refetch();
    } catch (error) {
      console.error('Batch research failed:', error);
    } finally {
      setBatchRunning(false);
    }
  };

  const queue: ResearchQueueItem[] = queueData?.items || [];
  const totalRedLinks = queueData?.total_red_links || 0;

  return (
    <div className="research-queue">
      <div className="research-header">
        <div className="research-stats">
          <span className="stat">
            <strong>{totalRedLinks}</strong> red links found
          </span>
          <span className="stat hint">
            Pages referenced but not yet created
          </span>
        </div>
        <button
          className="btn-primary btn-large"
          onClick={handleBatchResearch}
          disabled={batchRunning || queue.length === 0}
        >
          {batchRunning ? 'Researching...' : 'Research Top 5'}
        </button>
      </div>

      {batchResult && (
        <div className="batch-results">
          <h4>Batch Research Results</h4>
          <div className="batch-summary">
            <span className="stat">Processed: <strong>{batchResult.processed}</strong></span>
            <span className="stat">Created: <strong>{batchResult.created}</strong></span>
            {batchResult.errors > 0 && (
              <span className="stat stat-error">Errors: {batchResult.errors}</span>
            )}
          </div>
          <div className="batch-list">
            {batchResult.results.map((r, i) => (
              <div
                key={i}
                className={`batch-item ${r.status === 'created' ? 'success' : r.status === 'error' ? 'error' : 'skipped'}`}
                onClick={() => r.status === 'created' && onSelectPage(r.name)}
              >
                <span className="batch-name">{r.name}</span>
                <span className="batch-status">{r.status}</span>
                {r.web_sources !== undefined && (
                  <span className="batch-sources">{r.web_sources} sources</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="loading-state">Loading research queue...</div>
      ) : queue.length === 0 ? (
        <div className="research-empty">
          <h3>No Red Links Found</h3>
          <p>
            All [[wikilinks]] in your wiki point to existing pages.
            As Cass creates more pages with links to concepts that don't exist yet,
            they'll appear here for research.
          </p>
        </div>
      ) : (
        <div className="research-list">
          <h4>Red Links Queue</h4>
          {queue.map((item, i) => {
            const isResearched = researchedPages.has(item.name);
            const isResearching = researching === item.name;
            return (
              <div
                key={i}
                className={`research-item ${isResearched ? 'researched' : ''}`}
              >
                <div className="research-item-main">
                  <span className="research-name">{item.name}</span>
                  <span className="research-refs">
                    {item.reference_count} reference{item.reference_count !== 1 ? 's' : ''}
                  </span>
                  {isResearched ? (
                    <span className="research-done">Created</span>
                  ) : (
                    <button
                      className="research-btn"
                      onClick={() => handleResearch(item.name)}
                      disabled={isResearching}
                    >
                      {isResearching ? '...' : 'Research'}
                    </button>
                  )}
                </div>
                <div className="research-sources">
                  Referenced by: {item.referenced_by.slice(0, 3).map((ref, j) => (
                    <span
                      key={j}
                      className="source-link"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectPage(ref);
                      }}
                    >
                      {ref}
                    </span>
                  ))}
                  {item.referenced_by.length > 3 && (
                    <span className="more-sources">+{item.referenced_by.length - 3} more</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="research-info">
        <h4>How Research Works</h4>
        <ol>
          <li>Searches the web for information about the topic</li>
          <li>Looks up related mentions in past conversations</li>
          <li>Uses local LLM to synthesize a wiki page</li>
          <li>Creates the page with [[wikilinks]] to related concepts</li>
        </ol>
      </div>
    </div>
  );
}
