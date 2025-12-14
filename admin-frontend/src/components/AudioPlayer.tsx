import { useState, useRef, useCallback } from 'react';
import './AudioPlayer.css';

interface AudioPlayerProps {
  audio: string;  // base64 encoded audio
  format?: string;  // e.g., 'mp3'
}

export function AudioPlayer({ audio, format = 'mp3' }: AudioPlayerProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const handlePlay = useCallback(() => {
    if (!audioRef.current) {
      // Create audio element on first play
      setIsLoading(true);
      const audioElement = new Audio(`data:audio/${format};base64,${audio}`);
      audioRef.current = audioElement;

      audioElement.onloadeddata = () => {
        setIsLoading(false);
        audioElement.play();
        setIsPlaying(true);
      };

      audioElement.onended = () => {
        setIsPlaying(false);
      };

      audioElement.onerror = () => {
        setIsLoading(false);
        setIsPlaying(false);
        console.error('Audio playback failed');
      };
    } else if (isPlaying) {
      // Pause
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      // Resume or replay
      audioRef.current.currentTime = 0;
      audioRef.current.play();
      setIsPlaying(true);
    }
  }, [audio, format, isPlaying]);

  return (
    <button
      className={`audio-player-btn ${isPlaying ? 'playing' : ''} ${isLoading ? 'loading' : ''}`}
      onClick={handlePlay}
      title={isPlaying ? 'Pause' : 'Play audio'}
      disabled={isLoading}
    >
      {isLoading ? (
        <span className="audio-icon">...</span>
      ) : isPlaying ? (
        <span className="audio-icon">||</span>
      ) : (
        <span className="audio-icon">{'\u25B6'}</span>
      )}
    </button>
  );
}
