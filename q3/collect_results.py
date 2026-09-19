import argparse
import json
import re
import sys

from kubernetes import client, config

RESULT_RE = re.compile(r"RESULT_JSON\s+(\{.*\})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", default="signup-validation")
    parser.add_argument("--namespace", default="default")
    args = parser.parse_args()

    config.load_kube_config()
    v1 = client.CoreV1Api()

    pods = v1.list_namespaced_pod(
        namespace=args.namespace, label_selector=f"job-name={args.job}"
    )
    if not pods.items:
        print(f"no pods found for job '{args.job}'", file=sys.stderr)
        sys.exit(1)

    results = []
    for pod in pods.items:
        name = pod.metadata.name
        try:
            logs = v1.read_namespaced_pod_log(name=name, namespace=args.namespace)
        except client.exceptions.ApiException as exc:
            print(f"could not read logs for {name}: {exc.reason}", file=sys.stderr)
            continue
        match = RESULT_RE.search(logs)
        if match:
            results.append(json.loads(match.group(1)))

    results.sort(key=lambda r: r["shard"])

    print(f"{'SHARD':<7}{'TOTAL':<8}{'INVALID':<10}{'NODE':<22}POD")
    for r in results:
        print(f"{r['shard']:<7}{r['total_rows']:<8}{r['invalid_rows']:<10}{r['node']:<22}{r['pod']}")
    print(f"\nshards={len(results)}  invalid_total={sum(r['invalid_rows'] for r in results)}")


if __name__ == "__main__":
    main()
