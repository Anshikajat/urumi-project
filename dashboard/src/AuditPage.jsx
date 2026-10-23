import { useEffect, useState } from "react";
import { apiFetch } from "./api.js";

export default function AuditPage({ sessionKey, onAuthError }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      setRows(await apiFetch("/audit?limit=100", sessionKey));
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

  return (
    <div>
      <div className="section-header">
        <h2>Audit log</h2>
        <button className="secondary" onClick={load} disabled={loading}>
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      {!loading && rows.length === 0 && (
        <p className="muted">No tool calls recorded yet.</p>
      )}

      {rows.length > 0 && (
        <div className="panel">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>User</th>
                <th>Tool</th>
                <th>Status</th>
                <th>Duration</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{new Date(r.ts).toLocaleString()}</td>
                  <td>{r.user_name}</td>
                  <td>
                    <code>{r.tool}</code>
                  </td>
                  <td>
                    <span className={"status " + (r.status === "ok" ? "up" : "down")}>
                      {r.status}
                    </span>
                  </td>
                  <td>{r.duration_ms} ms</td>
                  <td>{r.error || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}