import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { voiceApi } from '../api/domains/voice';
import type { EnrollmentSession, EnrollmentStatus } from '../api/domains/voice';
import './VoiceEnrollment.css';

type EnrollmentState = 'loading' | 'not_enrolled' | 'enrolling' | 'recording' | 'processing' | 'enrolled';

interface SampleStatus {
  recorded: boolean;
  quality?: number;
  feedback?: string;
}

export function VoiceEnrollment() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const userId = user?.user_id;

  const [state, setState] = useState<EnrollmentState>('loading');
  const [enrollmentStatus, setEnrollmentStatus] = useState<EnrollmentStatus | null>(null);
  const [session, setSession] = useState<EnrollmentSession | null>(null);
  const [currentPhraseIndex, setCurrentPhraseIndex] = useState(0);
  const [sampleStatuses, setSampleStatuses] = useState<SampleStatus[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [audioLevel, setAudioLevel] = useState(0);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  // Check enrollment status on mount
  useEffect(() => {
    if (!userId) return;

    voiceApi.getEnrollmentStatus(userId)
      .then((res) => {
        setEnrollmentStatus(res.data);
        setState(res.data.enrolled ? 'enrolled' : 'not_enrolled');
      })
      .catch((err) => {
        console.error('Failed to check enrollment status:', err);
        setState('not_enrolled');
      });
  }, [userId]);

  // Audio level visualization
  const updateAudioLevel = useCallback(() => {
    if (!analyserRef.current) return;

    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
    analyserRef.current.getByteFrequencyData(dataArray);

    const average = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
    setAudioLevel(average / 255);

    if (state === 'recording') {
      animationFrameRef.current = requestAnimationFrame(updateAudioLevel);
    }
  }, [state]);

  // Start enrollment session
  const startEnrollment = async () => {
    if (!userId) return;

    try {
      setError(null);
      const res = await voiceApi.startEnrollment(userId);
      setSession(res.data);
      setSampleStatuses(res.data.phrases.map(() => ({ recorded: false })));
      setCurrentPhraseIndex(0);
      setState('enrolling');
    } catch (err) {
      console.error('Failed to start enrollment:', err);
      setError('Failed to start enrollment session');
    }
  };

  // Start recording for current phrase
  const startRecording = async () => {
    try {
      setError(null);

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

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
        // Clean up stream
        stream.getTracks().forEach((track) => track.stop());

        // Clean up audio context
        if (audioContextRef.current) {
          audioContextRef.current.close();
          audioContextRef.current = null;
        }

        // Process recording
        await processRecording();
      };

      mediaRecorder.start(100);
      setState('recording');
      updateAudioLevel();
    } catch (err) {
      console.error('Failed to start recording:', err);
      setError('Could not access microphone. Please check permissions.');
    }
  };

  // Stop recording
  const stopRecording = () => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
    }
    setAudioLevel(0);

    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
      setState('processing');
    }
  };

  // Process recorded audio
  const processRecording = async () => {
    if (!session || audioChunksRef.current.length === 0) {
      setError('No audio recorded');
      setState('enrolling');
      return;
    }

    const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });

    // Convert to base64
    const reader = new FileReader();
    reader.onload = async () => {
      const base64 = (reader.result as string).split(',')[1];

      try {
        const res = await voiceApi.addEnrollmentSample(
          session.session_id,
          currentPhraseIndex,
          base64
        );

        // Update sample status
        const newStatuses = [...sampleStatuses];
        newStatuses[currentPhraseIndex] = {
          recorded: res.data.accepted,
          quality: res.data.quality_score,
          feedback: res.data.feedback,
        };
        setSampleStatuses(newStatuses);

        if (!res.data.accepted) {
          setError(res.data.feedback);
        }

        setState('enrolling');
      } catch (err) {
        console.error('Failed to submit sample:', err);
        setError('Failed to process audio sample');
        setState('enrolling');
      }
    };

    reader.onerror = () => {
      setError('Failed to process audio');
      setState('enrolling');
    };

    reader.readAsDataURL(audioBlob);
  };

  // Move to next phrase
  const nextPhrase = () => {
    if (session && currentPhraseIndex < session.phrases.length - 1) {
      setCurrentPhraseIndex(currentPhraseIndex + 1);
      setError(null);
    }
  };

  // Move to previous phrase
  const prevPhrase = () => {
    if (currentPhraseIndex > 0) {
      setCurrentPhraseIndex(currentPhraseIndex - 1);
      setError(null);
    }
  };

  // Complete enrollment
  const completeEnrollment = async () => {
    if (!session) return;

    try {
      setState('processing');
      setError(null);

      const res = await voiceApi.completeEnrollment(session.session_id);

      if (res.data.success) {
        setEnrollmentStatus({
          enrolled: true,
          sample_count: res.data.sample_count,
          quality_score: res.data.quality_score,
        });
        setState('enrolled');
      } else {
        setError('Failed to complete enrollment');
        setState('enrolling');
      }
    } catch (err: unknown) {
      console.error('Failed to complete enrollment:', err);
      let errorMsg = 'Failed to complete enrollment';
      if (err && typeof err === 'object' && 'response' in err) {
        const response = (err as { response?: { data?: { detail?: string } } }).response;
        if (response?.data?.detail) {
          errorMsg = response.data.detail;
        }
      }
      setError(errorMsg);
      setState('enrolling');
    }
  };

  // Delete enrollment
  const deleteEnrollment = async () => {
    if (!userId) return;

    if (!confirm('Are you sure you want to delete your voice enrollment?')) {
      return;
    }

    try {
      await voiceApi.deleteEnrollment(userId);
      setEnrollmentStatus({ enrolled: false });
      setSession(null);
      setSampleStatuses([]);
      setState('not_enrolled');
    } catch (err) {
      console.error('Failed to delete enrollment:', err);
      setError('Failed to delete enrollment');
    }
  };

  // Check if all samples are recorded
  const allSamplesRecorded = sampleStatuses.every((s) => s.recorded);

  // Get quality color
  const getQualityColor = (quality?: number) => {
    if (!quality) return '#666';
    if (quality >= 0.8) return '#4ade80';
    if (quality >= 0.6) return '#fbbf24';
    return '#f87171';
  };

  // Loading state
  if (state === 'loading') {
    return (
      <div className="voice-enrollment-page">
        <div className="loading-state">Loading...</div>
      </div>
    );
  }

  return (
    <div className="voice-enrollment-page">
      <header className="enrollment-header">
        <h1>Voice Enrollment</h1>
        <p className="subtitle">
          Enroll your voice so Cass can recognize you automatically
        </p>
      </header>

      <main className="enrollment-main">
        {/* Already enrolled state */}
        {state === 'enrolled' && enrollmentStatus && (
          <div className="enrolled-state">
            <div className="success-icon">✓</div>
            <h2>Voice Enrolled</h2>
            <p>Cass can now recognize your voice.</p>
            <div className="enrollment-info">
              <div className="info-item">
                <span className="label">Samples:</span>
                <span className="value">{enrollmentStatus.sample_count}</span>
              </div>
              <div className="info-item">
                <span className="label">Quality:</span>
                <span
                  className="value"
                  style={{ color: getQualityColor(enrollmentStatus.quality_score) }}
                >
                  {((enrollmentStatus.quality_score || 0) * 100).toFixed(0)}%
                </span>
              </div>
              {enrollmentStatus.created_at && (
                <div className="info-item">
                  <span className="label">Enrolled:</span>
                  <span className="value">
                    {new Date(enrollmentStatus.created_at).toLocaleDateString()}
                  </span>
                </div>
              )}
            </div>
            <div className="enrolled-actions">
              <button className="btn-secondary" onClick={startEnrollment}>
                Re-enroll
              </button>
              <button className="btn-danger" onClick={deleteEnrollment}>
                Delete Enrollment
              </button>
            </div>
          </div>
        )}

        {/* Not enrolled state */}
        {state === 'not_enrolled' && (
          <div className="not-enrolled-state">
            <div className="mic-icon-large">🎤</div>
            <h2>Voice Not Enrolled</h2>
            <p>
              Record 5 short phrases to create your voiceprint.
              This allows Cass to identify you by your voice.
            </p>
            <button className="btn-primary" onClick={startEnrollment}>
              Start Enrollment
            </button>
          </div>
        )}

        {/* Enrolling state */}
        {(state === 'enrolling' || state === 'recording' || state === 'processing') && session && (
          <div className="enrolling-state">
            {/* Progress indicator */}
            <div className="progress-bar">
              {session.phrases.map((_, idx) => (
                <div
                  key={idx}
                  className={`progress-dot ${
                    sampleStatuses[idx]?.recorded ? 'recorded' : ''
                  } ${idx === currentPhraseIndex ? 'current' : ''}`}
                  onClick={() => setCurrentPhraseIndex(idx)}
                  style={{
                    backgroundColor: sampleStatuses[idx]?.recorded
                      ? getQualityColor(sampleStatuses[idx]?.quality)
                      : undefined,
                  }}
                >
                  {idx + 1}
                </div>
              ))}
            </div>

            {/* Current phrase */}
            <div className="phrase-card">
              <div className="phrase-number">
                Phrase {currentPhraseIndex + 1} of {session.phrases.length}
              </div>
              <div className="phrase-text">
                "{session.phrases[currentPhraseIndex]}"
              </div>

              {/* Sample status */}
              {sampleStatuses[currentPhraseIndex]?.recorded && (
                <div
                  className="sample-status"
                  style={{ color: getQualityColor(sampleStatuses[currentPhraseIndex]?.quality) }}
                >
                  ✓ {sampleStatuses[currentPhraseIndex]?.feedback}
                </div>
              )}
            </div>

            {/* Recording visualization */}
            <div className={`recording-viz ${state === 'recording' ? 'active' : ''}`}>
              <div
                className="viz-circle"
                style={{
                  transform: `scale(${1 + audioLevel * 0.5})`,
                  opacity: state === 'recording' ? 0.8 + audioLevel * 0.2 : 0.4,
                }}
              >
                <div className="viz-inner" />
              </div>
            </div>

            {/* Recording button */}
            <div className="recording-controls">
              {state === 'processing' ? (
                <div className="processing-indicator">Processing...</div>
              ) : state === 'recording' ? (
                <button className="record-btn recording" onClick={stopRecording}>
                  <span className="record-icon">⬛</span>
                  Stop Recording
                </button>
              ) : (
                <button
                  className="record-btn"
                  onClick={startRecording}
                >
                  <span className="record-icon">🔴</span>
                  {sampleStatuses[currentPhraseIndex]?.recorded ? 'Re-record' : 'Record'}
                </button>
              )}
            </div>

            {/* Error display */}
            {error && <div className="error-message">{error}</div>}

            {/* Navigation */}
            <div className="phrase-navigation">
              <button
                className="nav-btn"
                onClick={prevPhrase}
                disabled={currentPhraseIndex === 0}
              >
                ← Previous
              </button>

              {currentPhraseIndex < session.phrases.length - 1 ? (
                <button
                  className="nav-btn"
                  onClick={nextPhrase}
                  disabled={!sampleStatuses[currentPhraseIndex]?.recorded}
                >
                  Next →
                </button>
              ) : (
                <button
                  className="btn-primary"
                  onClick={completeEnrollment}
                  disabled={!allSamplesRecorded || state === 'processing'}
                >
                  Complete Enrollment
                </button>
              )}
            </div>

            {/* Cancel */}
            <button
              className="cancel-link"
              onClick={() => {
                setSession(null);
                setState(enrollmentStatus?.enrolled ? 'enrolled' : 'not_enrolled');
              }}
            >
              Cancel
            </button>
          </div>
        )}
      </main>

      {/* Back to voice call */}
      <footer className="enrollment-footer">
        <button className="back-link" onClick={() => navigate('/voice')}>
          ← Back to Voice Call
        </button>
      </footer>
    </div>
  );
}
