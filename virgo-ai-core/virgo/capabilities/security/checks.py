"""Conservative deterministic checks that report observations, not proof."""

import ast
import json
import re
import tomllib
from hashlib import sha256
from pathlib import Path

from virgo.contracts.models.security import (
    SecurityCategory,
    SecurityEvidence,
    SecurityFinding,
    SecurityRecommendation,
    SecuritySeverity,
)


def _finding(
    check: str,
    category: SecurityCategory,
    title: str,
    description: str,
    severity: SecuritySeverity,
    confidence: float,
    relative_path: str,
    evidence: str,
    recommendation: str,
    *,
    line_number: int | None = None,
    configuration_key: str | None = None,
) -> SecurityFinding:
    stable = sha256(f"{check}:{relative_path}:{title}".encode()).hexdigest()[:16]
    return SecurityFinding(
        finding_id=f"SEC-{stable}",
        category=category,
        title=title,
        description=description,
        severity=severity,
        confidence=confidence,
        affected_path=relative_path,
        evidence=(
            SecurityEvidence(
                summary=evidence,
                source_check_id=check,
                line_number=line_number,
                configuration_key=configuration_key,
            ),
        ),
        recommendation=SecurityRecommendation(summary=recommendation),
        source_check_id=check,
    )


class SecretCandidateCheck:
    check_id = "local.secret-candidate"
    category = SecurityCategory.SECRET_EXPOSURE
    description = (
        "Detect likely hard-coded credential assignments with redacted evidence."
    )
    _pattern = re.compile(
        r"(?im)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"]?([^\s'\"#]{8,})"
    )

    def execute(
        self, path: Path, relative_path: str, text: str
    ) -> tuple[SecurityFinding, ...]:
        findings = []
        for match in self._pattern.finditer(text):
            value = match.group(2)
            redacted = f"{value[:3]}...{value[-3:]}" if len(value) > 8 else "[REDACTED]"
            findings.append(
                _finding(
                    self.check_id,
                    self.category,
                    "Possible credential material in source",
                    "A secret-like assignment was observed; static matching cannot confirm validity.",
                    SecuritySeverity.HIGH,
                    0.78,
                    relative_path,
                    f"{match.group(1)} candidate: {redacted}",
                    "Remove valid credentials from source, rotate them, and use approved secret storage.",
                    line_number=text.count("\n", 0, match.start()) + 1,
                    configuration_key=match.group(1),
                )
            )
        return tuple(findings)


class DangerousCodeCheck:
    check_id = "local.dangerous-code"
    category = SecurityCategory.DANGEROUS_CODE
    description = "Detect explicit shell execution patterns."
    _pattern = re.compile(
        r"\b(?:subprocess\.(?:run|Popen|call)|os\.system)\s*\([^\n]{0,300}(?:shell\s*=\s*True|os\.system)"
    )

    def execute(
        self, path: Path, relative_path: str, text: str
    ) -> tuple[SecurityFinding, ...]:
        match = self._pattern.search(text)
        if match is None:
            return ()
        return (
            _finding(
                self.check_id,
                self.category,
                "Shell execution pattern observed",
                "Source appears to enable shell interpretation; input flow was not proven.",
                SecuritySeverity.MEDIUM,
                0.82,
                relative_path,
                "Observed a subprocess/os.system call with shell interpretation.",
                "Pass executable and arguments separately and validate any untrusted input.",
                line_number=text.count("\n", 0, match.start()) + 1,
            ),
        )


class DebugConfigurationCheck:
    check_id = "local.debug-configuration"
    category = SecurityCategory.INSECURE_CONFIGURATION
    description = "Detect explicit enabled debug settings."
    _pattern = re.compile(r"(?im)^\s*(?:DEBUG|debug)\s*[:=]\s*(?:true|1)\b")

    def execute(
        self, path: Path, relative_path: str, text: str
    ) -> tuple[SecurityFinding, ...]:
        match = self._pattern.search(text)
        if match is None:
            return ()
        return (
            _finding(
                self.check_id,
                self.category,
                "Debug mode appears enabled",
                "A deterministic debug=true-style setting was observed.",
                SecuritySeverity.LOW,
                0.88,
                relative_path,
                "Observed an enabled debug setting.",
                "Disable debug mode in production configuration.",
                line_number=text.count("\n", 0, match.start()) + 1,
                configuration_key="debug",
            ),
        )


class DynamicExecutionCheck:
    check_id = "local.dynamic-execution"
    category = SecurityCategory.DANGEROUS_CODE
    description = "Detect direct eval/exec calls in Python syntax trees."

    def execute(
        self, path: Path, relative_path: str, text: str
    ) -> tuple[SecurityFinding, ...]:
        if path.suffix.lower() != ".py":
            return ()
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return ()
        findings = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"eval", "exec"}
            ):
                findings.append(
                    _finding(
                        self.check_id,
                        self.category,
                        "Dynamic code execution observed",
                        f"A direct {node.func.id}() call was observed; input trust was not proven.",
                        SecuritySeverity.MEDIUM,
                        0.94,
                        relative_path,
                        f"Direct {node.func.id}() call in Python syntax.",
                        "Replace dynamic execution with explicit parsing or an allowlisted operation.",
                        line_number=node.lineno,
                    )
                )
        return tuple(findings)


