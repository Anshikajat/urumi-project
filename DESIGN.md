# System design and tradeoffs

## Architecture

Two namespaces on a k3d cluster (k3s in production):

- `store`: WordPress + WooCommerce (Deployment), MariaDB (StatefulSet), each on its own persistent volume. Exposed at `store.localhost` through Traefik Ingress.
- `mcp`: the `woo-mcp` server, two demo MCP servers (`notes`, `utils`), the `gateway` and the `dashboard`. Only the dashboard has an Ingress (`dashboard.localhost`). Every MCP server is a ClusterIP Service.

```
browser ─► Traefik ─► dashboard (nginx) ─ /api ─► gateway ─┬─► woo-mcp ─► WooCommerce REST API (store ns)
MCP client ─ /api/mcp (same route) ───────────────►        ├─► notes
                                                           ├─► utils
                                                           ├─► SQLite on a PVC
                                                           └─► Gemini API (chat)
```

Neither the browser nor an MCP client ever talks to an upstream server. Everything goes through the gateway, and a NetworkPolicy on each upstream allows ingress only from the gateway pod.

## Key choices and tradeoffs

**Gateway is both an MCP client and an MCP server.** It registers upstream servers in SQLite, connects to each over Streamable HTTP, and re-exposes the union of their tools on one `/mcp` endpoint. Tradeoff: every client sees one endpoint and one key, but the gateway becomes the single point that must be trusted and kept available.

**Stateless MCP sessions.** The gateway's MCP endpoint runs stateless with JSON responses, so no session state needs to be remembered between requests. This keeps the design simple and is what would let it scale to several replicas later. The current blocker for that is SQLite, not MCP.

**SQLite on a PVC, one replica, `Recreate` strategy.** Chosen for simplicity: no extra database to run, and the schema is small. Tradeoff: no horizontal scaling and a brief outage during upgrades. The next step would be PostgreSQL.

**WooCommerce access through its REST API.** The `woo-mcp` server calls the store's REST API with a consumer key and secret kept in a Kubernetes Secret. Why REST: it is the supported, versioned interface; it needs no plugin and no shell access to the WordPress pod; and a WooCommerce key can be scoped and revoked. The alternative, WP-CLI, would need exec access or a shared filesystem with WordPress, which couples the MCP server to the store's pod.

**API keys.** Each user has one key, stored only as a SHA-256 hash. Keys are high-entropy random tokens, so a fast hash is appropriate. Keys can be revoked (immediate) or rotated by their owner.

## Tool aggregation, routing and failure handling

- **Naming.** Each tool is exposed as `<server>__<tool>`, for example `woo__list_orders`. Server names are restricted to lowercase letters and digits, so the first `__` always splits server from tool. Two servers can expose a tool called `search` (`notes__search`, `utils__search`) without clashing.
- **Listing.** The gateway asks all enabled servers at the same time. Each has a 10 second timeout. A server that fails or times out is reported as down with its error, and the others' tools are still returned.
- **Calling.** A call is split on the first `__`, routed to that server, and limited to 30 seconds. Timeouts and upstream errors become a clear error message, and the call is still written to the audit log.
- **Disabling a server** removes its tools from the next listing for both the chat agent and external clients.
- **Audit.** Every call records user, server, tool, time, duration and outcome. Arguments and results are never stored.

## Chat agent

The dashboard chat calls `/chat` with the user's own key. The gateway runs a Gemini function-calling loop (at most 8 steps) and executes each tool call through the same code path as the MCP endpoint, as that user. So chat calls are authorised and audited exactly like an external client's. Temporary Gemini failures are retried after 2 and 4 seconds.

## Local setup and what changes for production

| Concern | Local (k3d) | Production (k3s on a VPS) |
|---|---|---|
| Domains | `store.localhost`, `dashboard.localhost` via Traefik | Real domains with DNS records pointing at the VPS |
| Images | Built locally, loaded with `k3d image import`, `pullPolicy: IfNotPresent` | Pushed to a registry; set `image.repository` and tag in values |
| Storage | k3d default `local-path` | `local-path` on k3s, or a named storage class, with larger sizes |
| Secrets | Passed with `--set-string` and kept in Kubernetes Secrets | Same, from the deploy environment; never in values files or git |
| WooCommerce URL for the MCP server | In-cluster Service plus a `store.localhost` Host header | Real store URL, no Host header override |
| TLS | None | cert-manager with Let's Encrypt (optional) |

These differences live in `values-local.yaml` and `values-prod.yaml` next to each chart; the templates are identical.

## Upgrade and rollback

```powershell
helm upgrade gateway .\charts\gateway -n mcp --reuse-values --set image.tag=0.2.4 --force-conflicts
helm history gateway -n mcp
helm rollback gateway <revision> -n mcp
```

Database changes are additive (the gateway adds missing columns at startup), and the code only selects the columns it needs, so rolling the image back does not break the existing database.

## Not implemented

Per-tool permissions, SSRF protection when adding a server URL, encryption of stored credentials, rate limits, multiple gateway replicas, OAuth, and the multi-store bonus. See the threat model for how these affect security.