import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useWebSocket } from '../hooks/useWebSocket';
import { voiceApi } from '../api/domains/voice';
import type { TTSSettings, SpeakerInfo } from '../api/domains/voice';
import { parseGestureTags } from '../utils/gestures';
import './VoiceCall.css';

type CallState = 'idle' | 'recording' | 'transcribing' | 'thinking' | 'speaking';
type TTSProvider = 'piper' | 'xtts';

export function VoiceCall() {
  const navigate = useNavigate();
  const [callState, setCallState] = useState<CallState>('idle');
  const [transcript, setTranscript] = useState<string | null>(null);
  const [response, setResponse] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [audioLevel, setAudioLevel] = useState(0);
  const [sttStatus, setSTTStatus] = useState<{ available: boolean; model: string | null } | null>(null);
  const [ttsSettings, setTTSSettings] = useState<TTSSettings | null>(null);
  const [ttsProvider, setTTSProvider] = useState<TTSProvider>('piper');
  const [identifiedSpeaker, setIdentifiedSpeaker] = useState<SpeakerInfo | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const recordingStartTimeRef = useRef<number>(0);
  const MIN_RECORDING_MS = 500; // Minimum recording duration

  const {
    isConnected,
    isThinking,
    messages,
    sendMessage,
    currentConversationId,
  } = useWebSocket();

  // Check STT and TTS status on mount
  useEffect(() => {
    voiceApi.getSTTStatus()
      .then((res) => setSTTStatus(res.data))
      .catch(() => setSTTStatus({ available: false, model: null }));

    voiceApi.getTTSSettings()
      .then((res) => {
        setTTSSettings(res.data);
        setTTSProvider(res.data.current_provider);
      })
      .catch((err) => console.error('Failed to load TTS settings:', err));
  }, []);

  // Handle TTS provider change
  const handleTTSProviderChange = useCallback(async (provider: TTSProvider) => {
    try {
      await voiceApi.setTTSProvider(provider);
      setTTSProvider(provider);
    } catch (err) {
      console.error('Failed to set TTS provider:', err);
      setError('Failed to change TTS provider');
    }
  }, []);

  // Watch for new assistant messages with audio
  useEffect(() => {
    if (messages.length === 0) return;

    const lastMessage = messages[messages.length - 1];
    if (lastMessage.role === 'assistant' && !lastMessage.isThinking) {
      // Parse out thinking blocks and gesture/emote tags
      const parsed = parseGestureTags(lastMessage.content);
      setResponse(parsed.text);

      // Auto-play audio if available
      if (lastMessage.audio && audioPlayerRef.current) {
        const audioData = `data:audio/${lastMessage.audioFormat || 'mp3'};base64,${lastMessage.audio}`;
        audioPlayerRef.current.src = audioData;
        audioPlayerRef.current.play()
          .then(() => setCallState('speaking'))
          .catch((e) => console.error('Audio playback failed:', e));
      } else {
        setCallState('idle');
      }
    }
  }, [messages]);

  // Update call state based on WebSocket thinking state
  useEffect(() => {
    if (isThinking && callState !== 'thinking') {
      setCallState('thinking');
    }
  }, [isThinking, callState]);

  // Audio level visualization
  const updateAudioLevel = useCallback(() => {
    if (!analyserRef.current) return;

    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
    analyserRef.current.getByteFrequencyData(dataArray);

    // Calculate average level
    const average = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
    setAudioLevel(average / 255);

    if (callState === 'recording') {
      animationFrameRef.current = requestAnimationFrame(updateAudioLevel);
    }
  }, [callState]);

  const startRecording = async () => {
    try {
      setError(null);
      setTranscript(null);
      setResponse(null);
      setIdentifiedSpeaker(null);

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      // Set up audio analysis for visualization
      audioContextRef.current = new AudioContext();
      const source = audioContextRef.current.createMediaStreamSource(stream);
      analyserRef.current = audioContextRef.current.createAnalyser();
      analyserRef.current.fftSize = 256;
      source.connect(analyserRef.current);

      // Set up recording
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4',
      });
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        // Stop all tracks
        stream.getTracks().forEach((track) => track.stop());

        // Clean up audio context
        if (audioContextRef.current) {
          audioContextRef.current.close();
          audioContextRef.current = null;
        }

        // Process recording
        await processRecording();
      };

      mediaRecorder.start(100); // Collect data every 100ms
      recordingStartTimeRef.current = Date.now();
      setCallState('recording');

      // Start audio level animation
      updateAudioLevel();
    } catch (err) {
      console.error('Failed to start recording:', err);
      setError('Could not access microphone. Please check permissions.');
      setCallState('idle');
    }
  };

  const stopRecording = () => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
    }
    setAudioLevel(0);

    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      const recordingDuration = Date.now() - recordingStartTimeRef.current;

      if (recordingDuration < MIN_RECORDING_MS) {
        // Too short - cancel and show message
        mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop());
        mediaRecorderRef.current = null;
        audioChunksRef.current = [];
        setError(`Hold the button longer (at least ${MIN_RECORDING_MS}ms)`);
        setCallState('idle');
        return;
      }

      mediaRecorderRef.current.stop();
      setCallState('transcribing');
    }
  };

  const processRecording = async () => {
    if (audioChunksRef.current.length === 0) {
      setError('No audio recorded');
      setCallState('idle');
      return;
    }

    const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
    console.log(`[VoiceCall] Audio blob: ${audioBlob.size} bytes from ${audioChunksRef.current.length} chunks`);

    // Convert to base64
    const reader = new FileReader();
    reader.onload = async () => {
      const base64 = (reader.result as string).split(',')[1];

      try {
        // Transcribe with speaker identification
        const response = await voiceApi.transcribe(base64, 'webm', undefined, true);
        const text = response.data.text;

        // Update identified speaker
        if (response.data.speaker) {
          setIdentifiedSpeaker(response.data.speaker);
        }

        if (!text.trim()) {
          setError('No speech detected. Try speaking louder or closer to the microphone.');
          setCallState('idle');
          return;
        }

        setTranscript(text);
        setCallState('thinking');

        // Send to chat with speaker recognition context
        sendMessage(
          text,
          currentConversationId || undefined,
          undefined,  // no image
          undefined,  // no attachments
          response.data.speaker || null
        );
      } catch (err: unknown) {
        console.error('Transcription failed:', err);
        // Extract error message from API response
        let errorMsg = 'Transcription failed.';
        if (err && typeof err === 'object' && 'response' in err) {
          const response = (err as { response?: { data?: { detail?: string } } }).response;
          if (response?.data?.detail) {
            errorMsg = response.data.detail;
          }
        }
        setError(errorMsg);
        setCallState('idle');
      }
    };

    reader.onerror = () => {
      setError('Failed to process audio');
      setCallState('idle');
    };

    reader.readAsDataURL(audioBlob);
  };

  const handleAudioEnded = () => {
    setCallState('idle');
  };

  const getStateLabel = () => {
    switch (callState) {
      case 'recording':
        return 'Listening...';
      case 'transcribing':
        return 'Transcribing...';
      case 'thinking':
        return 'Cass is thinking...';
      case 'speaking':
        return 'Cass is speaking...';
      default:
        return 'Press and hold to talk';
    }
  };

  const getStateClass = () => {
    return `voice-call-state voice-call-state-${callState}`;
  };

  return (
    <div className="voice-call-page">
      <header className="voice-call-header">
        <h1>Voice Call</h1>
        <div className="voice-call-status">
          <span className={`connection-indicator ${isConnected ? 'connected' : 'disconnected'}`}>
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
          {sttStatus && (
            <span className={`stt-indicator ${sttStatus.available ? 'available' : 'unavailable'}`}>
              STT: {sttStatus.available ? sttStatus.model : 'Unavailable'}
            </span>
          )}
          {identifiedSpeaker && identifiedSpeaker.user_id && (
            <span className={`speaker-indicator speaker-${identifiedSpeaker.confidence_level}`}>
              👤 {identifiedSpeaker.display_name || 'Unknown'} ({identifiedSpeaker.confidence_level})
            </span>
          )}
          {ttsSettings && (
            <div className="tts-provider-toggle">
              <span className="tts-label">TTS:</span>
              <div className="toggle-buttons">
                <button
                  className={`toggle-btn ${ttsProvider === 'piper' ? 'active' : ''}`}
                  onClick={() => handleTTSProviderChange('piper')}
                  title="Piper - Fast CPU-based TTS (~50ms)"
                >
                  Piper
                </button>
                <button
                  className={`toggle-btn ${ttsProvider === 'xtts' ? 'active' : ''}`}
                  onClick={() => handleTTSProviderChange('xtts')}
                  disabled={!ttsSettings.available_providers.includes('xtts')}
                  title={ttsSettings.available_providers.includes('xtts')
                    ? "XTTS - Higher quality GPU-based TTS (~1-2s)"
                    : "XTTS not available"}
                >
                  XTTS
                </button>
              </div>
            </div>
          )}
        </div>
      </header>

      <main className="voice-call-main">
        {/* Visualization area */}
        <div className={getStateClass()}>
          <div
            className="audio-visualizer"
            style={{
              transform: `scale(${1 + audioLevel * 0.5})`,
              opacity: callState === 'recording' ? 0.8 + audioLevel * 0.2 : 0.6,
            }}
          >
            <div className="visualizer-ring ring-1" />
            <div className="visualizer-ring ring-2" />
            <div className="visualizer-ring ring-3" />
            <div className="visualizer-core" />
          </div>
          <div className="state-label">{getStateLabel()}</div>
        </div>

        {/* Transcript display */}
        {transcript && (
          <div className="transcript-display">
            <div className="transcript-label">You said:</div>
            <div className="transcript-text">{transcript}</div>
          </div>
        )}

        {/* Response display */}
        {response && (
          <div className="response-display">
            <div className="response-label">Cass:</div>
            <div className="response-text">{response}</div>
          </div>
        )}

        {/* Error display */}
        {error && (
          <div className="error-display">
            {error}
          </div>
        )}

        {/* Push to talk button */}
        <div className="voice-call-controls">
          <button
            className={`push-to-talk-btn ${callState === 'recording' ? 'recording' : ''}`}
            onMouseDown={startRecording}
            onMouseUp={stopRecording}
            onMouseLeave={callState === 'recording' ? stopRecording : undefined}
            onTouchStart={startRecording}
            onTouchEnd={stopRecording}
            disabled={!isConnected || !sttStatus?.available || callState === 'transcribing' || callState === 'thinking' || callState === 'speaking'}
          >
            <svg className="mic-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
              <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
            </svg>
          </button>
          <div className="button-hint">
            {callState === 'idle' ? 'Hold to speak' : ''}
          </div>
        </div>

        {/* Hidden audio player for TTS playback */}
        <audio
          ref={audioPlayerRef}
          onEnded={handleAudioEnded}
          style={{ display: 'none' }}
        />
      </main>

      {/* Instructions */}
      <footer className="voice-call-footer">
        <div className="instructions">
          <p>Press and hold the microphone button to speak. Release to send.</p>
          <p>Cass will respond with voice when TTS is enabled.</p>
        </div>
        <div className="enroll-buttons">
          <button
            className="enroll-voice-btn"
            onClick={() => navigate('/voice-enrollment')}
          >
            Enroll Voice
          </button>
          <button
            className="enroll-face-btn"
            onClick={() => navigate('/face-enrollment')}
          >
            Enroll Face
          </button>
        </div>
      </footer>
    </div>
  );
}
