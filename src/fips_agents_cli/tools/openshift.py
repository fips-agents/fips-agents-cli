"""OpenShift and Helm deployment utilities."""

from __future__ import annotations

import fnmatch
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

DEFAULT_BUILD_EXCLUDES = [
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".coverage",
    "htmlcov",
    ".env",
    "node_modules",
    ".DS_Store",
    ".benchmarks",
    ".cache_ggshield",
]


def is_oc_installed() -> bool:
    """Check if OpenShift CLI (oc) is installed."""
    try:
        result = subprocess.run(
            ["oc", "version", "--client"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def is_oc_authenticated(context: str | None = None) -> tuple[bool, str]:
    """Check if authenticated to OpenShift cluster."""
    cmd = ["oc", "whoami"]
    if context:
        cmd.extend(["--context", context])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            username = result.stdout.strip()
            return True, username
        else:
            error = result.stderr.strip() or "Not authenticated"
            return False, error

    except FileNotFoundError:
        return False, "OpenShift CLI (oc) not installed"
    except subprocess.TimeoutExpired:
        return False, "Authentication check timed out"


def is_helm_installed() -> bool:
    """Check if Helm CLI is installed."""
    try:
        result = subprocess.run(
            ["helm", "version", "--short"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def namespace_exists(namespace: str, context: str | None = None) -> bool:
    """Check if namespace exists in cluster."""
    cmd = ["oc", "get", "namespace", namespace]
    if context:
        cmd.extend(["--context", context])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def create_namespace(namespace: str, context: str | None = None) -> tuple[bool, str]:
    """Create a new OpenShift project/namespace."""
    cmd = ["oc", "new-project", namespace]
    if context:
        cmd.extend(["--context", context])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            return True, f"Namespace '{namespace}' created successfully"
        else:
            error = result.stderr.strip()
            if "already exists" in error.lower():
                return True, f"Namespace '{namespace}' already exists"
            return False, f"Failed to create namespace: {error}"

    except FileNotFoundError:
        return False, "OpenShift CLI (oc) not installed"
    except subprocess.TimeoutExpired:
        return False, "Namespace creation timed out"


def oc_apply_manifest(
    manifest_path: Path,
    namespace: str,
    oc_context: str | None = None,
) -> tuple[bool, str]:
    """Apply a Kubernetes/OpenShift manifest file."""
    cmd = ["oc", "apply", "-f", str(manifest_path), "-n", namespace]
    if oc_context:
        cmd.extend(["--context", oc_context])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            output = result.stdout.strip()
            return True, output
        else:
            error = result.stderr.strip()
            return False, f"Failed to apply manifest: {error}"

    except FileNotFoundError:
        return False, "OpenShift CLI (oc) not installed"
    except subprocess.TimeoutExpired:
        return False, "Manifest application timed out"


def parse_manifest_resource_names(manifest_path: Path) -> dict[str, str]:
    """Parse a multi-document YAML manifest and extract resource names by kind.

    Returns a dict mapping Kind to metadata.name, e.g.
    {"BuildConfig": "mcp-server", "Deployment": "mcp-server", "Route": "mcp-server"}.
    """
    yaml = YAML(typ="safe")
    result = {}
    try:
        with open(manifest_path) as f:
            for doc in yaml.load_all(f):
                if doc and isinstance(doc, dict):
                    kind = doc.get("kind")
                    name = doc.get("metadata", {}).get("name")
                    if kind and name:
                        result[kind] = name
    except Exception:
        pass
    return result


def oc_get_imagestream_registry_path(
    name: str,
    namespace: str,
    oc_context: str | None = None,
) -> tuple[bool, str]:
    """Resolve an ImageStream to its internal registry path."""
    cmd = [
        "oc",
        "get",
        "imagestream",
        name,
        "-n",
        namespace,
        "-o",
        "jsonpath={.status.dockerImageRepository}",
    ]
    if oc_context:
        cmd.extend(["--context", oc_context])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            repo = result.stdout.strip()
            if repo:
                return True, repo
            return True, f"image-registry.openshift-image-registry.svc:5000/{namespace}/{name}"
        else:
            return (
                False,
                f"ImageStream '{name}' not found in namespace '{namespace}'",
            )

    except FileNotFoundError:
        return False, "OpenShift CLI (oc) not installed"
    except subprocess.TimeoutExpired:
        return False, "ImageStream query timed out"


def create_build_context(
    project_root: Path, exclude_patterns: list[str] | None = None
) -> tuple[bool, str, Path | None]:
    """
    Create a build context directory with proper permissions.

    Copies project files to a temp directory, excluding patterns from
    .dockerignore or DEFAULT_BUILD_EXCLUDES, then fixes permissions on
    Python files for OpenShift's non-root containers.
    """
    try:
        # Read exclude patterns
        dockerignore = project_root / ".dockerignore"
        if dockerignore.exists():
            patterns = []
            with open(dockerignore) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        patterns.append(line)
        else:
            patterns = exclude_patterns or DEFAULT_BUILD_EXCLUDES

        # Create temp directory
        temp_dir = Path(tempfile.mkdtemp(prefix="fips-build-"))

        # Copy function with ignore patterns
        def ignore_patterns(directory: str, names: list[str]) -> set[str]:
            ignored = set()
            for name in names:
                for pattern in patterns:
                    if fnmatch.fnmatch(name, pattern):
                        ignored.add(name)
                        break
            return ignored

        # Copy project to temp directory
        shutil.copytree(
            project_root,
            temp_dir,
            ignore=ignore_patterns,
            dirs_exist_ok=True,
        )

        # Fix permissions on Python files
        for py_file in temp_dir.rglob("*.py"):
            py_file.chmod(0o644)

        return True, "Build context created successfully", temp_dir

    except Exception as e:
        return False, f"Failed to create build context: {str(e)}", None


def oc_start_build(
    build_name: str,
    context_dir: Path,
    namespace: str,
    oc_context: str | None = None,
    follow: bool = True,
) -> tuple[bool, str]:
    """Start an OpenShift build from directory."""
    cmd = [
        "oc",
        "start-build",
        build_name,
        f"--from-dir={context_dir}",
        "-n",
        namespace,
    ]
    if oc_context:
        cmd.extend(["--context", oc_context])
    if follow:
        cmd.append("--follow")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )

        if result.returncode == 0:
            output = result.stdout.strip()
            return True, output
        else:
            error = result.stderr.strip()
            return False, f"Build failed: {error}"

    except FileNotFoundError:
        return False, "OpenShift CLI (oc) not installed"
    except subprocess.TimeoutExpired:
        return False, "Build timed out after 600 seconds"


def oc_rollout_restart(
    deployment_name: str,
    namespace: str,
    oc_context: str | None = None,
) -> tuple[bool, str]:
    """Restart an OpenShift deployment."""
    cmd = ["oc", "rollout", "restart", f"deployment/{deployment_name}", "-n", namespace]
    if oc_context:
        cmd.extend(["--context", oc_context])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            output = result.stdout.strip()
            return True, output
        else:
            error = result.stderr.strip()
            return False, f"Rollout restart failed: {error}"

    except FileNotFoundError:
        return False, "OpenShift CLI (oc) not installed"
    except subprocess.TimeoutExpired:
        return False, "Rollout restart timed out"


def oc_set_image(
    deployment_name: str,
    container_name: str,
    image: str,
    namespace: str,
    oc_context: str | None = None,
) -> tuple[bool, str]:
    """Set the container image on a deployment, triggering a rollout."""
    cmd = [
        "oc",
        "set",
        "image",
        f"deployment/{deployment_name}",
        f"{container_name}={image}",
        "-n",
        namespace,
    ]
    if oc_context:
        cmd.extend(["--context", oc_context])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            output = result.stdout.strip()
            return True, output
        else:
            error = result.stderr.strip()
            return False, f"Failed to set image: {error}"

    except FileNotFoundError:
        return False, "OpenShift CLI (oc) not installed"
    except subprocess.TimeoutExpired:
        return False, "Set image timed out"


def oc_rollout_status(
    deployment_name: str,
    namespace: str,
    oc_context: str | None = None,
    timeout: int = 120,
) -> tuple[bool, str]:
    """Check rollout status of an OpenShift deployment."""
    cmd = [
        "oc",
        "rollout",
        "status",
        f"deployment/{deployment_name}",
        "-n",
        namespace,
        f"--timeout={timeout}s",
    ]
    if oc_context:
        cmd.extend(["--context", oc_context])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 10,
        )

        if result.returncode == 0:
            output = result.stdout.strip()
            return True, output
        else:
            error = result.stderr.strip()
            return False, f"Rollout status check failed: {error}"

    except FileNotFoundError:
        return False, "OpenShift CLI (oc) not installed"
    except subprocess.TimeoutExpired:
        return False, f"Rollout status check timed out after {timeout} seconds"


def oc_get_route_url(
    route_name: str,
    namespace: str,
    oc_context: str | None = None,
) -> tuple[bool, str]:
    """Get the URL for an OpenShift route."""
    cmd = [
        "oc",
        "get",
        "route",
        route_name,
        "-n",
        namespace,
        "-o",
        "jsonpath={.spec.host}",
    ]
    if oc_context:
        cmd.extend(["--context", oc_context])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            host = result.stdout.strip()
            if host:
                return True, f"https://{host}"
            else:
                return False, "Route host not found"
        else:
            error = result.stderr.strip()
            return False, f"Failed to get route URL: {error}"

    except FileNotFoundError:
        return False, "OpenShift CLI (oc) not installed"
    except subprocess.TimeoutExpired:
        return False, "Route query timed out"


def read_helm_values(chart_dir: Path) -> dict[str, Any] | None:
    """Read Helm values.yaml file."""
    values_file = chart_dir / "values.yaml"
    if not values_file.exists():
        return None

    try:
        yaml = YAML(typ="safe")
        with open(values_file) as f:
            return yaml.load(f)
    except Exception:
        return None


def helm_deploy(
    release_name: str,
    chart_dir: Path,
    namespace: str,
    values_file: Path | None = None,
    oc_context: str | None = None,
    set_values: list[str] | None = None,
) -> tuple[bool, str]:
    """Deploy or upgrade a Helm chart."""
    cmd = [
        "helm",
        "upgrade",
        "--install",
        release_name,
        str(chart_dir),
        "-n",
        namespace,
    ]
    if values_file:
        cmd.extend(["-f", str(values_file)])
    if oc_context:
        cmd.extend(["--kube-context", oc_context])
    for sv in set_values or []:
        cmd.extend(["--set", sv])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode == 0:
            output = result.stdout.strip()
            return True, output
        else:
            error = result.stderr.strip()
            return False, f"Helm deployment failed: {error}"

    except FileNotFoundError:
        return False, "Helm CLI not installed"
    except subprocess.TimeoutExpired:
        return False, "Helm deployment timed out after 300 seconds"


def is_mac_platform() -> bool:
    """Check if running on macOS."""
    return platform.system() == "Darwin"
