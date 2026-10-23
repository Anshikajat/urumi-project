# Urumi MCP Gateway

WooCommerce hosting with a team MCP gateway on Kubernetes. A WooCommerce store runs in the cluster; an MCP server we wrote exposes its products and orders as tools; a gateway aggregates that server and others behind **one MCP endpoint**; a dashboard and a Gemini chat agent use the same endpoint.

More detail: [DESIGN.md](DESIGN.md) (architecture and tradeoffs) and [THREAT-MODEL.md](THREAT-MODEL.md) (security).

## Components

| Component | What it is | Chart | Image |
|---|---|---|---|
| `store` | WordPress + WooCommerce and MariaDB, on persistent volumes | `charts/store` | `wordpress:php8.2-apache`, `mariadb:11` |
| `woo-mcp` | MCP server we wrote; talks to the store's REST API | `charts/woo-mcp` | `woo-mcp:0.1.0` |
| `notes`, `utils` | Two demo MCP servers (3 tools each) | `charts/mcp-server` | `extra-mcp:0.1.0` |
| `gateway` | FastAPI: auth, server registry, tool aggregation, audit log, chat, `/mcp` | `charts/gateway` | `gateway:0.2.5` |
| `dashboard` | React app on nginx; proxies `/api` to the gateway | `charts/dashboard` | `dashboard:0.1.2` |

Namespaces: `store` (WordPress, MariaDB) and `mcp` (everything else), on a k3d cluster named `urumi`.

```
browser ─► Traefik ─► dashboard (nginx) ─ /api ─► gateway ─┬─► woo-mcp ─► WooCommerce REST API (store ns)
MCP client ─ http://dashboard.localhost/api/mcp ─►         ├─► notes
                                                           ├─► utils
                                                           ├─► SQLite on a PVC (/data/gateway.db)
                                                           └─► Gemini API (chat)
```

### Public and internal-only

| Reachable from outside | Internal only |
|---|---|
| `store.localhost` (storefront and wp-admin), `dashboard.localhost` (dashboard, plus the gateway through `/api`) | `woo-mcp`, `notes`, `utils`, MariaDB, and the gateway itself |

Internal services are ClusterIP only (no Ingress). This is enforced with NetworkPolicies:

- `woo-mcp`, `notes`, `utils`: accept traffic only from the gateway pod.
- `gateway`: accepts traffic only from the dashboard pod.
- `store` namespace: MariaDB accepts traffic only from WordPress; WordPress accepts traffic only from Traefik and from `woo-mcp`.

Every workload has readiness and liveness probes and resource requests and limits. Pods run as non-root; the gateway and dashboard also drop all Linux capabilities. Secrets (Gemini key, store passwords, WooCommerce keys) are Kubernetes Secrets created from values passed at install time.

## How the WooCommerce MCP server talks to the store

`woo-mcp/server.py` is a small FastMCP server (Streamable HTTP) that calls the **WooCommerce REST API v3** (`/wp-json/wc/v3`) with a consumer key and secret read from a Kubernetes Secret. It exposes `list_products`, `create_product`, `list_orders`, `get_order` and `update_order_status`.

Why REST: it is WooCommerce's supported, versioned interface, needs no extra plugin and no shell access to the WordPress pod, and the key can be scoped and revoked. WP-CLI would have required exec access or a shared filesystem with WordPress.

Two details specific to running inside the cluster:

- **Host header.** The MCP server reaches WordPress through the in-cluster Service (`wordpress.store.svc.cluster.local`), but WordPress is configured for the host `store.localhost`. Locally, `storeHostHeader: store.localhost` sends that Host header. In production the real domain is used and the override is empty.
- **HTTPS flag.** WooCommerce's key authentication requires HTTPS. `charts/store/files/rest-ssl.php` is a must-use plugin that marks only REST requests (`/wp-json/`) as HTTPS, so keys work over plain HTTP between pods. The tradeoff is that the key travels unencrypted inside the cluster; the NetworkPolicies limit who can reach WordPress.

## Local domains

`store.localhost` and `dashboard.localhost` are Ingress hosts served by the Traefik that ships with k3s. The k3d load balancer maps host port 80 to the cluster, and Traefik routes by Host header. Browsers resolve any `*.localhost` name to the local machine, so no hosts-file edits are needed.

## Local setup

Prerequisites: Docker, k3d, kubectl, Helm, and a Gemini API key from https://aistudio.google.com/apikey.

