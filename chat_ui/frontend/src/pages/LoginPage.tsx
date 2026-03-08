import { useState, useEffect, useRef } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

type Step = "credentials" | "setup" | "verify";

export function LoginPage() {
  const [step, setStep] = useState<Step>("credentials");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [tempToken, setTempToken] = useState("");
  const [qrImage, setQrImage] = useState("");
  const [secret, setSecret] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const codeRef = useRef<HTMLInputElement>(null);

  const { login, verifyTotp } = useAuth();
  const navigate = useNavigate();

  // Auto-focus OTP input when step changes to setup/verify
  useEffect(() => {
    if (step !== "credentials") {
      const t = setTimeout(() => codeRef.current?.focus(), 80);
      return () => clearTimeout(t);
    }
  }, [step]);

  // Auto-submit when all 6 digits are entered
  useEffect(() => {
    if (code.length === 6 && (step === "setup" || step === "verify")) {
      submitTotp();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code]);

  const handleCredentials = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await login(username, password);
      setTempToken(result.temp_token);
      if (result.setup_required) {
        setQrImage(result.qr_image ?? "");
        setSecret(result.secret ?? "");
        setStep("setup");
      } else {
        setStep("verify");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Invalid credentials");
    } finally {
      setLoading(false);
    }
  };

  const submitTotp = async () => {
    if (code.length !== 6 || loading) return;
    setError("");
    setLoading(true);
    try {
      await verifyTotp(tempToken, code.trim());
      navigate("/", { replace: true });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Invalid code");
      setCode("");
      setTimeout(() => codeRef.current?.focus(), 50);
    } finally {
      setLoading(false);
    }
  };

  const handleTotpSubmit = (e: FormEvent) => {
    e.preventDefault();
    submitTotp();
  };

  const goBack = () => {
    setStep("credentials");
    setError("");
    setCode("");
    setTempToken("");
  };

  return (
    <div className="login-page">
      <div className={`login-card${step !== "credentials" ? " login-card-wide" : ""}`}>
        <div className="login-header">
          <span className="login-icon">&#9096;</span>
          <h1>Sentinel K8s</h1>
          <p>Kubernetes Cluster Dashboard</p>
        </div>

        {/* ── Step 1: Username + Password ── */}
        {step === "credentials" && (
          <form onSubmit={handleCredentials} className="login-form">
            {error && <div className="login-error">{error}</div>}
            <div className="form-field">
              <label htmlFor="username">Username</label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="admin"
                autoFocus
                required
              />
            </div>
            <div className="form-field">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••"
                required
              />
            </div>
            <button type="submit" className="login-btn" disabled={loading}>
              {loading ? "Verifying..." : "Continue →"}
            </button>
          </form>
        )}

        {/* ── Step 2a: First-time 2FA setup with QR code ── */}
        {step === "setup" && (
          <form onSubmit={handleTotpSubmit} className="login-form">
            <div className="totp-setup-info">
              <p className="totp-setup-title">Set up Google Authenticator</p>
              <p className="totp-setup-desc">
                Open Google Authenticator, tap <strong>+</strong> →{" "}
                <strong>Scan QR code</strong>, and scan the image below. Then
                enter the 6-digit code to activate 2FA.
              </p>
            </div>

            {qrImage && (
              <div className="totp-qr-wrapper">
                <img
                  src={`data:image/png;base64,${qrImage}`}
                  alt="Scan with Google Authenticator"
                  className="totp-qr-image"
                />
              </div>
            )}

            {secret && (
              <div className="totp-secret-box">
                <span className="totp-secret-label">Or enter key manually:</span>
                <code className="totp-secret-key">{secret}</code>
              </div>
            )}

            {error && <div className="login-error">{error}</div>}

            <div className="form-field">
              <label htmlFor="totp-code">6-digit code from app</label>
              <input
                id="totp-code"
                ref={codeRef}
                type="text"
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                placeholder="000000"
                required
                className="totp-input"
                autoComplete="one-time-code"
              />
            </div>

            <button
              type="submit"
              className="login-btn"
              disabled={loading || code.length !== 6}
            >
              {loading ? "Activating 2FA..." : "Activate & Sign In"}
            </button>
            <button type="button" className="link-btn" onClick={goBack}>
              ← Back
            </button>
          </form>
        )}

        {/* ── Step 2b: TOTP verification for returning users ── */}
        {step === "verify" && (
          <form onSubmit={handleTotpSubmit} className="login-form">
            <div className="totp-verify-info">
              <span className="totp-verify-icon">&#128272;</span>
              <p className="totp-setup-title">Two-Factor Authentication</p>
              <p className="totp-setup-desc">
                Enter the 6-digit code from your Google Authenticator app.
              </p>
            </div>

            {error && <div className="login-error">{error}</div>}

            <div className="form-field">
              <label htmlFor="totp-code">Authenticator code</label>
              <input
                id="totp-code"
                ref={codeRef}
                type="text"
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                placeholder="000000"
                required
                className="totp-input"
                autoComplete="one-time-code"
              />
            </div>

            <button
              type="submit"
              className="login-btn"
              disabled={loading || code.length !== 6}
            >
              {loading ? "Verifying..." : "Sign In"}
            </button>
            <button type="button" className="link-btn" onClick={goBack}>
              ← Back
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