class PythonRiskPatternCheck:
    check_id = "local.python-risk-patterns"
    category = SecurityCategory.DANGEROUS_CODE
    description = "Detect high-signal unsafe Python API constructions."

    def execute(
        self, path: Path, relative_path: str, text: str
    ) -> tuple[SecurityFinding, ...]:
        if path.suffix.lower() != ".py":
            return ()
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return ()
        findings = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node.func)
            if name in {"pickle.loads", "yaml.load"}:
                findings.append(
                    _finding(
                        self.check_id,
                        self.category,
                        "Risky deserialization API observed",
                        f"{name} was observed; the trust of serialized input was not established.",
                        SecuritySeverity.MEDIUM,
                        0.86,
                        relative_path,
                        f"Direct {name} call.",
                        "Use a safe data format and validate input before deserialization.",
                        line_number=node.lineno,
                    )
                )
            elif name == "tempfile.mktemp":
                findings.append(
                    _finding(
                        self.check_id,
                        self.category,
                        "Weak temporary-file API observed",
                        "tempfile.mktemp() has a race between name selection and file creation.",
                        SecuritySeverity.MEDIUM,
                        0.98,
                        relative_path,
                        "Direct tempfile.mktemp() call.",
                        "Use NamedTemporaryFile or mkstemp and retain the opened handle.",
                        line_number=node.lineno,
                    )
                )
            elif (
                name in {"open", "pathlib.Path"}
                and node.args
                and isinstance(node.args[0], ast.Name)
            ):
                findings.append(
                    _finding(
                        self.check_id,
                        self.category,
                        "Unvalidated-looking path input observed",
                        "A bare variable is passed to a filesystem path API; containment was not observed locally.",
                        SecuritySeverity.LOW,
                        0.68,
                        relative_path,
                        f"Filesystem API receives variable '{node.args[0].id}'.",
                        "Canonicalize and validate containment beneath the authorized root before access.",
                        line_number=node.lineno,
                    )
                )
            elif (
                name.endswith("execute")
                and node.args
                and isinstance(node.args[0], (ast.JoinedStr, ast.BinOp))
            ):
                findings.append(
                    _finding(
                        self.check_id,
                        self.category,
                        "Constructed SQL passed to execute",
                        "A formatted/concatenated expression is passed directly to an execute-like call.",
                        SecuritySeverity.MEDIUM,
                        0.84,
                        relative_path,
                        "execute-like call receives constructed SQL expression.",
                        "Use parameterized SQL with values supplied separately.",
                        line_number=node.lineno,
                    )
                )
        return tuple(findings)


class SecurityConfigurationCheck:
    check_id = "local.security-configuration"
    category = SecurityCategory.INSECURE_CONFIGURATION
    description = "Detect explicit security-sensitive unsafe configuration values."
    _patterns = (
        (
            re.compile(r"(?i)verify\s*=\s*False"),
            "TLS verification disabled",
            "verify",
            SecuritySeverity.HIGH,
            "Enable certificate verification and use an approved trust store.",
        ),
        (
            re.compile(r"(?im)^\s*(?:HOST|host)\s*[:=]\s*['\"]?0\.0\.0\.0"),
            "Wildcard host binding configured",
            "host",
            SecuritySeverity.MEDIUM,
            "Bind to loopback or an explicitly approved interface where remote exposure is unnecessary.",
        ),
        (
            re.compile(
                r"(?im)^\s*(?:SESSION_COOKIE_SECURE|cookie_secure)\s*[:=]\s*(?:false|0)"
            ),
            "Secure cookie flag disabled",
            "cookie_secure",
            SecuritySeverity.MEDIUM,
            "Enable secure cookies for HTTPS deployments.",
        ),
        (
            re.compile(
                r"(?im)^\s*(?:CORS_ALLOWED_ORIGINS|allowed_origins|origins)\s*[:=].*\*"
            ),
            "Wildcard origin trust configured",
            "allowed_origins",
            SecuritySeverity.MEDIUM,
            "Replace wildcard trust with the minimum explicit origin allowlist.",
        ),
        (
            re.compile(r"(?im)^\s*(?:permissions?|mode)\s*[:=]\s*['\"]?(?:777|0o777)"),
            "Broad file permission configured",
            "permissions",
            SecuritySeverity.HIGH,
            "Use least-privilege file permissions appropriate to the runtime identity.",
        ),
    )

    def execute(
        self, path: Path, relative_path: str, text: str
    ) -> tuple[SecurityFinding, ...]:
        findings = []
        for pattern, title, key, severity, recommendation in self._patterns:
            match = pattern.search(text)
            if match is None:
                continue
            findings.append(
                _finding(
                    self.check_id,
                    self.category,
                    title,
                    "An explicit security-sensitive configuration value was observed; runtime exposure was not tested.",
                    severity,
                    0.9,
                    relative_path,
                    f"Observed unsafe value for {key}.",
                    recommendation,
                    line_number=text.count("\n", 0, match.start()) + 1,
                    configuration_key=key,
                )
            )
        return tuple(findings)


