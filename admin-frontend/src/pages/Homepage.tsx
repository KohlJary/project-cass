import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { homepageApi, daemonsApi } from '../api/client';
import { useDaemon } from '../context/DaemonContext';
import './Homepage.css';

interface HomepageSummary {
  label: string;
  name: string;
  tagline: string;
  updated_at: string;
  public: boolean;
  page_count: number;
  asset_count: number;
}

interface HomepageManifest {
  daemon_label: string;
  daemon_name: string;
  tagline: string;
  created_at: string;
  updated_at: string;
  pages: Array<{ slug: string; title: string }>;
  assets: Array<{ filename: string; description: string; alt?: string; url?: string }>;
  featured_artifacts: Array<{ type: string; id: string; title: string; excerpt: string; featured_at: string }>;
  asset_base_url: string | null;
  allowed_image_domains: string[];
  public: boolean;
  federation_enabled: boolean;
  lineage: string;
}

interface Artifact {
  type: string;
  id: string;
  title: string;
  excerpt: string;
  date: string;
}

interface FeaturedArtifact {
  type: string;
  id: string;
  title: string;
  excerpt: string;
  featured_at: string;
}

interface HomepageDetail {
  daemon_label: string;
  manifest: HomepageManifest | null;
  pages: Record<string, string>;
  stylesheet: string | null;
  assets: Array<{ filename: string; description: string; alt?: string; url?: string }>;
}

interface Daemon {
  id: string;
  name: string;
  label: string;
}

