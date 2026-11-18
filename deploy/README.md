# Deployment

The frontend runs in OpenShift; the backend, PocketBase and embedded LanceDB
run on a DGX Spark. The browser reaches the frontend over HTTPS. Nginx forwards
`/api/` through a Tailscale userspace client in the frontend container to Tailscale Serve on the
Spark, which forwards to FastAPI on host loopback. PocketBase shares the
backend's network namespace and listens only on loopback. LanceDB is a local
directory in the backend container, not a separate server.

These manifests are starting points and require the substitutions below. Run
Docker build commands from the repository root. The Spark requires an ARM64
NVIDIA driver and NVIDIA Container Toolkit configured for Docker; the locked
CUDA/PyTorch binaries and model must also support its hardware. This configuration
has not itself established compatibility with a particular Spark installation.
Use one backend worker and one Spark stack: the local databases and inference
runtime are not configured for multiple independent replicas.

## Spark

1. Install Docker Compose with GPU support, Tailscale, and join the tailnet.
   Enable HTTPS certificates and MagicDNS for the tailnet. Ensure the required
   model licenses have been accepted on Hugging Face.
2. Copy `deploy/spark/.env.example` to a private location outside the checkout,
   for example `/etc/event-analytics.env`. Set `MODEL_ID`, the exact public
   `AUTH_ALLOWED_ORIGINS`, and any required `HF_TOKEN` and `GEOAPIFY_API_KEY`.
   Protect this file; do not commit it. See `backend/README.md` for model,
   authentication, optional workflow, and memory settings. The deployment defaults
   to Transformers with the Google BF16 Gemma checkpoint; the existing CUDA
   dependency profile also installs vLLM, but Transformers does not load it.
   Additional backend
   environment settings can be added to the Compose service as needed.
3. From the repository root, build and start:

   ```sh
   docker compose --env-file /etc/event-analytics.env -f deploy/spark/compose.yaml up -d --build
   ```

   The first startup downloads and loads models and may take considerable time.
   Check `docker compose --env-file /etc/event-analytics.env -f deploy/spark/compose.yaml logs -f`.
4. Configure host Tailscale Serve to forward HTTPS port 443 to
   `http://127.0.0.1:8000`, for example:

   ```sh
   sudo tailscale serve --bg --https=443 http://127.0.0.1:8000
   tailscale serve status
   ```

   Serve is a host-level configuration, not a Compose service. Limit tailnet
   access to this port to the frontend's Tailscale identity using the
   tailnet policy. Do not expose PocketBase. Docker publishes FastAPI only on
   host loopback. Tailscale encrypts the connection between devices; Serve
   terminates HTTPS on the Spark and forwards locally to FastAPI.

Named volumes persist PocketBase records, LanceDB vectors, and model downloads
across container replacement. Back up PocketBase and LanceDB together while
the services are stopped or using a consistent backup procedure; the model
cache can be downloaded again. `docker compose down -v` deletes these volumes.
PocketBase migrations run at startup. After recreating the backend container,
recreate PocketBase too (`docker compose ... up -d --force-recreate pocketbase`)
so its shared network namespace follows the backend.

## OpenShift frontend

The frontend image runs Nginx and Tailscale in one container. Tailscale uses
userspace networking; a local TCP bridge passes Nginx's TLS connections through
its HTTP CONNECT proxy without terminating TLS. No Tailscale Operator or TUN
device is required. `SPARK_TAILSCALE_HOST` in the Deployment must match both
the `Host` and `proxy_ssl_name` values in Nginx and the Spark certificate name.
The Spark and the frontend identity must belong to the intended tailnet and
its policy must allow the frontend identity to reach the Spark on port 443.

1. Set the Spark's exact MagicDNS name in `nginx.conf` and `kubernetes.yaml`.
   Nginx uses that name for TLS SNI and certificate verification.
2. Build and push the frontend image from the repository root:

   ```sh
   docker build -f deploy/frontend/Dockerfile -t REGISTRY/event-frontend:TAG .
   docker push REGISTRY/event-frontend:TAG
   ```

3. In `kubernetes.yaml`, replace the Deployment image with the pushed image and
   the Route `spec.host` with the public hostname. Configure DNS to point to
   the OpenShift router. The Route uses edge TLS and the same `tls-acme`
   annotation as the example deployment; confirm your cluster has an ACME
   integration configured for that annotation and hostname, or arrange a
   certificate using your cluster's supported Route certificate process. The
   annotation alone does not provision a certificate. With no custom
   certificate, the router's default certificate must be valid for the host.
   The Route's `1h` timeout is an inactivity timeout for long inference streams;
   adjust it to your router's policy and expected inference time.

   If the cluster cannot already pull the private image, add an
   `imagePullSecrets` entry under the Deployment's pod `spec`, referencing a
   registry pull secret in the same namespace. Follow your cluster's approved
   secret provisioning process; do not commit registry credentials.

   Create the `event-tailscale-auth` Secret in the same namespace, with a key
   named `authkey` containing a Tailscale auth key authorized to register the
   frontend in the correct tailnet. Use the cluster's approved secret manager
   or create it from a protected local file, for example:

   ```sh
   oc -n NAMESPACE create secret generic event-tailscale-auth --from-file=authkey=/secure/path/to/authkey
   ```

   Do not commit the key, put it in the image, or pass it on the command line.
   The key for registering the Spark itself may be single-use or already used;
   the frontend needs a valid key for its own registration. The `emptyDir`
   state persists across container restarts in the same Pod but not replacement
   Pods. Use a suitably scoped reusable key valid for future Pod replacements,
   manage its expiry and rotation, and consider an ephemeral key to clean up old
   nodes. Provision an application identity and policy appropriate to your
   tailnet; the auth key grants the ability to register nodes.

   Set the same public HTTPS origin in the Spark environment file. Apply the
   file in the intended namespace:

   ```sh
   kubectl -n NAMESPACE apply -f deploy/frontend/kubernetes.yaml
   kubectl -n NAMESPACE rollout status deployment/event-frontend
   ```

The frontend starts only after Tailscale authenticates. The HTTP readiness
probe checks Nginx, not end-to-end connectivity to the Spark; verify that
separately. After changing the auth Secret, restart or replace the Pod as
appropriate. On an existing deployment, the old operator-created Service may
remain until removed separately; it is no longer used by the frontend.

Ensure the OpenShift router and any intervening proxies do not buffer or cache
streaming responses. Nginx disables buffering and automatic upstream retries.
Check that the public HTTPS
route can log in and that stream events arrive incrementally. The Spark API is
not intended to be directly exposed to browsers. Nginx forwards cookies and
Origin by default; FastAPI checks the configured public origin.

If the Spark's MagicDNS name changes, update the Deployment and Nginx references and rebuild the
frontend image. Proxy pods or tailnet connectivity failures can interrupt an
active stream; the application does not automatically retry analysis requests.