class DependencyManifestCheck:
    check_id = "local.dependency-manifest"
    category = SecurityCategory.DEPENDENCY_CONFIGURATION
    description = "Inspect supported local manifests without vulnerability claims."

    def execute(
        self, path: Path, relative_path: str, text: str
    ) -> tuple[SecurityFinding, ...]:
        name = path.name.lower()
        try:
            if name == "package.json":
                return self._package_json(path, relative_path, text)
            if name == "pyproject.toml":
                return self._pyproject(path, relative_path, text)
            if name == "cargo.toml":
                return self._cargo(path, relative_path, text)
            if name.startswith("requirements") and path.suffix.lower() == ".txt":
                return self._requirements(relative_path, text)
        except (json.JSONDecodeError, tomllib.TOMLDecodeError, ValueError, TypeError):
            return (
                _finding(
                    self.check_id,
                    self.category,
                    "Malformed dependency manifest",
                    "The supported manifest could not be parsed deterministically.",
                    SecuritySeverity.LOW,
                    0.99,
                    relative_path,
                    "Local parser rejected the manifest.",
                    "Correct the manifest syntax before relying on dependency analysis.",
                ),
            )
        return ()

    def _package_json(
        self, path: Path, relative_path: str, text: str
    ) -> tuple[SecurityFinding, ...]:
        data = json.loads(text)
        findings = []
        scripts = data.get("scripts", {})
        if isinstance(scripts, dict) and any(
            key in scripts for key in ("preinstall", "postinstall")
        ):
            findings.append(
                _finding(
                    self.check_id,
                    self.category,
                    "Dependency install hook present",
                    "A package installation lifecycle hook can execute during dependency installation.",
                    SecuritySeverity.MEDIUM,
                    0.96,
                    relative_path,
                    "preinstall/postinstall script key present.",
                    "Review and minimize install hooks; never install dependencies from untrusted manifests.",
                    configuration_key="scripts",
                )
            )
        dependencies = data.get("dependencies", {})
        if isinstance(dependencies, dict) and any(
            str(value) in {"*", "latest"} or str(value).startswith(("git+", "http:"))
            for value in dependencies.values()
        ):
            findings.append(
                _finding(
                    self.check_id,
                    self.category,
                    "Unbounded or remote dependency source",
                    "A dependency uses a wildcard/latest version or direct remote source.",
                    SecuritySeverity.MEDIUM,
                    0.92,
                    relative_path,
                    "Dependency specification is unbounded or remote.",
                    "Use reviewed registry packages with intentional version constraints and a lockfile.",
                )
            )
        if (
            dependencies
            and not (path.parent / "package-lock.json").exists()
            and not (path.parent / "yarn.lock").exists()
            and not (path.parent / "pnpm-lock.yaml").exists()
        ):
            findings.append(
                _finding(
                    self.check_id,
                    self.category,
                    "Package lockfile not found",
                    "Dependencies are declared but no supported sibling lockfile was observed.",
                    SecuritySeverity.LOW,
                    0.9,
                    relative_path,
                    "No package-lock.json, yarn.lock, or pnpm-lock.yaml sibling.",
                    "Generate and review a lockfile using the approved package manager.",
                )
            )
        return tuple(findings)

    def _pyproject(
        self, path: Path, relative_path: str, text: str
    ) -> tuple[SecurityFinding, ...]:
        data = tomllib.loads(text)
        dependencies = (
            data.get("project", {}).get("dependencies", [])
            if isinstance(data.get("project", {}), dict)
            else []
        )
        if isinstance(dependencies, list) and any(
            isinstance(item, str)
            and not any(
                token in item for token in ("==", ">=", "<=", "~=", "<", ">", "@")
            )
            for item in dependencies
        ):
            return (
                _finding(
                    self.check_id,
                    self.category,
                    "Unconstrained Python dependency",
                    "A project dependency has no version or direct-source constraint.",
                    SecuritySeverity.LOW,
                    0.93,
                    relative_path,
                    "Dependency entry without a version constraint.",
                    "Add an intentional compatible constraint and use a reviewed reproducible lock workflow.",
                ),
            )
        return ()

    def _cargo(
        self, path: Path, relative_path: str, text: str
    ) -> tuple[SecurityFinding, ...]:
        data = tomllib.loads(text)
        dependencies = data.get("dependencies", {})
        findings = []
        if isinstance(dependencies, dict) and any(
            isinstance(value, dict) and ("git" in value or "path" in value)
            for value in dependencies.values()
        ):
            findings.append(
                _finding(
                    self.check_id,
                    self.category,
                    "Git or path Rust dependency",
                    "A Rust dependency resolves from a git or local path source.",
                    SecuritySeverity.LOW,
                    0.94,
                    relative_path,
                    "Dependency table contains a git/path source.",
                    "Review the exact source and revision and prefer a trusted registry release where appropriate.",
                )
            )
        if dependencies and not (path.parent / "Cargo.lock").exists():
            findings.append(
                _finding(
                    self.check_id,
                    self.category,
                    "Cargo lockfile not found",
                    "Dependencies are declared but no sibling Cargo.lock was observed.",
                    SecuritySeverity.INFO,
                    0.9,
                    relative_path,
                    "No sibling Cargo.lock file.",
                    "For applications, generate and review Cargo.lock for reproducible resolution.",
                )
            )
        return tuple(findings)

    def _requirements(
        self, relative_path: str, text: str
    ) -> tuple[SecurityFinding, ...]:
        entries = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if any(
            line.startswith(("git+", "http:"))
            or not any(
                token in line for token in ("==", ">=", "<=", "~=", "<", ">", "@")
            )
            for line in entries
        ):
            return (
                _finding(
                    self.check_id,
                    self.category,
                    "Unconstrained or remote requirements entry",
                    "A requirement has no version constraint or uses a direct remote source.",
                    SecuritySeverity.LOW,
                    0.9,
                    relative_path,
                    "Unconstrained/direct-source requirements entry.",
                    "Use reviewed sources and intentional version constraints.",
                ),
            )
        return ()


