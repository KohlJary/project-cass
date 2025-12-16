import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import './Login.css';  // Reuse login styles
import './Register.css';

export function Register() {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [registrationReason, setRegistrationReason] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const { register } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    // Validate passwords match
    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    // Validate password length
    if (password.length < 6) {
      setError('Password must be at least 6 characters');
      return;
    }

    setIsLoading(true);

    const result = await register(username, password, email || undefined, registrationReason || undefined);

    if (result.success) {
      setIsSubmitted(true);
    } else {
      setError(result.message);
    }

    setIsLoading(false);
  };

  // Success state - show pending approval message
  if (isSubmitted) {
    return (
      <div className="login-page">
        <div className="login-container">
          <div className="register-success">
            <div className="success-icon">✓</div>
            <h2>Registration Submitted</h2>
            <p>
              Your account is pending approval. You'll be able to log in once an
              administrator approves your registration.
            </p>
            <Link to="/login" className="login-btn back-link">
              Back to Login
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="login-page">
      <div className="login-container">
        <div className="login-header">
          <h1>Create Account</h1>
          <p className="subtitle">Register for access to Cass</p>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          {error && <div className="login-error">{error}</div>}

          <div className="form-group">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Choose a username"
              autoComplete="username"
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="email">Email <span className="optional">(optional)</span></label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="your@email.com"
              autoComplete="email"
            />
            <span className="field-hint">Used to notify you when your account is approved</span>
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Create a password"
              autoComplete="new-password"
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="confirmPassword">Confirm Password</label>
            <input
              id="confirmPassword"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Confirm your password"
              autoComplete="new-password"
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="registrationReason">Why do you want to use Cass? <span className="optional">(optional)</span></label>
            <textarea
              id="registrationReason"
              value={registrationReason}
              onChange={(e) => setRegistrationReason(e.target.value)}
              placeholder="Tell us a bit about yourself and why you're interested..."
              rows={3}
            />
          </div>

          <button
            type="submit"
            className="login-btn"
            disabled={isLoading || !username || !password || !confirmPassword}
          >
            {isLoading ? 'Registering...' : 'Register'}
          </button>
        </form>

        <div className="login-footer">
          <p>Already have an account? <Link to="/login" className="register-link">Sign in</Link></p>
        </div>
      </div>
    </div>
  );
}
