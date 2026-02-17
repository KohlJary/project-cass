import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { artStudyApi } from '../api/client';
import type { ArtworkResponse, HouseStyleCreatedPiece } from '../api/client';
import type { ModalType, TabType, MainViewType, GalleryItem } from './artstudy/types';
import './ArtStudy.css';

function formatDate(dateStr: string | null): string {
  if (!dateStr) return 'Never';
  return new Date(dateStr).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function ArtStudy() {
  const [selectedArtistId, setSelectedArtistId] = useState<string | null>(null);
  const [selectedArtwork, setSelectedArtwork] = useState<ArtworkResponse | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [activeModal, setActiveModal] = useState<ModalType>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [studiedOnly, setStudiedOnly] = useState(false);
  const [mainView, setMainView] = useState<MainViewType>('artists');
  const [houseStyleCreatedPieces, setHouseStyleCreatedPieces] = useState<HouseStyleCreatedPiece[]>([]);
  const [magnifiedItem, setMagnifiedItem] = useState<GalleryItem | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Form states
  const [newArtistName, setNewArtistName] = useState('');
  const [newArtistPeriod, setNewArtistPeriod] = useState('');
  const [newArtistWikipedia, setNewArtistWikipedia] = useState('');
  const [newArtistMovements, setNewArtistMovements] = useState('');

  const [newArtworkTitle, setNewArtworkTitle] = useState('');
  const [newArtworkYear, setNewArtworkYear] = useState('');
  const [newArtworkMedium, setNewArtworkMedium] = useState('');
  const [copiedStudy, setCopiedStudy] = useState(false);
  const [createdPieces, setCreatedPieces] = useState<{
    image_path: string;
    filename: string;
    seed: number;
    title: string;
    artist_statement: string;
    borrowed_elements: string[];
    prompt_used: string;
    process_id: string;
  }[]>([]);

  const queryClient = useQueryClient();

  // Queries
  const { data: artistsData, isLoading: artistsLoading } = useQuery({
    queryKey: ['art-study-artists', studiedOnly],
    queryFn: () => artStudyApi.listArtists(studiedOnly).then(r => r.data),
  });

  const { data: selectedArtist } = useQuery({
    queryKey: ['art-study-artist', selectedArtistId],
    queryFn: () => selectedArtistId ? artStudyApi.getArtist(selectedArtistId).then(r => r.data) : null,
    enabled: !!selectedArtistId,
  });

  const { data: artworksData } = useQuery({
    queryKey: ['art-study-artworks', selectedArtistId],
    queryFn: () => selectedArtistId ? artStudyApi.listArtworks(selectedArtistId).then(r => r.data) : [],
    enabled: !!selectedArtistId,
  });

  const { data: observationsData } = useQuery({
    queryKey: ['art-study-observations', selectedArtistId],
    queryFn: () => selectedArtistId ? artStudyApi.getArtistObservations(selectedArtistId).then(r => r.data) : null,
    enabled: !!selectedArtistId && activeTab === 'observations',
  });

  const { data: synthesisData } = useQuery({
    queryKey: ['art-study-synthesis', selectedArtistId],
    queryFn: () => selectedArtistId ? artStudyApi.getArtistSynthesis(selectedArtistId).then(r => r.data).catch(() => null) : null,
    enabled: !!selectedArtistId && activeTab === 'synthesis',
  });

  const { data: creationsData } = useQuery({
    queryKey: ['art-study-creations', selectedArtistId],
    queryFn: () => selectedArtistId ? artStudyApi.listCreations(selectedArtistId).then(r => r.data).catch(() => []) : [],
    enabled: !!selectedArtistId && activeTab === 'synthesis',
  });

  const { data: studyData } = useQuery({
    queryKey: ['art-study-study', selectedArtwork?.id],
    queryFn: () => selectedArtwork ? artStudyApi.getArtworkStudy(selectedArtwork.id).then(r => r.data).catch(() => null) : null,
    enabled: !!selectedArtwork && activeModal === 'view-study',
  });

  // House Style queries
  const { data: houseStyleStats, refetch: refetchHouseStyleStats } = useQuery({
    queryKey: ['house-style-stats'],
    queryFn: () => artStudyApi.getHouseStyleStats().then(r => r.data),
    enabled: mainView === 'house-style',
  });

  const { data: houseStyle, refetch: refetchHouseStyle } = useQuery({
    queryKey: ['house-style'],
    queryFn: () => artStudyApi.getHouseStyle().then(r => r.data).catch(() => null),
    enabled: mainView === 'house-style',
  });

  const { data: adoptedElements, refetch: refetchElements } = useQuery({
    queryKey: ['adopted-elements'],
    queryFn: () => artStudyApi.getAdoptedElements({ active_only: true }).then(r => r.data),
    enabled: mainView === 'house-style',
  });

  const { data: houseStyleCreations } = useQuery({
    queryKey: ['house-style-creations'],
    queryFn: () => artStudyApi.listHouseStyleCreations().then(r => r.data).catch(() => []),
    enabled: mainView === 'house-style',
  });

  // Gallery: fetch all creations from all artists + house style
  const { data: galleryItems } = useQuery({
    queryKey: ['gallery-all', artistsData],
    queryFn: async () => {
      const items: GalleryItem[] = [];

      // Fetch house style creations
      try {
        const hsCreations = await artStudyApi.listHouseStyleCreations().then(r => r.data);
        for (const c of hsCreations) {
          items.push({
            id: c.process_id,
            filename: c.filename,
            title: c.title,
            artist_statement: c.artist_statement,
            prompt_used: c.prompt_used,
            source: 'house-style',
            elements: c.elements_used,
            style_aspects: c.style_aspects,
            style_version: c.style_version,
          });
        }
      } catch { /* ignore */ }

      // Fetch creations from all studied artists
      if (artistsData) {
        for (const artist of artistsData.filter(a => a.works_studied > 0)) {
          try {
            const artistCreations = await artStudyApi.listCreations(artist.id).then(r => r.data);
            for (const c of artistCreations) {
              items.push({
                id: c.process_id,
                filename: c.filename,
                title: c.title,
                artist_statement: c.artist_statement,
                prompt_used: c.prompt_used,
                source: 'artist',
                source_name: artist.name,
                elements: c.borrowed_elements,
              });
            }
          } catch { /* ignore */ }
        }
      }

      // Deduplicate by filename
      const seen = new Set<string>();
      return items.filter(item => {
        if (seen.has(item.filename)) return false;
        seen.add(item.filename);
        return true;
      });
    },
    enabled: mainView === 'gallery',
  });

  // Mutations
  const createArtistMutation = useMutation({
    mutationFn: artStudyApi.createArtist,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['art-study-artists'] });
      setActiveModal(null);
      resetArtistForm();
    },
  });

  const createArtworkMutation = useMutation({
    mutationFn: artStudyApi.createArtwork,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['art-study-artworks', selectedArtistId] });
      setActiveModal(null);
      resetArtworkForm();
    },
  });

  const fetchBiographyMutation = useMutation({
    mutationFn: (artistId: string) => artStudyApi.fetchBiography(artistId).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['art-study-artist', selectedArtistId] });
      queryClient.invalidateQueries({ queryKey: ['art-study-observations', selectedArtistId] });
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      const message = error.response?.data?.detail || error.message || 'Failed to fetch biography';
      alert(`Error: ${message}`);
    },
  });

  const uploadImageMutation = useMutation({
    mutationFn: ({ artworkId, file }: { artworkId: string; file: File }) =>
      artStudyApi.uploadArtworkImage(artworkId, file).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['art-study-artworks', selectedArtistId] });
    },
  });

  const studyArtworkMutation = useMutation({
    mutationFn: (artworkId: string) => artStudyApi.studyArtwork(artworkId).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['art-study-artworks', selectedArtistId] });
      queryClient.invalidateQueries({ queryKey: ['art-study-artist', selectedArtistId] });
      queryClient.invalidateQueries({ queryKey: ['art-study-study', selectedArtwork?.id] });
    },
  });

  const synthesizeMutation = useMutation({
    mutationFn: (artistId: string) => artStudyApi.synthesizeArtist(artistId, 1).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['art-study-synthesis', selectedArtistId] });
    },
  });

  const importArtworksMutation = useMutation({
    mutationFn: ({ artistId, maxWorks, provider }: { artistId: string; maxWorks?: number; provider?: string }) =>
      artStudyApi.importArtworks(artistId, maxWorks, provider).then(r => r.data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['art-study-artworks', selectedArtistId] });
      alert(data.message);
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      const message = error.response?.data?.detail || error.message || 'Failed to import artworks';
      alert(`Error: ${message}`);
    },
  });

  const createFromSynthesisMutation = useMutation({
    mutationFn: ({ artistId, numPieces }: { artistId: string; numPieces?: number }) =>
      artStudyApi.createFromSynthesis(artistId, numPieces).then(r => r.data),
    onSuccess: (data) => {
      setCreatedPieces(data);
      setActiveModal('view-created');
      // Refresh the gallery
      queryClient.invalidateQueries({ queryKey: ['art-study-creations', selectedArtistId] });
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      const message = error.response?.data?.detail || error.message || 'Failed to create artwork';
      alert(`Error: ${message}`);
    },
  });

  // House Style mutations
  const extractElementsMutation = useMutation({
    mutationFn: (artistId: string) => artStudyApi.extractAdoptedElements(artistId).then(r => r.data),
    onSuccess: () => {
      refetchElements();
      refetchHouseStyleStats();
      queryClient.invalidateQueries({ queryKey: ['house-style-stats'] });
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      const message = error.response?.data?.detail || error.message || 'Failed to extract elements';
      alert(`Error: ${message}`);
    },
  });

  const synthesizeHouseStyleMutation = useMutation({
    mutationFn: () => artStudyApi.synthesizeHouseStyle(3).then(r => r.data),
    onSuccess: () => {
      refetchHouseStyle();
      refetchHouseStyleStats();
      queryClient.invalidateQueries({ queryKey: ['house-style'] });
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      const message = error.response?.data?.detail || error.message || 'Failed to synthesize house style';
      alert(`Error: ${message}`);
    },
  });

  const createFromHouseStyleMutation = useMutation({
    mutationFn: (numPieces?: number) => artStudyApi.createFromHouseStyle(numPieces).then(r => r.data),
    onSuccess: (data) => {
      setHouseStyleCreatedPieces(data);
      setActiveModal('view-house-style-created');
      queryClient.invalidateQueries({ queryKey: ['house-style-creations'] });
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      const message = error.response?.data?.detail || error.message || 'Failed to create artwork';
      alert(`Error: ${message}`);
    },
  });

  const deactivateElementMutation = useMutation({
    mutationFn: (elementId: string) => artStudyApi.deactivateElement(elementId).then(r => r.data),
    onSuccess: () => {
      refetchElements();
      refetchHouseStyleStats();
    },
  });

  const resetArtistForm = () => {
    setNewArtistName('');
    setNewArtistPeriod('');
    setNewArtistWikipedia('');
    setNewArtistMovements('');
  };

  const resetArtworkForm = () => {
    setNewArtworkTitle('');
    setNewArtworkYear('');
    setNewArtworkMedium('');
  };

  const handleCreateArtist = () => {
    if (!newArtistName.trim()) return;
    createArtistMutation.mutate({
      name: newArtistName.trim(),
      period: newArtistPeriod || undefined,
      wikipedia_url: newArtistWikipedia || undefined,
      movements: newArtistMovements ? newArtistMovements.split(',').map(m => m.trim()) : undefined,
    });
  };

  const handleCreateArtwork = () => {
    if (!selectedArtistId || !newArtworkTitle.trim()) return;
    createArtworkMutation.mutate({
      artist_id: selectedArtistId,
      title: newArtworkTitle.trim(),
      year: newArtworkYear ? parseInt(newArtworkYear, 10) : undefined,
      medium: newArtworkMedium || undefined,
    });
  };

  const handleFileUpload = async (artwork: ArtworkResponse, file: File) => {
    await uploadImageMutation.mutateAsync({ artworkId: artwork.id, file });
  };

  const filteredArtists = artistsData?.filter(a =>
    a.name.toLowerCase().includes(searchQuery.toLowerCase())
  ) || [];

  const copyStudyToClipboard = () => {
    if (!studyData || !selectedArtwork) return;

    const artist = selectedArtist?.name || 'Unknown Artist';
    const lines: string[] = [
      `# Study: ${selectedArtwork.title}`,
      `**Artist:** ${artist}`,
      selectedArtwork.year ? `**Year:** ${selectedArtwork.year}` : '',
      selectedArtwork.medium ? `**Medium:** ${selectedArtwork.medium}` : '',
      '',
    ].filter(Boolean);

    if (studyData.first_impression) {
      lines.push('## First Impression', studyData.first_impression, '');
    }
    if (studyData.composition_analysis) {
      lines.push('## Composition', studyData.composition_analysis, '');
    }
    if (studyData.color_analysis) {
      lines.push('## Color', studyData.color_analysis, '');
    }
    if (studyData.brushwork_notes) {
      lines.push('## Brushwork', studyData.brushwork_notes, '');
    }
    if (studyData.emotional_quality) {
      lines.push('## Emotional Quality', studyData.emotional_quality, '');
    }
    if (studyData.thematic_elements) {
      lines.push('## Thematic Elements', studyData.thematic_elements, '');
    }
    if (studyData.key_learnings.length > 0) {
      lines.push('## Key Learnings');
      studyData.key_learnings.forEach(l => lines.push(`- ${l}`));
      lines.push('');
    }
    if (studyData.prompt_vocabulary.length > 0) {
      lines.push('## Prompt Vocabulary');
      lines.push(studyData.prompt_vocabulary.join(', '));
      lines.push('');
    }

    lines.push(`---`, `*Studied: ${formatDate(studyData.studied_at)}*`);

    navigator.clipboard.writeText(lines.join('\n'));
  };

  const artworks = artworksData || [];
  const observations = observationsData?.observations || [];

  return (
    <div className="art-study-page">
      {/* Header */}
      <div className="art-study-header">
        <div className="header-top">
          <div>
            <h1>Art Study</h1>
            <p className="subtitle">Cass's visual art education system</p>
          </div>
          <div className="view-toggle">
            <button
              className={`toggle-btn ${mainView === 'artists' ? 'active' : ''}`}
              onClick={() => setMainView('artists')}
            >
              🎨 Artists
            </button>
            <button
              className={`toggle-btn ${mainView === 'house-style' ? 'active' : ''}`}
              onClick={() => setMainView('house-style')}
            >
              🏠 House Style
            </button>
            <button
              className={`toggle-btn ${mainView === 'gallery' ? 'active' : ''}`}
              onClick={() => setMainView('gallery')}
            >
              🖼️ Gallery
            </button>
          </div>
        </div>
        {mainView === 'artists' && (
          <div className="header-actions">
            <button className="btn btn-primary" onClick={() => setActiveModal('create-artist')}>
              + Add Artist
            </button>
          </div>
        )}
      </div>

      {/* Main Layout */}
      <div className="art-study-main">
        {mainView === 'house-style' ? (
          /* House Style View */
          <div className="house-style-panel">
            {/* Stats */}
            <div className="house-style-stats">
              <div className="stat-card">
                <div className="stat-value">{houseStyleStats?.artists_studied || 0}</div>
                <div className="stat-label">Artists Studied</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{houseStyleStats?.elements_adopted || 0}</div>
                <div className="stat-label">Elements Adopted</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">v{houseStyleStats?.style_version || 0}</div>
                <div className="stat-label">Style Version</div>
              </div>
              {houseStyleStats?.has_manifesto && (
                <div className="stat-card manifesto">
                  <div className="stat-value">✓</div>
                  <div className="stat-label">Has Manifesto</div>
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="house-style-actions">
              <button
                className="btn btn-primary"
                onClick={() => synthesizeHouseStyleMutation.mutate()}
                disabled={synthesizeHouseStyleMutation.isPending || (houseStyleStats?.artists_studied || 0) < 3}
                title={`Need at least 3 artists studied (have ${houseStyleStats?.artists_studied || 0})`}
              >
                {synthesizeHouseStyleMutation.isPending ? 'Synthesizing...' : houseStyle ? '🔄 Re-synthesize Style' : '✨ Synthesize House Style'}
              </button>
              {houseStyle && (
                <>
                  <button
                    className="btn btn-accent"
                    onClick={() => createFromHouseStyleMutation.mutate(5)}
                    disabled={createFromHouseStyleMutation.isPending}
                  >
                    {createFromHouseStyleMutation.isPending ? 'Creating...' : '🎨 Create 5 Pieces'}
                  </button>
                  {houseStyleCreations && houseStyleCreations.length > 0 && (
                    <button
                      className="btn btn-ghost"
                      onClick={() => {
                        setHouseStyleCreatedPieces(houseStyleCreations);
                        setActiveModal('view-house-style-created');
                      }}
                    >
                      🖼️ Gallery ({houseStyleCreations.length})
                    </button>
                  )}
                </>
              )}
            </div>

            {/* House Style Display */}
            {houseStyle ? (
              <div className="house-style-content">
                <div className="house-style-header">
                  <h2>Personal Style v{houseStyle.version}</h2>
                  <span className="style-meta">
                    {houseStyle.artists_studied} artists · {houseStyle.elements_adopted} elements
                  </span>
                </div>

                {houseStyle.style_manifesto && (
                  <div className="style-section manifesto-section">
                    <h3>Style Manifesto</h3>
                    <blockquote>{houseStyle.style_manifesto}</blockquote>
                  </div>
                )}

                {houseStyle.what_makes_it_mine && (
                  <div className="style-section">
                    <h3>What Makes It Mine</h3>
                    <p>{houseStyle.what_makes_it_mine}</p>
                  </div>
                )}

                <div className="style-grid">
                  {houseStyle.color_philosophy && (
                    <div className="style-card">
                      <h4>🎨 Color Philosophy</h4>
                      <p>{houseStyle.color_philosophy}</p>
                    </div>
                  )}
                  {houseStyle.light_approach && (
                    <div className="style-card">
                      <h4>💡 Light Approach</h4>
                      <p>{houseStyle.light_approach}</p>
                    </div>
                  )}
                  {houseStyle.compositional_voice && (
                    <div className="style-card">
                      <h4>📐 Compositional Voice</h4>
                      <p>{houseStyle.compositional_voice}</p>
                    </div>
                  )}
                  {houseStyle.emotional_register && (
                    <div className="style-card">
                      <h4>💜 Emotional Register</h4>
                      <p>{houseStyle.emotional_register}</p>
                    </div>
                  )}
                </div>

                {houseStyle.style_descriptors.length > 0 && (
                  <div className="style-section">
                    <h3>Style Descriptors</h3>
                    <div className="tag-list">
                      {houseStyle.style_descriptors.map((desc, i) => (
                        <span key={i} className="tag style">{desc}</span>
                      ))}
                    </div>
                  </div>
                )}

                {houseStyle.recurring_themes.length > 0 && (
                  <div className="style-section">
                    <h3>Recurring Themes</h3>
                    <div className="tag-list">
                      {houseStyle.recurring_themes.map((theme, i) => (
                        <span key={i} className="tag theme">{theme}</span>
                      ))}
                    </div>
                  </div>
                )}

                {houseStyle.signature_techniques.length > 0 && (
                  <div className="style-section">
                    <h3>Signature Techniques</h3>
                    <ul>
                      {houseStyle.signature_techniques.map((tech, i) => (
                        <li key={i}>{tech}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <div className="empty-state house-style-empty">
                <div className="empty-state-icon">🏠</div>
                <h3>No House Style Yet</h3>
                <p>
                  Study at least 3 artists, synthesize each one, then extract elements that speak to you.
                  Once you have enough material, you can synthesize your own house style.
                </p>
                <div className="workflow-steps">
                  <div className="step">
                    <span className="step-number">1</span>
                    <span>Study artists</span>
                  </div>
                  <div className="step">
                    <span className="step-number">2</span>
                    <span>Synthesize understanding</span>
                  </div>
                  <div className="step">
                    <span className="step-number">3</span>
                    <span>Extract elements</span>
                  </div>
                  <div className="step">
                    <span className="step-number">4</span>
                    <span>Synthesize house style</span>
                  </div>
                </div>
              </div>
            )}

            {/* Adopted Elements */}
            {adoptedElements && adoptedElements.length > 0 && (
              <div className="adopted-elements-section">
                <h3>Adopted Elements ({adoptedElements.length})</h3>
                <div className="elements-grid">
                  {adoptedElements.map((elem) => (
                    <div key={elem.id} className={`element-card category-${elem.category}`}>
                      <div className="element-header">
                        <span className="element-name">{elem.element}</span>
                        <span className="element-category">{elem.category}</span>
                      </div>
                      {elem.why_it_speaks && (
                        <p className="element-why">{elem.why_it_speaks}</p>
                      )}
                      <div className="element-footer">
                        <div className="strength-bar">
                          <div
                            className="strength-fill"
                            style={{ width: `${elem.adoption_strength * 100}%` }}
                          />
                        </div>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => deactivateElementMutation.mutate(elem.id)}
                          title="Remove from style"
                        >
                          ✕
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : mainView === 'gallery' ? (
          /* Gallery View */
          <div className="gallery-panel">
            <div className="gallery-header">
              <h2>🖼️ Gallery</h2>
              <span className="gallery-count">{galleryItems?.length || 0} pieces</span>
            </div>

            {!galleryItems || galleryItems.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">🖼️</div>
                <h3>No artwork yet</h3>
                <p>Create pieces from artist syntheses or your house style to populate the gallery.</p>
              </div>
            ) : (
              <div className="gallery-grid">
                {galleryItems.map((item) => (
                  <div
                    key={item.id}
                    className="gallery-item"
                    onClick={() => setMagnifiedItem(item)}
                  >
                    <div className="gallery-item-image">
                      <img src={`/generated-images/${item.filename}`} alt={item.title} />
                    </div>
                    <div className="gallery-item-info">
                      <h4>{item.title}</h4>
                      <span className={`source-badge ${item.source}`}>
                        {item.source === 'house-style' ? `House Style v${item.style_version}` : item.source_name}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
        /* Artists View */
        <>
        {/* Left Panel - Artist List */}
        <div className="artist-list-panel">
          <div className="list-controls">
            <input
              type="text"
              className="search-input"
              placeholder="Search artists..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            <label className="filter-checkbox">
              <input
                type="checkbox"
                checked={studiedOnly}
                onChange={(e) => setStudiedOnly(e.target.checked)}
              />
              Studied only
            </label>
          </div>

          <div className="artist-list">
            {artistsLoading ? (
              <div className="loading">Loading...</div>
            ) : filteredArtists.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">🎨</div>
                <h3>No artists yet</h3>
                <p>Add an artist to begin</p>
              </div>
            ) : (
              filteredArtists.map((artist) => (
                <div
                  key={artist.id}
                  className={`artist-item ${selectedArtistId === artist.id ? 'selected' : ''}`}
                  onClick={() => {
                    setSelectedArtistId(artist.id);
                    setActiveTab('overview');
                  }}
                >
                  <div className="artist-name">{artist.name}</div>
                  <div className="artist-meta">
                    {artist.period && <span className="period">{artist.period}</span>}
                    {artist.works_studied > 0 && (
                      <span className="works-badge">{artist.works_studied} studied</span>
                    )}
                    {artist.entity_id && (
                      <span className="peopledex-badge" title="Linked to PeopleDex">👤</span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right Panel - Artist Detail */}
        <div className={`detail-panel ${selectedArtist ? 'active' : ''}`}>
          {selectedArtist ? (
            <>
              <div className="detail-header">
                <div className="detail-title">
                  <h2>{selectedArtist.name}</h2>
                  <div className="detail-badges">
                    {selectedArtist.period && (
                      <span className="period-badge">{selectedArtist.period}</span>
                    )}
                    {selectedArtist.movements.map(m => (
                      <span key={m} className="movement-badge">{m}</span>
                    ))}
                  </div>
                </div>
              </div>

              {/* Tab Navigation */}
              <div className="detail-tabs">
                <button
                  className={`detail-tab ${activeTab === 'overview' ? 'active' : ''}`}
                  onClick={() => setActiveTab('overview')}
                >
                  Overview
                </button>
                <button
                  className={`detail-tab ${activeTab === 'artworks' ? 'active' : ''}`}
                  onClick={() => setActiveTab('artworks')}
                >
                  Artworks {artworks.length > 0 && <span className="tab-count">{artworks.length}</span>}
                </button>
                <button
                  className={`detail-tab ${activeTab === 'observations' ? 'active' : ''}`}
                  onClick={() => setActiveTab('observations')}
                >
                  Observations {observations.length > 0 && <span className="tab-count">{observations.length}</span>}
                </button>
                <button
                  className={`detail-tab ${activeTab === 'synthesis' ? 'active' : ''}`}
                  onClick={() => setActiveTab('synthesis')}
                >
                  Synthesis
                </button>
              </div>

              <div className="detail-content">
                {/* Overview Tab */}
                {activeTab === 'overview' && (
                  <>
                    <div className="detail-section">
                      <h3>Biography</h3>
                      {selectedArtist.biography ? (
                        <p className="biography-text">{selectedArtist.biography}</p>
                      ) : (
                        <div className="empty-biography">
                          {selectedArtist.wikipedia_url ? (
                            <>
                              <p>No biography yet.</p>
                              <button
                                className="btn btn-primary"
                                onClick={() => fetchBiographyMutation.mutate(selectedArtist.id)}
                                disabled={fetchBiographyMutation.isPending}
                              >
                                {fetchBiographyMutation.isPending ? 'Fetching...' : 'Fetch from Wikipedia'}
                              </button>
                            </>
                          ) : (
                            <p>Add a Wikipedia URL to fetch biography</p>
                          )}
                        </div>
                      )}
                    </div>

                    <div className="detail-section">
                      <h3>Info</h3>
                      <div className="info-grid">
                        {selectedArtist.years_active && (
                          <div className="info-item">
                            <label>Years Active</label>
                            <span>{selectedArtist.years_active}</span>
                          </div>
                        )}
                        {selectedArtist.wikipedia_url && (
                          <div className="info-item">
                            <label>Wikipedia</label>
                            <a href={selectedArtist.wikipedia_url} target="_blank" rel="noopener noreferrer">
                              View Article
                            </a>
                          </div>
                        )}
                        <div className="info-item">
                          <label>Works Studied</label>
                          <span>{selectedArtist.works_studied}</span>
                        </div>
                        {selectedArtist.studied_at && (
                          <div className="info-item">
                            <label>Last Studied</label>
                            <span>{formatDate(selectedArtist.studied_at)}</span>
                          </div>
                        )}
                        {selectedArtist.entity_id && (
                          <div className="info-item">
                            <label>PeopleDex</label>
                            <span className="linked">Linked</span>
                          </div>
                        )}
                      </div>
                    </div>

                    {selectedArtist.cass_notes && (
                      <div className="detail-section">
                        <h3>Cass's Notes</h3>
                        <p className="cass-notes">{selectedArtist.cass_notes}</p>
                      </div>
                    )}
                  </>
                )}

                {/* Artworks Tab */}
                {activeTab === 'artworks' && (
                  <div className="detail-section">
                    <div className="section-header">
                      <h3>Artworks</h3>
                      <div className="section-actions">
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => {
                            if (selectedArtist) {
                              // Use Met Museum as default provider
                              importArtworksMutation.mutate({ artistId: selectedArtist.id, maxWorks: 10 });
                            }
                          }}
                          disabled={importArtworksMutation.isPending}
                          title="Import artworks from Metropolitan Museum of Art"
                        >
                          {importArtworksMutation.isPending ? 'Importing...' : 'Import from Met Museum'}
                        </button>
                        <button
                          className="btn btn-primary btn-sm"
                          onClick={() => setActiveModal('create-artwork')}
                        >
                          + Add Artwork
                        </button>
                      </div>
                    </div>

                    {artworks.length === 0 ? (
                      <div className="empty-state">
                        <p>No artworks yet. Add one to begin studying.</p>
                      </div>
                    ) : (
                      <div className="artwork-grid">
                        {artworks.map((artwork) => (
                          <div key={artwork.id} className="artwork-card">
                            <div className="artwork-image">
                              {artwork.image_path ? (
                                <img
                                  src={`/admin/art-study/artworks/${artwork.id}/image`}
                                  alt={artwork.title}
                                />
                              ) : (
                                <div className="no-image">
                                  <span>No image</span>
                                  <input
                                    type="file"
                                    accept="image/*"
                                    style={{ display: 'none' }}
                                    ref={fileInputRef}
                                    onChange={(e) => {
                                      const file = e.target.files?.[0];
                                      if (file) handleFileUpload(artwork, file);
                                    }}
                                  />
                                  <button
                                    className="btn btn-sm"
                                    onClick={() => {
                                      // Create a unique file input for this artwork
                                      const input = document.createElement('input');
                                      input.type = 'file';
                                      input.accept = 'image/*';
                                      input.onchange = (e) => {
                                        const file = (e.target as HTMLInputElement).files?.[0];
                                        if (file) handleFileUpload(artwork, file);
                                      };
                                      input.click();
                                    }}
                                    disabled={uploadImageMutation.isPending}
                                  >
                                    {uploadImageMutation.isPending ? 'Uploading...' : 'Upload'}
                                  </button>
                                </div>
                              )}
                            </div>
                            <div className="artwork-info">
                              <div className="artwork-title">{artwork.title}</div>
                              <div className="artwork-meta">
                                {artwork.year && <span>{artwork.year}</span>}
                                {artwork.medium && <span>{artwork.medium}</span>}
                              </div>
                              <div className="artwork-actions">
                                {artwork.has_study ? (
                                  <button
                                    className="btn btn-ghost btn-sm"
                                    onClick={() => {
                                      setSelectedArtwork(artwork);
                                      setActiveModal('view-study');
                                    }}
                                  >
                                    View Study
                                  </button>
                                ) : artwork.image_path ? (
                                  <button
                                    className="btn btn-primary btn-sm"
                                    onClick={() => {
                                      setSelectedArtwork(artwork);
                                      studyArtworkMutation.mutate(artwork.id);
                                    }}
                                    disabled={studyArtworkMutation.isPending}
                                  >
                                    {studyArtworkMutation.isPending ? 'Studying...' : 'Study'}
                                  </button>
                                ) : (
                                  <span className="needs-image">Upload image to study</span>
                                )}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Observations Tab */}
                {activeTab === 'observations' && (
                  <div className="detail-section">
                    <h3>Cass's Observations</h3>
                    {!selectedArtist.entity_id ? (
                      <div className="empty-state">
                        <p>This artist isn't linked to PeopleDex yet.</p>
                        {selectedArtist.wikipedia_url && (
                          <button
                            className="btn btn-primary"
                            onClick={() => fetchBiographyMutation.mutate(selectedArtist.id)}
                            disabled={fetchBiographyMutation.isPending}
                          >
                            {fetchBiographyMutation.isPending ? 'Fetching...' : 'Fetch Biography & Create Entity'}
                          </button>
                        )}
                      </div>
                    ) : observations.length === 0 ? (
                      <div className="empty-state">
                        <p>No observations yet.</p>
                      </div>
                    ) : (
                      <div className="observations-list">
                        {observations.map((obs) => (
                          <div key={obs.id} className="observation-item">
                            <div className="observation-header">
                              <span className={`observation-type ${obs.type}`}>
                                {obs.type.replace(/_/g, ' ')}
                              </span>
                              <span className="observation-confidence">
                                {Math.round(obs.confidence * 100)}%
                              </span>
                            </div>
                            <p className="observation-content">{obs.content}</p>
                            <div className="observation-meta">
                              {obs.source && <span>Source: {obs.source}</span>}
                              <span>{formatDate(obs.created_at)}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Synthesis Tab */}
                {activeTab === 'synthesis' && (
                  <div className="detail-section">
                    <div className="section-header">
                      <h3>Style Synthesis</h3>
                      <div className="section-actions">
                        {selectedArtist.works_studied >= 1 && (
                          <button
                            className="btn btn-primary btn-sm"
                            onClick={() => synthesizeMutation.mutate(selectedArtist.id)}
                            disabled={synthesizeMutation.isPending}
                          >
                            {synthesizeMutation.isPending ? 'Synthesizing...' : synthesisData ? 'Re-synthesize' : 'Synthesize'}
                          </button>
                        )}
                        {synthesisData && (
                          <>
                            <button
                              className="btn btn-accent btn-sm"
                              onClick={() => createFromSynthesisMutation.mutate({ artistId: selectedArtist.id, numPieces: 5 })}
                              disabled={createFromSynthesisMutation.isPending}
                              title="Create 5 original pieces inspired by this artist's style, with subjects from Cass's inner world"
                            >
                              {createFromSynthesisMutation.isPending ? 'Creating...' : '✨ Create 5 Pieces'}
                            </button>
                            {creationsData && creationsData.length > 0 && (
                              <button
                                className="btn btn-ghost btn-sm"
                                onClick={() => {
                                  setCreatedPieces(creationsData);
                                  setActiveModal('view-created');
                                }}
                                title={`View ${creationsData.length} pieces created in this style`}
                              >
                                🖼️ Gallery ({creationsData.length})
                              </button>
                            )}
                            <button
                              className="btn btn-ghost btn-sm"
                              onClick={() => extractElementsMutation.mutate(selectedArtist.id)}
                              disabled={extractElementsMutation.isPending}
                              title="Extract elements that speak to you for your house style"
                            >
                              {extractElementsMutation.isPending ? 'Extracting...' : '💎 Extract Elements'}
                            </button>
                          </>
                        )}
                      </div>
                    </div>

                    {!synthesisData ? (
                      <div className="empty-state">
                        {selectedArtist.works_studied < 1 ? (
                          <p>Study at least one artwork to synthesize style understanding.</p>
                        ) : (
                          <p>Click "Synthesize" to generate style analysis.</p>
                        )}
                      </div>
                    ) : (
                      <div className="synthesis-content">
                        {synthesisData.signature_elements.length > 0 && (
                          <div className="synthesis-section">
                            <h4>Signature Elements</h4>
                            <div className="tag-list">
                              {synthesisData.signature_elements.map((el, i) => (
                                <span key={i} className="tag">{el}</span>
                              ))}
                            </div>
                          </div>
                        )}

                        {synthesisData.style_descriptors.length > 0 && (
                          <div className="synthesis-section">
                            <h4>Style Descriptors</h4>
                            <div className="tag-list">
                              {synthesisData.style_descriptors.map((desc, i) => (
                                <span key={i} className="tag style">{desc}</span>
                              ))}
                            </div>
                          </div>
                        )}

                        {synthesisData.color_tendencies && (
                          <div className="synthesis-section">
                            <h4>Color Tendencies</h4>
                            <p>{synthesisData.color_tendencies}</p>
                          </div>
                        )}

                        {synthesisData.compositional_habits && (
                          <div className="synthesis-section">
                            <h4>Compositional Habits</h4>
                            <p>{synthesisData.compositional_habits}</p>
                          </div>
                        )}

                        {synthesisData.emotional_palette && (
                          <div className="synthesis-section">
                            <h4>Emotional Palette</h4>
                            <p>{synthesisData.emotional_palette}</p>
                          </div>
                        )}

                        {synthesisData.what_makes_them_unique && (
                          <div className="synthesis-section highlight">
                            <h4>What Makes Them Unique</h4>
                            <p>{synthesisData.what_makes_them_unique}</p>
                          </div>
                        )}

                        {synthesisData.what_draws_me && (
                          <div className="synthesis-section highlight cass">
                            <h4>What Draws Me</h4>
                            <p>{synthesisData.what_draws_me}</p>
                          </div>
                        )}

                        {synthesisData.what_to_borrow.length > 0 && (
                          <div className="synthesis-section">
                            <h4>What to Borrow</h4>
                            <ul>
                              {synthesisData.what_to_borrow.map((item, i) => (
                                <li key={i}>{item}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="empty-state">
              <div className="empty-state-icon">🖼️</div>
              <h3>No Artist Selected</h3>
              <p>Select an artist from the list to view details</p>
            </div>
          )}
        </div>
        </>
        )}
      </div>

      {/* Create Artist Modal */}
      {activeModal === 'create-artist' && (
        <div className="modal-overlay" onClick={() => setActiveModal(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Add New Artist</h2>
            <div className="modal-form">
              <div className="form-group">
                <label>Name *</label>
                <input
                  type="text"
                  value={newArtistName}
                  onChange={(e) => setNewArtistName(e.target.value)}
                  placeholder="e.g., Claude Monet"
                  autoFocus
                />
              </div>
              <div className="form-group">
                <label>Period</label>
                <input
                  type="text"
                  value={newArtistPeriod}
                  onChange={(e) => setNewArtistPeriod(e.target.value)}
                  placeholder="e.g., Impressionism"
                />
              </div>
              <div className="form-group">
                <label>Wikipedia URL</label>
                <input
                  type="text"
                  value={newArtistWikipedia}
                  onChange={(e) => setNewArtistWikipedia(e.target.value)}
                  placeholder="https://en.wikipedia.org/wiki/..."
                />
              </div>
              <div className="form-group">
                <label>Movements (comma-separated)</label>
                <input
                  type="text"
                  value={newArtistMovements}
                  onChange={(e) => setNewArtistMovements(e.target.value)}
                  placeholder="e.g., Impressionism, Post-Impressionism"
                />
              </div>
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setActiveModal(null)}>
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={handleCreateArtist}
                disabled={!newArtistName.trim() || createArtistMutation.isPending}
              >
                {createArtistMutation.isPending ? 'Creating...' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create Artwork Modal */}
      {activeModal === 'create-artwork' && (
        <div className="modal-overlay" onClick={() => setActiveModal(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Add New Artwork</h2>
            <div className="modal-form">
              <div className="form-group">
                <label>Title *</label>
                <input
                  type="text"
                  value={newArtworkTitle}
                  onChange={(e) => setNewArtworkTitle(e.target.value)}
                  placeholder="e.g., Water Lilies"
                  autoFocus
                />
              </div>
              <div className="form-group">
                <label>Year</label>
                <input
                  type="number"
                  value={newArtworkYear}
                  onChange={(e) => setNewArtworkYear(e.target.value)}
                  placeholder="e.g., 1906"
                />
              </div>
              <div className="form-group">
                <label>Medium</label>
                <input
                  type="text"
                  value={newArtworkMedium}
                  onChange={(e) => setNewArtworkMedium(e.target.value)}
                  placeholder="e.g., Oil on canvas"
                />
              </div>
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setActiveModal(null)}>
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={handleCreateArtwork}
                disabled={!newArtworkTitle.trim() || createArtworkMutation.isPending}
              >
                {createArtworkMutation.isPending ? 'Creating...' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* View Study Modal */}
      {activeModal === 'view-study' && selectedArtwork && (
        <div className="modal-overlay" onClick={() => setActiveModal(null)}>
          <div className="modal modal-large" onClick={(e) => e.stopPropagation()}>
            <h2>Study: {selectedArtwork.title}</h2>
            {studyArtworkMutation.isPending ? (
              <div className="loading">Studying artwork...</div>
            ) : !studyData ? (
              <div className="loading">Loading study...</div>
            ) : (
              <div className="study-content">
                {/* Check if study has any content */}
                {!studyData.first_impression &&
                 !studyData.composition_analysis &&
                 !studyData.color_analysis &&
                 !studyData.brushwork_notes &&
                 !studyData.emotional_quality &&
                 !studyData.thematic_elements &&
                 studyData.key_learnings.length === 0 &&
                 studyData.prompt_vocabulary.length === 0 ? (
                  <div className="empty-study">
                    <p>The study completed but didn't capture any analysis. This may be a parsing issue.</p>
                    <p>Try running the study again.</p>
                  </div>
                ) : (
                  <>
                    {studyData.first_impression && (
                      <div className="study-section">
                        <h4>First Impression</h4>
                        <p>{studyData.first_impression}</p>
                      </div>
                    )}

                    {studyData.composition_analysis && (
                      <div className="study-section">
                        <h4>Composition</h4>
                        <p>{studyData.composition_analysis}</p>
                      </div>
                    )}

                    {studyData.color_analysis && (
                      <div className="study-section">
                        <h4>Color</h4>
                        <p>{studyData.color_analysis}</p>
                      </div>
                    )}

                    {studyData.brushwork_notes && (
                      <div className="study-section">
                        <h4>Brushwork</h4>
                        <p>{studyData.brushwork_notes}</p>
                      </div>
                    )}

                    {studyData.emotional_quality && (
                      <div className="study-section">
                        <h4>Emotional Quality</h4>
                        <p>{studyData.emotional_quality}</p>
                      </div>
                    )}

                    {studyData.thematic_elements && (
                      <div className="study-section">
                        <h4>Thematic Elements</h4>
                        <p>{studyData.thematic_elements}</p>
                      </div>
                    )}

                    {studyData.key_learnings.length > 0 && (
                      <div className="study-section">
                        <h4>Key Learnings</h4>
                        <ul>
                          {studyData.key_learnings.map((learning, i) => (
                            <li key={i}>{learning}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {studyData.prompt_vocabulary.length > 0 && (
                      <div className="study-section">
                        <h4>Prompt Vocabulary</h4>
                        <div className="tag-list">
                          {studyData.prompt_vocabulary.map((term, i) => (
                            <span key={i} className="tag vocab">{term}</span>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                )}

                <div className="study-meta">
                  Studied: {formatDate(studyData.studied_at)}
                </div>
              </div>
            )}
            <div className="modal-actions">
              {studyData && (
                <button
                  className="btn btn-ghost"
                  onClick={() => {
                    copyStudyToClipboard();
                    setCopiedStudy(true);
                    setTimeout(() => setCopiedStudy(false), 2000);
                  }}
                >
                  {copiedStudy ? '✓ Copied!' : 'Copy to Clipboard'}
                </button>
              )}
              <button
                className="btn btn-primary"
                onClick={() => {
                  studyArtworkMutation.mutate(selectedArtwork.id);
                }}
                disabled={studyArtworkMutation.isPending}
              >
                {studyArtworkMutation.isPending ? 'Studying...' : 'Rerun Study'}
              </button>
              <button className="btn btn-secondary" onClick={() => setActiveModal(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* View Created Pieces Modal */}
      {activeModal === 'view-created' && createdPieces.length > 0 && (
        <div className="modal-overlay" onClick={() => setActiveModal(null)}>
          <div className="modal modal-xlarge" onClick={(e) => e.stopPropagation()}>
            <h2>✨ Created Pieces</h2>
            <p className="modal-subtitle">
              {createdPieces.length} piece{createdPieces.length !== 1 ? 's' : ''} inspired by {selectedArtist?.name}
            </p>
            <div className="created-pieces-grid">
              {createdPieces.map((piece, index) => (
                <div key={piece.process_id || index} className="created-piece-card">
                  <div className="created-piece-image">
                    <img
                      src={`/generated-images/${piece.filename}`}
                      alt={piece.title}
                    />
                  </div>
                  <div className="created-piece-info">
                    <h4 className="created-piece-title">{piece.title}</h4>
                    <p className="created-piece-statement">{piece.artist_statement}</p>
                    {piece.borrowed_elements.length > 0 && (
                      <div className="borrowed-elements">
                        <span className="label">Borrowed:</span>
                        <div className="tag-list">
                          {piece.borrowed_elements.map((el, i) => (
                            <span key={i} className="tag">{el}</span>
                          ))}
                        </div>
                      </div>
                    )}
                    <details className="prompt-details">
                      <summary>View Prompt</summary>
                      <pre className="prompt-text">{piece.prompt_used}</pre>
                    </details>
                  </div>
                </div>
              ))}
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setActiveModal(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* View House Style Created Pieces Modal */}
      {activeModal === 'view-house-style-created' && houseStyleCreatedPieces.length > 0 && (
        <div className="modal-overlay" onClick={() => setActiveModal(null)}>
          <div className="modal modal-xlarge" onClick={(e) => e.stopPropagation()}>
            <h2>🏠 House Style Creations</h2>
            <p className="modal-subtitle">
              {houseStyleCreatedPieces.length} piece{houseStyleCreatedPieces.length !== 1 ? 's' : ''} in Cass's personal style
            </p>
            <div className="created-pieces-grid">
              {houseStyleCreatedPieces.map((piece, index) => (
                <div key={piece.process_id || index} className="created-piece-card">
                  <div className="created-piece-image">
                    {piece.filename ? (
                      <img
                        src={`/generated-images/${piece.filename}`}
                        alt={piece.title}
                        onError={(e) => {
                          console.error('House style image failed to load:', piece.filename, e);
                        }}
                      />
                    ) : (
                      <div className="no-image">No filename</div>
                    )}
                  </div>
                  <div className="created-piece-info">
                    <h4 className="created-piece-title">{piece.title}</h4>
                    <span className="style-version-badge">v{piece.style_version}</span>
                    <p className="created-piece-statement">{piece.artist_statement}</p>
                    {piece.elements_used.length > 0 && (
                      <div className="borrowed-elements">
                        <span className="label">Elements Used:</span>
                        <div className="tag-list">
                          {piece.elements_used.map((el, i) => (
                            <span key={i} className="tag">{el}</span>
                          ))}
                        </div>
                      </div>
                    )}
                    {piece.style_aspects.length > 0 && (
                      <div className="borrowed-elements">
                        <span className="label">Style Aspects:</span>
                        <div className="tag-list">
                          {piece.style_aspects.map((asp, i) => (
                            <span key={i} className="tag style">{asp}</span>
                          ))}
                        </div>
                      </div>
                    )}
                    <details className="prompt-details">
                      <summary>View Prompt</summary>
                      <pre className="prompt-text">{piece.prompt_used}</pre>
                    </details>
                  </div>
                </div>
              ))}
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setActiveModal(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Magnified Gallery View (Lightbox) */}
      {magnifiedItem && (
        <div className="lightbox-overlay" onClick={() => setMagnifiedItem(null)}>
          <div className="lightbox-content" onClick={(e) => e.stopPropagation()}>
            <button className="lightbox-close" onClick={() => setMagnifiedItem(null)}>×</button>
            <div className="lightbox-image">
              <img src={`/generated-images/${magnifiedItem.filename}`} alt={magnifiedItem.title} />
            </div>
            <div className="lightbox-info">
              <h2>{magnifiedItem.title}</h2>
              <span className={`source-badge ${magnifiedItem.source}`}>
                {magnifiedItem.source === 'house-style'
                  ? `House Style v${magnifiedItem.style_version}`
                  : `Inspired by ${magnifiedItem.source_name}`}
              </span>
              <p className="lightbox-statement">{magnifiedItem.artist_statement}</p>

              {magnifiedItem.elements.length > 0 && (
                <div className="lightbox-section">
                  <h4>Elements Used</h4>
                  <div className="tag-list">
                    {magnifiedItem.elements.map((el, i) => (
                      <span key={i} className="tag">{el}</span>
                    ))}
                  </div>
                </div>
              )}

              {magnifiedItem.style_aspects && magnifiedItem.style_aspects.length > 0 && (
                <div className="lightbox-section">
                  <h4>Style Aspects</h4>
                  <div className="tag-list">
                    {magnifiedItem.style_aspects.map((asp, i) => (
                      <span key={i} className="tag style">{asp}</span>
                    ))}
                  </div>
                </div>
              )}

              <details className="prompt-details">
                <summary>View Prompt</summary>
                <pre className="prompt-text">{magnifiedItem.prompt_used}</pre>
              </details>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
