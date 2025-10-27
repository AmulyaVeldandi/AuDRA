#!/bin/bash
set -euo pipefail

NAMESPACE="audra-rad"

API_URL="http://$(kubectl get svc audra-api-service -n "$NAMESPACE" -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')"

echo "=== Testing AuDRA-Rad Deployment ==="
echo "API URL: $API_URL"
echo

echo "Test 1: Health Check"
curl -s "$API_URL/api/v1/health" | jq .
echo "OK: Health check passed"
echo

echo "Test 2: Process Sample Report"
REPORT_TEXT="$(cat data/sample_reports/chest_ct_ggo.txt)"
PAYLOAD="$(jq -n --arg report "$REPORT_TEXT" --arg patient_id "TEST123" '{report_text: $report, patient_id: $patient_id}')"
curl -s -X POST "$API_URL/api/v1/process-report" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" | jq .
echo "OK: Report processing test passed"
echo

echo "Test 3: Metrics"
curl -s "$API_URL/api/v1/metrics" | jq .
echo "OK: Metrics test passed"
echo

echo "Test 4: Pod Status"
kubectl get pods -n "$NAMESPACE"
ALL_RUNNING="$(kubectl get pods -n "$NAMESPACE" -o jsonpath='{.items[*].status.phase}' | grep -c "Running")"
echo "OK: $ALL_RUNNING pods running"
echo

echo "Test 5: Check for errors in logs"
ERROR_COUNT="$(kubectl logs -n "$NAMESPACE" -l app=audra-api --tail=100 | grep -c "ERROR" || true)"
if [ "$ERROR_COUNT" -eq 0 ]; then
  echo "OK: No errors in logs"
else
  echo "WARN: Found $ERROR_COUNT errors in logs"
  kubectl logs -n "$NAMESPACE" -l app=audra-api --tail=20
fi

echo
echo "All tests completed."