```powershell
# 1. Cluster (maps host port 80 to Traefik)
k3d cluster create urumi -p "80:80@loadbalancer"

# 2. Build and load the images
docker build -t gateway:0.2.5 .\gateway
docker build -t dashboard:0.1.2 .\dashboard
docker build -t woo-mcp:0.1.0 .\woo-mcp
docker build -t extra-mcp:0.1.0 .\extra-mcp
k3d image import gateway:0.2.5 dashboard:0.1.2 woo-mcp:0.1.0 extra-mcp:0.1.0 -c urumi

# 3. Store
helm install store .\charts\store -n store --create-namespace -f .\charts\store\values-local.yaml
```

Open http://store.localhost and finish the WordPress setup. Install and activate WooCommerce, enable **Cash on delivery** (WooCommerce, Settings, Payments), and create a REST API key (WooCommerce, Settings, Advanced, REST API, Read/Write). Then:

```powershell
# 4. MCP servers (use the real key and secret from step 3)
$ck = Read-Host "WooCommerce consumer key"
$cs = Read-Host "WooCommerce consumer secret"
helm install woo-mcp .\charts\woo-mcp -n mcp --create-namespace -f .\charts\woo-mcp\values-local.yaml --set-string wc.key=$ck --set-string wc.secret=$cs
helm install notes .\charts\mcp-server -n mcp --set script=notes_server.py
helm install utils .\charts\mcp-server -n mcp --set script=utils_server.py

# 5. Gateway and dashboard
$gk = Read-Host "Gemini API key"
helm install gateway .\charts\gateway -n mcp -f .\charts\gateway\values-local.yaml --set-string gemini.apiKey=$gk
helm install dashboard .\charts\dashboard -n mcp -f .\charts\dashboard\values-local.yaml

# 6. First admin key (printed once in the gateway log)
kubectl logs -n mcp deploy/gateway | findstr "urumi_"
```

Open http://dashboard.localhost, sign in with the admin key, and register the three servers (Servers page, Add a server):

| Name | URL |
|---|---|
| `woo` | `http://woo-mcp.mcp.svc.cluster.local:8000/mcp` |
| `notes` | `http://notes:8000/mcp` |
| `utils` | `http://utils:8000/mcp` |

## Production on a VPS (k3s)

The same charts are used. Only values change, through `values-prod.yaml` next to each `values.yaml`.

1. Install k3s (`curl -sfL https://get.k3s.io | sh -`). It includes Traefik and the `local-path` storage class.
2. Point DNS A records for the store (for example `shop.example.com`) and the dashboard (`dashboard.example.com`) at the VPS.
3. Push the images to a registry and set `image.repository` and `image.tag` in the prod values (replace `YOUR_USER`).
4. Edit the domains in `charts/store/values-prod.yaml`, `charts/woo-mcp/values-prod.yaml` and `charts/dashboard/values-prod.yaml`. Set the WordPress site address to the real domain in the store's settings.
5. Install with the prod files and pass every secret with `--set-string`:

```bash
helm install store ./charts/store -n store --create-namespace -f charts/store/values-prod.yaml \
  --set-string secrets.dbRootPassword=... --set-string secrets.dbPassword=...
helm install woo-mcp ./charts/woo-mcp -n mcp --create-namespace -f charts/woo-mcp/values-prod.yaml \
  --set-string wc.key=... --set-string wc.secret=...
helm install gateway ./charts/gateway -n mcp -f charts/gateway/values-prod.yaml --set-string gemini.apiKey=...
helm install dashboard ./charts/dashboard -n mcp -f charts/dashboard/values-prod.yaml
```

| Concern | Local | VPS |
|---|---|---|
| Domains | `*.localhost` | Real domains via DNS |
| Images | `k3d image import` | Registry |
| Storage | `local-path` | `local-path` or a named class, larger sizes |
| Secrets | `--set-string` | `--set-string`, from the deploy environment |
| WooCommerce URL for woo-mcp | In-cluster Service plus Host header | Real store URL |
| TLS | none | optional, with cert-manager (not included in these charts) |

## Using it

**Place an order.** Open http://store.localhost, add a product to the cart, check out with Cash on delivery, then open http://store.localhost/wp-admin, WooCommerce, Orders, to see it.

**Chat agent.** Open the Chat tab at http://dashboard.localhost, for example "What products do we sell?" or "What orders came in today?". The reply lists the tools it called. Calls run as the signed-in user and appear in the audit log under that user.

**Your own API key.** Click **My key**, then **Generate new key**. The key is shown once and the old one stops working at once. Admins create team members on the Members page and send them their first key.

**External MCP client** (Claude Code, Cursor, MCP Inspector). The only things needed are the gateway URL and a personal key:

