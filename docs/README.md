# Screenshots

| File | What it shows |
|---|---|
| `pytest.png` | the test suite passing |
| `compose-up-and-smoke.png` | `docker compose up -d --build`, then `/ready`, create, stats, and the page through nginx |
| `app-compose.png` | the UI served by the compose stack |
| `terraform-plan.png` | `terraform plan` for the VPC and EKS cluster, 57 resources |
| `helm-deploy.png` | `helm upgrade --install` on Minikube, pods, services, ingress, hpa, pvc |
| `verify-through-ingress.png` | requests through the Ingress, `/metrics`, and the postgres Pod replaced with data intact |
| `app-on-kubernetes.png` | the UI through the Ingress |
| `monitoring-and-hpa.png` | Prometheus targets, PromQL answers, the HPA scaling under load |
| `prometheus-targets.png` | the targets page with all backend Pods up |
| `grafana-dashboard.png` | the provisioned dashboard with live panels |
| `argocd-gitops.png` | Argo CD adopting the release and syncing a replica change from a commit |
| `fault-1.png`, `fault-2.png` | the troubleshooting drill |
