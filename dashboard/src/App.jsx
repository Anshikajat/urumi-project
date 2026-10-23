import { useState } from "react";
import { apiFetch } from "./api.js";
import ServersPage from "./ServersPage.jsx";
import MembersPage from "./MembersPage.jsx";
import AuditPage from "./AuditPage.jsx";
import ChatPage from "./ChatPage.jsx";

export default function App() {
  const [keyInput, setKeyInput] = useState("");
  const [session, setSession] = useState(() => {
    // Remember the login only for this browser tab
    try {
      const saved = sessionStorage.getItem("session");
      return saved ? JSON.parse(saved) : null;
    } catch (e) {
      return null;
    }
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState("servers");

  // "My key" panel
  const [showKey, setShowKey] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [keyBusy, setKeyBusy] = useState(false);
  const [keyError, setKeyError] = useState("");
  const [copied, setCopied] = useState(false);

  async function handleLogin(event) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const key = keyInput.trim();
      const user = await apiFetch("/me", key);
      const next = { key, user };
      sessionStorage.setItem("session", JSON.stringify(next));
      setSession(next);
      setTab("servers");
      setKeyInput("");
    } catch (e) {
      if (e.status === 401) {
        setError("That API key is not valid.");
      } else {
        setError("Could not reach the gateway. Is the port-forward running?");
      }
    } finally {
      setBusy(false);
    }
  }

  function handleLogout() {
    sessionStorage.removeItem("session");
    setSession(null);
    setShowKey(false);
    setNewKey("");
  }

  function toggleKeyPanel() {
    setShowKey(!showKey);
    setNewKey("");
    setKeyError("");
    setCopied(false);
  }

  async function handleRotateKey() {
    if (
      !window.confirm(
        "Generate a new API key? Your current key stops working immediately, " +
          "including in any MCP client that uses it."
      )
    ) {
      return;
    }
    setKeyBusy(true);
    setKeyError("");
    setCopied(false);
    try {
      const result = await apiFetch("/me/key", session.key, { method: "POST" });
      // Keep this browser signed in with the new key
      const next = { ...session, key: result.api_key };
      sessionStorage.setItem("session", JSON.stringify(next));
      setSession(next);
      setNewKey(result.api_key);
    } catch (e) {
      if (e.status === 401) {
        handleLogout();
      } else {
        setKeyError(e.message);
      }
    } finally {
      setKeyBusy(false);
    }
  }

  async function handleCopyKey() {
    try {
      await navigator.clipboard.writeText(newKey);
      setCopied(true);
    } catch (e) {
      setCopied(false);
    }
  }

  if (!session) {
    return (
      <div className="page">
        <form className="card" onSubmit={handleLogin}>
          <h1>Urumi MCP Gateway</h1>
          <p className="muted">Sign in with your API key.</p>
          <input
            type="password"
            placeholder="urumi_..."
            value={keyInput}
            onChange={(e) => setKeyInput(e.target.value)}
            autoFocus
          />
          <button type="submit" disabled={busy || keyInput.trim() === ""}>
            {busy ? "Checking..." : "Sign in"}
          </button>
          {error && <p className="error">{error}</p>}
        </form>
      </div>
    );
  }

  const isAdmin = session.user.role === "admin";
  const tabs = [
    { id: "servers", label: "Servers" },
    { id: "chat", label: "Chat" },
  ];
  if (isAdmin) {
    tabs.push({ id: "members", label: "Members" });
    tabs.push({ id: "audit", label: "Audit log" });
  }

  return (
    <div className="layout">
      <header className="topbar">
        <h1>Urumi MCP Gateway</h1>
        <div className="topbar-right">
          <span>
            {session.user.name}{" "}
            <span className={"badge " + session.user.role}>{session.user.role}</span>
          </span>
          <button className="secondary" onClick={toggleKeyPanel}>
            My key
          </button>
          <button className="secondary" onClick={handleLogout}>
            Sign out
          </button>
        </div>
      </header>
      <nav className="tabs">
        {tabs.map((t) => (
          <button
            key={t.id}
            className={"tab" + (tab === t.id ? " active" : "")}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>
      <main className="content">
        {showKey && (
          <div className="panel key-box">
            <strong>My API key</strong>
            {newKey ? (
              <>
                <p className="muted small">
                  This is your new key. Copy it now: it is shown only once and cannot be
                  recovered. Your old key no longer works.
                </p>
                <div className="row">
                  <code className="grow key-text">{newKey}</code>
                  <button onClick={handleCopyKey}>{copied ? "Copied" : "Copy"}</button>
                </div>
              </>
            ) : (
              <>
                <p className="muted small">
                  Keys are stored only as a hash, so your current key cannot be shown again.
                  Generate a new one if you need it for an MCP client. The old key stops
                  working immediately.
                </p>
                <div className="row">
                  <button onClick={handleRotateKey} disabled={keyBusy}>
                    {keyBusy ? "Generating..." : "Generate new key"}
                  </button>
                </div>
              </>
            )}
            {keyError && <p className="error">{keyError}</p>}
            <button className="secondary" onClick={toggleKeyPanel}>
              {newKey ? "I have saved it" : "Close"}
            </button>
          </div>
        )}

        {tab === "servers" && (
          <ServersPage
            sessionKey={session.key}
            isAdmin={isAdmin}
            onAuthError={handleLogout}
          />
        )}
        {/* Chat stays mounted so switching tabs does not lose the conversation */}
        <div style={{ display: tab === "chat" ? "block" : "none" }}>
          <ChatPage sessionKey={session.key} onAuthError={handleLogout} />
        </div>
        {tab === "members" && isAdmin && (
          <MembersPage sessionKey={session.key} onAuthError={handleLogout} />
        )}
        {tab === "audit" && isAdmin && (
          <AuditPage sessionKey={session.key} onAuthError={handleLogout} />
        )}
      </main>
    </div>
  );
}