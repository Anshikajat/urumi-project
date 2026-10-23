import { useState } from "react";
import { apiFetch } from "./api.js";

export default function ChatPage({ sessionKey, onAuthError }) {
  const [messages, setMessages] = useState([]); // { role, content, toolCalls? }
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleSend(event) {
    event.preventDefault();
    const text = input.trim();
    if (!text || busy) return;

    const next = [...messages, { role: "user", content: text }];
    setMessages(next);
    setInput("");
    setError("");
    setBusy(true);

    try {
      const data = await apiFetch("/chat", sessionKey, {
        method: "POST",
        body: JSON.stringify({
          messages: next.map((m) => ({ role: m.role, content: m.content })),
        }),
      });
      setMessages([
        ...next,
        { role: "assistant", content: data.reply, toolCalls: data.tool_calls },
      ]);
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

  return (
    <div>
      <div className="section-header">
        <h2>Chat</h2>
        <button
          className="secondary"
          onClick={() => {
            setMessages([]);
            setError("");
          }}
          disabled={busy || messages.length === 0}
        >
          Clear
        </button>
      </div>

      <div className="panel chat-log">
        {messages.length === 0 && (
          <p className="muted">
            Ask about the store, for example: "What products do we sell?"
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={"bubble " + m.role}>
            <div className="bubble-text">{m.content}</div>
            {m.toolCalls && m.toolCalls.length > 0 && (
              <div className="chips">
                {m.toolCalls.map((c, j) => (
                  <span
                    key={j}
                    className={"chip " + (c.status === "ok" ? "" : "chip-error")}
                  >
                    {c.tool}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
        {busy && <p className="muted">Thinking...</p>}
      </div>

      {error && <p className="error">{error}</p>}

      <form className="row" onSubmit={handleSend}>
        <input
          className="grow"
          placeholder="Type a message"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={busy}
        />
        <button type="submit" disabled={busy || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}