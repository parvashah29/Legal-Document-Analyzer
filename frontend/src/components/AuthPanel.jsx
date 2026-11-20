import React, { useState } from 'react';
import { Shield, Mail, Lock, LogIn, UserPlus, ArrowRight, X } from 'lucide-react';

export default function AuthPanel({ onLogin, onGuest, onClose }) {
  const [isRegistering, setIsRegistering] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!email || !password) {
      setError('Please fill out all fields.');
      return;
    }
    if (password.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }

    // Simulate backend auth for now
    const user = { email };
    
    if (isRegistering) {
      // Simulate checking if user exists
      const existing = localStorage.getItem(`lda-user-${email}`);
      if (existing) {
        setError('An account with this email already exists.');
        return;
      }
      localStorage.setItem(`lda-user-${email}`, JSON.stringify({ email, password }));
    } else {
      const existingRaw = localStorage.getItem(`lda-user-${email}`);
      if (!existingRaw) {
        setError('Invalid email or password.');
        return;
      }
      const existing = JSON.parse(existingRaw);
      if (existing.password !== password) {
        setError('Invalid email or password.');
        return;
      }
    }

    onLogin(user);
  };

  return (
    <div className="auth-overlay">
      <div className="auth-card glass-panel animate-slide-up">
        <button onClick={onClose} className="auth-close-btn">
          <X size={20} />
        </button>
        
        <div className="auth-header">
          <div className="auth-icon-box">
            <Shield size={28} color="var(--accent)" />
          </div>
          <h2>{isRegistering ? 'Create Account' : 'Welcome Back'}</h2>
          <p>
            {isRegistering 
              ? 'Join to save your contract audit history persistently.' 
              : 'Sign in to access your saved diagnostics and history.'}
          </p>
        </div>

        {error && (
          <div className="auth-error">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="auth-form">
          <div className="input-group">
            <label>Email Address</label>
            <div className="input-with-icon">
              <Mail size={16} className="input-icon" />
              <input 
                type="email" 
                placeholder="you@company.com" 
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
          </div>

          <div className="input-group">
            <label>Password</label>
            <div className="input-with-icon">
              <Lock size={16} className="input-icon" />
              <input 
                type="password" 
                placeholder="••••••••" 
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
          </div>

          <button type="submit" className="cta-btn primary-cta auth-submit-btn">
            {isRegistering ? (
              <><UserPlus size={18} /> Create Account</>
            ) : (
              <><LogIn size={18} /> Sign In</>
            )}
          </button>
        </form>

        <div className="auth-divider">
          <span>or</span>
        </div>

        <button onClick={onGuest} className="cta-btn secondary-cta guest-btn">
          <span>Continue as Guest</span>
          <ArrowRight size={16} className="cta-arrow" />
        </button>

        <p className="auth-toggle-text">
          {isRegistering ? 'Already have an account?' : "Don't have an account?"}{' '}
          <button 
            type="button"
            className="auth-toggle-btn"
            onClick={() => {
              setIsRegistering(!isRegistering);
              setError('');
            }}
          >
            {isRegistering ? 'Sign In' : 'Register'}
          </button>
        </p>
      </div>
    </div>
  );
}