class SelectedLogSecurityCheck:
    check_id = "local.selected-log-security"
    category = SecurityCategory.LOG_SECURITY
    description = "Summarize repeated security events in explicitly selected logs."
    _indicators = (
        (
            re.compile(
                r"(?i)authentication (?:failed|failure)|invalid password|login failed"
            ),
            "Repeated authentication failures",
        ),
        (
            re.compile(r"(?i)permission denied|access denied"),
            "Repeated permission-denied events",
        ),
        (
            re.compile(r"(?i)blocked action|security violation"),
            "Repeated blocked security actions",
        ),
    )

    def execute(
        self, path: Path, relative_path: str, text: str
    ) -> tuple[SecurityFinding, ...]:
        if path.suffix.lower() != ".log":
            return ()
        findings = []
        for pattern, title in self._indicators:
            matches = tuple(pattern.finditer(text))
            if len(matches) < 3:
                continue
            findings.append(
                _finding(
                    self.check_id,
                    self.category,
                    title,
                    "The selected log contains a repeated deterministic security event pattern.",
                    SecuritySeverity.MEDIUM,
                    0.88,
                    relative_path,
                    f"Observed {len(matches)} matching events; log content omitted and secrets redacted.",
                    "Review the relevant local service and correlate with authorized identity and access records.",
                    line_number=text.count("\n", 0, matches[0].start()) + 1,
                )
            )
        return tuple(findings)


class MalwareIndicatorCheck:
    check_id = "local.malware-indicator"
    category = SecurityCategory.MALWARE_INDICATOR
    description = (
        "Detect harmless static potential indicators without execution or verdicts."
    )
    _patterns = (
        re.compile(r"(?i)CurrentVersion\\Run|schtasks\s+/create"),
        re.compile(r"(?is)base64\.b64decode.{0,200}\bexec\s*\("),
        re.compile(r"(?i)AppData[/\\](?:Roaming|Local)[/\\].*\.(?:ps1|vbs|bat)"),
    )

    def execute(
        self, path: Path, relative_path: str, text: str
    ) -> tuple[SecurityFinding, ...]:
        for pattern in self._patterns:
            match = pattern.search(text)
            if match is not None:
                digest = sha256(text.encode("utf-8")).hexdigest()
                return (
                    _finding(
                        self.check_id,
                        self.category,
                        "Potential malware-related indicator",
                        "A suspicious persistence/encoded-execution pattern was observed; this is not a malware verdict.",
                        SecuritySeverity.MEDIUM,
                        0.72,
                        relative_path,
                        f"POTENTIAL_INDICATOR; local SHA-256 {digest[:12]}...; content not executed.",
                        "Review the file in an isolated authorized workflow and validate its provenance.",
                        line_number=text.count("\n", 0, match.start()) + 1,
                    ),
                )
        return ()


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""
