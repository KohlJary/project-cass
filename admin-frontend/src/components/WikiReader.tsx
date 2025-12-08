import { useState, useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
import { wikiApi } from '../api/client';
import './WikiReader.css';

// Shared types
export interface WikiPage {
  name: string;
  title: string;
  page_type: string;
  link_count: number;
  modified_at: string;
}

export interface WikiPageData {
  name: string;
  content: string;
  page_type: string;
  title: string;
  links: string[];
}

export interface WikiBacklink {
  name: string;
  title: string;
  page_type: string;
}

export interface WikiMaturity {
  level: number;
  depth_score: number;
  connections: { incoming: number; outgoing: number };
  should_deepen: boolean;
}

// Options for customizing the reader
export interface WikiReaderOptions {
  /** Show the sidebar with page list */
  showSidebar?: boolean;
  /** Show the search box in sidebar */
  showSearch?: boolean;
  /** Show edit button and enable editing */
  editable?: boolean;
  /** Show maturity information */
  showMaturity?: boolean;
  /** Show backlinks section */
  showBacklinks?: boolean;
  /** Show outgoing links section */
  showOutgoingLinks?: boolean;
  /** Custom empty state message */
  emptyMessage?: string;
  /** Compact mode - smaller text, tighter spacing */
  compact?: boolean;
  /** Maximum height (for embedding in panels) */
  maxHeight?: string;
}

const defaultOptions: WikiReaderOptions = {
  showSidebar: true,
  showSearch: true,
  editable: true,
  showMaturity: true,
  showBacklinks: true,
  showOutgoingLinks: true,
  compact: false,
};

// Full-featured WikiReader with all props managed externally
export interface WikiReaderProps {
  pages: WikiPage[];
  selectedPage: string | null;
  pageData: WikiPageData | null;
  backlinks?: WikiBacklink[];
  maturity?: WikiMaturity | null;
  onSelectPage: (name: string) => void;
  onEdit?: () => void;
  isEditing?: boolean;
  editContent?: string;
  onEditChange?: (content: string) => void;
  onSave?: () => void;
  onCancelEdit?: () => void;
  isSaving?: boolean;
  options?: WikiReaderOptions;
}

export function WikiReader({
  pages,
  selectedPage,
  pageData,
  backlinks = [],
  maturity,
  onSelectPage,
  onEdit,
  isEditing = false,
  editContent = '',
  onEditChange,
  onSave,
  onCancelEdit,
  isSaving = false,
  options = {},
}: WikiReaderProps) {
  const opts = { ...defaultOptions, ...options };
  const [searchQuery, setSearchQuery] = useState('');

  // Filter pages for sidebar
  const filteredPages = useMemo(() => {
    if (!searchQuery) return pages;
    const query = searchQuery.toLowerCase();
    return pages.filter(p =>
      p.name.toLowerCase().includes(query) ||
      p.title.toLowerCase().includes(query)
    );
  }, [pages, searchQuery]);

  // Strip YAML frontmatter from content for display
  const displayContent = useMemo(() => {
    if (!pageData?.content) return '';
    const content = pageData.content;
    if (content.startsWith('---')) {
      const endIndex = content.indexOf('---', 3);
      if (endIndex !== -1) {
        return content.slice(endIndex + 3).trim();
      }
    }
    return content;
  }, [pageData?.content]);

  const renderContent = useCallback((content: string) => {
    const cleanContent = content.replace(/\[\[([^\]]+)\]\]/g, '$1');
    return <ReactMarkdown>{cleanContent}</ReactMarkdown>;
  }, []);

  const getMaturityLabel = (level: number) => {
    switch (level) {
      case 0: return 'Seed';
      case 1: return 'Sprouting';
      case 2: return 'Growing';
      case 3: return 'Mature';
      case 4: return 'Deep';
      default: return 'Unknown';
    }
  };

  const containerClass = `wiki-reader ${opts.compact ? 'compact' : ''} ${!opts.showSidebar ? 'no-sidebar' : ''}`;
  const containerStyle = opts.maxHeight ? { maxHeight: opts.maxHeight, overflow: 'auto' } : {};

  return (
    <div className={containerClass} style={containerStyle}>
      {/* Page list sidebar */}
      {opts.showSidebar && (
        <div className="reader-sidebar">
          {opts.showSearch && (
            <div className="reader-search">
              <input
                type="text"
                placeholder="Search pages..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
          )}
          <div className="reader-page-list">
            {filteredPages.map(page => (
              <div
                key={page.name}
                className={`reader-page-item ${selectedPage === page.name ? 'selected' : ''}`}
                onClick={() => onSelectPage(page.name)}
              >
                <span className={`type-dot type-${page.page_type}`} />
                <span className="page-name">{page.name}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Main content area */}
      <div className="reader-content">
        {!selectedPage ? (
          <div className="reader-empty">
            <h2>{opts.emptyMessage || 'Select a page to read'}</h2>
            {opts.showSidebar && (
              <p>Choose a page from the list on the left, or search for a specific topic.</p>
            )}
            {!opts.showSidebar && pages.length > 0 && (
              <div className="quick-links">
                <div className="quick-link-grid">
                  {pages.slice(0, 8).map(page => (
                    <button
                      key={page.name}
                      className="quick-link-btn"
                      onClick={() => onSelectPage(page.name)}
                    >
                      {page.name}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : !pageData ? (
          <div className="reader-loading">Loading page...</div>
        ) : isEditing && opts.editable ? (
          <div className="reader-edit">
            <div className="edit-header">
              <h2>Editing: {pageData.title}</h2>
              <div className="edit-actions">
                <button className="btn-primary" onClick={onSave} disabled={isSaving}>
                  {isSaving ? 'Saving...' : 'Save'}
                </button>
                <button className="btn-secondary" onClick={onCancelEdit}>
                  Cancel
                </button>
              </div>
            </div>
            <textarea
              className="edit-textarea"
              value={editContent}
              onChange={(e) => onEditChange?.(e.target.value)}
            />
          </div>
        ) : (
          <article className="reader-article">
            <header className="article-header">
              <div className="article-meta">
                <span className={`type-badge type-${pageData.page_type}`}>
                  {pageData.page_type}
                </span>
                {opts.showMaturity && maturity && maturity.level !== undefined && (
                  <span className={`maturity-badge maturity-${maturity.level}`}>
                    {getMaturityLabel(maturity.level)}
                    {maturity.depth_score !== undefined && ` (${maturity.depth_score.toFixed(2)})`}
                  </span>
                )}
                {opts.editable && onEdit && (
                  <button className="edit-btn" onClick={onEdit}>Edit</button>
                )}
              </div>
              <h1>{pageData.title}</h1>
            </header>

            <div className="article-body">
              {renderContent(displayContent)}
            </div>

            {/* Connections section */}
            <footer className="article-footer">
              {opts.showOutgoingLinks && pageData.links && pageData.links.length > 0 && (
                <div className="footer-section outgoing-links">
                  <h4>Links to ({pageData.links.length})</h4>
                  <div className="link-chips">
                    {[...new Set(pageData.links)].map(link => {
                      const exists = pages.some(p => p.name.toLowerCase() === link.toLowerCase());
                      return (
                        <button
                          key={link}
                          className={`link-chip ${exists ? 'exists' : 'red-link'}`}
                          onClick={() => onSelectPage(link)}
                        >
                          {link}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {opts.showBacklinks && backlinks.length > 0 && (
                <div className="footer-section backlinks">
                  <h4>Linked from ({backlinks.length})</h4>
                  <div className="link-chips">
                    {backlinks.map(bl => (
                      <button
                        key={bl.name}
                        className="link-chip exists"
                        onClick={() => onSelectPage(bl.name)}
                      >
                        {bl.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {opts.showMaturity && maturity && maturity.level !== undefined && (
                <div className="footer-section maturity-info">
                  <h4>Maturity</h4>
                  <div className="maturity-details">
                    <span>Level {maturity.level}: {getMaturityLabel(maturity.level)}</span>
                    {maturity.depth_score !== undefined && <span>Depth: {maturity.depth_score.toFixed(2)}</span>}
                    {maturity.connections && <span>In: {maturity.connections.incoming} / Out: {maturity.connections.outgoing}</span>}
                    {maturity.should_deepen && (
                      <span className="deepen-indicator">Ready for deepening</span>
                    )}
                  </div>
                </div>
              )}
            </footer>
          </article>
        )}
      </div>
    </div>
  );
}

// Self-contained WikiReader that manages its own data fetching
// Good for embedding in other pages with minimal setup
export interface StandaloneWikiReaderProps {
  /** List of page names to show (if not provided, fetches all pages) */
  pageNames?: string[];
  /** Initially selected page */
  initialPage?: string;
  /** Callback when page selection changes */
  onPageChange?: (pageName: string | null) => void;
  /** Options for customizing the reader */
  options?: WikiReaderOptions;
}

export function StandaloneWikiReader({
  pageNames,
  initialPage,
  onPageChange,
  options = {},
}: StandaloneWikiReaderProps) {
  const [selectedPage, setSelectedPage] = useState<string | null>(initialPage || null);

  // Fetch all pages or filter by names
  const { data: allPagesData } = useQuery({
    queryKey: ['wiki-pages'],
    queryFn: () => wikiApi.getPages().then(r => r.data),
  });

  // Filter pages if pageNames provided
  const pages: WikiPage[] = useMemo(() => {
    const allPages: WikiPage[] = allPagesData?.pages || [];
    if (!pageNames || pageNames.length === 0) return allPages;
    return allPages.filter((p: WikiPage) => pageNames.includes(p.name));
  }, [allPagesData, pageNames]);

  // Fetch selected page data
  const { data: pageData } = useQuery({
    queryKey: ['wiki-page', selectedPage],
    queryFn: () => selectedPage ? wikiApi.getPage(selectedPage).then(r => r.data) : null,
    enabled: !!selectedPage,
  });

  // Fetch backlinks if enabled
  const { data: backlinksData } = useQuery({
    queryKey: ['wiki-backlinks', selectedPage],
    queryFn: () => selectedPage ? wikiApi.getBacklinks(selectedPage).then(r => r.data) : null,
    enabled: !!selectedPage && options.showBacklinks !== false,
  });

  // Fetch maturity if enabled
  const { data: maturityData } = useQuery({
    queryKey: ['wiki-maturity', selectedPage],
    queryFn: () => selectedPage ? wikiApi.getPageMaturity(selectedPage).then(r => r.data) : null,
    enabled: !!selectedPage && options.showMaturity !== false,
  });

  const handleSelectPage = (name: string) => {
    setSelectedPage(name);
    onPageChange?.(name);
  };

  return (
    <WikiReader
      pages={pages}
      selectedPage={selectedPage}
      pageData={pageData?.page || null}
      backlinks={backlinksData?.backlinks || []}
      maturity={maturityData}
      onSelectPage={handleSelectPage}
      options={{
        editable: false, // Standalone version is read-only by default
        ...options,
      }}
    />
  );
}

export default WikiReader;
