from __future__ import annotations

import json
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import quote, urlencode


DOCKER_SOCKET = "/var/run/docker.sock"
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 9104
SOCKET_TIMEOUT_SECONDS = 3
COMPOSE_PROJECT = "omnicall"
STATS_WORKERS = 16


def docker_get(path: str) -> Any:
    request = (
        f"GET {path} HTTP/1.1\r\n"
        "Host: docker\r\n"
        "User-Agent: omnicall-docker-exporter\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("utf-8")

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(SOCKET_TIMEOUT_SECONDS)
        client.connect(DOCKER_SOCKET)
        client.sendall(request)
        chunks: list[bytes] = []
        while True:
            try:
                chunk = client.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            chunks.append(chunk)

    raw = b"".join(chunks)
    header, _, body = raw.partition(b"\r\n\r\n")
    status_line = header.splitlines()[0].decode("utf-8", errors="replace")
    if " 200 " not in status_line:
        raise RuntimeError(status_line)
    if b"transfer-encoding: chunked" in header.lower():
        body = decode_chunked(body)
    return json.loads(body.decode("utf-8"))


def decode_chunked(body: bytes) -> bytes:
    decoded = bytearray()
    index = 0
    while index < len(body):
        line_end = body.find(b"\r\n", index)
        if line_end < 0:
            break
        size_text = body[index:line_end].split(b";", 1)[0]
        size = int(size_text, 16)
        index = line_end + 2
        if size == 0:
            break
        decoded.extend(body[index : index + size])
        index += size + 2
    return bytes(decoded)


def label_value(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def labels(values: dict[str, Any]) -> str:
    pairs = [f'{key}="{label_value(value)}"' for key, value in values.items()]
    return "{" + ",".join(pairs) + "}"


def metric_line(name: str, metric_labels: dict[str, Any], value: int | float) -> str:
    return f"{name}{labels(metric_labels)} {value}"


def container_labels(container: dict[str, Any]) -> dict[str, str]:
    docker_labels = container.get("Labels") or {}
    names = container.get("Names") or []
    container_name = names[0].lstrip("/") if names else container.get("Id", "")[:12]
    return {
        "container_id": container.get("Id", "")[:12],
        "container_name": container_name,
        "compose_project": docker_labels.get("com.docker.compose.project", ""),
        "compose_service": docker_labels.get("com.docker.compose.service", ""),
        "image": container.get("Image", ""),
    }


def cpu_cores(stats: dict[str, Any]) -> float:
    cpu_stats = stats.get("cpu_stats") or {}
    previous = stats.get("precpu_stats") or {}
    cpu_delta = (
        (cpu_stats.get("cpu_usage") or {}).get("total_usage", 0)
        - (previous.get("cpu_usage") or {}).get("total_usage", 0)
    )
    system_delta = cpu_stats.get("system_cpu_usage", 0) - previous.get("system_cpu_usage", 0)
    online_cpus = cpu_stats.get("online_cpus") or len(
        (cpu_stats.get("cpu_usage") or {}).get("percpu_usage") or []
    )
    if cpu_delta <= 0 or system_delta <= 0 or online_cpus <= 0:
        return 0.0
    return (cpu_delta / system_delta) * online_cpus


def memory_values(stats: dict[str, Any]) -> tuple[int, int]:
    memory = stats.get("memory_stats") or {}
    usage = int(memory.get("usage") or 0)
    stats_map = memory.get("stats") or {}
    cache = int(stats_map.get("cache") or stats_map.get("inactive_file") or 0)
    return max(0, usage - cache), usage


def collect_metrics() -> str:
    lines = [
        "# HELP omnicall_docker_exporter_scrape_error 1 when Docker stats collection fails.",
        "# TYPE omnicall_docker_exporter_scrape_error gauge",
        "# HELP omnicall_docker_container_up 1 when a Docker container is running.",
        "# TYPE omnicall_docker_container_up gauge",
        "# HELP omnicall_docker_container_cpu_cores Docker container CPU usage in cores.",
        "# TYPE omnicall_docker_container_cpu_cores gauge",
        "# HELP omnicall_docker_container_memory_working_set_bytes Docker container memory working set.",
        "# TYPE omnicall_docker_container_memory_working_set_bytes gauge",
        "# HELP omnicall_docker_container_memory_usage_bytes Docker container memory usage.",
        "# TYPE omnicall_docker_container_memory_usage_bytes gauge",
    ]

    try:
        filters = urlencode(
            {"filters": json.dumps({"label": [f"com.docker.compose.project={COMPOSE_PROJECT}"]})}
        )
        containers = docker_get(f"/containers/json?{filters}")
        lines.append("omnicall_docker_exporter_scrape_error 0")
        with ThreadPoolExecutor(max_workers=STATS_WORKERS) as executor:
            future_map = {
                executor.submit(container_metric_lines, container): container
                for container in containers
            }
            for future in as_completed(future_map):
                try:
                    lines.extend(future.result())
                except Exception as exc:
                    metric_labels = container_labels(future_map[future])
                    lines.append(metric_line("omnicall_docker_container_up", metric_labels, 0))
                    lines.append(f'# container_scrape_error="{label_value(exc)}"')
    except Exception as exc:
        lines.append("omnicall_docker_exporter_scrape_error 1")
        lines.append(f'# scrape_error="{label_value(exc)}"')

    lines.append("")
    return "\n".join(lines)


def container_metric_lines(container: dict[str, Any]) -> list[str]:
    metric_labels = container_labels(container)
    lines = [metric_line("omnicall_docker_container_up", metric_labels, 1)]
    container_id = quote(container.get("Id", ""), safe="")
    stats = docker_get(f"/containers/{container_id}/stats?stream=false")
    working_set, usage = memory_values(stats)
    lines.append(metric_line("omnicall_docker_container_cpu_cores", metric_labels, cpu_cores(stats)))
    lines.append(
        metric_line(
            "omnicall_docker_container_memory_working_set_bytes",
            metric_labels,
            working_set,
        )
    )
    lines.append(metric_line("omnicall_docker_container_memory_usage_bytes", metric_labels, usage))
    return lines


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok\n")
            return
        if self.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            return

        started_at = time.monotonic()
        body = collect_metrics()
        elapsed = time.monotonic() - started_at
        body += f"omnicall_docker_exporter_scrape_duration_seconds {elapsed}\n"
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), MetricsHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
