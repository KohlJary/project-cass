import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { faceApi } from '../api/domains/face';
import type { EnrollmentSession, EnrollmentStatus } from '../api/domains/face';
import './FaceEnrollment.css';

type EnrollmentState = 'loading' | 'unavailable' | 'not_enrolled' | 'enrolling' | 'capturing' | 'processing' | 'enrolled';

interface SampleStatus {
  captured: boolean;
  quality?: number;
  feedback?: string;
}

export function FaceEnrollment() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const userId = user?.user_id;

  const [state, setState] = useState<EnrollmentState>('loading');
  const [enrollmentStatus, setEnrollmentStatus] = useState<EnrollmentStatus | null>(null);
  const [session, setSession] = useState<EnrollmentSession | null>(null);
  const [currentInstructionIndex, setCurrentInstructionIndex] = useState(0);
  const [sampleStatuses, setSampleStatuses] = useState<SampleStatus[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [cameraReady, setCameraReady] = useState(false);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  // Check face service status and enrollment on mount
  useEffect(() => {
    if (!userId) return;

    const checkStatus = async () => {
      try {
        const statusRes = await faceApi.getStatus();
        if (!statusRes.data.available) {
          setState('unavailable');
          setError(statusRes.data.error || 'Face identification not available');
          return;
        }

        const enrollRes = await faceApi.getEnrollmentStatus(userId);
        setEnrollmentStatus(enrollRes.data);
        setState(enrollRes.data.enrolled ? 'enrolled' : 'not_enrolled');
      } catch (err) {
        console.error('Failed to check face status:', err);
        setState('not_enrolled');
      }
    };

    checkStatus();
  }, [userId]);

  // Start camera when enrolling
  useEffect(() => {
    if (state === 'enrolling' || state === 'capturing') {
      startCamera();
    } else {
      stopCamera();
    }

    return () => {
      stopCamera();
    };
  }, [state]);

  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: 640, height: 480 },
      });
      streamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.onloadedmetadata = () => {
          setCameraReady(true);
        };
      }
    } catch (err) {
      console.error('Failed to start camera:', err);
      setError('Could not access camera. Please check permissions.');
    }
  };

  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    setCameraReady(false);
  };

  // Start enrollment session
  const startEnrollment = async () => {
    if (!userId) return;

    try {
      setError(null);
      const res = await faceApi.startEnrollment(userId);
      setSession(res.data);
      setSampleStatuses(res.data.instructions.map(() => ({ captured: false })));
      setCurrentInstructionIndex(0);
      setState('enrolling');
    } catch (err) {
      console.error('Failed to start enrollment:', err);
      setError('Failed to start enrollment session');
    }
  };

  // Capture current frame
  const captureFrame = useCallback(async () => {
    if (!session || !videoRef.current || !canvasRef.current || !cameraReady) return;

    setState('capturing');
    setError(null);

    const video = videoRef.current;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');

    if (!ctx) return;

    // Set canvas size to match video
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    // Draw current frame (mirror it for natural feel)
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(video, 0, 0);
    ctx.setTransform(1, 0, 0, 1, 0, 0);

    // Convert to base64 JPEG
    const imageData = canvas.toDataURL('image/jpeg', 0.9);
    const base64 = imageData.split(',')[1];

    setState('processing');

    try {
      const res = await faceApi.addEnrollmentSample(session.session_id, base64);

      // Update sample status
      const newStatuses = [...sampleStatuses];
      newStatuses[currentInstructionIndex] = {
        captured: res.data.accepted,
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
      setError('Failed to process image');
      setState('enrolling');
    }
  }, [session, cameraReady, currentInstructionIndex, sampleStatuses]);

  // Move to next instruction
  const nextInstruction = () => {
    if (session && currentInstructionIndex < session.instructions.length - 1) {
      setCurrentInstructionIndex(currentInstructionIndex + 1);
      setError(null);
    }
  };

  // Move to previous instruction
  const prevInstruction = () => {
    if (currentInstructionIndex > 0) {
      setCurrentInstructionIndex(currentInstructionIndex - 1);
      setError(null);
    }
  };

  // Complete enrollment
  const completeEnrollment = async () => {
    if (!session) return;

    try {
      setState('processing');
      setError(null);

      const res = await faceApi.completeEnrollment(session.session_id);

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

    if (!confirm('Are you sure you want to delete your face enrollment?')) {
      return;
    }

    try {
      await faceApi.deleteEnrollment(userId);
      setEnrollmentStatus({ enrolled: false });
      setSession(null);
      setSampleStatuses([]);
      setState('not_enrolled');
    } catch (err) {
      console.error('Failed to delete enrollment:', err);
      setError('Failed to delete enrollment');
    }
  };

  // Check if all samples are captured
  const allSamplesCaptured = sampleStatuses.every((s) => s.captured);

  // Get quality color
  const getQualityColor = (quality?: number) => {
    if (!quality) return '#666';
    if (quality >= 0.7) return '#4ade80';
    if (quality >= 0.5) return '#fbbf24';
    return '#f87171';
  };

  // Loading state
  if (state === 'loading') {
    return (
      <div className="face-enrollment-page">
        <div className="loading-state">Loading...</div>
      </div>
    );
  }

  // Unavailable state
  if (state === 'unavailable') {
    return (
      <div className="face-enrollment-page">
        <header className="enrollment-header">
          <h1>Face Enrollment</h1>
        </header>
        <main className="enrollment-main">
          <div className="unavailable-state">
            <div className="error-icon">⚠️</div>
            <h2>Face Identification Unavailable</h2>
            <p>{error || 'The face_recognition library is not installed on the server.'}</p>
            <p className="install-hint">
              Install with: <code>pip install face-recognition</code>
            </p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="face-enrollment-page">
      <header className="enrollment-header">
        <h1>Face Enrollment</h1>
        <p className="subtitle">
          Enroll your face so Cass can recognize you visually
        </p>
      </header>

      <main className="enrollment-main">
        {/* Already enrolled state */}
        {state === 'enrolled' && enrollmentStatus && (
          <div className="enrolled-state">
            <div className="success-icon">✓</div>
            <h2>Face Enrolled</h2>
            <p>Cass can now recognize your face.</p>
            <div className="enrollment-info">
              <div className="info-item">
                <span className="label">Images:</span>
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
            <div className="camera-icon-large">📷</div>
            <h2>Face Not Enrolled</h2>
            <p>
              Capture 5 photos from different angles to create your faceprint.
              This allows Cass to identify you by sight.
            </p>
            <button className="btn-primary" onClick={startEnrollment}>
              Start Enrollment
            </button>
          </div>
        )}

        {/* Enrolling state */}
        {(state === 'enrolling' || state === 'capturing' || state === 'processing') && session && (
          <div className="enrolling-state">
            {/* Progress indicator */}
            <div className="progress-bar">
              {session.instructions.map((_, idx) => (
                <div
                  key={idx}
                  className={`progress-dot ${
                    sampleStatuses[idx]?.captured ? 'captured' : ''
                  } ${idx === currentInstructionIndex ? 'current' : ''}`}
                  onClick={() => setCurrentInstructionIndex(idx)}
                  style={{
                    backgroundColor: sampleStatuses[idx]?.captured
                      ? getQualityColor(sampleStatuses[idx]?.quality)
                      : undefined,
                  }}
                >
                  {idx + 1}
                </div>
              ))}
            </div>

            {/* Current instruction */}
            <div className="instruction-card">
              <div className="instruction-number">
                Photo {currentInstructionIndex + 1} of {session.instructions.length}
              </div>
              <div className="instruction-text">
                {session.instructions[currentInstructionIndex]}
              </div>

              {/* Sample status */}
              {sampleStatuses[currentInstructionIndex]?.captured && (
                <div
                  className="sample-status"
                  style={{ color: getQualityColor(sampleStatuses[currentInstructionIndex]?.quality) }}
                >
                  ✓ {sampleStatuses[currentInstructionIndex]?.feedback}
                </div>
              )}
            </div>

            {/* Camera preview */}
            <div className={`camera-preview ${state === 'capturing' ? 'capturing' : ''}`}>
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                style={{ transform: 'scaleX(-1)' }}
              />
              <canvas ref={canvasRef} style={{ display: 'none' }} />
              {!cameraReady && (
                <div className="camera-loading">Starting camera...</div>
              )}
              {state === 'processing' && (
                <div className="processing-overlay">Processing...</div>
              )}
            </div>

            {/* Capture button */}
            <div className="capture-controls">
              {state === 'processing' ? (
                <div className="processing-indicator">Analyzing face...</div>
              ) : (
                <button
                  className="capture-btn"
                  onClick={captureFrame}
                  disabled={!cameraReady}
                >
                  <span className="capture-icon">📸</span>
                  {sampleStatuses[currentInstructionIndex]?.captured ? 'Retake' : 'Capture'}
                </button>
              )}
            </div>

            {/* Error display */}
            {error && <div className="error-message">{error}</div>}

            {/* Navigation */}
            <div className="instruction-navigation">
              <button
                className="nav-btn"
                onClick={prevInstruction}
                disabled={currentInstructionIndex === 0}
              >
                ← Previous
              </button>

              {currentInstructionIndex < session.instructions.length - 1 ? (
                <button
                  className="nav-btn"
                  onClick={nextInstruction}
                  disabled={!sampleStatuses[currentInstructionIndex]?.captured}
                >
                  Next →
                </button>
              ) : (
                <button
                  className="btn-primary"
                  onClick={completeEnrollment}
                  disabled={!allSamplesCaptured || state === 'processing'}
                >
                  Complete Enrollment
                </button>
              )}
            </div>

            {/* Cancel */}
            <button
              className="cancel-link"
              onClick={() => {
                stopCamera();
                setSession(null);
                setState(enrollmentStatus?.enrolled ? 'enrolled' : 'not_enrolled');
              }}
            >
              Cancel
            </button>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="enrollment-footer">
        <button className="back-link" onClick={() => navigate('/voice')}>
          ← Back to Voice Call
        </button>
      </footer>
    </div>
  );
}