```powershell
# MCP Inspector: transport "Streamable HTTP", URL below, header Authorization: Bearer <your key>
npx @modelcontextprotocol/inspector

# Claude Code
claude mcp add --transport http urumi http://dashboard.localhost/api/mcp --header "Authorization: Bearer <your key>"
```

The URL is `http://dashboard.localhost/api/mcp`: the dashboard's nginx forwards `/api/` to the gateway. Tools appear as `server__tool` (for example `woo__list_orders`).

## API summary

Authenticate every request with `Authorization: Bearer <api key>`.

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/health` | none | Liveness |
| GET | `/me` | any user | Who am I |
| POST | `/me/key` | any user | Issue yourself a new key; the old one stops working |
| GET, POST | `/users` | admin | List or create users |
| POST | `/users/{id}/revoke` | admin | Deactivate a user immediately |
| GET | `/servers` | any user | List servers (with `has_credential`) |
| POST | `/servers` | admin | Register a server |
| PATCH | `/servers/{id}` | admin | Edit name, URL or credential |
| POST | `/servers/{id}/enable`, `/disable` | admin | Turn a server on or off |
| DELETE | `/servers/{id}` | admin | Remove a server |
| GET | `/tools` | any user | Tools and health of each server |
| GET | `/audit` | admin | Recent tool calls |
| POST | `/chat` | any user | Chat agent |
| any | `/mcp` | any user | MCP endpoint |

Tool names are `<server>__<tool>`. Server names are lowercase letters and digits, so the first `__` always separates server from tool, and two servers can expose the same tool name.

## Gateway features

- **Server credentials.** One optional credential per server, sent as `Authorization: Bearer <credential>` on discovery and calls. It is write-only: the API shows only `has_credential`. Stored as plain text in SQLite (a documented limitation).
- **Revoke.** Immediate on both REST and `/mcp`. The last active admin cannot be revoked.
- **Failure handling.** Discovery has a 10 second timeout per server and calls 30 seconds. A dead or slow server is shown as Unreachable and does not affect the others.
- **Gemini retry.** Network errors, timeouts and HTTP 500, 502, 503, 504 are retried after 2 and 4 seconds, logging `gemini call failed (...), retrying in 2s`. Search with `kubectl logs -n mcp deploy/gateway | findstr "retrying"`.
- **Database upgrade.** The gateway adds missing columns at startup, so existing data is kept.

## Upgrading and rolling back

```powershell
docker build --no-cache -t gateway:0.2.5 .\gateway
k3d image import gateway:0.2.5 -c urumi
helm upgrade gateway .\charts\gateway -n mcp --reuse-values --set image.tag=0.2.5 --force-conflicts
kubectl rollout status deploy/gateway -n mcp

helm history gateway -n mcp
helm rollback gateway <revision> -n mcp
```

- Use a new image tag every time; a reused tag can leave the cluster on the old image.
- Always pass `--reuse-values`. Without it Helm resets `gemini.apiKey` and the store passwords.
- `--force-conflicts` is needed if the image was ever changed with `kubectl set image`.
- Restart any `kubectl port-forward` after a rollout.
- The gateway database is additive-only, so rolling the image back does not break it.

## Verifying NetworkPolicies

```powershell
# A random pod cannot reach an upstream or the store (connection refused)
kubectl run np-test -n mcp --rm -it --restart=Never --image=busybox:1.36 -- wget -qO- -T 3 http://woo-mcp:8000/mcp
kubectl run np-store -n mcp --rm -it --restart=Never --image=busybox:1.36 -- wget -qO- -T 3 http://wordpress.store.svc.cluster.local

# A pod carrying the gateway label gets through (HTTP 406 from the MCP server)
kubectl run np-ok -n mcp --labels=app=gateway --rm -it --restart=Never --image=busybox:1.36 -- wget -qO- -T 3 http://woo-mcp:8000/mcp
```

## Known limitations

- Upstream credentials are stored unencrypted.
- No per-tool permissions: every member can call every tool of every enabled server.
- No protection against an admin registering an internal URL (SSRF).
- No rate limits; one SQLite database and one gateway replica.
- The Gemini retry cannot be triggered on demand.

## Bonus and stand-out items

- **Multi-store provisioning bonus:** not attempted.
- **Security hardening (partial):** NetworkPolicies for upstreams, the gateway and the store; non-root pods; dropped capabilities; hashed API keys. Not done: SSRF protection, encryption of credentials at rest, RBAC for Kubernetes API clients.
- **Upgrades and rollback:** documented above, with the `--reuse-values` pitfalls.