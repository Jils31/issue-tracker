# Issue Tracker

[![ci-cd](https://github.com/Jils31/issue-tracker/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/Jils31/issue-tracker/actions/workflows/ci-cd.yml)

A small issue tracker and the full delivery pipeline around it. The app is a React front end,
a FastAPI back end and PostgreSQL. It runs locally with Docker Compose, gets built, tested and
scanned in GitHub Actions, is published to GHCR, and deploys to Kubernetes with Helm. Terraform
provisions the AWS network and EKS cluster. Prometheus and Grafana watch it, Argo CD keeps the
cluster in sync with this repo.

```
git push ──> GitHub Actions ──> pytest, vite build
                               docker build backend + frontend
                               trivy (fail on HIGH/CRITICAL)
                               push ghcr.io/<owner>/issue-tracker/{backend,frontend}:<sha>
                               helm upgrade --install on kind, smoke test

browser ──> Ingress ──┬── /      frontend (nginx, React bundle)
                      └── /api   backend  (FastAPI) ──> postgres (StatefulSet + PVC)
                                    │
                             Prometheus ──> Grafana
```

## Layout

```
backend/          FastAPI app, SQLAlchemy models, Alembic migrations, pytest suite, Dockerfile
frontend/         React + Vite source, nginx config, Dockerfile
docker-compose.yml
helm/issue-tracker/   chart: postgres, backend, frontend, ingress, hpa, configmap, secret
k8s/              namespace and the Argo CD Application
terraform/        VPC + EKS (terraform-aws-modules)
monitoring/       Prometheus and Grafana manifests with a provisioned dashboard
troubleshooting/  two planted faults used for the troubleshooting drill
scripts/          load generator
docs/             screenshots
```

## Run it locally

```bash
cp .env.example .env
docker compose up -d --build
open http://localhost:3000
curl localhost:8000/api/issues/stats
```

Ports 3000, 8000 and 5432 are taken on some machines; set `FRONTEND_PORT` and `BACKEND_PORT`
in `.env` if so. Postgres is not published to the host.

Without Docker, for development:

```bash
docker run -d --name pg -e POSTGRES_DB=tracker -e POSTGRES_USER=tracker -e POSTGRES_PASSWORD=tracker -p 5432:5432 postgres:16-alpine
cd backend && python3.12 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
cd ../frontend && npm ci && npm run dev
```

## API

| Method | Path | |
|---|---|---|
| GET | `/health` | process is up |
| GET | `/ready` | database answers |
| GET | `/metrics` | Prometheus exposition |
| GET | `/api/issues` | list, optional `?status_=open` |
| POST | `/api/issues` | create, returns 201 |
| GET | `/api/issues/{id}` | |
| PUT | `/api/issues/{id}` | partial update |
| DELETE | `/api/issues/{id}` | 204 |
| GET | `/api/issues/stats` | counts by status and priority |
| GET | `/docs` | OpenAPI UI |

Priority is one of `low`, `medium`, `high`; status is `open`, `in_progress`, `done`. Anything
else is a 422.

## Tests

```bash
cd backend && python -m pytest -v
```

Eight tests. They run against a throwaway SQLite file through a dependency override, so no
database is needed and they finish in well under a second. CI runs the same command.

## Images

Both Dockerfiles are multi-stage and run as a fixed non-root UID. The backend installs
dependencies in one stage and copies only the result; `entrypoint.sh` runs `alembic upgrade
head` and then uvicorn, so a fresh database is migrated on first start. The frontend builds the
Vite bundle with Node and serves it from `nginx-unprivileged`, with nginx proxying `/api`,
`/health`, `/ready`, `/docs` and `/metrics` to the backend so the browser talks to one origin.

Both images get `apk upgrade` or `apt-get upgrade` in the final stage. The first CI runs
failed in Trivy on exactly that: the stock Alpine base carried fixable OpenSSL CVEs, and the
pinned FastAPI pulled in a Starlette with three HIGH findings. The fixes were base-image
updates and a FastAPI/Starlette bump; the images now scan clean for fixable HIGH and CRITICAL.

## CI/CD

`.github/workflows/ci-cd.yml` runs on every push to `main` and on pull requests.

1. `test` and `frontend` in parallel: pytest with a JUnit artifact, `vite build` with the bundle as an artifact.
2. `images`, a matrix over backend and frontend: build, Trivy with `severity: HIGH,CRITICAL`,
   `ignore-unfixed: true`, `exit-code: 1`, a JSON report artifact, then push to GHCR tagged with
   the 7-character commit SHA. Pull requests stop before the push.
3. `deploy`: a kind cluster in the runner, a pull secret from `GITHUB_TOKEN`, `helm upgrade
   --install` with the tag just pushed, then a curl from inside the cluster through the
   frontend Service: `/ready`, create an issue, `/stats`, and `/metrics` must show the counter.

Only `GITHUB_TOKEN` is used. Nothing long-lived is stored in the repository or its secrets.

## Kubernetes and Helm

```bash
kubectl apply -f k8s/namespace.yaml
helm upgrade --install tracker helm/issue-tracker \
  --set image.backend=ghcr.io/<owner>/issue-tracker/backend \
  --set image.frontend=ghcr.io/<owner>/issue-tracker/frontend \
  --set image.tag=<sha> --set image.pullPolicy=IfNotPresent --set image.pullSecret=ghcr
kubectl -n issue-tracker get pods,svc,ingress,hpa,pvc
helm list -n issue-tracker
```

The chart's defaults assume Minikube with images built straight into the node
(`minikube image build`, `pullPolicy: Never`). `values-dev.yaml` drops to single replicas with
no HPA; `values-prod.yaml` raises replicas, uses `IfNotPresent`, and expects the database
Secret to exist already (`postgres.existingSecret`) instead of rendering one.

What is in the chart: a postgres StatefulSet with a `volumeClaimTemplate` and `pg_isready`
probes; a backend Deployment with startup, readiness and liveness probes, `runAsNonRoot`,
dropped capabilities, resource limits, Prometheus scrape annotations and a config checksum so
ConfigMap changes roll the Pods; a frontend Deployment with nginx config from a ConfigMap; an
Ingress sending `/api` to the backend and `/` to the frontend; an HPA on backend CPU.

Add `<ingress ip> tracker.local` to `/etc/hosts` to open it in a browser. On Minikube with the
Docker driver, use `minikube service ingress-nginx-controller -n ingress-nginx --url` and send
`Host: tracker.local`.

## Terraform

`terraform/` creates a VPC with two public and two private subnets across two availability
zones, one NAT gateway, and an EKS cluster with a managed node group in the private subnets.
It uses `terraform-aws-modules/vpc` and `terraform-aws-modules/eks`.

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
terraform apply
aws eks update-kubeconfig --region ap-south-1 --name issue-tracker-dev
terraform destroy
```

Credentials come from the environment or an AWS CLI profile, never from a file in this repo.
The cluster and NAT gateway cost money by the hour; destroy when done. On EKS, install
ingress-nginx and metrics-server first, then run the same `helm upgrade --install` as above.

## Monitoring

`monitoring/prometheus.yaml` runs Prometheus in the app namespace with RBAC to list Pods and a
`kubernetes_sd_configs` job that keeps Pods annotated `prometheus.io/scrape: "true"`. The chart
puts those annotations on the backend, so Pods added by the HPA are scraped automatically. Two
rules: `BackendHighErrorRate` and `BackendDown`.

`monitoring/grafana.yaml` provisions the datasource and an Issue Tracker dashboard: requests
per second by route, p95 latency, issues created, error rate, backend Pods scraped.

```bash
kubectl apply -f monitoring/
kubectl -n issue-tracker port-forward svc/prometheus 9090:9090
kubectl -n issue-tracker port-forward svc/grafana 3000:3000
./scripts/load-test.sh http://<ingress> tracker.local 120
```

The backend's `/metrics` comes from `prometheus_client`: a request counter by method, route
template and status, a latency histogram, an in-flight gauge and an issues-created counter.

## GitOps

`k8s/argocd-application.yaml` points Argo CD at `helm/issue-tracker` on `main` with automated
sync, prune and self-heal. Replica drift on the backend Deployment is ignored because the HPA
owns that number. Change `values.yaml`, push, and the cluster follows.

## Troubleshooting drill

`troubleshooting/` holds two faults to apply against a running release:

- `fault-1-wrong-db-host.yaml`, a values override that points the backend at a database host
  that does not exist. The rollout stalls with the new Pod `0/1`; the old Pods keep serving.
  `kubectl logs` on the new Pod shows the name-resolution error, `kubectl get configmap` shows
  the bad value. `helm rollback tracker` fixes it.
- `fault-2-ingress-wrong-service.yaml`, an Ingress whose `/api` path names a Service that does
  not exist. The UI loads, every API call returns 503. `kubectl describe ingress` shows
  `services "tracker-backend-v2" not found`; the backend answers fine from inside the cluster.
  Re-rendering the chart's Ingress fixes it.

Both follow the same order: status, events, logs, then the path between components.

## Screenshots

See [docs/](docs/).
