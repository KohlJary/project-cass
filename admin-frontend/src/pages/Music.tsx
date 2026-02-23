import { useState, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { musicApi } from '../api/client';
import type { MusicComposition } from '../api/client';
import './Music.css';

const PURPOSES = ['all', 'whistle', 'song', 'ambient', 'general'] as const;

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatPurpose(purpose: string): string {
  return purpose.charAt(0).toUpperCase() + purpose.slice(1);
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return '--:--';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function AudioPlayer({ composition }: { composition: MusicComposition }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [duration, setDuration] = useState(0);

  const audioUrl = musicApi.getAudioUrl(composition);

  const togglePlay = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
    setIsPlaying(!isPlaying);
  };

  const handleTimeUpdate = () => {
    if (!audioRef.current) return;
    setProgress(audioRef.current.currentTime);
  };

  const handleLoadedMetadata = () => {
    if (!audioRef.current) return;
    setDuration(audioRef.current.duration);
  };

  const handleEnded = () => {
    setIsPlaying(false);
    setProgress(0);
  };

  const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!audioRef.current || !duration) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const percent = x / rect.width;
    audioRef.current.currentTime = percent * duration;
  };

  if (!audioUrl) {
    return <div className="audio-unavailable">Audio not available</div>;
  }

  return (
    <div className="audio-player">
      <audio
        ref={audioRef}
        src={audioUrl}
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoadedMetadata}
        onEnded={handleEnded}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
      />
      <button className="play-btn" onClick={togglePlay}>
        {isPlaying ? '⏸' : '▶'}
      </button>
      <div className="progress-container" onClick={handleSeek}>
        <div
          className="progress-bar"
          style={{ width: duration ? `${(progress / duration) * 100}%` : '0%' }}
        />
      </div>
      <span className="time-display">
        {formatDuration(progress)} / {formatDuration(duration || composition.metadata?.duration || null)}
      </span>
    </div>
  );
}

