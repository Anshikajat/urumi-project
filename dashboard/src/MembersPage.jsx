import { useEffect, useState } from "react";
import { apiFetch } from "./api.js";

export default function MembersPage({ sessionKey, onAuthError }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("member");
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState(null); // holds the new user + real key, shown once
  const [copied, setCopied] = useState(false);

  async function load() {
    setLoading(true);
    setError("");
    try {
      setUsers(await apiFetch("/users", sessionKey));
    } catch (e) {
      if (e.status === 401) {
        onAuthError();
      } else {
        setError(e.message);
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleCreate(event) {
    event.preventDefault();
    setFormError("");
    setCreated(null);
    setCopied(false);
    setBusy(true);
    try {
      const user = await apiFetch("/users", sessionKey, {
        method: "POST",
        body: JSON.stringify({ name: name.trim(), role }),
      });
      setCreated(user);
      setName("");
      setRole("member");
      await load();
    } catch (e) {
      if (e.status === 401) {
        onAuthError();
      } else {
        setFormError(e.message);
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleRevoke(user) {
    if (
      !window.confirm(
        "Revoke access for '" +
          user.name +
          "'? Their API key stops working immediately and cannot be restored."
      )
    ) {
      return;
    }
    setError("");
    setBusy(true);
    try {
      await apiFetch("/users/" + user.id + "/revoke", sessionKey, {
        method: "POST",
      });
      await load();
    } catch (e) {
      if (e.status === 401) {
        onAuthError();
      } else {
        setError(e.message);
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(created.api_key);
      setCopied(true);
    } catch (e) {
      setCopied(false);
    }
  }

  return (
    <div>
      <div className="section-header">
        <h2>Members</h2>
        <button className="secondary" onClick={load} disabled={loading || busy}>
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      <form className="panel add-form" onSubmit={handleCreate}>
        <h3>Create a user</h3>
        <div className="row">
          <input
            className="grow"
            placeholder="name (e.g. carol)"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="member">member</option>
            <option value="admin">admin</option>
          </select>
          <button type="submit" disabled={busy || !name.trim()}>
            Create
          </button>
        </div>
        {formError && <p className="error">{formError}</p>}
      </form>

      {created && (
        <div className="panel key-box">
          <strong>
            Key for {created.name} ({created.role})
          </strong>
          <p className="muted small">
            Copy it now. It is shown only once and cannot be recovered later.
          </p>
          <div className="row">
            <code className="grow key-text">{created.api_key}</code>
            <button onClick={handleCopy}>{copied ? "Copied" : "Copy"}</button>
          </div>
          <button className="secondary" onClick={() => setCreated(null)}>
            I have saved it
          </button>
        </div>
      )}

      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Role</th>
              <th>Key prefix</th>
              <th>Status</th>
              <th>Created</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className={u.active ? "" : "inactive"}>
                <td>{u.name}</td>
                <td>
                  <span className={"badge " + u.role}>{u.role}</span>
                </td>
                <td>
                  <code>{u.key_prefix}...</code>
                </td>
                <td>
                  <span className={"badge " + (u.active ? "active" : "revoked")}>
                    {u.active ? "active" : "revoked"}
                  </span>
                </td>
                <td>{new Date(u.created_at).toLocaleString()}</td>
                <td>
                  {!!u.active && (
                    <button
                      className="danger small-btn"
                      disabled={busy}
                      onClick={() => handleRevoke(u)}
                    >
                      Revoke
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}