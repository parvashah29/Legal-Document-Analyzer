import { useState } from 'react';
import { Shield, Mail, LogIn, ArrowRight, X } from 'lucide-react';

export default function AuthPanel({ onLogin, onGuest, onClose }) {
    const [email, setEmail] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    const trimmed = email.trim();
    if (!/^\S+@\S+\.\S+$/.test(trimmed)) {
      setError('Please enter a valid email address.');
      return;
    }
    // Local profile only: the email just names the saved-audit list kept in this browser.
    onLogin({ email: trimmed });
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
          <h2>Local Profile</h2>
          <p>
            Enter an email to keep a list of your past analyses in this browser.
            There is no account or server login: nothing is sent anywhere and no password is stored.
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

          <button type="submit" className="cta-btn primary-cta auth-submit-btn">
            <><LogIn size={18} /> Continue</>
          </button>
        </form>

        <div className="auth-divider">
          <span>or</span>
        </div>

        <button onClick={onGuest} className="cta-btn secondary-cta guest-btn">
          <span>Continue as Guest</span>
          <ArrowRight size={16} className="cta-arrow" />
        </button>

      </div>
    </div>
  );
}
