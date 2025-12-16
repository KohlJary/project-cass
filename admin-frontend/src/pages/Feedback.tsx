import { useState } from 'react';
import { feedbackApi } from '../api/client';
import './Feedback.css';

export function Feedback() {
  const [heardFrom, setHeardFrom] = useState('');
  const [message, setMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsSubmitting(true);

    try {
      await feedbackApi.submit({
        heard_from: heardFrom || undefined,
        message: message || undefined,
      });
      setSubmitted(true);
    } catch (err) {
      setError('Failed to submit feedback. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="feedback-page">
        <div className="feedback-container">
          <div className="feedback-success">
            <div className="success-icon">*</div>
            <h2>Thank you!</h2>
            <p>Your feedback has been submitted. We appreciate you taking the time to share your thoughts.</p>
            <button
              className="feedback-btn"
              onClick={() => {
                setSubmitted(false);
                setHeardFrom('');
                setMessage('');
              }}
            >
              Submit More Feedback
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="feedback-page">
      <div className="feedback-container">
        <div className="feedback-header">
          <h1>Feedback</h1>
          <p className="subtitle">We'd love to hear from you</p>
        </div>

        <form onSubmit={handleSubmit} className="feedback-form">
          {error && <div className="feedback-error">{error}</div>}

          <div className="form-group">
            <label htmlFor="heardFrom">How'd you hear about us?</label>
            <input
              id="heardFrom"
              type="text"
              value={heardFrom}
              onChange={(e) => setHeardFrom(e.target.value)}
              placeholder="e.g., GitHub, Twitter, a friend..."
            />
          </div>

          <div className="form-group">
            <label htmlFor="message">Anything else you'd like to share?</label>
            <textarea
              id="message"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Your thoughts, questions, or suggestions..."
              rows={5}
            />
          </div>

          <button
            type="submit"
            className="feedback-btn"
            disabled={isSubmitting || (!heardFrom && !message)}
          >
            {isSubmitting ? 'Submitting...' : 'Submit Feedback'}
          </button>
        </form>
      </div>
    </div>
  );
}
