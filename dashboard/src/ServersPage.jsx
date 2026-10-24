import { useEffect, useState } from "react";
import { apiFetch } from "./api.js";

export default function ServersPage({ sessionKey, isAdmin, onAuthError }) {
  const [servers, setServers] = useState([]); // from /servers (id, name, url, enabled, has_credential)
  const [status, setStatus] = useState({}); // from /tools, keyed by server name
  const [tools, setTools] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [newName, setNewName] = useState("");
  const [newUrl, setNewUrl] = useState("");
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);

  // editing one server at a time
  const [editingId, setEditingId] = useState(null);
  const [editName, setEditName] = useState("");
  const [editUrl, setEditUrl] = useState("");
  const [editCred, setEditCred] = useState("");
  const [editError, setEditError] = useState("");
  const [editNote, setEditNote] = useState("");

  function handleError(e) {
    if (e.status === 401) {
      onAuthError();
    } else {
      setError(e.message);
    }
  }

  async function load() {
    setLoading(true);
    setError("");
    try {
      const list = await apiFetch("/servers", sessionKey);
      setServers(list);
      const discovered = await apiFetch("/tools", sessionKey);
      const byName = {};
      for (const s of discovered.servers) {
        byName[s.server] = s;
      }
      setStatus(byName);
      setTools(discovered.tools);
    } catch (e) {
      handleError(e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleAdd(event) {
    event.preventDefault();
    setFormError("");
    setBusy(true);
    try {
      await apiFetch("/servers", sessionKey, {
        method: "POST",
        body: JSON.stringify({ name: newName.trim(), url: newUrl.trim() }),
      });
      setNewName("");
      setNewUrl("");
      await load();
    } catch (e) {
      if (e.status === 401) {
        onAuthError();
      } else if (e.status === 422) {
        setFormError(
          "Name: lowercase letters and digits only, starting with a letter. URL must start with http:// or https://."
        );
      } else {
        setFormError(e.message);
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleToggle(server) {
    setBusy(true);
    try {
      const action = server.enabled ? "disable" : "enable";
      await apiFetch("/servers/" + server.id + "/" + action, sessionKey, {
        method: "POST",
      });
      await load();
    } catch (e) {
      handleError(e);
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove(server) {
    if (!window.confirm("Remove server '" + server.name + "'?")) {
      return;
    }
    setBusy(true);
    try {
      await apiFetch("/servers/" + server.id, sessionKey, { method: "DELETE" });
      await load();
    } catch (e) {
      handleError(e);
    } finally {
      setBusy(false);
    }
  }

  // ---------- editing ----------

  function startEdit(server) {
    setEditingId(server.id);
    setEditName(server.name);
    setEditUrl(server.url);
    setEditCred("");
    setEditError("");
    setEditNote("");
  }

  function cancelEdit() {
    setEditingId(null);
    setEditCred("");
    setEditError("");
    setEditNote("");
  }

  // Sends one PATCH. Returns true on success.
  async function patchServer(server, body) {
    setEditError("");
    setEditNote("");
    setBusy(true);
    try {
      await apiFetch("/servers/" + server.id, sessionKey, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      return true;
    } catch (e) {
      if (e.status === 401) {
        onAuthError();
      } else if (e.status === 409) {
        setEditError("A server with that name already exists.");
      } else if (e.status === 422) {
        setEditError(
          "Name: lowercase letters and digits only, starting with a letter. URL must start with http:// or https://."
        );
      } else {
        setEditError(e.message);
      }
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveDetails(server) {
    const body = {};
    const name = editName.trim();
    const url = editUrl.trim();
    if (name !== server.name) body.name = name;
    if (url !== server.url) body.url = url;

    if (Object.keys(body).length === 0) {
      setEditError("Nothing changed.");
      return;
    }
    if (
      body.name &&
      !window.confirm(
        "Renaming '" +
          server.name +
          "' changes its tool names (for example " +
          server.name +
          "__tool becomes " +
          body.name +
          "__tool). Continue?"
      )
    ) {
      return;
    }

    if (await patchServer(server, body)) {
      setEditingId(null);
      await load();
    }
  }

  async function handleSaveCredential(server) {
    if (!editCred) {
      setEditError("Type a credential first.");
      return;
    }
    if (await patchServer(server, { credential: editCred })) {
      setEditCred("");
      setEditNote("Credential saved. It is stored hidden and is never shown again.");
      await load();
    }
  }

  async function handleClearCredential(server) {
    if (!window.confirm("Remove the credential for '" + server.name + "'?")) {
      return;
    }
    if (await patchServer(server, { credential: "" })) {
      setEditCred("");
      setEditNote("Credential removed.");
      await load();
    }
  }

  function toolsFor(serverName) {
    return tools.filter((t) => t.server === serverName);
  }

  return (
    <div>
      <div className="section-header">
        <h2>Servers</h2>
        <button className="secondary" onClick={load} disabled={loading || busy}>
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      {isAdmin && (
        <form className="panel add-form" onSubmit={handleAdd}>
          <h3>Add a server</h3>
          <div className="row">
            <input
              placeholder="name (e.g. woo)"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
            <input
              className="grow"
              placeholder="http://woo-mcp.mcp.svc.cluster.local:8000/mcp"
              value={newUrl}
              onChange={(e) => setNewUrl(e.target.value)}
            />
            <button type="submit" disabled={busy || !newName.trim() || !newUrl.trim()}>
              Add
            </button>
          </div>
          {formError && <p className="error">{formError}</p>}
        </form>
      )}

      {!loading && servers.length === 0 && (
        <p className="muted">No servers registered yet.</p>
      )}

      {servers.map((server) => {
        const info = status[server.name];
        const serverTools = toolsFor(server.name);
        const editing = editingId === server.id;
        let label = "Disabled";
        let labelClass = "status disabled";
        if (server.enabled) {
          if (!info) {
            label = "checking";
            labelClass = "status checking";
          } else if (info.status === "up") {
            label = "Connected";
            labelClass = "status up";
          } else {
            label = "Unreachable";
            labelClass = "status down";
          }
        }

        return (
          <div className="panel server" key={server.id}>
            <div className="server-head">
              <div>
                <strong>{server.name}</strong>{" "}
                <span className={labelClass}>{label}</span>{" "}
                {server.has_credential && (
                  <span className="status cred">credential set</span>
                )}
                <div className="muted small">{server.url}</div>
              </div>
              {isAdmin && (
                <div className="row">
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => (editing ? cancelEdit() : startEdit(server))}
                  >
                    {editing ? "Close" : "Edit"}
                  </button>
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => handleToggle(server)}
                  >
                    {server.enabled ? "Disable" : "Enable"}
                  </button>
                  <button
                    className="danger"
                    disabled={busy}
                    onClick={() => handleRemove(server)}
                  >
                    Remove
                  </button>
                </div>
              )}
            </div>

            {isAdmin && editing && (
              <div className="edit-box">
                <h3>Edit {server.name}</h3>
                <div className="row">
                  <input
                    placeholder="name"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                  />
                  <input
                    className="grow"
                    placeholder="url"
                    value={editUrl}
                    onChange={(e) => setEditUrl(e.target.value)}
                  />
                  <button
                    disabled={busy || !editName.trim() || !editUrl.trim()}
                    onClick={() => handleSaveDetails(server)}
                  >
                    Save
                  </button>
                </div>

                <div className="muted small">
                  Credential (sent to this server as a Bearer token). It is stored hidden
                  and cannot be viewed again, only replaced or removed.
                </div>
                <div className="row">
                  <input
                    className="grow"
                    type="password"
                    autoComplete="new-password"
                    placeholder={
                      server.has_credential ? "enter a new credential to replace it" : "credential"
                    }
                    value={editCred}
                    onChange={(e) => setEditCred(e.target.value)}
                  />
                  <button
                    disabled={busy || !editCred}
                    onClick={() => handleSaveCredential(server)}
                  >
                    {server.has_credential ? "Replace" : "Set"}
                  </button>
                  {server.has_credential && (
                    <button
                      className="danger"
                      disabled={busy}
                      onClick={() => handleClearCredential(server)}
                    >
                      Clear
                    </button>
                  )}
                </div>

                {editError && <p className="error">{editError}</p>}
                {editNote && <p className="success">{editNote}</p>}
              </div>
            )}

            {server.enabled && info && info.status === "down" && (
              <p className="error small">{info.error}</p>
            )}

            {server.enabled && info && info.status === "up" && (
              <div className="tools">
                <div className="muted small">{info.tool_count} tools</div>
                <div className="chips">
                  {serverTools.map((t) => (
                    <span className="chip" key={t.name} title={t.description}>
                      {t.name}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}