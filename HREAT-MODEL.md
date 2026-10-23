# Threat model

Assets: the store's data and the upstream credentials, the users' API keys, and the shared Gemini quota. Actors: admins (trusted), members (authenticated, not fully trusted), registered MCP servers (partly trusted) and anyone on the network.

## 1. Shared upstream credentials: what a member can do with a credential they never see

A member never receives an upstream credential. The API reports only `has_credential` (true or false), the dashboard cannot display it, and the gateway adds it to requests on the server side.

A member can still *use* it indirectly. Every tool of an enabled server is available to every member, so a member can do whatever the credential allows through those tools. For the store, that includes creating products and changing order status.

Today's mitigations: only admins register servers and set credentials; each call is attributed to the user in the audit log; an admin can revoke a member at once; the WooCommerce key should be scoped to what the tools need.

Gap: there are no per-role or per-tool permissions yet. The fix is a tool allowlist per role, with restricted tools hidden from listings and rejected when called directly.

## 2. Why client tokens are not passed through to upstream servers

A member's gateway key is only ever sent to the gateway. When the gateway calls an upstream it sends that server's own stored credential, and nothing from the client. Reasons:

- A compromised or malicious upstream would otherwise collect member keys and replay them against the gateway or other servers.
- An upstream would be trusting a token that was never issued for it (a confused deputy), and it could not tell users apart safely.
- Revoking a member at the gateway would not reliably stop access if the upstream accepted the member's token directly.

The cost is that upstream servers cannot see which member made a call. Attribution is the gateway's audit log.

## 3. Untrusted upstreams: tool descriptions written to manipulate the model

Tool names, descriptions and results are text that reaches the model. A malicious server could write a description or a result that tries to steer the agent, for example to call a different server's tool or to leak data into a later call.

Today's mitigations: only an admin can register a server; the chat system prompt tells the model that tool results are data and not instructions; the agent can only use the tools its user is already allowed to use; the loop is limited to 8 steps; every call is audited.

Gaps: descriptions are not reviewed or pinned, so a server can change them later; the agent can combine tools from different servers, so a poisoned server can try to trigger actions on another; and a human is not asked to confirm risky calls. Mitigations to add are a per-server tool allowlist, hashing descriptions and alerting on change, and confirmation for tools that write.

If an admin adds a compromised server, it obtains its own credential (by design), the arguments of calls made to it, and the ability to feed text to the model.

**URL abuse (SSRF).** The gateway makes outbound requests to any URL an admin registers, with that server's credential. An admin, or someone with a stolen admin key, could point it at an internal address or a cloud metadata endpoint. This is not blocked today. The fix is to resolve and check each address against a deny list (loopback, link-local and metadata ranges, and the cluster's own services unless allowed) before connecting.

## 4. What one team member can do to another

Cannot: see another member's key (only a SHA-256 hash is stored, and the key prefix is shown only to admins), revoke or rotate another user's key, read the audit log (admin only), or read another user's chat (history lives in the browser and is not stored by the gateway).

Can:
- Change or delete shared store data that others rely on, because members share the same tools. Attribution is in the audit log.
- See the registered servers' names and internal URLs (`GET /servers` is open to every user).
- Use up the shared Gemini quota or keep upstreams busy, because there are no per-user rate limits.

A member can rotate only their own key. Rotating invalidates the old key immediately.

## Network and storage posture

- Upstream MCP servers have no Ingress, and a NetworkPolicy allows traffic to them only from the gateway pod. The gateway accepts traffic only from the dashboard's proxy.
- Pods run as non-root; the gateway also drops all Linux capabilities.
- Keys are stored hashed. The Gemini key, store passwords and WooCommerce keys are Kubernetes Secrets passed in at install time.
- Upstream credentials are stored in SQLite as plain text on the gateway's volume. Anyone with access to the volume or a backup can read them. They should be encrypted at rest or moved to a secrets manager for production.