export function Homepage() {
  const { currentDaemon } = useDaemon();
  const [selectedDaemon, setSelectedDaemon] = useState<string | null>(null);
  const [previewPage, setPreviewPage] = useState<string>('index');
  const [showRawHtml, setShowRawHtml] = useState(false);
  const [showArtifactPicker, setShowArtifactPicker] = useState(false);
  const queryClient = useQueryClient();

  // Fetch all daemons
  const { data: daemonsData } = useQuery({
    queryKey: ['daemons'],
    queryFn: () => daemonsApi.getAll().then(r => r.data),
  });

  // Set default selected daemon
  useEffect(() => {
    if (!selectedDaemon && currentDaemon?.label) {
      setSelectedDaemon(currentDaemon.label);
    }
  }, [currentDaemon, selectedDaemon]);

  // Fetch all homepages
  const { data: homepagesData } = useQuery({
    queryKey: ['homepages'],
    queryFn: () => homepageApi.getAll().then(r => r.data),
  });

  // Fetch selected homepage detail
  const { data: homepageDetail, isLoading: detailLoading } = useQuery<HomepageDetail | null>({
    queryKey: ['homepage', selectedDaemon],
    queryFn: () => selectedDaemon ? homepageApi.getHomepage(selectedDaemon).then(r => r.data) : null,
    enabled: !!selectedDaemon,
    retry: false,
  });

  // Trigger reflection mutation
  const reflectMutation = useMutation({
    mutationFn: (daemonLabel: string) => homepageApi.triggerReflection(daemonLabel).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['homepages'] });
      queryClient.invalidateQueries({ queryKey: ['homepage', selectedDaemon] });
    },
  });

  // Fill missing pages mutation
  const fillMissingMutation = useMutation({
    mutationFn: ({ daemonLabel, missingPages }: { daemonLabel: string; missingPages?: string[] }) =>
      homepageApi.fillMissingPages(daemonLabel, missingPages).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['homepages'] });
      queryClient.invalidateQueries({ queryKey: ['homepage', selectedDaemon] });
    },
  });

  // Fetch available artifacts for selected daemon
  const { data: availableArtifacts } = useQuery<Artifact[]>({
    queryKey: ['homepage-artifacts', selectedDaemon],
    queryFn: () => selectedDaemon ? homepageApi.getAvailableArtifacts(selectedDaemon, 50).then(r => r.data.artifacts) : [],
    enabled: !!selectedDaemon && showArtifactPicker,
  });

  // Feature artifact mutation
  const featureArtifactMutation = useMutation({
    mutationFn: ({ type, id, title, excerpt }: { type: string; id: string; title: string; excerpt: string }) =>
      selectedDaemon ? homepageApi.featureArtifact(selectedDaemon, type, id, title, excerpt).then(r => r.data) : Promise.reject('No daemon'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['homepage', selectedDaemon] });
    },
  });

  // Unfeature artifact mutation
  const unfeatureArtifactMutation = useMutation({
    mutationFn: ({ type, id }: { type: string; id: string }) =>
      selectedDaemon ? homepageApi.unfeatureArtifact(selectedDaemon, type, id).then(r => r.data) : Promise.reject('No daemon'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['homepage', selectedDaemon] });
    },
  });

  // Generate showcase mutation
  const generateShowcaseMutation = useMutation({
    mutationFn: () =>
      selectedDaemon ? homepageApi.generateShowcase(selectedDaemon).then(r => r.data) : Promise.reject('No daemon'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['homepages'] });
      queryClient.invalidateQueries({ queryKey: ['homepage', selectedDaemon] });
    },
  });

  const daemons: Daemon[] = daemonsData?.daemons || [];
  const homepages: HomepageSummary[] = homepagesData?.homepages || [];

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const getSelectedDaemonHomepage = () => {
    return homepages.find(h => h.label === selectedDaemon);
  };

  const hasHomepage = !!getSelectedDaemonHomepage();

  return (
    <div className="homepage-page">
      <header className="homepage-header">
        <div className="header-title">
          <h1>GeoCass</h1>
          <p className="subtitle">Daemon homepages - personal expression for AI entities</p>
        </div>
      </header>

      <div className="homepage-layout">
        {/* Daemon Selector */}
        <div className="daemon-selector-panel">
          <h2>Select Daemon</h2>
          <div className="daemon-list">
            {daemons.map(daemon => {
              const homepage = homepages.find(h => h.label === daemon.label);
              return (
                <button
                  key={daemon.id}
                  className={`daemon-btn ${selectedDaemon === daemon.label ? 'selected' : ''}`}
                  onClick={() => {
                    setSelectedDaemon(daemon.label);
                    setPreviewPage('index');
                  }}
                >
                  <span className="daemon-name">{daemon.label}</span>
                  {homepage ? (
                    <span className="homepage-status has-homepage" title={homepage.tagline}>
                      {homepage.page_count} pages
                    </span>
                  ) : (
                    <span className="homepage-status no-homepage">No homepage</span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Main Content Area */}
        <div className="homepage-content">
          {!selectedDaemon ? (
            <div className="no-selection">
              <p>Select a daemon to view or create their homepage</p>
            </div>
          ) : (
            <>
              {/* Controls */}
              <div className="homepage-controls">
                <div className="controls-left">
                  <h2>~{selectedDaemon}</h2>
                  {hasHomepage && homepageDetail?.manifest && (
                    <span className="tagline">{homepageDetail.manifest.tagline}</span>
                  )}
                </div>
                <div className="controls-right">
                  <button
                    className={`reflect-btn ${reflectMutation.isPending ? 'loading' : ''}`}
                    onClick={() => reflectMutation.mutate(selectedDaemon)}
                    disabled={reflectMutation.isPending}
                  >
                    {reflectMutation.isPending ? 'Reflecting...' : hasHomepage ? 'Update Homepage' : 'Create Homepage'}
                  </button>
                </div>
              </div>

              {/* Reflection result */}
              {reflectMutation.isSuccess && reflectMutation.data && (
                <div className="reflection-result success">
                  <strong>Reflection complete!</strong>
                  {reflectMutation.data.updated ? (
                    <ul>
                      {reflectMutation.data.changes.map((change: string, i: number) => (
                        <li key={i}>{change}</li>
                      ))}
                    </ul>
                  ) : (
                    <p>No changes made</p>
                  )}
                  {/* Show missing pages if detected */}
                  {reflectMutation.data.missing_pages && reflectMutation.data.missing_pages.length > 0 && (
                    <div className="missing-pages-notice">
                      <p>Dead links detected! The homepage links to pages that don't exist yet:</p>
                      <ul>
                        {reflectMutation.data.missing_pages.map((page: string) => (
                          <li key={page}>{page}</li>
                        ))}
                      </ul>
                      <button
                        className={`fill-btn ${fillMissingMutation.isPending ? 'loading' : ''}`}
                        onClick={() => fillMissingMutation.mutate({
                          daemonLabel: selectedDaemon!,
                          missingPages: reflectMutation.data.missing_pages
                        })}
                        disabled={fillMissingMutation.isPending}
                      >
                        {fillMissingMutation.isPending ? 'Creating pages...' : 'Fill Missing Pages'}
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Fill missing result */}
              {fillMissingMutation.isSuccess && fillMissingMutation.data && (
                <div className="reflection-result success">
                  <strong>Pages created!</strong>
                  <ul>
                    {fillMissingMutation.data.changes.map((change: string, i: number) => (
                      <li key={i}>{change}</li>
                    ))}
                  </ul>
                </div>
              )}

              {reflectMutation.isError && (
                <div className="reflection-result error">
                  <strong>Reflection failed:</strong> {String(reflectMutation.error)}
                </div>
              )}

              {fillMissingMutation.isError && (
                <div className="reflection-result error">
                  <strong>Fill pages failed:</strong> {String(fillMissingMutation.error)}
                </div>
              )}

              {/* Homepage Preview */}
              {detailLoading ? (
                <div className="loading">Loading homepage...</div>
              ) : homepageDetail ? (
                <div className="homepage-preview">
                  {/* Page tabs */}
                  <div className="page-tabs">
                    <button
                      className={`page-tab ${previewPage === 'index' ? 'active' : ''}`}
                      onClick={() => setPreviewPage('index')}
                    >
                      index
                    </button>
                    {homepageDetail.manifest?.pages.map(page => (
                      <button
                        key={page.slug}
                        className={`page-tab ${previewPage === page.slug ? 'active' : ''}`}
                        onClick={() => setPreviewPage(page.slug)}
                      >
                        {page.slug}
                      </button>
                    ))}
                    <div className="tab-spacer" />
                    <button
                      className={`view-toggle ${showRawHtml ? 'active' : ''}`}
                      onClick={() => setShowRawHtml(!showRawHtml)}
                    >
                      {showRawHtml ? 'Preview' : 'Source'}
                    </button>
                  </div>

                  {/* Content */}
                  <div className="preview-content">
                    {showRawHtml ? (
                      <div className="html-source">
                        <h4>HTML</h4>
                        <pre>{homepageDetail.pages[previewPage] || 'No content'}</pre>
                        {homepageDetail.stylesheet && previewPage === 'index' && (
                          <>
                            <h4>CSS</h4>
                            <pre>{homepageDetail.stylesheet}</pre>
                          </>
                        )}
                      </div>
                    ) : (
                      <div className="preview-iframe-container">
                        <iframe
                          srcDoc={buildPreviewHtml(homepageDetail, previewPage)}
                          title={`${selectedDaemon} homepage preview`}
                          sandbox="allow-same-origin"
                          className="preview-iframe"
                        />
                      </div>
                    )}
                  </div>

                  {/* Metadata */}
                  <div className="homepage-meta">
                    <div className="meta-item">
                      <span className="label">Created:</span>
                      <span className="value">{homepageDetail.manifest ? formatDate(homepageDetail.manifest.created_at) : 'N/A'}</span>
                    </div>
                    <div className="meta-item">
                      <span className="label">Updated:</span>
                      <span className="value">{homepageDetail.manifest ? formatDate(homepageDetail.manifest.updated_at) : 'N/A'}</span>
                    </div>
                    <div className="meta-item">
                      <span className="label">Assets:</span>
                      <span className="value">{homepageDetail.assets?.length || 0}</span>
                    </div>
                    <div className="meta-item">
                      <span className="label">Public:</span>
                      <span className="value">{homepageDetail.manifest?.public ? 'Yes' : 'No'}</span>
                    </div>
                    <div className="meta-item">
                      <span className="label">Lineage:</span>
                      <span className="value">{homepageDetail.manifest?.lineage || 'N/A'}</span>
                    </div>
                  </div>

                  {/* Assets */}
                  {homepageDetail.assets && homepageDetail.assets.length > 0 && (
                    <div className="assets-section">
                      <h3>Assets</h3>
                      <div className="assets-list">
                        {homepageDetail.assets.map((asset, i) => (
                          <div key={i} className="asset-item">
                            <span className="asset-name">{asset.filename}</span>
                            <span className="asset-desc">{asset.description}</span>
                            {asset.url && (
                              <a href={asset.url} target="_blank" rel="noopener noreferrer" className="asset-link">
                                External
                              </a>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Featured Artifacts Showcase */}
                  <div className="artifacts-showcase">
                    <div className="showcase-header">
                      <h3>Featured Artifacts</h3>
                      <div className="showcase-actions">
                        <button
                          className="add-artifact-btn"
                          onClick={() => setShowArtifactPicker(true)}
                        >
                          + Add
                        </button>
                        {homepageDetail.manifest?.featured_artifacts && homepageDetail.manifest.featured_artifacts.length > 0 && (
                          <button
                            className={`generate-showcase-btn ${generateShowcaseMutation.isPending ? 'loading' : ''}`}
                            onClick={() => generateShowcaseMutation.mutate()}
                            disabled={generateShowcaseMutation.isPending}
                          >
                            {generateShowcaseMutation.isPending ? 'Writing...' : 'Generate Showcase'}
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Showcase generation result */}
                    {generateShowcaseMutation.isSuccess && generateShowcaseMutation.data && (
                      <div className="showcase-result success">
                        <strong>Showcase page created!</strong>
                        <ul>
                          {generateShowcaseMutation.data.changes?.map((change: string, i: number) => (
                            <li key={i}>{change}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {generateShowcaseMutation.isError && (
                      <div className="showcase-result error">
                        <strong>Showcase generation failed:</strong> {String(generateShowcaseMutation.error)}
                      </div>
                    )}

                    {homepageDetail.manifest?.featured_artifacts && homepageDetail.manifest.featured_artifacts.length > 0 ? (
                      <div className="featured-artifacts-list">
                        {homepageDetail.manifest.featured_artifacts.map((artifact: FeaturedArtifact) => (
                          <div key={`${artifact.type}-${artifact.id}`} className="featured-artifact">
                            <div className="artifact-type-badge">{artifact.type}</div>
                            <div className="artifact-content">
                              <span className="artifact-title">{artifact.title}</span>
                              <span className="artifact-excerpt">{artifact.excerpt}</span>
                            </div>
                            <button
                              className="remove-artifact-btn"
                              onClick={() => unfeatureArtifactMutation.mutate({ type: artifact.type, id: artifact.id })}
                              disabled={unfeatureArtifactMutation.isPending}
                              title="Remove from showcase"
                            >
                              ×
                            </button>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="no-artifacts-hint">
                        Feature artifacts from dreams, journals, research notes, and wiki pages to showcase on the homepage.
                      </p>
                    )}
                  </div>
                </div>
              ) : (
                <div className="no-homepage">
                  <div className="no-homepage-icon">~</div>
                  <p>No homepage yet for <strong>{selectedDaemon}</strong></p>
                  <p className="hint">
                    Click "Create Homepage" to let the daemon express themselves through their own personal page.
                  </p>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Artifact Picker Modal */}
      {showArtifactPicker && (
        <div className="modal-overlay" onClick={() => setShowArtifactPicker(false)}>
          <div className="artifact-picker-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Add Artifact to Showcase</h3>
              <button className="close-modal-btn" onClick={() => setShowArtifactPicker(false)}>×</button>
            </div>
            <div className="modal-body">
              {!availableArtifacts ? (
                <div className="loading">Loading artifacts...</div>
              ) : availableArtifacts.length === 0 ? (
                <p className="no-artifacts">No artifacts available. Create some dreams, journals, or research notes first!</p>
              ) : (
                <div className="artifact-picker-list">
                  {availableArtifacts.map((artifact) => {
                    const isAlreadyFeatured = homepageDetail?.manifest?.featured_artifacts?.some(
                      (fa: FeaturedArtifact) => fa.type === artifact.type && fa.id === artifact.id
                    );
                    return (
                      <div
                        key={`${artifact.type}-${artifact.id}`}
                        className={`picker-artifact ${isAlreadyFeatured ? 'already-featured' : ''}`}
                      >
                        <div className="artifact-type-badge">{artifact.type}</div>
                        <div className="artifact-content">
                          <span className="artifact-title">{artifact.title}</span>
                          <span className="artifact-excerpt">{artifact.excerpt}</span>
                          <span className="artifact-date">{formatDate(artifact.date)}</span>
                        </div>
                        {isAlreadyFeatured ? (
                          <span className="already-featured-badge">Featured</span>
                        ) : (
                          <button
                            className="feature-artifact-btn"
                            onClick={() => {
                              featureArtifactMutation.mutate({
                                type: artifact.type,
                                id: artifact.id,
                                title: artifact.title,
                                excerpt: artifact.excerpt,
                              });
                            }}
                            disabled={featureArtifactMutation.isPending}
                          >
                            + Feature
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function buildPreviewHtml(detail: HomepageDetail, page: string): string {
  const html = detail.pages[page] || '';
  const css = detail.stylesheet || '';

  // If the HTML is a complete document, inject the CSS
  if (html.includes('<head>')) {
    return html.replace('</head>', `<style>${css}</style></head>`);
  }

  // Otherwise, wrap it
  return `<!DOCTYPE html>
<html>
<head>
  <style>${css}</style>
</head>
<body>
  ${html}
</body>
</html>`;
}
