# Troubleshooting drill

Apply one fault at a time against a running release, diagnose it with kubectl before
changing anything, then fix it.

## Fault 1: wrong database host

```bash
helm upgrade tracker helm/issue-tracker -f troubleshooting/fault-1-wrong-db-host.yaml --wait --timeout 90s
kubectl -n issue-tracker get pods -l app.kubernetes.io/name=backend
kubectl -n issue-tracker logs <new pod>
kubectl -n issue-tracker get configmap tracker-config -o jsonpath='{.data.POSTGRES_HOST}'
kubectl -n issue-tracker get svc | grep postgres
helm rollback tracker
```

Expected: the upgrade times out, one new Pod stays `0/1` with a readiness 503, the two old Pods
keep serving. The log says `failed to resolve host 'tracker-postgres-typo'`. The Service is
called `tracker-postgres`. Rollback restores revision 1.

## Fault 2: Ingress to a missing Service

```bash
kubectl apply -f troubleshooting/fault-2-ingress-wrong-service.yaml
curl -H 'Host: tracker.local' http://<ingress>/api/issues/stats
kubectl -n issue-tracker describe ingress tracker
kubectl -n issue-tracker run tmp --rm -i --restart=Never --image=curlimages/curl -- curl -s http://tracker-backend/api/issues/stats
helm template tracker helm/issue-tracker --show-only templates/ingress.yaml | kubectl apply -f -
```

Expected: 503 from the Ingress, `describe` shows `services "tracker-backend-v2" not found`,
the backend Service answers from inside the cluster. Re-rendering the Ingress fixes it.