export function Music() {
  const [selectedPurpose, setSelectedPurpose] = useState<string>('all');
  const [selectedGenre, setSelectedGenre] = useState<string>('all');
  const [selectedComposition, setSelectedComposition] = useState<MusicComposition | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ['music', selectedPurpose, selectedGenre],
    queryFn: () => musicApi.list({
      purpose: selectedPurpose === 'all' ? undefined : selectedPurpose,
      genre: selectedGenre === 'all' ? undefined : selectedGenre,
      limit: 100,
    }).then(r => r.data),
  });

  const { data: serviceStatus } = useQuery({
    queryKey: ['music-service'],
    queryFn: () => musicApi.checkService().then(r => r.data),
    refetchInterval: 30000,
  });

  const genres = data?.genres || [];

  return (
    <div className="music-page">
      <header className="page-header">
        <div className="header-content">
          <h1>Music</h1>
          <p className="subtitle">Compositions by Cass</p>
        </div>
        <div className="header-status">
          {data && (
            <div className="composition-count">
              {data.count} composition{data.count !== 1 ? 's' : ''}
            </div>
          )}
          <div className={`service-status ${serviceStatus?.available ? 'available' : 'unavailable'}`}>
            {serviceStatus?.available ? '● ACE-Step Online' : '○ ACE-Step Offline'}
          </div>
        </div>
      </header>

      {/* Filters */}
      <div className="music-filters">
        <div className="filter-group">
          <label>Purpose</label>
          <div className="filter-buttons">
            {PURPOSES.map(purpose => (
              <button
                key={purpose}
                className={`filter-btn ${selectedPurpose === purpose ? 'active' : ''}`}
                onClick={() => setSelectedPurpose(purpose)}
              >
                {purpose === 'all' ? 'All' : formatPurpose(purpose)}
              </button>
            ))}
          </div>
        </div>

        {genres.length > 0 && (
          <div className="filter-group">
            <label>Genre</label>
            <div className="filter-buttons">
              <button
                className={`filter-btn ${selectedGenre === 'all' ? 'active' : ''}`}
                onClick={() => setSelectedGenre('all')}
              >
                All
              </button>
              {genres.map(genre => (
                <button
                  key={genre}
                  className={`filter-btn ${selectedGenre === genre ? 'active' : ''}`}
                  onClick={() => setSelectedGenre(genre)}
                >
                  {genre}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Loading / Error states */}
      {isLoading && (
        <div className="music-loading">Loading compositions...</div>
      )}

      {error && (
        <div className="music-error">Failed to load compositions</div>
      )}

      {/* Compositions List */}
      {data && data.compositions.length > 0 && (
        <div className="compositions-list">
          {data.compositions.map(composition => (
            <div
              key={composition.id}
              className={`composition-card ${composition.status} ${selectedComposition?.id === composition.id ? 'selected' : ''}`}
              onClick={() => setSelectedComposition(composition)}
            >
              <div className="composition-header">
                <span className={`purpose-badge ${composition.purpose}`}>
                  {formatPurpose(composition.purpose)}
                </span>
                <span className={`status-badge ${composition.status}`}>
                  {composition.status}
                </span>
                <span className="composition-date">
                  {formatDate(composition.created_at)}
                </span>
              </div>

              <div className="composition-prompt">
                {composition.prompt}
              </div>

              {composition.metadata && (
                <div className="composition-meta">
                  {composition.metadata.bpm && <span>{composition.metadata.bpm} BPM</span>}
                  {composition.metadata.keyscale && <span>{composition.metadata.keyscale}</span>}
                  {composition.metadata.duration && <span>{formatDuration(composition.metadata.duration)}</span>}
                  {composition.metadata.genres && <span className="genres">{composition.metadata.genres}</span>}
                </div>
              )}

              {composition.status === 'completed' && (
                <AudioPlayer composition={composition} />
              )}

              {composition.status === 'failed' && composition.error && (
                <div className="composition-error">
                  {composition.error}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {data && data.compositions.length === 0 && (
        <div className="music-empty">
          <p>No compositions found</p>
          {(selectedPurpose !== 'all' || selectedGenre !== 'all') && (
            <p className="empty-hint">Try adjusting your filters</p>
          )}
        </div>
      )}

      {/* Detail Modal */}
      {selectedComposition && (
        <div className="detail-modal" onClick={() => setSelectedComposition(null)}>
          <div className="detail-content" onClick={e => e.stopPropagation()}>
            <button className="detail-close" onClick={() => setSelectedComposition(null)}>
              x
            </button>

            <div className="detail-header">
              <span className={`purpose-badge ${selectedComposition.purpose}`}>
                {formatPurpose(selectedComposition.purpose)}
              </span>
              <span className={`status-badge ${selectedComposition.status}`}>
                {selectedComposition.status}
              </span>
              <span className="detail-date">
                {formatDate(selectedComposition.created_at)}
              </span>
            </div>

            <div className="detail-section">
              <label>Prompt</label>
              <p>{selectedComposition.prompt}</p>
            </div>

            {selectedComposition.lyrics && (
              <div className="detail-section">
                <label>Lyrics</label>
                <pre className="lyrics-display">{selectedComposition.lyrics}</pre>
              </div>
            )}

            {selectedComposition.metadata && (
              <div className="detail-section metadata-grid">
                <label>Metadata</label>
                <div className="metadata-items">
                  {selectedComposition.metadata.bpm && (
                    <div className="metadata-item">
                      <span className="meta-label">BPM</span>
                      <span className="meta-value">{selectedComposition.metadata.bpm}</span>
                    </div>
                  )}
                  {selectedComposition.metadata.keyscale && (
                    <div className="metadata-item">
                      <span className="meta-label">Key</span>
                      <span className="meta-value">{selectedComposition.metadata.keyscale}</span>
                    </div>
                  )}
                  {selectedComposition.metadata.timesignature && (
                    <div className="metadata-item">
                      <span className="meta-label">Time</span>
                      <span className="meta-value">{selectedComposition.metadata.timesignature}</span>
                    </div>
                  )}
                  {selectedComposition.metadata.duration && (
                    <div className="metadata-item">
                      <span className="meta-label">Duration</span>
                      <span className="meta-value">{formatDuration(selectedComposition.metadata.duration)}</span>
                    </div>
                  )}
                  {selectedComposition.metadata.genres && (
                    <div className="metadata-item full-width">
                      <span className="meta-label">Genres</span>
                      <span className="meta-value">{selectedComposition.metadata.genres}</span>
                    </div>
                  )}
                  {selectedComposition.metadata.language && (
                    <div className="metadata-item">
                      <span className="meta-label">Language</span>
                      <span className="meta-value">{selectedComposition.metadata.language}</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {selectedComposition.status === 'completed' && (
              <div className="detail-section">
                <label>Audio</label>
                <AudioPlayer composition={selectedComposition} />
              </div>
            )}

            {selectedComposition.error && (
              <div className="detail-section">
                <label>Error</label>
                <p className="error-text">{selectedComposition.error}</p>
              </div>
            )}

            <div className="detail-section">
              <label>ID</label>
              <code className="composition-id">{selectedComposition.id}</code>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
