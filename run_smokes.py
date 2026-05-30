#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import hashlib
import io
import json
import os
import pty
import re
import select
import shutil
import socket
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent


def resolve_rust_client_root() -> Path:
    configured = os.environ.get("LPM_SMOKE_RUST_CLIENT_ROOT")
    if not configured:
        return ROOT.parent / "rust-client"
    configured_path = Path(configured).expanduser()
    if configured_path.is_absolute():
        return configured_path.resolve()
    return (Path.cwd() / configured_path).resolve()


RUST_CLIENT_ROOT = resolve_rust_client_root()
LPM_MANIFEST = RUST_CLIENT_ROOT / "Cargo.toml"
WORKSPACE_TARGETING_FIXTURE = ROOT / "workspace" / "targeting"


def resolve_cargo_target_dir() -> Path:
    configured = os.environ.get("CARGO_TARGET_DIR")
    if not configured:
        return RUST_CLIENT_ROOT / "target"
    target_dir = Path(configured)
    if target_dir.is_absolute():
        return target_dir
    return (RUST_CLIENT_ROOT / target_dir).resolve()


LPM_TARGET_DIR = resolve_cargo_target_dir()
LPM_BIN = LPM_TARGET_DIR / "debug" / "lpm-rs"

DEFAULT_ENV = {
    "NO_COLOR": "1",
    "FORCE_COLOR": "0",
    "CLICOLOR": "0",
}

REAL_HOME = os.environ.get("HOME")
REAL_CARGO_HOME = os.environ.get("CARGO_HOME")
REAL_RUSTUP_HOME = os.environ.get("RUSTUP_HOME")

NATIVE_SECURITY_UNLOCK_ENV = "LPM_SMOKE_NATIVE_SECURITY_UNLOCK"

CONFIG_AWARE_BASELINE_PACKAGE_JSON = """{
  \"name\": \"config-aware-smoke\",
  \"private\": true,
  \"version\": \"0.0.0\"
}
"""

CONFIG_AWARE_BASELINE_TSCONFIG = """{
  \"compilerOptions\": {
    \"baseUrl\": \".\",
    \"paths\": {
      \"@/*\": [\"./*\"]
    }
  }
}
"""

PROJECT_DISCOVERY_NEAREST_BASELINE_PACKAGE_JSON = """{
    \"name\": \"project-discovery-nearest-ancestor\",
    \"private\": true,
    \"version\": \"0.0.0\"
}
"""

ENGINES_STRICT_FAIL_BASELINE_PACKAGE_JSON = """{
    \"name\": \"engines-strict-fail\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"engines\": {
        \"lpm\": \">=999.0.0\"
    }
}
"""

ENGINES_CONFIG_OPTOUT_BASELINE_PACKAGE_JSON = """{
    \"name\": \"engines-config-optout\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"engines\": {
        \"lpm\": \">=999.0.0\"
    },
    \"lpm\": {
        \"engineStrict\": false
    }
}
"""

WORKSPACE_TARGETING_ROOT_BASELINE_PACKAGE_JSON = (
    WORKSPACE_TARGETING_FIXTURE / "package.json"
).read_text(encoding="utf-8")

WORKSPACE_TARGETING_WEB_BASELINE_PACKAGE_JSON = (
    WORKSPACE_TARGETING_FIXTURE / "apps" / "web" / "package.json"
).read_text(encoding="utf-8")

WORKSPACE_TARGETING_DOCS_BASELINE_PACKAGE_JSON = (
    WORKSPACE_TARGETING_FIXTURE / "apps" / "docs" / "package.json"
).read_text(encoding="utf-8")

WORKSPACE_TARGETING_CORE_BASELINE_PACKAGE_JSON = (
    WORKSPACE_TARGETING_FIXTURE / "packages" / "core" / "package.json"
).read_text(encoding="utf-8")

SAVE_POLICY_DEFAULT_BASELINE_PACKAGE_JSON = """{
    \"name\": \"save-policy-default\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"dependencies\": {}
}
"""

SAVE_POLICY_EXISTING_RANGE_BASELINE_PACKAGE_JSON = """{
    \"name\": \"save-policy-existing-range\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"dependencies\": {
        \"smoke-save-lib\": \"~1.2.3\"
    }
}
"""

PEER_DEPS_OPTIONAL_MISSING_BASELINE_PACKAGE_JSON = """{
    \"name\": \"peer-deps-optional-missing-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"dependencies\": {
        \"optional-peer-host\": \"^1.0.0\"
    }
}
"""

PEER_DEPS_REQUIRED_MISSING_BASELINE_PACKAGE_JSON = """{
    \"name\": \"peer-deps-required-missing-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"dependencies\": {
        \"required-peer-host\": \"^1.0.0\"
    },
    \"lpm\": {
        \"autoInstallPeers\": false
    }
}
"""

PEER_DEPS_CONFLICT_BASELINE_PACKAGE_JSON = """{
    \"name\": \"peer-deps-conflict-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"dependencies\": {
        \"peer-consumer-a\": \"^1.0.0\",
        \"peer-consumer-b\": \"^1.0.0\"
    }
}
"""

CATALOG_MANUAL_BASELINE_PACKAGE_JSON = """{
    \"name\": \"catalog-manual-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"catalogs\": {
        \"default\": {
            \"is-positive\": \"^2.0.0\"
        }
    }
}
"""

CATALOG_PREFER_BASELINE_PACKAGE_JSON = """{
    \"name\": \"catalog-prefer-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"catalogs\": {
        \"default\": {
            \"is-positive\": \"^2.0.0\"
        }
    },
    \"lpm\": {
        \"catalogMode\": \"prefer\"
    }
}
"""

CATALOG_STRICT_BASELINE_PACKAGE_JSON = """{
    \"name\": \"catalog-strict-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"catalogs\": {
        \"default\": {
            \"is-positive\": \"^1.0.0\"
        }
    },
    \"lpm\": {
        \"catalogMode\": \"strict\"
    }
}
"""

CATALOG_NAMED_BASELINE_PACKAGE_JSON = """{
    \"name\": \"catalog-named-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"catalogs\": {
        \"testing\": {
            \"is-positive\": \"^2.0.0\"
        }
    }
}
"""

CATALOG_CLEANUP_BASELINE_PACKAGE_JSON = """{
    \"name\": \"catalog-cleanup-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"dependencies\": {
        \"is-positive\": \"catalog:\"
    },
    \"catalogs\": {
        \"default\": {
            \"is-positive\": \"^2.0.0\",
            \"unused-lib\": \"^9.9.9\"
        }
    },
    \"lpm\": {
        \"cleanupUnusedCatalogs\": true
    }
}
"""

CATALOG_PNPM_WORKSPACE_BASELINE_PACKAGE_JSON = """{
    \"name\": \"catalog-pnpm-workspace-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"dependencies\": {
        \"is-positive\": \"catalog:\"
    }
}
"""

CATALOG_PNPM_WORKSPACE_BASELINE_YAML = """packages:
  - \"packages/*\"
catalog:
  is-positive: ^2.0.0
  unused-lib: ^9.9.9
cleanupUnusedCatalogs: true
"""

SCRIPT_POLICY_BASELINE_PACKAGE_JSON = """{
    \"name\": \"script-policy-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"dependencies\": {}
}
"""

GLOBAL_INSTALL_BASELINE_PACKAGE_JSON = """{
    \"name\": \"global-install-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"dependencies\": {
        \"left-pad\": \"1.3.0\"
    }
}
"""

OFFLINE_INTEGRITY_BASELINE_PACKAGE_JSON = """{
    \"name\": \"offline-integrity-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"dependencies\": {}
}
"""

MINIMUM_RELEASE_AGE_BASELINE_PACKAGE_JSON = """{
    \"name\": \"minimum-release-age-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"dependencies\": {}
}
"""

AUDIT_AFTER_INSTALL_BASELINE_PACKAGE_JSON = """{
    \"name\": \"audit-after-install-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"dependencies\": {}
}
"""

AUDIT_COMMAND_BASELINE_PACKAGE_JSON = """{
    \"name\": \"audit-command-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"dependencies\": {
        \"audit-eval-pkg\": \"^1.0.0\",
        \"audit-clean-pkg\": \"^1.0.0\"
    }
}
"""

QUERY_COMMAND_BASELINE_PACKAGE_JSON = """{
    \"name\": \"query-command-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"dependencies\": {
        \"query-eval-pkg\": \"^1.0.0\",
        \"query-network-pkg\": \"^1.0.0\",
        \"query-clean-pkg\": \"^1.0.0\"
    }
}
"""

APPROVE_SCRIPTS_BASELINE_PACKAGE_JSON = """{
    \"name\": \"approve-scripts-command-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"dependencies\": {
        \"smoke-approve-scripted\": \"^1.0.0\"
    }
}
"""

TRUST_COMMAND_BASELINE_PACKAGE_JSON = """{
    \"name\": \"trust-command-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"dependencies\": {
        \"smoke-trust-scripted\": \"^1.0.0\",
        \"smoke-trust-keep\": \"^1.0.0\"
    }
}
"""

REBUILD_COMMAND_BASELINE_PACKAGE_JSON = """{
    \"name\": \"rebuild-command-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"dependencies\": {
        \"smoke-rebuild-scripted\": \"^1.0.0\"
    }
}
"""

PATCH_COMMAND_BASELINE_PACKAGE_JSON = """{
    \"name\": \"patch-command-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"dependencies\": {
        \"smoke-patch-lib\": \"^1.0.0\"
    }
}
"""

PATCH_COMMAND_TRACKED_FIXTURE = ROOT / "install" / "patch" / "basic"

PATCH_COMMAND_TRACKED_PACKAGE_JSON = (PATCH_COMMAND_TRACKED_FIXTURE / "package.json").read_text(
        encoding="utf-8"
)

PATCH_COMMAND_TRACKED_NPMRC = (PATCH_COMMAND_TRACKED_FIXTURE / ".npmrc").read_text(
        encoding="utf-8"
)

PATCH_COMMAND_TRACKED_PATCH = (
        PATCH_COMMAND_TRACKED_FIXTURE / "patches" / "smoke-patch-lib@1.0.0.patch"
).read_text(encoding="utf-8")

PATCH_SCOPED_COMMAND_BASELINE_PACKAGE_JSON = """{
    \"name\": \"patch-scoped-command-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"dependencies\": {
        \"@smoke/patch-lib\": \"^1.0.0\"
    }
}
"""

PATCH_BINARY_COMMAND_BASELINE_PACKAGE_JSON = """{
    \"name\": \"patch-binary-command-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"dependencies\": {
        \"smoke-patch-binary-lib\": \"^1.0.0\"
    }
}
"""

DOWNLOAD_COMMAND_BASELINE_PACKAGE_JSON = """{
    \"name\": \"download-command-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\"
}
"""

RESOLVE_COMMAND_BASELINE_PACKAGE_JSON = """{
    \"name\": \"resolve-command-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\"
}
"""

CACHE_COMMAND_BASELINE_PACKAGE_JSON = """{
    \"name\": \"cache-command-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\"
}
"""

CACHE_PRUNE_BASELINE_PACKAGE_JSON = """{
    \"name\": \"cache-prune-command-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\"
}
"""

STORE_COMMAND_BASELINE_PACKAGE_JSON = """{
    \"name\": \"store-command-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\"
}
"""

GRAPH_COMMAND_BASELINE_PACKAGE_JSON = """{
    \"name\": \"graph-test-project\",
    \"version\": \"1.0.0\",
    \"dependencies\": {
        \"express\": \"^4.22.0\",
        \"@lpm.dev/neo.highlight\": \"^1.0.0\"
    },
    \"devDependencies\": {
        \"vitest\": \"^1.0.0\"
    }
}
"""

DEV_COMMAND_BASELINE_PACKAGE_JSON = """{
    \"name\": \"dev-command-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"scripts\": {
        \"dev\": \"node dev-script.cjs\"
    }
}
"""

DEV_COMMAND_BASELINE_LPM_JSON = """{
    \"envSchema\": {
        \"vars\": {
            \"REQUIRED_TOKEN\": {
                \"required\": true
            }
        }
    }
}
"""

DEV_COMMAND_BASELINE_ENV_EXAMPLE = """BASE=from-example
SHARED=from-example
"""

DEV_COMMAND_BASELINE_ENV_LOCAL = """LOCAL_ONLY=from-local
SHARED=from-local
"""

DEV_COMMAND_BASELINE_ENV_STAGING = """STAGE_ONLY=from-staging
SHARED=from-staging
"""

DEV_COMMAND_BASELINE_ENV_STAGING_LOCAL = """LOCAL_STAGE=from-staging-local
SHARED=from-staging-local
"""

DEV_COMMAND_BASELINE_SCRIPT = """const fs = require(\"node:fs\")
const http = require(\"node:http\")

const args = process.argv.slice(2)
let port = 3000
let capturePath = \"dev-capture.json\"

for (let index = 0; index < args.length; index += 1) {
    const arg = args[index]
    if (arg === \"--port\" && index + 1 < args.length) {
        port = Number(args[index + 1])
        index += 1
        continue
    }
    if (arg === \"--capture\" && index + 1 < args.length) {
        capturePath = args[index + 1]
        index += 1
    }
}

if (!Number.isInteger(port) || port <= 0) {
    throw new Error(`invalid --port value: ${port}`)
}

const payload = {
    args,
    env: {
        BASE: process.env.BASE ?? null,
        SHARED: process.env.SHARED ?? null,
        LOCAL_ONLY: process.env.LOCAL_ONLY ?? null,
        STAGE_ONLY: process.env.STAGE_ONLY ?? null,
        LOCAL_STAGE: process.env.LOCAL_STAGE ?? null,
        REQUIRED_TOKEN: process.env.REQUIRED_TOKEN ?? null,
        NODE_EXTRA_CA_CERTS: process.env.NODE_EXTRA_CA_CERTS ?? null,
        SSL_CERT_FILE: process.env.SSL_CERT_FILE ?? null,
        SSL_KEY_FILE: process.env.SSL_KEY_FILE ?? null,
    },
}

fs.writeFileSync(capturePath, `${JSON.stringify(payload, null, 2)}\n`, \"utf8\")

const server = http.createServer((_request, response) => {
    response.writeHead(200, { \"content-type\": \"text/plain\" })
    response.end(\"ok\")
})

server.listen(port, \"127.0.0.1\", () => {
    setTimeout(() => {
        server.close(() => process.exit(0))
    }, 1200)
})
"""

DEV_ORCHESTRATION_BASELINE_PACKAGE_JSON = """{
    \"name\": \"dev-orchestration-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\"
}
"""

DEV_ORCHESTRATION_BASELINE_LPM_JSON = """{
    \"services\": {
        \"db\": {
            \"command\": \"node service-runner.cjs --service db --capture orchestration-events.jsonl --listen-delay-ms 250 --wait-ms 1200\",
            \"port\": 45001,
            \"readyPort\": 45001,
            \"readyTimeout\": 5
        },
        \"api\": {
            \"command\": \"node service-runner.cjs --service api --capture orchestration-events.jsonl --require-url-env DB_URL --listen-delay-ms 250 --wait-ms 900\",
            \"port\": 45002,
            \"readyUrl\": \"http://127.0.0.1:45002/health\",
            \"readyTimeout\": 5,
            \"dependsOn\": [\"db\"],
            \"env\": {
                \"API_SENTINEL\": \"from-config\"
            }
        },
        \"web\": {
            \"command\": \"node service-runner.cjs --service web --capture orchestration-events.jsonl --require-url-env API_URL --wait-ms 600\",
            \"port\": 45003,
            \"readyPort\": 45003,
            \"readyTimeout\": 5,
            \"dependsOn\": [\"api\"],
            \"primary\": true,
            \"env\": {
                \"WEB_SENTINEL\": \"from-config\"
            }
        }
    }
}
"""

DEV_ORCHESTRATION_BASELINE_SERVICE_RUNNER = """const fs = require(\"node:fs\")
const http = require(\"node:http\")

function getArg(flag, fallback = null) {
    const index = process.argv.indexOf(flag)
    if (index === -1 || index + 1 >= process.argv.length) {
        return fallback
    }
    return process.argv[index + 1]
}

function appendEvent(capturePath, event, extra = {}) {
    fs.appendFileSync(
        capturePath,
        `${JSON.stringify({ service, event, ...extra })}\n`,
        \"utf8\"
    )
}

const service = getArg(\"--service\")
const capturePath = getArg(\"--capture\", \"orchestration-events.jsonl\")
const requireUrlEnv = getArg(\"--require-url-env\")
const listenDelayMs = Number(getArg(\"--listen-delay-ms\", \"0\"))
const waitMs = Number(getArg(\"--wait-ms\", \"500\"))
const port = Number(process.env.PORT || getArg(\"--port\", \"0\"))

if (!service) {
    throw new Error(\"missing --service\")
}

if (!Number.isInteger(port) || port <= 0) {
    throw new Error(`invalid PORT for ${service}: ${process.env.PORT ?? \"unset\"}`)
}

async function main() {
    appendEvent(capturePath, \"start\", {
        port,
        env: {
            PORT: process.env.PORT ?? null,
            DB_URL: process.env.DB_URL ?? null,
            DB_PORT: process.env.DB_PORT ?? null,
            API_URL: process.env.API_URL ?? null,
            API_PORT: process.env.API_PORT ?? null,
            API_SENTINEL: process.env.API_SENTINEL ?? null,
            WEB_SENTINEL: process.env.WEB_SENTINEL ?? null,
        },
    })

    if (requireUrlEnv) {
        const depUrl = process.env[requireUrlEnv]
        if (!depUrl) {
            throw new Error(`${requireUrlEnv} missing for ${service}`)
        }
        const response = await fetch(`${depUrl}/health`)
        if (!response.ok) {
            throw new Error(`${service} dependency probe failed: ${depUrl} -> ${response.status}`)
        }
        appendEvent(capturePath, \"dependency-ok\", {
            port,
            requireUrlEnv,
            depUrl,
            status: response.status,
        })
    }

    await new Promise(resolve => setTimeout(resolve, listenDelayMs))

    const server = http.createServer((request, response) => {
        if (request.url === \"/health\") {
            response.writeHead(200, { \"content-type\": \"application/json\" })
            response.end(JSON.stringify({ ok: true, service }))
            return
        }

        response.writeHead(200, { \"content-type\": \"application/json\" })
        response.end(JSON.stringify({ service, ok: true }))
    })

    server.listen(port, \"127.0.0.1\", () => {
        appendEvent(capturePath, \"listening\", { port })
        setTimeout(() => {
            server.close(() => {
                appendEvent(capturePath, \"exit\", { port })
                process.exit(0)
            })
        }, waitMs)
    })
}

main().catch(error => {
    appendEvent(capturePath, \"error\", { message: error.message })
    console.error(`[${service}] ${error.message}`)
    process.exit(1)
})
"""

GRAPH_COMMAND_BASELINE_LOCKFILE = """[metadata]
lockfile-version = 1

[[packages]]
name = \"express\"
version = \"4.22.1\"
source = \"registry+https://registry.npmjs.org\"
dependencies = [\"accepts@1.3.8\", \"debug@2.6.9\"]

[[packages]]
name = \"accepts\"
version = \"1.3.8\"
source = \"registry+https://registry.npmjs.org\"
dependencies = [\"mime-types@2.1.35\"]

[[packages]]
name = \"debug\"
version = \"2.6.9\"
source = \"registry+https://registry.npmjs.org\"
dependencies = [\"ms@2.0.0\"]

[[packages]]
name = \"ms\"
version = \"2.0.0\"
source = \"registry+https://registry.npmjs.org\"
dependencies = []

[[packages]]
name = \"mime-types\"
version = \"2.1.35\"
source = \"registry+https://registry.npmjs.org\"
dependencies = []

[[packages]]
name = \"@lpm.dev/neo.highlight\"
version = \"1.1.1\"
source = \"registry+https://lpm.dev\"
dependencies = []

[[packages]]
name = \"vitest\"
version = \"1.6.0\"
source = \"registry+https://registry.npmjs.org\"
dependencies = [\"ms@2.1.3\"]

[[packages]]
name = \"ms\"
version = \"2.1.3\"
source = \"registry+https://registry.npmjs.org\"
dependencies = []
"""

PORTS_COMMAND_BASELINE_PACKAGE_JSON = """{
    \"name\": \"ports-command-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\"
}
"""

TUNNEL_COMMAND_BASELINE_PACKAGE_JSON = """{
    \"name\": \"tunnel-command-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\"
}
"""

CERT_COMMAND_BASELINE_PACKAGE_JSON = """{
    \"name\": \"cert-command-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\"
}
"""

DOCTOR_COMMAND_BASELINE_PACKAGE_JSON = """{
    \"name\": \"doctor-command-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\"
}
"""

HEALTH_COMMAND_BASELINE_PACKAGE_JSON = """{
    \"name\": \"health-command-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\"
}
"""

MIGRATE_NPM_BASELINE_PACKAGE_JSON = """{
    \"name\": \"npm-migrate-test\",
    \"version\": \"1.0.0\",
    \"dependencies\": {
        \"ms\": \"2.1.3\"
    }
}
"""

MIGRATE_NPM_BASELINE_PACKAGE_LOCK = """{
    \"name\": \"npm-migrate-test\",
    \"version\": \"1.0.0\",
    \"lockfileVersion\": 3,
    \"requires\": true,
    \"packages\": {
        \"\": {
            \"name\": \"npm-migrate-test\",
            \"version\": \"1.0.0\",
            \"dependencies\": {
                \"ms\": \"2.1.3\"
            }
        },
        \"node_modules/ms\": {
            \"version\": \"2.1.3\",
            \"resolved\": \"https://registry.npmjs.org/ms/-/ms-2.1.3.tgz\",
            \"integrity\": \"sha512-6FlzubTLZG3J2a/NVCAleEhjzq5oxgHyaCU9yYXvcLsFEhGdFC6jHFJMMCkdA97dNQCJ4CiGADqXyp1J+bHA==\"
        }
    }
}
"""

MIGRATE_PNPM_BASELINE_PACKAGE_JSON = """{
    \"name\": \"migrate-pnpm-overrides-fixture\",
    \"dependencies\": {
        \"ms\": \"^2.1.3\",
        \"depd\": \"^2.0.0\"
    },
    \"pnpm\": {
        \"overrides\": {
            \"lodash\": \"^4.17.21\",
            \"react\": \"18.2.0\"
        }
    }
}
"""

MIGRATE_PNPM_BASELINE_LOCK = """lockfileVersion: '9.0'

settings:
    autoInstallPeers: true
    excludeLinksFromLockfile: false

importers:
    .:
        dependencies:
            depd:
                specifier: ^2.0.0
                version: 2.0.0
            ms:
                specifier: ^2.1.3
                version: 2.1.3

packages:
    depd@2.0.0:
        resolution: {integrity: sha512-g7nH6P6dyDioJogAAGprGpCtVImJhkHkst9GbYOkCfKSMpXGVvokat2E8j5c0S0q1P0Y7Z6RlpKIxfWGcp/4fw==}
        engines: {node: '>= 0.8'}

    ms@2.1.3:
        resolution: {integrity: sha512-6FlzubTLZG3J2a/NVCAleEhjzq5oxgHyaCU9yYXvcLsVVw6Qy6/M+cSyZDJhGAVoS1CNDaMhVTDcLP06bIXw==}
"""

MIGRATE_PNPM_PATCHES_BASELINE_PACKAGE_JSON = """{
    \"name\": \"migrate-pnpm-patches-fixture\",
    \"dependencies\": {
        \"ms\": \"^2.1.3\",
        \"depd\": \"^2.0.0\"
    },
    \"pnpm\": {
        \"patchedDependencies\": {
            \"ms@2.1.3\": \"patches/ms@2.1.3.patch\"
        }
    }
}
"""

MIGRATE_PNPM_PATCHES_BASELINE_PATCH = """--- a/index.js
+++ b/index.js
@@ -1,1 +1,1 @@
-module.exports = function() { /* original */ }
+module.exports = function() { /* patched */ }
"""

MIGRATE_BUN_BASELINE_PACKAGE_JSON = """{
    \"name\": \"migrate-bun-fixture\",
    \"dependencies\": {
        \"ms\": \"^2.1.3\",
        \"depd\": \"^2.0.0\"
    }
}
"""

MIGRATE_BUN_BASELINE_LOCK = """{
    \"lockfileVersion\": 0,
    \"workspaces\": {
        \"\": {
            \"name\": \"migrate-bun-fixture\",
            \"dependencies\": {
                \"depd\": \"^2.0.0\",
                \"ms\": \"^2.1.3\"
            }
        }
    },
    \"packages\": {
        \"depd\": [\"depd@2.0.0\", \"https://registry.npmjs.org/depd/-/depd-2.0.0.tgz\", \"sha512-g7nH6P6dyDioJogAAGprGpCtVImJhkHkst9GbYOkCfKSMpXGVvokat2E8j5c0S0q1P0Y7Z6RlpKIxfWGcp/4fw==\", {}],
        \"ms\": [\"ms@2.1.3\", \"https://registry.npmjs.org/ms/-/ms-2.1.3.tgz\", \"sha512-6FlzubTLZG3J2a/NVCAleEhjzq5oxgHyaCU9yYXvcLsVVw6Qy6/M+cSyZDJhGAVoS1CNDaMhVTDcLP06bIXw==\", {}]
    }
}
"""

MIGRATE_YARN_BASELINE_PACKAGE_JSON = """{
    \"name\": \"migrate-yarn-fixture\",
    \"dependencies\": {
        \"ms\": \"^2.1.3\",
        \"depd\": \"^2.0.0\"
    },
    \"devDependencies\": {
        \"prettier\": \"^3.0.0\"
    }
}
"""

MIGRATE_YARN_BASELINE_LOCK = """# THIS IS AN AUTOGENERATED FILE. DO NOT EDIT THIS FILE DIRECTLY.
# yarn lockfile v1


depd@^2.0.0:
    version \"2.0.0\"
    resolved \"https://registry.yarnpkg.com/depd/-/depd-2.0.0.tgz#b696163cc757560d09cf22cc8fad1571b79e76df\"
    integrity sha512-g7nH6P6dyDioJogAAGprGpCtVImJhkHkst9GbYOkCfKSMpXGVvokat2E8j5c0S0q1P0Y7Z6RlpKIxfWGcp/4fw==

ms@^2.1.3:
    version \"2.1.3\"
    resolved \"https://registry.yarnpkg.com/ms/-/ms-2.1.3.tgz#574c8138ce1d2b5861f0b44579dbadd60c6615b2\"
    integrity sha512-6FlzubTLZG3J2a/NVCAleEhjzq5oxgHyaCU9yYXvcLsVVw6Qy6/M+cSyZDJhGAVoS1CNDaMhVTDcLP06bIXw==

prettier@^3.0.0:
    version \"3.4.2\"
    resolved \"https://registry.yarnpkg.com/prettier/-/prettier-3.4.2.tgz#a5ce1fb522a588b4b2b0d2add8e3bff73d4af07c\"
    integrity sha512-e9MewbtFo+Fevyuxn/4rrcDAaq0IYxPGLvII5cOKcLnMRiHbjfKsY/l/K+tQvPwMgE1HSL/RMBiBv4RE7/oIDg==
"""

MIGRATE_COMMON_EXTRA_DELETE = [
        ".npmrc",
        ".npmrc.backup",
        ".gitattributes",
        ".gitattributes.backup",
        ".lpm-migrate-manifest.json",
        "package.json.backup",
        "package-lock.json.backup",
        "pnpm-lock.yaml.backup",
        "bun.lock.backup",
        "yarn.lock.backup",
        "lpm.lock.backup",
        "lpm.lockb.backup",
        ".github",
]

UPGRADE_BASELINE_PACKAGE_JSON = """{
    \"name\": \"upgrade-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"dependencies\": {
        \"smoke-upgrade-lib\": \"^1.0.0\"
    }
}
"""

OUTDATED_BASELINE_PACKAGE_JSON = """{
    \"name\": \"outdated-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"dependencies\": {
        \"smoke-outdated-dep\": \"^1.0.0\"
    },
    \"devDependencies\": {
        \"smoke-outdated-dev\": \"^5.0.0\"
    }
}
"""

READ_ONLY_ROUTING_BASELINE_PACKAGE_JSON = """{
    \"name\": \"read-only-routing-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\"
}
"""

UNINSTALL_BASIC_BASELINE_PACKAGE_JSON = """{
    \"name\": \"uninstall-basic-smoke\",
    \"private\": true,
    \"version\": \"0.0.0\",
    \"dependencies\": {
        \"smoke-uninstall-dep\": \"^1.0.0\"
    },
    \"devDependencies\": {
        \"smoke-uninstall-dev\": \"^1.0.0\"
    },
    \"peerDependencies\": {
        \"smoke-uninstall-peer\": \"^1.0.0\"
    },
    \"optionalDependencies\": {
        \"smoke-uninstall-optional\": \"^1.0.0\"
    },
    \"lpm\": {
        \"trustedDependencies\": {
            \"smoke-uninstall-dep@1.0.0\": {
                \"integrity\": \"sha512-smoke-uninstall\",
                \"scriptHash\": \"sha256-smoke-uninstall\"
            }
        }
    }
}
"""


class SmokeFailure(RuntimeError):
    pass


class LocalRegistryRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self._serve_route(include_body=True)

    def do_HEAD(self) -> None:
        self._serve_route(include_body=False)

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length > 0:
            self.rfile.read(content_length)
        self._serve_route(include_body=True)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _serve_route(self, include_body: bool) -> None:
        path = unquote(self.path.split("?", 1)[0])
        self.server.request_log.append((self.command, path))
        route = self.server.routes.get(path)
        if route is None:
            self.send_response(404)
            self.end_headers()
            return

        content_type, body = route
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)


class LocalRegistryServer(ThreadingHTTPServer):
    def __init__(self, routes: dict[str, tuple[str, bytes]]):
        super().__init__(("127.0.0.1", 0), LocalRegistryRequestHandler)
        self.routes = routes
        self.request_log: list[tuple[str, str]] = []


class MockRegistry:
    def __init__(
        self,
        packages: list[dict[str, object]],
        *,
        serve_proxy_metadata: bool = True,
        serve_npm_search: bool = False,
        token_create_response: dict[str, object] | None = None,
    ):
        self._packages = packages
        self._serve_proxy_metadata = serve_proxy_metadata
        self._serve_npm_search = serve_npm_search
        self._token_create_response = token_create_response
        self._server: LocalRegistryServer | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> MockRegistry:
        self._server = LocalRegistryServer({})
        self._server.routes = self._build_routes(self.registry_url)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    @property
    def registry_url(self) -> str:
        if self._server is None:
            raise SmokeFailure("mock registry accessed before startup")
        host, port = self._server.server_address
        return f"http://{host}:{port}/"

    def _build_routes(self, registry_url: str) -> dict[str, tuple[str, bytes]]:
        routes: dict[str, tuple[str, bytes]] = {}
        batch_metadata_lines: list[str] = []
        search_objects: list[dict[str, object]] = []

        routes["/api/registry/health"] = (
            "application/json",
            b'{"ok":true}',
        )

        if self._token_create_response is not None:
            routes["/api/registry/-/token/create"] = (
                "application/json",
                json.dumps(self._token_create_response, separators=(",", ":")).encode(
                    "utf-8"
                ),
            )

        for package in self._packages:
            name = package["name"]
            versions = package["versions"]
            dist_tags = package["dist_tags"]
            time_map: dict[str, str] = {}
            metadata_versions: dict[str, object] = {}

            for version, version_spec in versions.items():
                tarball = build_package_tarball(
                    name,
                    version,
                    version_spec.get("package_json_extra", {}),
                    version_spec.get("files", {}),
                )
                tarball_path = f"/tarballs/{name}/-/{name}-{version}.tgz"
                routes[tarball_path] = ("application/octet-stream", tarball)
                metadata_versions[version] = build_registry_version_metadata(
                    registry_url,
                    name,
                    version,
                    tarball,
                    version_spec.get("metadata_extra", {}),
                )
                time_map[version] = version_spec.get(
                    "published_at",
                    "2024-01-01T00:00:00.000Z",
                )

            metadata = {
                "name": name,
                "dist-tags": dist_tags,
                "versions": metadata_versions,
                "time": time_map,
            }
            routes[f"/{name}"] = (
                "application/json",
                json.dumps(metadata, separators=(",", ":")).encode("utf-8"),
            )
            if self._serve_proxy_metadata:
                routes[f"/api/registry/{name}"] = (
                    "application/json",
                    json.dumps(metadata, separators=(",", ":")).encode("utf-8"),
                )
            batch_metadata_lines.append(
                json.dumps({"name": name, "metadata": metadata}, separators=(",", ":"))
            )
            latest_version = dist_tags.get("latest")
            if latest_version is not None:
                search_objects.append(
                    {
                        "package": {
                            "name": name,
                            "version": latest_version,
                            "description": package.get("description", ""),
                        }
                    }
                )

        routes["/api/registry/batch-metadata"] = (
            "application/x-ndjson",
            ("\n".join(batch_metadata_lines) + "\n").encode("utf-8"),
        )
        if self._serve_npm_search:
            routes["/-/v1/search"] = (
                "application/json",
                json.dumps({"objects": search_objects}, separators=(",", ":")).encode(
                    "utf-8"
                ),
            )

        return routes

    def requested_paths(self) -> list[str]:
        if self._server is None:
            raise SmokeFailure("mock registry request log accessed before startup")
        return [path for _, path in self._server.request_log]


class _RemoteCacheHTTPServer(ThreadingHTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _RemoteCacheRequestHandler)
        self.request_log: list[dict[str, object]] = []
        self.artifact_bytes: bytes | None = None
        self.artifact_tag: str | None = None
        self.download_bytes_override: bytes | None = None
        self.download_tag_override: str | None = None
        self.download_status_code: int | None = None
        self.download_body: dict[str, object] | None = None
        self.status_code = 200
        self.status_body: dict[str, object] = {
            "status": "enabled",
            "usageBytes": 1024,
            "limitBytes": 2048,
        }
        self.upload_status_code = 200
        self.upload_body: dict[str, object] | None = None


class _RemoteCacheRequestHandler(BaseHTTPRequestHandler):
    server: _RemoteCacheHTTPServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        parsed = self._record_request(0)
        if parsed.path == "/v8/artifacts/status":
            self._json_response(self.server.status_code, self.server.status_body)
            return

        if parsed.path.startswith("/v8/artifacts/"):
            if self.server.download_status_code is not None:
                self._json_response(
                    self.server.download_status_code,
                    self.server.download_body
                    or {"error": "remote cache download override"},
                )
                return

            payload = self.server.download_bytes_override
            if payload is None:
                payload = self.server.artifact_bytes
            if payload is None:
                self.send_error(404)
                return

            tag = self.server.download_tag_override
            if tag is None:
                tag = self.server.artifact_tag

            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(payload)))
            if tag is not None:
                self.send_header("x-artifact-tag", tag)
            self.end_headers()
            self.wfile.write(payload)
            return

        self.send_error(404)

    def do_PUT(self) -> None:
        body = self._read_body()
        parsed = self._record_request(len(body))
        if not parsed.path.startswith("/v8/artifacts/"):
            self.send_error(404)
            return

        if self.server.upload_status_code != 200:
            self._json_response(
                self.server.upload_status_code,
                self.server.upload_body
                or {"error": "remote cache upload override"},
            )
            return

        self.server.artifact_bytes = body
        self.server.artifact_tag = self.headers.get("x-artifact-tag")
        hash_value = parsed.path.rsplit("/", 1)[-1]
        origin = f"http://127.0.0.1:{self.server.server_port}"
        self._json_response(
            200,
            self.server.upload_body
            or {"urls": [f"{origin}/v8/artifacts/{hash_value}"]},
        )

    def _read_body(self) -> bytes:
        content_length = self.headers.get("Content-Length")
        if content_length is None:
            return b""
        return self.rfile.read(int(content_length))

    def _record_request(self, body_length: int) -> ParseResult:
        parsed = urlparse(self.path)
        self.server.request_log.append(
            {
                "method": self.command,
                "path": parsed.path,
                "query": parse_qs(parsed.query),
                "headers": {key.lower(): value for key, value in self.headers.items()},
                "body_length": body_length,
            }
        )
        return parsed

    def _json_response(self, status_code: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class MockRemoteCache:
    def __init__(self) -> None:
        self._server: _RemoteCacheHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "MockRemoteCache":
        self._server = _RemoteCacheHTTPServer()
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._server = None
        self._thread = None

    @property
    def base_url(self) -> str:
        server = self._require_server()
        return f"http://127.0.0.1:{server.server_port}/v8"

    @property
    def artifact_tag(self) -> str | None:
        return self._require_server().artifact_tag

    def requests(self, method: str | None = None, path: str | None = None) -> list[dict[str, object]]:
        requests = list(self._require_server().request_log)
        if method is not None:
            requests = [entry for entry in requests if entry.get("method") == method]
        if path is not None:
            requests = [entry for entry in requests if entry.get("path") == path]
        return requests

    def clear_requests(self) -> None:
        self._require_server().request_log.clear()

    def reset_artifact(self) -> None:
        server = self._require_server()
        server.artifact_bytes = None
        server.artifact_tag = None
        server.download_bytes_override = None
        server.download_tag_override = None
        server.download_status_code = None
        server.download_body = None
        server.upload_status_code = 200
        server.upload_body = None

    def set_status(self, status_code: int, body: dict[str, object]) -> None:
        server = self._require_server()
        server.status_code = status_code
        server.status_body = body

    def set_download_tag_override(self, tag: str | None) -> None:
        self._require_server().download_tag_override = tag

    def set_download_response(
        self,
        status_code: int | None,
        body: dict[str, object] | None = None,
    ) -> None:
        server = self._require_server()
        server.download_status_code = status_code
        server.download_body = body

    def set_upload_response(
        self,
        status_code: int,
        body: dict[str, object] | None = None,
    ) -> None:
        server = self._require_server()
        server.upload_status_code = status_code
        server.upload_body = body

    def _require_server(self) -> _RemoteCacheHTTPServer:
        if self._server is None:
            raise SmokeFailure("remote cache server accessed before startup")
        return self._server


def log(message: str) -> None:
    print(f"[smoke] {message}", flush=True)


def merged_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.update(DEFAULT_ENV)
    if extra:
        env.update(extra)
        if "LPM_HOME" in extra and "HOME" not in extra:
            env["HOME"] = extra["LPM_HOME"]
    return env


@contextmanager
def isolated_default_smoke_home() -> Path:
    previous_home = os.environ.get("HOME")
    previous_lpm_home = os.environ.get("LPM_HOME")
    lpm_home = Path(tempfile.mkdtemp(prefix="lpm-smoke-default-home-"))

    os.environ["HOME"] = str(lpm_home)
    os.environ["LPM_HOME"] = str(lpm_home)
    try:
        yield lpm_home
    finally:
        if previous_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = previous_home

        if previous_lpm_home is None:
            os.environ.pop("LPM_HOME", None)
        else:
            os.environ["LPM_HOME"] = previous_lpm_home

        cleanup_error: OSError | None = None
        for _ in range(10):
            try:
                shutil.rmtree(lpm_home)
                cleanup_error = None
                break
            except FileNotFoundError:
                cleanup_error = None
                break
            except OSError as error:
                cleanup_error = error
                time.sleep(0.05)

        if cleanup_error is not None:
            raise SmokeFailure(
                f"failed to clean isolated smoke home {lpm_home}: {cleanup_error}"
            )


def fnv1a_64_hex(value: str) -> str:
    hash_value = 0xCBF29CE484222325
    for byte in value.encode("utf-8"):
        hash_value ^= byte
        hash_value = (hash_value * 0x00000100000001B3) & 0xFFFFFFFFFFFFFFFF
    return f"{hash_value:016x}"


def project_port_override_key(project_dir: Path) -> str:
    return f"project_{fnv1a_64_hex(str(project_dir))}"


def reserve_then_release_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def build_websocket_text_frame(payload: str) -> bytes:
    encoded = payload.encode("utf-8")
    length = len(encoded)
    if length < 126:
        return bytes([0x81, length]) + encoded
    if length < 65536:
        return bytes([0x81, 126]) + length.to_bytes(2, "big") + encoded
    return bytes([0x81, 127]) + length.to_bytes(8, "big") + encoded


def read_inspector_sessions(db_path: Path) -> list[dict[str, object]]:
    if not db_path.exists():
        return []
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "select id, domain, local_port, ended_at from sessions order by rowid asc"
        ).fetchall()
    return [dict(row) for row in rows]


class FakeTunnelRelay:
    def __init__(self, port: int, tunnel_url: str, session_id: str) -> None:
        self.port = port
        self.tunnel_url = tunnel_url
        self.session_id = session_id
        self.request_path: str | None = None
        self.request_headers: dict[str, str] = {}
        self.connected = threading.Event()
        self.ready = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._error: Exception | None = None

    def __enter__(self) -> "FakeTunnelRelay":
        self._thread.start()
        if not self.ready.wait(timeout=2):
            raise SmokeFailure(
                f"fake tunnel relay on port {self.port} did not become ready"
            )
        if self._error is not None:
            raise SmokeFailure(f"fake tunnel relay failed to start: {self._error}")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        if self._error is not None and exc is None:
            raise SmokeFailure(f"fake tunnel relay failed: {self._error}")

    def wait_for_connection(self, timeout: float = 5) -> None:
        if self.connected.wait(timeout=timeout):
            if self._error is not None:
                raise SmokeFailure(f"fake tunnel relay failed: {self._error}")
            return
        if self._error is not None:
            raise SmokeFailure(f"fake tunnel relay failed: {self._error}")
        raise SmokeFailure("fake tunnel relay: expected a websocket client connection")

    def request_query(self) -> dict[str, list[str]]:
        if self.request_path is None:
            return {}
        return parse_qs(urlparse(self.request_path).query)

    def _serve(self) -> None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.bind(("127.0.0.1", self.port))
                server.listen(1)
                server.settimeout(0.1)
                self.ready.set()

                while not self._stop.is_set():
                    try:
                        connection, _ = server.accept()
                    except socket.timeout:
                        continue

                    with connection:
                        connection.settimeout(0.1)
                        request_bytes = b""
                        while b"\r\n\r\n" not in request_bytes:
                            if self._stop.is_set():
                                return
                            chunk = connection.recv(4096)
                            if not chunk:
                                raise RuntimeError(
                                    "websocket client closed before sending handshake"
                                )
                            request_bytes += chunk

                        request_text = request_bytes.decode("latin-1")
                        request_head = request_text.split("\r\n\r\n", 1)[0]
                        lines = request_head.split("\r\n")
                        method, path, _ = lines[0].split(" ", 2)
                        if method != "GET":
                            raise RuntimeError(
                                f"expected websocket upgrade GET request, got {method}"
                            )
                        self.request_path = path
                        self.request_headers = {}
                        for line in lines[1:]:
                            if not line or ":" not in line:
                                continue
                            key, value = line.split(":", 1)
                            self.request_headers[key.strip().lower()] = value.strip()

                        sec_key = self.request_headers.get("sec-websocket-key")
                        if sec_key is None:
                            raise RuntimeError(
                                "websocket upgrade missing Sec-WebSocket-Key header"
                            )
                        accept_value = base64.b64encode(
                            hashlib.sha1(
                                (
                                    sec_key
                                    + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
                                ).encode("ascii")
                            ).digest()
                        ).decode("ascii")
                        response = (
                            "HTTP/1.1 101 Switching Protocols\r\n"
                            "Upgrade: websocket\r\n"
                            "Connection: Upgrade\r\n"
                            f"Sec-WebSocket-Accept: {accept_value}\r\n"
                            "\r\n"
                        )
                        connection.sendall(response.encode("ascii"))

                        hello_frame = json.dumps(
                            {
                                "type": "hello",
                                "subdomain": self.tunnel_url.replace(
                                    "https://", ""
                                ).replace("http://", ""),
                                "tunnel_url": self.tunnel_url,
                                "session_id": self.session_id,
                            }
                        )
                        connection.sendall(build_websocket_text_frame(hello_frame))
                        self.connected.set()

                        while not self._stop.is_set():
                            try:
                                chunk = connection.recv(4096)
                            except socket.timeout:
                                continue
                            if not chunk:
                                return
                    return
        except Exception as error:  # pragma: no cover - smoke helper failure path
            self._error = error
            self.ready.set()
            self.connected.set()


def seed_refresh_backed_session(
    auth_env: dict[str, str],
    registry_url: str,
    access_token: str,
    refresh_token: str,
    expires_at: str,
) -> None:
    cargo_env = dict(auth_env)
    if "CARGO_HOME" not in cargo_env:
        if REAL_CARGO_HOME:
            cargo_env["CARGO_HOME"] = REAL_CARGO_HOME
        elif REAL_HOME:
            cargo_env["CARGO_HOME"] = str(Path(REAL_HOME) / ".cargo")
    if "RUSTUP_HOME" not in cargo_env:
        if REAL_RUSTUP_HOME:
            cargo_env["RUSTUP_HOME"] = REAL_RUSTUP_HOME
        elif REAL_HOME:
            cargo_env["RUSTUP_HOME"] = str(Path(REAL_HOME) / ".rustup")

    run_command(
        "seed refresh-backed session",
        RUST_CLIENT_ROOT,
        [
            "cargo",
            "run",
            "--quiet",
            "-p",
            "lpm-auth",
            "--example",
            "seed_refresh_backed_session",
            "--",
            registry_url,
            access_token,
            refresh_token,
            expires_at,
        ],
        extra_env=cargo_env,
    )


def delete_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    shutil.rmtree(path)


def write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)


def seed_fake_tsdown(binary_path: Path, log_path: Path, marker: str) -> None:
    script = "\n".join(
        [
            "#!/usr/bin/env node",
            "const fs = require('node:fs')",
            "const path = require('node:path')",
            f"const logPath = {json.dumps(str(log_path))}",
            f"const marker = {json.dumps(marker)}",
            "fs.mkdirSync(path.dirname(logPath), { recursive: true })",
            "fs.appendFileSync(logPath, JSON.stringify({ cwd: process.cwd(), args: process.argv.slice(2) }) + '\\n', 'utf8')",
            "process.stdout.write(marker + '\\n')",
        ]
    )
    write_executable(binary_path, script + "\n")


def read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def normalize_test_path(path: str) -> str:
    return path.removeprefix("/private")


def reset_single_project_fixture(
    fixture: Path,
    baseline_files: dict[str, str] | None = None,
    extra_delete: list[str] | None = None,
) -> Path:
    for rel in [
        ".lpm",
        "node_modules",
        "lpm.lock",
        "lpm.lockb",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "bun.lock",
        "bun.lockb",
    ]:
        delete_path(fixture / rel)

    if extra_delete:
        for rel in extra_delete:
            delete_path(fixture / rel)

    fixture.mkdir(parents=True, exist_ok=True)
    for rel, content in (baseline_files or {}).items():
        path = fixture / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    return fixture


def reset_workspace_fixture(name: str) -> Path:
    fixture = ROOT / "workspace" / name
    for rel in [".lpm", "node_modules", "lpm.lock", "lpm.lockb"]:
        delete_path(fixture / rel)

    for parent_name in ["apps", "packages"]:
        parent = fixture / parent_name
        if not parent.exists():
            continue
        for child in parent.iterdir():
            for rel in [".lpm", "node_modules", "lpm.lock", "lpm.lockb"]:
                delete_path(child / rel)

    return fixture


def reset_config_aware_fixture() -> Path:
    fixture = ROOT / "install" / "config-aware"
    return reset_single_project_fixture(
        fixture,
        baseline_files={
            "package.json": CONFIG_AWARE_BASELINE_PACKAGE_JSON,
            "tsconfig.json": CONFIG_AWARE_BASELINE_TSCONFIG,
        },
        extra_delete=["components", "styles", "lib"],
    )


def reset_project_discovery_nearest_fixture() -> Path:
    fixture = ROOT / "install" / "project-discovery" / "nearest-ancestor"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": PROJECT_DISCOVERY_NEAREST_BASELINE_PACKAGE_JSON},
    )


def reset_project_discovery_fresh_fixture() -> Path:
    fixture = ROOT / "install" / "project-discovery" / "fresh-dir" / "empty"
    return reset_single_project_fixture(
        fixture,
        extra_delete=["package.json"],
    )


def reset_engines_fixture(name: str, package_json: str) -> Path:
    fixture = ROOT / "install" / "engines" / name
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": package_json},
    )


def reset_peer_deps_fixture(name: str, package_json: str) -> Path:
    fixture = ROOT / "install" / "peer-deps" / name
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": package_json},
        extra_delete=[".npmrc"],
    )


def reset_catalog_fixture(
    name: str,
    package_json: str,
    *,
    pnpm_workspace_yaml: str | None = None,
) -> Path:
    fixture = ROOT / "install" / "catalog" / name
    baseline_files = {"package.json": package_json}
    if pnpm_workspace_yaml is not None:
        baseline_files["pnpm-workspace.yaml"] = pnpm_workspace_yaml
    return reset_single_project_fixture(
        fixture,
        baseline_files=baseline_files,
        extra_delete=[".npmrc", "pnpm-workspace.yaml"],
    )


def reset_workspace_targeting_fixture() -> Path:
    fixture = reset_workspace_fixture("targeting")
    for rel in [
        ".git",
        "record-concurrency.js",
        "concurrency-state.json",
        "concurrency-state.lock",
        "lpm.toml",
        "packages/project-1",
        "packages/project-2",
        "packages/project-3",
        "packages/project-4",
        "packages/no-bail-utils",
        "packages/no-bail-core",
        "packages/no-bail-app",
        "packages/concurrency-alpha",
        "packages/concurrency-beta",
        "packages/concurrency-gamma",
        "packages/changed-app",
        "packages/test-pattern-utils",
        "packages/test-pattern-app",
        "apps/scope-web",
        "packages/scope-ui",
        "apps/other-admin",
    ]:
        delete_path(fixture / rel)
    (fixture / "package.json").write_text(
        WORKSPACE_TARGETING_ROOT_BASELINE_PACKAGE_JSON,
        encoding="utf-8",
    )
    (fixture / "apps" / "web" / "package.json").write_text(
        WORKSPACE_TARGETING_WEB_BASELINE_PACKAGE_JSON,
        encoding="utf-8",
    )
    (fixture / "apps" / "docs" / "package.json").write_text(
        WORKSPACE_TARGETING_DOCS_BASELINE_PACKAGE_JSON,
        encoding="utf-8",
    )
    (fixture / "packages" / "core" / "package.json").write_text(
        WORKSPACE_TARGETING_CORE_BASELINE_PACKAGE_JSON,
        encoding="utf-8",
    )
    return fixture


def run_git_command(label: str, cwd: Path, args: list[str]) -> str:
    result = run_command_result(
        label,
        cwd,
        ["git", *args],
        extra_env={
            "GIT_AUTHOR_NAME": "smoke",
            "GIT_AUTHOR_EMAIL": "smoke@example.com",
            "GIT_COMMITTER_NAME": "smoke",
            "GIT_COMMITTER_EMAIL": "smoke@example.com",
        },
    )
    combined = result.stdout + result.stderr
    if result.returncode != 0:
        raise SmokeFailure(f"{label} failed with exit code {result.returncode}")
    return combined


def seed_workspace_filter_prod_members(fixture: Path) -> None:
    members = {
        "project-1": {
            "name": "project-1",
            "version": "1.0.0",
            "dependencies": {
                "project-2": "workspace:*",
                "project-3": "workspace:*",
            },
            "scripts": {
                "check": "node -e \"require('fs').writeFileSync('ran-project-1.txt','ok')\"",
            },
        },
        "project-2": {
            "name": "project-2",
            "version": "1.0.0",
            "scripts": {
                "check": "node -e \"require('fs').writeFileSync('ran-project-2.txt','ok')\"",
            },
        },
        "project-3": {
            "name": "project-3",
            "version": "1.0.0",
            "dependencies": {
                "project-2": "workspace:*",
            },
            "scripts": {
                "check": "node -e \"require('fs').writeFileSync('ran-project-3.txt','ok')\"",
            },
        },
        "project-4": {
            "name": "project-4",
            "version": "1.0.0",
            "devDependencies": {
                "project-3": "workspace:*",
            },
            "scripts": {
                "check": "node -e \"require('fs').writeFileSync('ran-project-4.txt','ok')\"",
            },
        },
    }

    for member, manifest in members.items():
        write_package_json(fixture / "packages" / member / "package.json", manifest)


def seed_workspace_no_bail_members(fixture: Path) -> None:
    members = {
        "no-bail-utils": {
            "name": "@smoke/no-bail-utils",
            "version": "1.0.0",
            "scripts": {
                "check": "node -e \"require('fs').writeFileSync('ran-utils.txt','failed'); process.exit(1)\"",
            },
        },
        "no-bail-core": {
            "name": "@smoke/no-bail-core",
            "version": "1.0.0",
            "dependencies": {
                "@smoke/no-bail-utils": "workspace:*",
            },
            "scripts": {
                "check": "node -e \"require('fs').writeFileSync('ran-core.txt','ok')\"",
            },
        },
        "no-bail-app": {
            "name": "@smoke/no-bail-app",
            "version": "1.0.0",
            "dependencies": {
                "@smoke/no-bail-core": "workspace:*",
            },
            "scripts": {
                "check": "node -e \"require('fs').writeFileSync('ran-app.txt','ok')\"",
            },
        },
    }

    for member, manifest in members.items():
        write_package_json(fixture / "packages" / member / "package.json", manifest)


def seed_workspace_concurrency_members(fixture: Path) -> None:
    (fixture / "record-concurrency.js").write_text(
        """
const fs = require('fs');
const path = require('path');

const root = __dirname;
const statePath = path.join(root, 'concurrency-state.json');
const lockPath = path.join(root, 'concurrency-state.lock');

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function acquireLock() {
  const deadline = Date.now() + 10000;
  while (true) {
    try {
      fs.mkdirSync(lockPath);
      return;
    } catch (error) {
      if (error.code !== 'EEXIST' || Date.now() > deadline) {
        throw error;
      }
    }
  }
}

function withLock(callback) {
  acquireLock();
  try {
    return callback();
  } finally {
    fs.rmSync(lockPath, { recursive: true, force: true });
  }
}

function mutateActive(delta) {
  withLock(() => {
    let state = { active: 0, max: 0 };
    try {
      state = JSON.parse(fs.readFileSync(statePath, 'utf8'));
    } catch (error) {
      if (error.code !== 'ENOENT') {
        throw error;
      }
    }

    state.active += delta;
    if (state.active < 0) {
      throw new Error('active counter went negative');
    }
    state.max = Math.max(state.max, state.active);
    fs.writeFileSync(statePath, JSON.stringify(state));
  });
}

(async () => {
  mutateActive(1);
  await sleep(250);
  mutateActive(-1);
})().catch(error => {
  console.error(error);
  process.exit(1);
});
""".strip()
        + "\n",
        encoding="utf-8",
    )

    for member in ["concurrency-alpha", "concurrency-beta", "concurrency-gamma"]:
        write_package_json(
            fixture / "packages" / member / "package.json",
            {
                "name": f"@smoke/{member}",
                "version": "1.0.0",
                "scripts": {
                    "check": "node ../../record-concurrency.js",
                },
            },
        )


def seed_workspace_changed_app_git_repo(fixture: Path, *, write_config: bool = False) -> None:
    if write_config:
        (fixture / "lpm.toml").write_text(
            "[workspace]\nchanged-files-ignore-pattern = \"**/README.md\"\n",
            encoding="utf-8",
        )

    write_package_json(
        fixture / "packages" / "changed-app" / "package.json",
        {
            "name": "changed-app",
            "version": "1.0.0",
            "scripts": {
                "check": "node -e \"require('fs').writeFileSync('ran-changed-app.txt','ok')\"",
            },
        },
    )
    (fixture / "packages" / "changed-app" / "README.md").write_text("before\n", encoding="utf-8")

    run_git_command("workspace/filter-controls git init", fixture, ["init", "-b", "main"])
    run_git_command("workspace/filter-controls git add baseline", fixture, ["add", "."])
    run_git_command(
        "workspace/filter-controls git commit baseline",
        fixture,
        ["commit", "-m", "baseline"],
    )
    run_git_command("workspace/filter-controls git checkout feature", fixture, ["checkout", "-b", "feature"])

    (fixture / "packages" / "changed-app" / "README.md").write_text("after\n", encoding="utf-8")
    run_git_command("workspace/filter-controls git add readme change", fixture, ["add", "."])
    run_git_command(
        "workspace/filter-controls git commit readme change",
        fixture,
        ["commit", "-m", "readme change"],
    )


def seed_workspace_test_pattern_git_repo(fixture: Path) -> None:
    write_package_json(
        fixture / "packages" / "test-pattern-utils" / "package.json",
        {
            "name": "test-pattern-utils",
            "version": "1.0.0",
            "scripts": {
                "check": "node -e \"require('fs').writeFileSync('ran-utils.txt','ok')\"",
            },
        },
    )
    write_package_json(
        fixture / "packages" / "test-pattern-app" / "package.json",
        {
            "name": "test-pattern-app",
            "version": "1.0.0",
            "dependencies": {
                "test-pattern-utils": "workspace:*",
            },
            "scripts": {
                "check": "node -e \"require('fs').writeFileSync('ran-app.txt','ok')\"",
            },
        },
    )

    utils_src = fixture / "packages" / "test-pattern-utils" / "src"
    app_src = fixture / "packages" / "test-pattern-app" / "src"
    utils_src.mkdir(parents=True, exist_ok=True)
    app_src.mkdir(parents=True, exist_ok=True)
    (utils_src / "index.js").write_text("module.exports = 'before'\n", encoding="utf-8")
    (utils_src / "index.test.js").write_text("test('before', () => {})\n", encoding="utf-8")
    (app_src / "index.js").write_text("require('test-pattern-utils')\n", encoding="utf-8")

    run_git_command("workspace/filter-controls git init", fixture, ["init", "-b", "main"])
    run_git_command("workspace/filter-controls git add baseline", fixture, ["add", "."])
    run_git_command(
        "workspace/filter-controls git commit baseline",
        fixture,
        ["commit", "-m", "baseline"],
    )
    run_git_command("workspace/filter-controls git checkout feature", fixture, ["checkout", "-b", "feature"])

    (utils_src / "index.test.js").write_text("test('after', () => {})\n", encoding="utf-8")
    run_git_command("workspace/filter-controls git add test-pattern change", fixture, ["add", "."])
    run_git_command(
        "workspace/filter-controls git commit test-pattern change",
        fixture,
        ["commit", "-m", "test pattern change"],
    )


def seed_workspace_combined_name_path_members(fixture: Path) -> None:
    write_package_json(
        fixture / "apps" / "scope-web" / "package.json",
        {
            "name": "@scope/web",
            "version": "1.0.0",
        },
    )
    write_package_json(
        fixture / "packages" / "scope-ui" / "package.json",
        {
            "name": "@scope/ui",
            "version": "1.0.0",
        },
    )
    write_package_json(
        fixture / "apps" / "other-admin" / "package.json",
        {
            "name": "@other/admin",
            "version": "1.0.0",
        },
    )


def selected_workspace_names(stdout: str) -> set[str]:
    return {line.strip() for line in stdout.splitlines() if line.strip()}


def reset_pack_fixture() -> Path:
    fixture = ROOT / "install" / "pack" / "basic"
    return reset_single_project_fixture(
        fixture,
        extra_delete=["dist"],
    )


def reset_workspace_pack_fixture() -> Path:
    fixture = reset_workspace_fixture("pack")
    for rel in ["apps/web/dist", "apps/docs/dist", "packages/core/dist"]:
        delete_path(fixture / rel)
    return fixture


def reset_save_policy_fixture(name: str, package_json: str) -> Path:
    fixture = ROOT / "install" / "save-policy" / name
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": package_json},
        extra_delete=[".npmrc"],
    )


def reset_script_policy_fixture(name: str, dependency_name: str) -> Path:
    fixture = ROOT / "install" / "script-policy" / name
    return reset_single_project_fixture(
        fixture,
        baseline_files={
            "package.json": json.dumps(
                {
                    "name": "script-policy-smoke",
                    "private": True,
                    "version": "0.0.0",
                    "dependencies": {dependency_name: "^1.0.0"},
                },
                indent=4,
            )
            + "\n"
        },
        extra_delete=[".npmrc"],
    )


def reset_security_fixture(name: str) -> Path:
    fixture = ROOT / "install" / "security" / name
    return reset_single_project_fixture(
        fixture,
        baseline_files={
            "package.json": json.dumps(
                {
                    "name": f"security-smoke-{name}",
                    "private": True,
                    "version": "0.0.0",
                },
                indent=4,
            )
            + "\n"
        },
        extra_delete=[".npmrc"],
    )


def reset_global_install_fixture(name: str) -> Path:
    fixture = ROOT / "install" / "global-install" / name
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": GLOBAL_INSTALL_BASELINE_PACKAGE_JSON},
        extra_delete=[".npmrc"],
    )


def reset_offline_integrity_fixture() -> Path:
    fixture = ROOT / "install" / "offline-integrity" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": OFFLINE_INTEGRITY_BASELINE_PACKAGE_JSON},
        extra_delete=[".npmrc"],
    )


def reset_minimum_release_age_fixture() -> Path:
    fixture = ROOT / "install" / "minimum-release-age" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": MINIMUM_RELEASE_AGE_BASELINE_PACKAGE_JSON},
        extra_delete=[".npmrc"],
    )


def reset_audit_after_install_fixture() -> Path:
    fixture = ROOT / "install" / "audit-after-install" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": AUDIT_AFTER_INSTALL_BASELINE_PACKAGE_JSON},
        extra_delete=[".npmrc"],
    )


def reset_audit_command_fixture() -> Path:
    fixture = ROOT / "install" / "audit" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": AUDIT_COMMAND_BASELINE_PACKAGE_JSON},
        extra_delete=[".npmrc"],
    )


def reset_query_command_fixture() -> Path:
    fixture = ROOT / "install" / "query" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": QUERY_COMMAND_BASELINE_PACKAGE_JSON},
        extra_delete=[".npmrc"],
    )


def reset_approve_scripts_fixture() -> Path:
    fixture = ROOT / "install" / "approve-scripts" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": APPROVE_SCRIPTS_BASELINE_PACKAGE_JSON},
        extra_delete=[".npmrc"],
    )


def reset_trust_command_fixture() -> Path:
    fixture = ROOT / "install" / "trust" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": TRUST_COMMAND_BASELINE_PACKAGE_JSON},
        extra_delete=[".npmrc"],
    )


def reset_rebuild_command_fixture() -> Path:
    fixture = ROOT / "install" / "rebuild" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": REBUILD_COMMAND_BASELINE_PACKAGE_JSON},
        extra_delete=[".npmrc"],
    )


def reset_patch_command_fixture() -> Path:
    fixture = ROOT / "install" / "patch" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": PATCH_COMMAND_BASELINE_PACKAGE_JSON},
        extra_delete=[".npmrc", "patches"],
    )


def restore_patch_command_fixture() -> Path:
    fixture = ROOT / "install" / "patch" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={
            ".npmrc": PATCH_COMMAND_TRACKED_NPMRC,
            "package.json": PATCH_COMMAND_TRACKED_PACKAGE_JSON,
            "patches/smoke-patch-lib@1.0.0.patch": PATCH_COMMAND_TRACKED_PATCH,
        },
    )


def reset_patch_scoped_command_fixture() -> Path:
    fixture = ROOT / "install" / "patch" / "scoped"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": PATCH_SCOPED_COMMAND_BASELINE_PACKAGE_JSON},
        extra_delete=[".npmrc", "patches"],
    )


def reset_patch_binary_command_fixture() -> Path:
    fixture = ROOT / "install" / "patch" / "binary"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": PATCH_BINARY_COMMAND_BASELINE_PACKAGE_JSON},
        extra_delete=[".npmrc", "patches"],
    )


def reset_download_command_fixture() -> Path:
    fixture = ROOT / "install" / "download" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": DOWNLOAD_COMMAND_BASELINE_PACKAGE_JSON},
        extra_delete=[".npmrc", "download-out", "nested"],
    )


def reset_resolve_command_fixture() -> Path:
    fixture = ROOT / "install" / "resolve" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": RESOLVE_COMMAND_BASELINE_PACKAGE_JSON},
        extra_delete=[".npmrc"],
    )


def reset_cache_command_fixture() -> Path:
    fixture = ROOT / "install" / "cache" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": CACHE_COMMAND_BASELINE_PACKAGE_JSON},
    )


def reset_cache_prune_fixture() -> Path:
    fixture = ROOT / "install" / "cache" / "prune" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": CACHE_PRUNE_BASELINE_PACKAGE_JSON},
        extra_delete=["node_modules"],
    )


def reset_store_fixture() -> Path:
    fixture = ROOT / "install" / "store" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": STORE_COMMAND_BASELINE_PACKAGE_JSON},
    )


def reset_graph_fixture() -> Path:
    fixture = ROOT / "install" / "graph" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={
            "package.json": GRAPH_COMMAND_BASELINE_PACKAGE_JSON,
            "lpm.lock": GRAPH_COMMAND_BASELINE_LOCKFILE,
        },
    )


def reset_dev_fixture() -> Path:
    fixture = ROOT / "install" / "dev" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={
            "package.json": DEV_COMMAND_BASELINE_PACKAGE_JSON,
            "lpm.json": DEV_COMMAND_BASELINE_LPM_JSON,
            ".env.example": DEV_COMMAND_BASELINE_ENV_EXAMPLE,
            ".env.local": DEV_COMMAND_BASELINE_ENV_LOCAL,
            ".env.staging": DEV_COMMAND_BASELINE_ENV_STAGING,
            ".env.staging.local": DEV_COMMAND_BASELINE_ENV_STAGING_LOCAL,
            "dev-script.cjs": DEV_COMMAND_BASELINE_SCRIPT,
        },
        extra_delete=[".env", "dev-capture.json"],
    )


def reset_env_fixture() -> Path:
    fixture = ROOT / "install" / "e2e-sandbox"
    return reset_single_project_fixture(
        fixture,
        extra_delete=[".env", ".env.local", ".env.staging.local", ".env.preview.local"],
    )


def reset_dev_orchestration_fixture() -> Path:
    fixture = ROOT / "install" / "dev" / "orchestration"
    return reset_single_project_fixture(
        fixture,
        baseline_files={
            "package.json": DEV_ORCHESTRATION_BASELINE_PACKAGE_JSON,
            "lpm.json": DEV_ORCHESTRATION_BASELINE_LPM_JSON,
            "service-runner.cjs": DEV_ORCHESTRATION_BASELINE_SERVICE_RUNNER,
        },
        extra_delete=["orchestration-events.jsonl", ".lpm"],
    )


def reset_ports_fixture() -> Path:
    fixture = ROOT / "install" / "ports" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": PORTS_COMMAND_BASELINE_PACKAGE_JSON},
        extra_delete=["lpm.json"],
    )


def reset_tunnel_fixture() -> Path:
    fixture = ROOT / "install" / "tunnel" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": TUNNEL_COMMAND_BASELINE_PACKAGE_JSON},
    )


def reset_cert_fixture() -> Path:
    fixture = ROOT / "install" / "cert" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": CERT_COMMAND_BASELINE_PACKAGE_JSON},
    )


def reset_doctor_fixture() -> Path:
    fixture = ROOT / "install" / "doctor" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": DOCTOR_COMMAND_BASELINE_PACKAGE_JSON},
        extra_delete=[".gitattributes", ".gitignore"],
    )


def reset_health_fixture() -> Path:
    fixture = ROOT / "install" / "health" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": HEALTH_COMMAND_BASELINE_PACKAGE_JSON},
    )


def reset_migrate_fixture(
    name: str,
    lockfile_name: str,
    package_json: str,
    lockfile: str,
    extra_delete: list[str] | None = None,
    extra_baseline_files: dict[str, str] | None = None,
) -> Path:
    fixture = ROOT / "install" / "migrate" / name / "basic"
    baseline_files = {
        "package.json": package_json,
        lockfile_name: lockfile,
    }
    if extra_baseline_files:
        baseline_files.update(extra_baseline_files)
    return reset_single_project_fixture(
        fixture,
        baseline_files=baseline_files,
        extra_delete=MIGRATE_COMMON_EXTRA_DELETE + (extra_delete or []),
    )


def reset_migrate_npm_fixture() -> Path:
    return reset_migrate_fixture(
        "npm",
        "package-lock.json",
        MIGRATE_NPM_BASELINE_PACKAGE_JSON,
        MIGRATE_NPM_BASELINE_PACKAGE_LOCK,
    )


def reset_migrate_pnpm_fixture() -> Path:
    return reset_migrate_fixture(
        "pnpm",
        "pnpm-lock.yaml",
        MIGRATE_PNPM_BASELINE_PACKAGE_JSON,
        MIGRATE_PNPM_BASELINE_LOCK,
    )


def reset_migrate_pnpm_patches_fixture() -> Path:
    return reset_migrate_fixture(
        "pnpm-patches",
        "pnpm-lock.yaml",
        MIGRATE_PNPM_PATCHES_BASELINE_PACKAGE_JSON,
        MIGRATE_PNPM_BASELINE_LOCK,
        extra_delete=["patches"],
        extra_baseline_files={"patches/ms@2.1.3.patch": MIGRATE_PNPM_PATCHES_BASELINE_PATCH},
    )


def reset_migrate_bun_fixture() -> Path:
    return reset_migrate_fixture(
        "bun",
        "bun.lock",
        MIGRATE_BUN_BASELINE_PACKAGE_JSON,
        MIGRATE_BUN_BASELINE_LOCK,
    )


def reset_migrate_yarn_fixture() -> Path:
    return reset_migrate_fixture(
        "yarn",
        "yarn.lock",
        MIGRATE_YARN_BASELINE_PACKAGE_JSON,
        MIGRATE_YARN_BASELINE_LOCK,
    )


def reset_upgrade_fixture() -> Path:
    fixture = ROOT / "install" / "upgrade" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": UPGRADE_BASELINE_PACKAGE_JSON},
        extra_delete=[".npmrc", ".lpm", ".gitattributes", ".gitignore"],
    )


def reset_outdated_fixture() -> Path:
    fixture = ROOT / "install" / "outdated" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": OUTDATED_BASELINE_PACKAGE_JSON},
        extra_delete=[".npmrc"],
    )


def reset_read_only_routing_fixture() -> Path:
    fixture = ROOT / "install" / "read-only-routing" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": READ_ONLY_ROUTING_BASELINE_PACKAGE_JSON},
        extra_delete=[".npmrc", "downloaded-package"],
    )


def reset_uninstall_fixture() -> Path:
    fixture = ROOT / "install" / "uninstall" / "basic"
    return reset_single_project_fixture(
        fixture,
        baseline_files={"package.json": UNINSTALL_BASIC_BASELINE_PACKAGE_JSON},
    )


def reset_source_delivery_fixture() -> Path:
    fixture = ROOT / "install" / "source-delivery"
    return reset_single_project_fixture(
        fixture,
        extra_delete=["custom", ".npmrc"],
    )


def write_registry_npmrc(fixture: Path, registry_url: str) -> None:
    npmrc_path = fixture / ".npmrc"
    npmrc_path.write_text(f"registry={registry_url}\n", encoding="utf-8")


def build_package_tarball(
    name: str,
    version: str,
    package_json_extra: dict[str, object],
    files: dict[str, str],
) -> bytes:
    package_json = {
        "name": name,
        "version": version,
        **package_json_extra,
    }
    tar_stream = io.BytesIO()

    with tarfile.open(fileobj=tar_stream, mode="w:gz") as archive:
        add_tar_text_file(
            archive,
            "package/package.json",
            json.dumps(package_json, separators=(",", ":")),
        )
        add_tar_text_file(archive, "package/index.js", "module.exports = 'ok'\n")
        for rel_path, content in files.items():
            add_tar_text_file(archive, f"package/{rel_path}", content)

    return tar_stream.getvalue()


def add_tar_text_file(archive: tarfile.TarFile, path: str, content: str) -> None:
    data = content.encode("utf-8")
    info = tarfile.TarInfo(path)
    info.size = len(data)
    info.mode = 0o755 if path.endswith(".js") else 0o644
    archive.addfile(info, io.BytesIO(data))


def compute_sha512_sri(content: bytes) -> str:
    integrity = base64.b64encode(hashlib.sha512(content).digest()).decode("ascii")
    return f"sha512-{integrity}"


def build_registry_version_metadata(
    registry_url: str,
    name: str,
    version: str,
    tarball: bytes,
    metadata_extra: dict[str, object],
) -> dict[str, object]:
    return {
        "name": name,
        "version": version,
        "dist": {
            "tarball": f"{registry_url}tarballs/{name}/-/{name}-{version}.tgz",
            "integrity": compute_sha512_sri(tarball),
        },
        **metadata_extra,
    }


def write_package_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=4) + "\n", encoding="utf-8")


def read_json_file(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def seed_installed_package(project_dir: Path, package_name: str, version: str) -> None:
    package_dir = project_dir / "node_modules" / package_name
    write_package_json(
        package_dir / "package.json",
        {
            "name": package_name,
            "version": version,
        },
    )


def seed_node_modules_package(
    project_dir: Path,
    package_name: str,
    version: str,
    files: dict[str, str],
    package_json_extra: dict[str, object] | None = None,
) -> None:
    package_dir = project_dir / "node_modules" / package_name
    payload = {
        "name": package_name,
        "version": version,
        **(package_json_extra or {}),
    }
    write_package_json(package_dir / "package.json", payload)
    for rel_path, content in files.items():
        target = package_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def seed_lockfile_pair(project_dir: Path) -> None:
    (project_dir / "lpm.lock").write_text("placeholder lockfile\n", encoding="utf-8")
    (project_dir / "lpm.lockb").write_bytes(b"placeholder binary lockfile")


def seed_registry_lockfile_entries(
    project_dir: Path,
    entries: list[tuple[str, str, str]],
) -> None:
    lockfile_lines = [
        "[metadata]",
        "lockfile-version = 2",
        'resolved-with = "greedy-fusion"',
        "",
    ]
    for package_name, version, source_url in entries:
        lockfile_lines.extend(
            [
                "[[packages]]",
                f'name = "{package_name}"',
                f'version = "{version}"',
                f'source = "registry+{source_url}"',
                "",
            ]
        )

    (project_dir / "lpm.lock").write_text("\n".join(lockfile_lines), encoding="utf-8")
    (project_dir / "lpm.lockb").write_bytes(b"placeholder binary lockfile")


def seed_registry_lockfile(project_dir: Path, package_name: str, version: str, source_url: str) -> None:
    seed_registry_lockfile_entries(project_dir, [(package_name, version, source_url)])


def seed_store_verify_lockfile(
    project_dir: Path,
    entries: list[tuple[str, str, str]],
) -> None:
    lockfile_lines = [
        "[metadata]",
        "lockfile-version = 2",
        'resolved-with = "greedy-fusion"',
        "",
    ]
    for package_name, version, integrity in entries:
        tarball_name = package_name.split("/")[-1]
        lockfile_lines.extend(
            [
                "[[packages]]",
                f'name = "{package_name}"',
                f'version = "{version}"',
                'source = "registry+https://registry.npmjs.org"',
                f'integrity = "{integrity}"',
                f'tarball = "https://registry.npmjs.org/{tarball_name}/-/{tarball_name}-{version}.tgz"',
                "",
            ]
        )

    (project_dir / "lpm.lock").write_text("\n".join(lockfile_lines), encoding="utf-8")


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def seed_store_v1_entry(
    lpm_home: str,
    *,
    package_name: str,
    version: str,
    files: dict[str, str],
    integrity: str | None = None,
) -> Path:
    safe_name = package_name.replace("/", "+").replace("\\", "+")
    store_dir = Path(lpm_home) / "store" / "v1" / f"{safe_name}@{version}"
    write_package_json(
        store_dir / "package.json",
        {
            "name": package_name,
            "version": version,
        },
    )
    for rel_path, content in files.items():
        target = store_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    if integrity is not None:
        (store_dir / ".integrity").write_text(integrity, encoding="utf-8")
    return store_dir


def iso8601_n_secs_ago(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def seed_cache_prune_entry(
    lpm_home: str,
    *,
    entry_name: str,
    package_name: str,
    version: str,
    graph_key_digest_hex: str,
    object_segment: str,
    last_referenced_at: str,
) -> tuple[Path, Path]:
    link_root = Path(lpm_home) / "store" / "v2" / "links" / entry_name
    object_dir = Path(lpm_home) / "store" / "v2" / "objects" / object_segment
    write_package_json(
        link_root / "node_modules" / package_name / "package.json",
        {
            "name": package_name,
            "version": version,
        },
    )
    write_bytes(link_root / "node_modules" / package_name / "index.js", b"module.exports = 'ok'\n")
    write_package_json(
        object_dir / "package.json",
        {
            "name": package_name,
            "version": version,
        },
    )
    write_bytes(object_dir / ".integrity", object_segment.encode("utf-8"))
    write_bytes(object_dir / "marker.txt", f"{package_name}@{version}\n".encode("utf-8"))
    sidecar = {
        "schema": 1,
        "graph_key": entry_name,
        "name": package_name,
        "version": version,
        "source_sri": object_segment,
        "object_path": f"objects/{object_segment}",
        "graph_key_digest_hex": graph_key_digest_hex,
        "deps": [],
        "platform": {"os": "darwin", "cpu": "arm64"},
        "created_at": last_referenced_at,
        "last_referenced_at": last_referenced_at,
    }
    sidecar_path = link_root / ".lpm-link-meta.json"
    sidecar_path.write_text(
        json.dumps(sidecar, separators=(",", ":")),
        encoding="utf-8",
    )
    touched_at = datetime.fromisoformat(last_referenced_at.replace("Z", "+00:00")).timestamp()
    os.utime(sidecar_path, (touched_at, touched_at))
    return link_root, object_dir


def seed_cache_prune_project_link(project_dir: Path, package_name: str, link_root: Path) -> None:
    package_target = link_root / "node_modules" / package_name
    node_modules_dir = project_dir / "node_modules"
    node_modules_dir.mkdir(parents=True, exist_ok=True)
    link_path = node_modules_dir / package_name
    delete_path(link_path)
    link_path.symlink_to(package_target, target_is_directory=True)


def read_dependency_spec(path: Path, package_name: str) -> str | None:
    package_json = json.loads(path.read_text(encoding="utf-8"))
    dependencies = package_json.get("dependencies", {})
    return dependencies.get(package_name)


def read_installed_package_version(fixture: Path, package_name: str) -> str | None:
    package_json_path = fixture / "node_modules" / package_name / "package.json"
    if not package_json_path.exists():
        return None
    package_json = json.loads(package_json_path.read_text(encoding="utf-8"))
    return package_json.get("version")


def read_optional_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def resolve_global_shim_path(lpm_home: str, command_name: str) -> Path:
    bin_dir = Path(lpm_home) / "bin"
    for candidate in [
        bin_dir / command_name,
        bin_dir / f"{command_name}.cmd",
        bin_dir / f"{command_name}.exe",
    ]:
        if candidate.exists():
            return candidate
    return bin_dir / command_name


def run_command_result(
    label: str,
    cwd: Path,
    args: list[str],
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    log(f"{label}: {' '.join(args)}")
    result = subprocess.run(
        args,
        cwd=cwd,
        env=merged_env(extra_env),
        capture_output=True,
        text=True,
    )

    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)

    return result


def run_command(label: str, cwd: Path, args: list[str], extra_env: dict[str, str] | None = None) -> str:
    result = run_command_result(label, cwd, args, extra_env=extra_env)

    combined = result.stdout + result.stderr
    if result.returncode != 0:
        raise SmokeFailure(f"{label} failed with exit code {result.returncode}")
    return combined


def run_command_expect_failure(
    label: str,
    cwd: Path,
    args: list[str],
    extra_env: dict[str, str] | None = None,
) -> str:
    result = run_command_result(label, cwd, args, extra_env=extra_env)

    combined = result.stdout + result.stderr
    if result.returncode == 0:
        raise SmokeFailure(f"{label} unexpectedly succeeded")
    return combined


def run_interactive_command(
    label: str,
    cwd: Path,
    args: list[str],
    prompts: list[tuple[str, str]],
    extra_env: dict[str, str] | None = None,
    timeout_seconds: int = 600,
) -> str:
    log(f"{label}: {' '.join(args)}")
    env = merged_env(extra_env)
    pid, fd = pty.fork()

    if pid == 0:
        os.chdir(cwd)
        os.execvpe(args[0], args, env)

    transcript = ""
    next_prompt = 0
    deadline = time.monotonic() + timeout_seconds

    while True:
        if time.monotonic() > deadline:
            os.close(fd)
            os.kill(pid, 9)
            os.waitpid(pid, 0)
            raise SmokeFailure(f"{label} timed out waiting for interactive completion")

        ready, _, _ = select.select([fd], [], [], 0.1)
        if fd in ready:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                chunk = b""

            if chunk:
                decoded = chunk.decode("utf-8", errors="replace")
                transcript += decoded
                sys.stdout.write(decoded)
                sys.stdout.flush()

                while next_prompt < len(prompts) and prompts[next_prompt][0] in transcript:
                    os.write(fd, prompts[next_prompt][1].encode("utf-8"))
                    next_prompt += 1

        finished_pid, status = os.waitpid(pid, os.WNOHANG)
        if finished_pid == pid:
            os.close(fd)
            if os.WIFEXITED(status):
                exit_code = os.WEXITSTATUS(status)
            elif os.WIFSIGNALED(status):
                exit_code = 128 + os.WTERMSIG(status)
            else:
                exit_code = 1

            if exit_code != 0:
                raise SmokeFailure(f"{label} failed with exit code {exit_code}")
            return transcript


def parse_json_stdout(label: str, result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise SmokeFailure(
            f"{label}: expected JSON on stdout, got {result.stdout!r}"
        ) from error

    if not isinstance(payload, dict):
        raise SmokeFailure(f"{label}: expected top-level JSON object")
    return payload


def require_success_payload(
    label: str,
    result: subprocess.CompletedProcess[str],
    payload_key: str,
) -> dict[str, object]:
    if result.returncode != 0:
        raise SmokeFailure(f"{label} failed with exit code {result.returncode}")

    envelope = parse_json_stdout(label, result)
    if envelope.get("success") is not True:
        raise SmokeFailure(f"{label}: expected success=true JSON envelope")

    payload = envelope.get(payload_key)
    if not isinstance(payload, dict):
        raise SmokeFailure(f"{label}: expected `{payload_key}` object in JSON envelope")
    return payload


def require_security_approval_envelope(
    label: str,
    result: subprocess.CompletedProcess[str],
    expected_scope: str,
) -> dict[str, object]:
    if result.returncode == 0:
        raise SmokeFailure(f"{label}: unexpectedly succeeded")

    envelope = parse_json_stdout(label, result)
    if envelope.get("success") is not False:
        raise SmokeFailure(f"{label}: expected success=false JSON envelope")

    error = envelope.get("error")
    if not isinstance(error, dict):
        raise SmokeFailure(f"{label}: expected error object in JSON envelope")
    if error.get("code") != "SECURITY_APPROVAL_REQUIRED":
        raise SmokeFailure(
            f"{label}: expected SECURITY_APPROVAL_REQUIRED, got {error.get('code')!r}"
        )

    requested_scopes = error.get("requested_scopes")
    if not isinstance(requested_scopes, list) or expected_scope not in requested_scopes:
        raise SmokeFailure(
            f"{label}: expected requested_scopes to include {expected_scope!r}, got {requested_scopes!r}"
        )
    return envelope


def require_audit_event(
    rows: list[dict[str, object]],
    *,
    event: str,
    allowed: bool,
    expected_scope: str,
    context: str,
) -> dict[str, object]:
    for row in rows:
        candidate = row.get("payload") if isinstance(row.get("payload"), dict) else row
        scopes = candidate.get("scopes") if isinstance(candidate, dict) else None
        if (
            isinstance(candidate, dict)
            and candidate.get("event") == event
            and candidate.get("allowed") == allowed
            and isinstance(scopes, list)
            and expected_scope in scopes
        ):
            return candidate

    raise SmokeFailure(
        f"{context}: expected audit event {event!r} allowed={allowed} scope={expected_scope!r}"
    )


def require_contains(text: str, needle: str, context: str) -> None:
    if needle not in text:
        raise SmokeFailure(f"{context}: expected to find {needle!r}")


def require_not_contains(text: str, needle: str, context: str) -> None:
    if needle in text:
        raise SmokeFailure(f"{context}: did not expect to find {needle!r}")


def require_exists(path: Path) -> None:
    if not path.exists():
        raise SmokeFailure(f"expected path to exist: {path}")


def require_not_exists(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise SmokeFailure(f"expected path to be absent: {path}")


def require_directory_empty_or_absent(path: Path, context: str) -> None:
    if not path.exists():
        return
    if any(path.iterdir()):
        raise SmokeFailure(f"{context}: expected directory to be absent or empty, got entries under {path}")


def ensure_lpm_binary() -> None:
    run_command(
        "build lpm-cli",
        RUST_CLIENT_ROOT,
        [
            "cargo",
            "build",
            "--manifest-path",
            str(LPM_MANIFEST),
            "-p",
            "lpm-cli",
        ],
    )
    require_exists(LPM_BIN)


def scenario_workspace_basic() -> None:
    fixture = reset_workspace_fixture("basic")
    app_dir = fixture / "apps" / "app"

    output = run_command(
        "workspace/basic install from apps/app",
        app_dir,
        [str(LPM_BIN), "install"],
    )
    require_not_contains(output, "phantom dependency import", "workspace/basic install")

    node_output = run_command(
        "workspace/basic app entrypoint",
        app_dir,
        ["node", "index.js"],
    )
    require_contains(node_output, "workspace core ready", "workspace/basic node run")


def scenario_workspace_complex() -> None:
    fixture = reset_workspace_fixture("complex")
    web_dir = fixture / "apps" / "web"
    docs_dir = fixture / "apps" / "docs"

    web_output = run_command(
        "workspace/complex install from apps/web",
        web_dir,
        [str(LPM_BIN), "install"],
    )
    require_not_contains(web_output, "phantom dependency import", "workspace/complex web install")
    require_contains(
        run_command("workspace/complex web entrypoint", web_dir, ["node", "index.js"]),
        "complex workspace: [smoke-blue] web",
        "workspace/complex web node run",
    )

    docs_output = run_command(
        "workspace/complex install from apps/docs",
        docs_dir,
        [str(LPM_BIN), "install"],
    )
    require_not_contains(docs_output, "phantom dependency import", "workspace/complex docs install")
    require_contains(
        run_command("workspace/complex docs entrypoint", docs_dir, ["node", "index.js"]),
        "complex workspace: [smoke-blue] docs",
        "workspace/complex docs node run",
    )


def scenario_workspace_nested_boundary() -> None:
    fixture = reset_workspace_fixture("nested-boundary")
    app_dir = fixture / "apps" / "studio"

    output = run_command(
        "workspace/nested-boundary install from apps/studio",
        app_dir,
        [str(LPM_BIN), "install"],
    )
    require_not_contains(output, "phantom dependency import", "workspace/nested-boundary install")
    require_not_contains(output, "lodash", "workspace/nested-boundary install")
    require_contains(
        run_command("workspace/nested-boundary studio entrypoint", app_dir, ["node", "index.js"]),
        "nested boundary workspace: [boundary-accent] studio",
        "workspace/nested-boundary node run",
    )


def scenario_install_config_aware() -> None:
    fixture = reset_config_aware_fixture()

    output = run_interactive_command(
        "install/config-aware interactive add",
        fixture,
        [
            str(LPM_BIN),
            "add",
            "@lpm-registry/ex-source",
            "--path",
            "components",
            "--alias",
            "@/components",
            "--no-skills",
            "--no-editor-setup",
        ],
        prompts=[
            ("Which components do you want?", "\n"),
            ("Styling framework", "\n"),
            ("Include dark mode support?", "\n"),
        ],
    )

    require_contains(output, "Added @lpm-registry/ex-source@", "install/config-aware add output")
    require_exists(fixture / "components" / "button" / "index.js")
    require_exists(fixture / "components" / "dialog" / "index.js")
    require_exists(fixture / "components" / "styles" / "config.js")
    require_exists(fixture / "components" / "styles" / "dark-mode.css")
    require_exists(fixture / "components" / "lib" / "tokens.js")

    package_json_text = (fixture / "package.json").read_text(encoding="utf-8")
    require_contains(package_json_text, "@pandacss/dev", "install/config-aware package.json")


def scenario_install_remove() -> None:
    package_name = "smoke-remove-source"
    version = "1.0.0"
    registry_packages = [
        {
            "name": package_name,
            "dist_tags": {"latest": version},
            "versions": {
                version: {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {},
                    "files": {
                        "lpm.config.json": json.dumps(
                            {
                                "ecosystem": "js",
                                "files": [{"src": "Foo.tsx"}],
                            },
                            separators=(",", ":"),
                        ),
                        "Foo.tsx": "export const Foo = () => null;\n",
                    },
                }
            },
        }
    ]

    with MockRegistry(registry_packages) as registry, tempfile.TemporaryDirectory(
        prefix="lpm-smoke-home-"
    ) as lpm_home:
        fixture = reset_source_delivery_fixture()
        write_registry_npmrc(fixture, registry.registry_url)
        scenario_env = {"LPM_HOME": lpm_home, "LPM_NPM_ROUTE": "proxy"}

        add_result = run_command_result(
            "install/source-delivery add manifest-backed source package",
            fixture,
            [
                str(LPM_BIN),
                "--json",
                "add",
                package_name,
                "--yes",
                "--path",
                "custom/widgets",
                "--no-skills",
                "--no-editor-setup",
            ],
            extra_env=scenario_env,
        )
        if add_result.returncode != 0:
            raise SmokeFailure(
                "install/source-delivery add manifest-backed source package failed with exit code "
                f"{add_result.returncode}"
            )

        add_envelope = json.loads(add_result.stdout)
        if add_envelope.get("success") is not True:
            raise SmokeFailure("install/source-delivery add: expected success=true json envelope")
        if add_envelope.get("package", {}).get("name") != package_name:
            raise SmokeFailure("install/source-delivery add: package.name did not match the bare package spec")
        if add_envelope.get("install_path") != "custom/widgets":
            raise SmokeFailure("install/source-delivery add: expected install_path to be custom/widgets")

        require_exists(fixture / "custom" / "widgets" / "Foo.tsx")
        require_exists(fixture / ".lpm" / "added-sources.json")

        added_sources = json.loads((fixture / ".lpm" / "added-sources.json").read_text(encoding="utf-8"))
        recorded_files = (
            added_sources.get("packages", {})
            .get(package_name, {})
            .get("files", [])
        )
        if "custom/widgets/Foo.tsx" not in recorded_files:
            raise SmokeFailure(
                "install/source-delivery add: expected .lpm/added-sources.json to track custom/widgets/Foo.tsx"
            )

        remove_result = run_command_result(
            "install/source-delivery remove manifest-backed source package",
            fixture,
            [str(LPM_BIN), "remove", package_name, "--json"],
            extra_env=scenario_env,
        )
        if remove_result.returncode != 0:
            raise SmokeFailure(
                "install/source-delivery remove manifest-backed source package failed with exit code "
                f"{remove_result.returncode}"
            )

        remove_envelope = json.loads(remove_result.stdout)
        if remove_envelope.get("success") is not True:
            raise SmokeFailure("install/source-delivery remove: expected success=true json envelope")
        if "custom/widgets/Foo.tsx" not in remove_envelope.get("removed", []):
            raise SmokeFailure(
                "install/source-delivery remove: expected removed[] to include custom/widgets/Foo.tsx"
            )

        require_not_exists(fixture / "custom" / "widgets" / "Foo.tsx")
        require_not_exists(fixture / "custom" / "widgets")
        require_not_exists(fixture / "custom")
        require_not_exists(fixture / ".lpm" / "added-sources.json")


def scenario_install_project_discovery() -> None:
    nearest = reset_project_discovery_nearest_fixture()
    nested_cwd = nearest / "apps" / "web" / "src"

    run_command(
        "install/project-discovery nearest-ancestor from nested cwd",
        nested_cwd,
        [str(LPM_BIN), "install", "kleur"],
    )
    require_contains(
        (nearest / "package.json").read_text(encoding="utf-8"),
        '"kleur"',
        "install/project-discovery nearest-ancestor package.json",
    )
    require_exists(nearest / "node_modules")
    require_exists(nearest / "lpm.lock")
    require_exists(nearest / "lpm.lockb")
    require_not_exists(nearest / "apps" / "web" / "package.json")
    require_not_exists(nested_cwd / "package.json")

    fresh = reset_project_discovery_fresh_fixture()
    run_command(
        "install/project-discovery fresh-dir from empty cwd",
        fresh,
        [str(LPM_BIN), "install", "kleur"],
    )
    require_exists(fresh / "package.json")
    require_contains(
        (fresh / "package.json").read_text(encoding="utf-8"),
        '"kleur"',
        "install/project-discovery fresh-dir package.json",
    )
    require_exists(fresh / "node_modules")
    require_exists(fresh / "lpm.lock")
    require_exists(fresh / "lpm.lockb")


def scenario_install_engines() -> None:
    strict_fail = reset_engines_fixture("strict-fail", ENGINES_STRICT_FAIL_BASELINE_PACKAGE_JSON)
    failure_output = run_command_expect_failure(
        "install/engines strict-fail install",
        strict_fail,
        [str(LPM_BIN), "install", "kleur"],
    )
    require_contains(failure_output.lower(), "engine", "install/engines strict-fail output")
    require_contains(
        failure_output,
        "does not satisfy required",
        "install/engines strict-fail output",
    )
    require_not_contains(
        (strict_fail / "package.json").read_text(encoding="utf-8"),
        '"kleur"',
        "install/engines strict-fail package.json",
    )
    require_not_exists(strict_fail / "node_modules")
    require_not_exists(strict_fail / "lpm.lock")
    require_not_exists(strict_fail / "lpm.lockb")

    config_optout = reset_engines_fixture(
        "config-optout",
        ENGINES_CONFIG_OPTOUT_BASELINE_PACKAGE_JSON,
    )
    run_command(
        "install/engines config-optout install",
        config_optout,
        [str(LPM_BIN), "install", "kleur"],
    )
    require_contains(
        (config_optout / "package.json").read_text(encoding="utf-8"),
        '"kleur"',
        "install/engines config-optout package.json",
    )
    require_exists(config_optout / "node_modules")
    require_exists(config_optout / "lpm.lock")
    require_exists(config_optout / "lpm.lockb")


def scenario_workspace_targeting() -> None:
    fixture = reset_workspace_targeting_fixture()

    try:
        run_command(
            "workspace/targeting filtered install from root",
            fixture,
            [str(LPM_BIN), "install", "kleur", "--filter", "./apps/*", "-y"],
        )
        require_contains(
            (fixture / "apps" / "web" / "package.json").read_text(encoding="utf-8"),
            '"kleur"',
            "workspace/targeting web package.json",
        )
        require_contains(
            (fixture / "apps" / "docs" / "package.json").read_text(encoding="utf-8"),
            '"kleur"',
            "workspace/targeting docs package.json",
        )
        require_not_contains(
            (fixture / "packages" / "core" / "package.json").read_text(encoding="utf-8"),
            '"kleur"',
            "workspace/targeting core package.json",
        )

        no_match_output = run_command_expect_failure(
            "workspace/targeting no-match filter",
            fixture,
            [str(LPM_BIN), "install", "kleur", "--filter", "./missing/*", "--fail-if-no-match"],
        )
        require_contains(no_match_output.lower(), "match", "workspace/targeting no-match output")
    finally:
        reset_workspace_targeting_fixture()


def scenario_workspace_filter_controls() -> None:
    try:
        filter_prod_fixture = reset_workspace_targeting_fixture()
        seed_workspace_filter_prod_members(filter_prod_fixture)

        run_command(
            "workspace/filter-controls filter-prod run",
            filter_prod_fixture,
            [str(LPM_BIN), "run", "check", "--filter-prod", "...project-3"],
        )
        require_exists(filter_prod_fixture / "packages" / "project-1" / "ran-project-1.txt")
        require_exists(filter_prod_fixture / "packages" / "project-3" / "ran-project-3.txt")
        require_not_exists(filter_prod_fixture / "packages" / "project-2" / "ran-project-2.txt")
        require_not_exists(filter_prod_fixture / "packages" / "project-4" / "ran-project-4.txt")

        no_bail_fixture = reset_workspace_targeting_fixture()
        seed_workspace_no_bail_members(no_bail_fixture)

        no_bail_result = run_command_result(
            "workspace/filter-controls no-bail run",
            no_bail_fixture,
            [str(LPM_BIN), "run", "check", "--filter", "@smoke/no-bail-*", "--no-bail"],
        )
        if no_bail_result.returncode == 0:
            raise SmokeFailure("workspace/filter-controls no-bail run: expected non-zero exit when one member fails")
        require_exists(no_bail_fixture / "packages" / "no-bail-utils" / "ran-utils.txt")
        require_exists(no_bail_fixture / "packages" / "no-bail-core" / "ran-core.txt")
        require_exists(no_bail_fixture / "packages" / "no-bail-app" / "ran-app.txt")

        concurrency_fixture = reset_workspace_targeting_fixture()
        seed_workspace_concurrency_members(concurrency_fixture)

        run_command(
            "workspace/filter-controls workspace-concurrency run",
            concurrency_fixture,
            [
                str(LPM_BIN),
                "run",
                "check",
                "--filter",
                "@smoke/concurrency-*",
                "--workspace-concurrency",
                "1",
            ],
        )
        concurrency_state = read_json_file(concurrency_fixture / "concurrency-state.json")
        if concurrency_state.get("max") != 1:
            raise SmokeFailure(
                "workspace/filter-controls workspace-concurrency run: expected max recorded concurrency to be 1"
            )
    finally:
        reset_workspace_targeting_fixture()


def scenario_workspace_filter_selectors() -> None:
    try:
        changed_cli_fixture = reset_workspace_targeting_fixture()
        seed_workspace_changed_app_git_repo(changed_cli_fixture)

        changed_cli_result = run_command_result(
            "workspace/filter-selectors changed-files-ignore-pattern cli",
            changed_cli_fixture,
            [
                str(LPM_BIN),
                "filter",
                "[main]",
                "--changed-files-ignore-pattern",
                "**/README.md",
            ],
        )
        if changed_cli_result.returncode != 0:
            raise SmokeFailure(
                "workspace/filter-selectors changed-files-ignore-pattern cli failed with exit code "
                f"{changed_cli_result.returncode}"
            )
        if "changed-app" in selected_workspace_names(changed_cli_result.stdout):
            raise SmokeFailure(
                "workspace/filter-selectors changed-files-ignore-pattern cli: expected README-only changes to be ignored"
            )

        changed_config_fixture = reset_workspace_targeting_fixture()
        seed_workspace_changed_app_git_repo(changed_config_fixture, write_config=True)

        changed_config_result = run_command_result(
            "workspace/filter-selectors changed-files-ignore-pattern config",
            changed_config_fixture,
            [str(LPM_BIN), "filter", "[main]"],
        )
        if changed_config_result.returncode != 0:
            raise SmokeFailure(
                "workspace/filter-selectors changed-files-ignore-pattern config failed with exit code "
                f"{changed_config_result.returncode}"
            )
        if "changed-app" in selected_workspace_names(changed_config_result.stdout):
            raise SmokeFailure(
                "workspace/filter-selectors changed-files-ignore-pattern config: expected workspace config to ignore README-only changes"
            )

        test_pattern_fixture = reset_workspace_targeting_fixture()
        seed_workspace_test_pattern_git_repo(test_pattern_fixture)

        test_pattern_filter_result = run_command_result(
            "workspace/filter-selectors test-pattern filter",
            test_pattern_fixture,
            [str(LPM_BIN), "filter", "...[main]", "--test-pattern", "**/*.test.js"],
        )
        if test_pattern_filter_result.returncode != 0:
            raise SmokeFailure(
                "workspace/filter-selectors test-pattern filter failed with exit code "
                f"{test_pattern_filter_result.returncode}"
            )
        test_pattern_filter_names = selected_workspace_names(test_pattern_filter_result.stdout)
        if "test-pattern-utils" not in test_pattern_filter_names:
            raise SmokeFailure(
                "workspace/filter-selectors test-pattern filter: expected directly changed test-pattern-utils to stay selected"
            )
        if "test-pattern-app" in test_pattern_filter_names:
            raise SmokeFailure(
                "workspace/filter-selectors test-pattern filter: expected test-only changes to avoid dependent expansion"
            )

        test_pattern_run_result = run_command_result(
            "workspace/filter-selectors test-pattern affected run",
            test_pattern_fixture,
            [str(LPM_BIN), "run", "check", "--affected", "--test-pattern", "**/*.test.js"],
        )
        if test_pattern_run_result.returncode != 0:
            raise SmokeFailure(
                "workspace/filter-selectors test-pattern affected run failed with exit code "
                f"{test_pattern_run_result.returncode}"
            )
        require_exists(test_pattern_fixture / "packages" / "test-pattern-utils" / "ran-utils.txt")
        require_not_exists(test_pattern_fixture / "packages" / "test-pattern-app" / "ran-app.txt")

        combined_fixture = reset_workspace_targeting_fixture()
        seed_workspace_combined_name_path_members(combined_fixture)

        combined_result = run_command_result(
            "workspace/filter-selectors combined name+path filter",
            combined_fixture,
            [str(LPM_BIN), "filter", "@scope/*{./apps/scope-web}"],
        )
        if combined_result.returncode != 0:
            raise SmokeFailure(
                "workspace/filter-selectors combined name+path filter failed with exit code "
                f"{combined_result.returncode}"
            )
        combined_names = selected_workspace_names(combined_result.stdout)
        if "@scope/web" not in combined_names:
            raise SmokeFailure(
                "workspace/filter-selectors combined name+path filter: expected @scope/web to match both selector halves"
            )
        if "@scope/ui" in combined_names or "@other/admin" in combined_names:
            raise SmokeFailure(
                "workspace/filter-selectors combined name+path filter: expected non-intersecting members to stay excluded"
            )
    finally:
        reset_workspace_targeting_fixture()


def scenario_install_uninstall() -> None:
    fixture = reset_uninstall_fixture()
    seed_installed_package(fixture, "smoke-uninstall-dep", "1.0.0")
    seed_installed_package(fixture, "smoke-uninstall-dev", "1.0.0")
    seed_installed_package(fixture, "smoke-uninstall-optional", "1.0.0")
    seed_lockfile_pair(fixture)

    uninstall_result = run_command_result(
        "install/uninstall alias removes deps and lockfiles",
        fixture,
        [
            str(LPM_BIN),
            "un",
            "smoke-uninstall-dep",
            "smoke-uninstall-dev",
            "--json",
        ],
    )
    if uninstall_result.returncode != 0:
        raise SmokeFailure(
            "install/uninstall alias removes deps and lockfiles failed with exit code "
            f"{uninstall_result.returncode}"
        )

    uninstall_envelope = json.loads(uninstall_result.stdout)
    if uninstall_envelope.get("success") is not True:
        raise SmokeFailure("install/uninstall json envelope: expected success=true")
    if uninstall_envelope.get("removed") != ["smoke-uninstall-dep", "smoke-uninstall-dev"]:
        raise SmokeFailure(
            "install/uninstall json envelope: expected removed[] to list the dependency and devDependency"
        )

    manifest = read_json_file(fixture / "package.json")
    if manifest.get("dependencies") != {}:
        raise SmokeFailure("install/uninstall package.json: expected dependencies to be emptied")
    if manifest.get("devDependencies") != {}:
        raise SmokeFailure("install/uninstall package.json: expected devDependencies to be emptied")
    if manifest.get("peerDependencies", {}).get("smoke-uninstall-peer") != "^1.0.0":
        raise SmokeFailure("install/uninstall package.json: expected peerDependencies to stay untouched")
    if manifest.get("optionalDependencies", {}).get("smoke-uninstall-optional") != "^1.0.0":
        raise SmokeFailure("install/uninstall package.json: expected optionalDependencies to stay untouched")

    trusted_dependencies = (
        manifest.get("lpm", {}).get("trustedDependencies", {})
        if isinstance(manifest.get("lpm"), dict)
        else {}
    )
    if "smoke-uninstall-dep@1.0.0" not in trusted_dependencies:
        raise SmokeFailure(
            "install/uninstall package.json: expected lpm.trustedDependencies to keep the removed package entry"
        )

    require_not_exists(fixture / "node_modules" / "smoke-uninstall-dep")
    require_not_exists(fixture / "node_modules" / "smoke-uninstall-dev")
    require_exists(fixture / "node_modules" / "smoke-uninstall-optional")
    require_exists(fixture / "lpm.lock")
    require_exists(fixture / "lpm.lockb")


def scenario_install_upgrade() -> None:
    package_name = "smoke-upgrade-lib"
    registry_packages = [
        {
            "name": package_name,
            "dist_tags": {"latest": "1.4.0"},
            "versions": {
                "1.0.0": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {},
                    "files": {},
                },
                "1.4.0": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {},
                    "files": {},
                },
            },
        }
    ]

    with MockRegistry(registry_packages) as registry, tempfile.TemporaryDirectory(
        prefix="lpm-smoke-home-"
    ) as lpm_home:
        fixture = reset_upgrade_fixture()
        seed_registry_lockfile(fixture, package_name, "1.0.0", "https://registry.npmjs.org")
        seed_installed_package(fixture, package_name, "1.0.0")

        scenario_env = {"LPM_HOME": lpm_home, "LPM_NPM_ROUTE": "proxy"}

        dry_run_result = run_command_result(
            "install/upgrade dry-run npm candidate",
            fixture,
            [
                str(LPM_BIN),
                "--registry",
                registry.registry_url,
                "--insecure",
                "upgrade",
                "-y",
                "--dry-run",
                "--json",
            ],
            extra_env=scenario_env,
        )
        if dry_run_result.returncode != 0:
            raise SmokeFailure(
                f"install/upgrade dry-run npm candidate failed with exit code {dry_run_result.returncode}"
            )

        dry_run_envelope = json.loads(dry_run_result.stdout)
        if dry_run_envelope.get("success") is not True:
            raise SmokeFailure("install/upgrade dry-run json envelope: expected success=true")
        if dry_run_envelope.get("upgraded") != 1:
            raise SmokeFailure("install/upgrade dry-run json envelope: expected one npm upgrade candidate")
        if dry_run_envelope.get("packages", [{}])[0].get("name") != package_name:
            raise SmokeFailure("install/upgrade dry-run json envelope: expected smoke-upgrade-lib candidate")
        if dry_run_envelope.get("packages", [{}])[0].get("new_range") != "^1.4.0":
            raise SmokeFailure("install/upgrade dry-run json envelope: expected new_range ^1.4.0")

        run_command(
            "install/upgrade applies npm upgrade",
            fixture,
            [
                str(LPM_BIN),
                "--registry",
                registry.registry_url,
                "--insecure",
                "upgrade",
                "-y",
            ],
            extra_env=scenario_env,
        )

        if read_dependency_spec(fixture / "package.json", package_name) != "^1.4.0":
            raise SmokeFailure("install/upgrade package.json: expected smoke-upgrade-lib to rewrite to ^1.4.0")
        if read_installed_package_version(fixture, package_name) != "1.4.0":
            raise SmokeFailure("install/upgrade node_modules: expected smoke-upgrade-lib 1.4.0 to be installed")
        require_exists(fixture / "lpm.lock")
        require_exists(fixture / "lpm.lockb")
        require_contains(
            read_optional_text(fixture / "lpm.lock"),
            'version = "1.4.0"',
            "install/upgrade lpm.lock",
        )


def scenario_install_outdated() -> None:
    runtime_package = "smoke-outdated-dep"
    dev_package = "smoke-outdated-dev"
    registry_packages = [
        {
            "name": runtime_package,
            "dist_tags": {"latest": "2.0.0"},
            "versions": {
                "1.0.0": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {},
                    "files": {},
                },
                "1.4.0": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {},
                    "files": {},
                },
                "2.0.0": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {},
                    "files": {},
                },
            },
        },
        {
            "name": dev_package,
            "dist_tags": {"latest": "6.0.0"},
            "versions": {
                "5.0.0": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {},
                    "files": {},
                },
                "5.9.1": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {},
                    "files": {},
                },
                "6.0.0": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {},
                    "files": {},
                },
            },
        },
    ]

    with MockRegistry(registry_packages) as registry, tempfile.TemporaryDirectory(
        prefix="lpm-smoke-home-"
    ) as lpm_home:
        fixture = reset_outdated_fixture()
        seed_registry_lockfile_entries(
            fixture,
            [
                (runtime_package, "1.0.0", "https://registry.npmjs.org"),
                (dev_package, "5.0.0", "https://registry.npmjs.org"),
            ],
        )
        seed_installed_package(fixture, runtime_package, "1.0.0")
        seed_installed_package(fixture, dev_package, "5.0.0")

        scenario_env = {"LPM_HOME": lpm_home, "LPM_NPM_ROUTE": "proxy"}
        command_prefix = [
            str(LPM_BIN),
            "--registry",
            registry.registry_url,
            "--insecure",
            "outdated",
        ]

        outdated_result = run_command_result(
            "install/outdated json",
            fixture,
            command_prefix + ["--json"],
            extra_env=scenario_env,
        )
        if outdated_result.returncode != 0:
            raise SmokeFailure(
                f"install/outdated json failed with exit code {outdated_result.returncode}"
            )

        outdated_envelope = json.loads(outdated_result.stdout)
        if outdated_envelope.get("success") is not True:
            raise SmokeFailure("install/outdated json envelope: expected success=true")
        if outdated_envelope.get("schema_version") != 2:
            raise SmokeFailure("install/outdated json envelope: expected schema_version=2")
        if outdated_envelope.get("count") != 2 or outdated_envelope.get("outdated_count") != 2:
            raise SmokeFailure(
                "install/outdated json envelope: expected two outdated dependency entries"
            )

        packages = {
            package.get("name"): package for package in outdated_envelope.get("packages", [])
        }
        runtime_entry = packages.get(runtime_package)
        dev_entry = packages.get(dev_package)
        if runtime_entry is None or dev_entry is None:
            raise SmokeFailure(
                "install/outdated json envelope: expected both runtime and dev dependency rows"
            )

        if runtime_entry.get("section") != "dependencies":
            raise SmokeFailure("install/outdated json envelope: expected runtime section=dependencies")
        if runtime_entry.get("wanted") != "1.4.0" or runtime_entry.get("wanted_range") != "^1.0.0":
            raise SmokeFailure(
                "install/outdated json envelope: expected runtime wanted=1.4.0 and wanted_range=^1.0.0"
            )
        if runtime_entry.get("latest") != "2.0.0":
            raise SmokeFailure("install/outdated json envelope: expected runtime latest=2.0.0")

        if dev_entry.get("section") != "devDependencies":
            raise SmokeFailure("install/outdated json envelope: expected dev section=devDependencies")
        if dev_entry.get("wanted") != "5.9.1" or dev_entry.get("wanted_range") != "^5.0.0":
            raise SmokeFailure(
                "install/outdated json envelope: expected dev wanted=5.9.1 and wanted_range=^5.0.0"
            )
        if dev_entry.get("latest") != "6.0.0":
            raise SmokeFailure("install/outdated json envelope: expected dev latest=6.0.0")

        text_output = run_command(
            "install/outdated text",
            fixture,
            command_prefix,
            extra_env=scenario_env,
        )
        require_contains(text_output, "Section", "install/outdated text output")
        require_contains(text_output, "Wanted", "install/outdated text output")
        require_contains(text_output, runtime_package, "install/outdated text output")
        require_contains(text_output, "devDependencies", "install/outdated text output")


def scenario_install_outdated_skipped_private() -> None:
    private_package = "smoke-private-skip"
    skipped_private_reason = (
        "Packages without a recorded npm-public source were skipped to avoid leaking private names "
        "to registry.npmjs.org. Run `lpm install` to resolve sources, then re-run."
    )

    with MockRegistry([]) as registry, tempfile.TemporaryDirectory(
        prefix="lpm-smoke-home-"
    ) as lpm_home:
        fixture = reset_outdated_fixture()
        write_package_json(
            fixture / "package.json",
            {
                "name": "outdated-skipped-private-smoke",
                "private": True,
                "version": "0.0.0",
                "dependencies": {private_package: "^2.1.3"},
            },
        )
        seed_registry_lockfile_entries(
            fixture,
            [(private_package, "2.1.3", "https://npm.internal.example.com")],
        )
        seed_installed_package(fixture, private_package, "2.1.3")

        scenario_env = {"LPM_HOME": lpm_home, "LPM_NPM_ROUTE": "proxy"}
        command_prefix = [
            str(LPM_BIN),
            "--registry",
            registry.registry_url,
            "--insecure",
        ]

        original_manifest = read_optional_text(fixture / "package.json")

        outdated_result = run_command_result(
            "install/outdated skipped-private json",
            fixture,
            command_prefix + ["outdated", "--json"],
            extra_env=scenario_env,
        )
        if outdated_result.returncode != 0:
            raise SmokeFailure(
                "install/outdated skipped-private json failed with exit code "
                f"{outdated_result.returncode}"
            )

        outdated_envelope = json.loads(outdated_result.stdout)
        if outdated_envelope.get("success") is not True:
            raise SmokeFailure(
                "install/outdated skipped-private json envelope: expected success=true"
            )
        if outdated_envelope.get("count") != 0 or outdated_envelope.get("outdated_count") != 0:
            raise SmokeFailure(
                "install/outdated skipped-private json envelope: expected no reportable packages"
            )
        if outdated_envelope.get("packages") != []:
            raise SmokeFailure(
                "install/outdated skipped-private json envelope: expected packages=[]"
            )
        if outdated_envelope.get("skipped_private") != [private_package]:
            raise SmokeFailure(
                "install/outdated skipped-private json envelope: expected skipped_private to list the internal-registry package"
            )
        if outdated_envelope.get("skipped_private_reason") != skipped_private_reason:
            raise SmokeFailure(
                "install/outdated skipped-private json envelope: expected the shared no-leak reason string"
            )

        upgrade_result = run_command_result(
            "install/upgrade skipped-private dry-run json",
            fixture,
            command_prefix + ["upgrade", "-y", "--dry-run", "--json"],
            extra_env=scenario_env,
        )
        if upgrade_result.returncode != 0:
            raise SmokeFailure(
                "install/upgrade skipped-private dry-run json failed with exit code "
                f"{upgrade_result.returncode}"
            )

        upgrade_envelope = json.loads(upgrade_result.stdout)
        if upgrade_envelope.get("success") is not True:
            raise SmokeFailure(
                "install/upgrade skipped-private dry-run json envelope: expected success=true"
            )
        if upgrade_envelope.get("upgraded") != 0 or upgrade_envelope.get("packages") != []:
            raise SmokeFailure(
                "install/upgrade skipped-private dry-run json envelope: expected no upgrade candidates"
            )
        if upgrade_envelope.get("skipped_private") != [private_package]:
            raise SmokeFailure(
                "install/upgrade skipped-private dry-run json envelope: expected skipped_private to list the internal-registry package"
            )
        if upgrade_envelope.get("skipped_private_reason") != skipped_private_reason:
            raise SmokeFailure(
                "install/upgrade skipped-private dry-run json envelope: expected the shared no-leak reason string"
            )

        if read_optional_text(fixture / "package.json") != original_manifest:
            raise SmokeFailure(
                "install/upgrade skipped-private dry-run package.json: expected no manifest mutation"
            )

        leaked_paths = [path for path in registry.requested_paths() if private_package in path]
        if leaked_paths:
            raise SmokeFailure(
                "install/outdated skipped-private request log: expected no registry request for the internal package, got "
                + ", ".join(leaked_paths)
            )


def scenario_install_read_only_routing() -> None:
    package_name = "lodash.merge"
    version = "4.6.2"
    registry_packages = [
        {
            "name": package_name,
            "description": "Deep object merge helper",
            "dist_tags": {"latest": version},
            "versions": {
                version: {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {},
                    "files": {},
                }
            },
        }
    ]

    with MockRegistry(
        registry_packages,
        serve_proxy_metadata=False,
        serve_npm_search=True,
    ) as registry, tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as lpm_home:
        fixture = reset_read_only_routing_fixture()
        write_registry_npmrc(fixture, registry.registry_url)
        scenario_env = {"LPM_HOME": lpm_home}
        command_prefix = [
            str(LPM_BIN),
            "--registry",
            registry.registry_url,
            "--insecure",
        ]

        info_result = run_command_result(
            "install/read-only-routing info",
            fixture,
            command_prefix + ["info", package_name, "--json"],
            extra_env=scenario_env,
        )
        if info_result.returncode != 0:
            raise SmokeFailure(
                f"install/read-only-routing info failed with exit code {info_result.returncode}"
            )
        info_envelope = json.loads(info_result.stdout)
        if info_envelope.get("success") is not True or info_envelope.get("name") != package_name:
            raise SmokeFailure(
                "install/read-only-routing info: expected success=true and npm package metadata"
            )

        resolve_result = run_command_result(
            "install/read-only-routing resolve",
            fixture,
            command_prefix + ["resolve", package_name, "--json"],
            extra_env=scenario_env,
        )
        if resolve_result.returncode != 0:
            raise SmokeFailure(
                f"install/read-only-routing resolve failed with exit code {resolve_result.returncode}"
            )
        resolve_envelope = json.loads(resolve_result.stdout)
        resolved_packages = resolve_envelope.get("packages", [])
        if (
            resolve_envelope.get("success") is not True
            or len(resolved_packages) != 1
            or resolved_packages[0].get("package") != package_name
            or resolved_packages[0].get("version") != version
        ):
            raise SmokeFailure(
                "install/read-only-routing resolve: expected a single routed npm package result"
            )

        search_result = run_command_result(
            "install/read-only-routing search",
            fixture,
            command_prefix + ["search", package_name, "--json"],
            extra_env=scenario_env,
        )
        if search_result.returncode != 0:
            raise SmokeFailure(
                f"install/read-only-routing search failed with exit code {search_result.returncode}"
            )
        search_envelope = json.loads(search_result.stdout)
        search_packages = search_envelope.get("packages", [])
        if (
            search_envelope.get("success") is not True
            or search_envelope.get("count") != 1
            or len(search_packages) != 1
            or search_packages[0].get("name") != package_name
            or search_packages[0].get("latestVersion") != version
        ):
            raise SmokeFailure(
                "install/read-only-routing search: expected npm-style search results from the project registry"
            )

        download_result = run_command_result(
            "install/read-only-routing download",
            fixture,
            command_prefix
            + [
                "download",
                package_name,
                "--json",
                "--output",
                "downloaded-package",
            ],
            extra_env=scenario_env,
        )
        if download_result.returncode != 0:
            raise SmokeFailure(
                f"install/read-only-routing download failed with exit code {download_result.returncode}"
            )
        download_envelope = json.loads(download_result.stdout)
        if (
            download_envelope.get("success") is not True
            or download_envelope.get("package") != package_name
            or download_envelope.get("version") != version
        ):
            raise SmokeFailure(
                "install/read-only-routing download: expected routed npm tarball extraction metadata"
            )
        require_exists(fixture / "downloaded-package" / "package.json")


def scenario_workspace_uninstall() -> None:
    fixture = reset_workspace_targeting_fixture()
    root_manifest_path = fixture / "package.json"
    web_manifest_path = fixture / "apps" / "web" / "package.json"
    docs_manifest_path = fixture / "apps" / "docs" / "package.json"

    root_manifest = read_json_file(root_manifest_path)
    root_manifest.setdefault("dependencies", {})["smoke-uninstall-root"] = "^1.0.0"
    write_package_json(root_manifest_path, root_manifest)

    for manifest_path in [web_manifest_path, docs_manifest_path]:
        manifest = read_json_file(manifest_path)
        manifest.setdefault("dependencies", {})["smoke-uninstall-leaf"] = "^1.0.0"
        write_package_json(manifest_path, manifest)

    seed_installed_package(fixture, "smoke-uninstall-root", "1.0.0")
    seed_lockfile_pair(fixture)
    seed_installed_package(fixture / "apps" / "web", "smoke-uninstall-leaf", "1.0.0")
    seed_lockfile_pair(fixture / "apps" / "web")
    seed_installed_package(fixture / "apps" / "docs", "smoke-uninstall-leaf", "1.0.0")
    seed_lockfile_pair(fixture / "apps" / "docs")

    filtered_result = run_command_result(
        "workspace/uninstall filtered member only",
        fixture,
        [
            str(LPM_BIN),
            "uninstall",
            "smoke-uninstall-leaf",
            "--filter",
            "./apps/web",
            "--yes",
            "--json",
        ],
    )
    if filtered_result.returncode != 0:
        raise SmokeFailure(
            "workspace/uninstall filtered member only failed with exit code "
            f"{filtered_result.returncode}"
        )

    filtered_envelope = json.loads(filtered_result.stdout)
    if filtered_envelope.get("success") is not True:
        raise SmokeFailure("workspace/uninstall filtered json envelope: expected success=true")
    if len(filtered_envelope.get("target_set", [])) != 1:
        raise SmokeFailure("workspace/uninstall filtered json envelope: expected one targeted package.json")

    web_manifest = read_json_file(web_manifest_path)
    docs_manifest = read_json_file(docs_manifest_path)
    root_manifest = read_json_file(root_manifest_path)

    if "smoke-uninstall-leaf" in web_manifest.get("dependencies", {}):
        raise SmokeFailure("workspace/uninstall filtered package.json: expected web dependency to be removed")
    if docs_manifest.get("dependencies", {}).get("smoke-uninstall-leaf") != "^1.0.0":
        raise SmokeFailure("workspace/uninstall filtered package.json: expected docs dependency to stay untouched")
    if root_manifest.get("dependencies", {}).get("smoke-uninstall-root") != "^1.0.0":
        raise SmokeFailure("workspace/uninstall filtered package.json: expected root dependency to stay untouched")

    require_not_exists(fixture / "apps" / "web" / "node_modules" / "smoke-uninstall-leaf")
    require_exists(fixture / "apps" / "docs" / "node_modules" / "smoke-uninstall-leaf")
    require_exists(fixture / "apps" / "web" / "lpm.lock")
    require_exists(fixture / "apps" / "web" / "lpm.lockb")
    require_exists(fixture / "apps" / "docs" / "lpm.lock")
    require_exists(fixture / "apps" / "docs" / "lpm.lockb")
    require_exists(fixture / "lpm.lock")
    require_exists(fixture / "lpm.lockb")

    workspace_root_result = run_command_result(
        "workspace/uninstall root only",
        fixture,
        [str(LPM_BIN), "uninstall", "smoke-uninstall-root", "-w", "--json"],
    )
    if workspace_root_result.returncode != 0:
        raise SmokeFailure(
            f"workspace/uninstall root only failed with exit code {workspace_root_result.returncode}"
        )

    workspace_root_envelope = json.loads(workspace_root_result.stdout)
    if workspace_root_envelope.get("success") is not True:
        raise SmokeFailure("workspace/uninstall root json envelope: expected success=true")

    root_manifest = read_json_file(root_manifest_path)
    if root_manifest.get("dependencies") != {}:
        raise SmokeFailure("workspace/uninstall root package.json: expected root dependency to be removed")

    require_not_exists(fixture / "node_modules" / "smoke-uninstall-root")
    require_exists(fixture / "lpm.lock")
    require_exists(fixture / "lpm.lockb")
    if docs_manifest_path.read_text(encoding="utf-8") != json.dumps(docs_manifest, indent=4) + "\n":
        raise SmokeFailure("workspace/uninstall root package.json: expected docs manifest to stay unchanged")

    no_match_output = run_command_expect_failure(
        "workspace/uninstall no-match filter",
        fixture,
        [
            str(LPM_BIN),
            "uninstall",
            "smoke-uninstall-leaf",
            "--filter",
            "./missing/*",
            "--fail-if-no-match",
        ],
    )
    require_contains(no_match_output.lower(), "match", "workspace/uninstall no-match output")


def scenario_install_uninstall_global() -> None:
    package_name = "smoke-global-uninstall"
    version = "1.0.0"
    bin_name = "smoke-global-uninstall"
    registry_packages = [
        {
            "name": package_name,
            "dist_tags": {"latest": version},
            "versions": {
                version: {
                    "metadata_extra": {
                        "bin": {bin_name: "bin/cli.js"},
                        "dependencies": {},
                    },
                    "package_json_extra": {
                        "bin": {bin_name: "bin/cli.js"},
                    },
                    "files": {
                        "bin/cli.js": "#!/usr/bin/env node\nprocess.stdout.write('global uninstall smoke\\n')\n",
                    },
                }
            },
        }
    ]

    with MockRegistry(registry_packages) as registry, tempfile.TemporaryDirectory(
        prefix="lpm-smoke-home-"
    ) as lpm_home:
        fixture = reset_global_install_fixture("basic")
        baseline_package_json = (fixture / "package.json").read_text(encoding="utf-8")
        registry_env = {"LPM_HOME": lpm_home, "LPM_NPM_ROUTE": "proxy"}

        run_command(
            "install/uninstall-global install package",
            fixture,
            [
                str(LPM_BIN),
                "--registry",
                registry.registry_url,
                "--insecure",
                "install",
                "-g",
                f"{package_name}@{version}",
                "--no-skills",
                "--no-editor-setup",
            ],
            extra_env=registry_env,
        )

        global_manifest_path = Path(lpm_home) / "global" / "manifest.toml"
        global_install_path = Path(lpm_home) / "global" / "installs" / f"{package_name}@{version}"
        shim_path = resolve_global_shim_path(lpm_home, bin_name)

        require_exists(global_manifest_path)
        require_exists(global_install_path)
        require_exists(shim_path)
        require_contains(
            read_optional_text(global_manifest_path),
            package_name,
            "install/uninstall-global manifest after install",
        )

        run_command(
            "install/uninstall-global remove package",
            fixture,
            [str(LPM_BIN), "uninstall", "-g", package_name],
            extra_env=registry_env,
        )

        require_not_exists(global_install_path)
        require_not_exists(shim_path)
        require_not_contains(
            read_optional_text(global_manifest_path),
            package_name,
            "install/uninstall-global manifest after uninstall",
        )
        if (fixture / "package.json").read_text(encoding="utf-8") != baseline_package_json:
            raise SmokeFailure(
                "install/uninstall-global fixture package.json: expected local fixture manifest to stay unchanged"
            )


def scenario_install_save_policy() -> None:
    registry_packages = [
        {
            "name": "smoke-save-lib",
            "dist_tags": {"latest": "1.2.3"},
            "versions": {
                "1.2.3": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {},
                    "files": {},
                }
            },
        },
        {
            "name": "smoke-save-beta",
            "dist_tags": {"latest": "1.9.0", "beta": "2.0.0-beta.2"},
            "versions": {
                "1.9.0": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {},
                    "files": {},
                },
                "2.0.0-beta.2": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {},
                    "files": {},
                },
            },
        },
    ]

    with MockRegistry(registry_packages) as registry, tempfile.TemporaryDirectory(
        prefix="lpm-smoke-home-"
    ) as lpm_home:
        scenario_env = {"LPM_HOME": lpm_home}
        install_flags = [
            "--no-skills",
            "--no-editor-setup",
        ]

        default_fixture = reset_save_policy_fixture(
            "default",
            SAVE_POLICY_DEFAULT_BASELINE_PACKAGE_JSON,
        )
        write_registry_npmrc(default_fixture, registry.registry_url)
        run_command(
            "install/save-policy bare default",
            default_fixture,
            [str(LPM_BIN), "install", "smoke-save-lib", *install_flags],
            extra_env=scenario_env,
        )
        require_exists(default_fixture / "lpm.lock")
        require_exists(default_fixture / "lpm.lockb")
        require_exists(default_fixture / "node_modules")
        if read_dependency_spec(default_fixture / "package.json", "smoke-save-lib") != "^1.2.3":
            raise SmokeFailure("install/save-policy bare default: expected smoke-save-lib to save as ^1.2.3")

        default_fixture = reset_save_policy_fixture(
            "default",
            SAVE_POLICY_DEFAULT_BASELINE_PACKAGE_JSON,
        )
        write_registry_npmrc(default_fixture, registry.registry_url)
        run_command(
            "install/save-policy exact preserved",
            default_fixture,
            [str(LPM_BIN), "install", "smoke-save-lib@1.2.3", *install_flags],
            extra_env=scenario_env,
        )
        if read_dependency_spec(default_fixture / "package.json", "smoke-save-lib") != "1.2.3":
            raise SmokeFailure("install/save-policy exact preserved: expected smoke-save-lib to save as 1.2.3")

        default_fixture = reset_save_policy_fixture(
            "default",
            SAVE_POLICY_DEFAULT_BASELINE_PACKAGE_JSON,
        )
        write_registry_npmrc(default_fixture, registry.registry_url)
        run_command(
            "install/save-policy range preserved",
            default_fixture,
            [str(LPM_BIN), "install", "smoke-save-lib@^1.0.0", *install_flags],
            extra_env=scenario_env,
        )
        if read_dependency_spec(default_fixture / "package.json", "smoke-save-lib") != "^1.0.0":
            raise SmokeFailure("install/save-policy range preserved: expected smoke-save-lib to keep ^1.0.0")

        default_fixture = reset_save_policy_fixture(
            "default",
            SAVE_POLICY_DEFAULT_BASELINE_PACKAGE_JSON,
        )
        write_registry_npmrc(default_fixture, registry.registry_url)
        run_command(
            "install/save-policy latest tag",
            default_fixture,
            [str(LPM_BIN), "install", "smoke-save-lib@latest", *install_flags],
            extra_env=scenario_env,
        )
        if read_dependency_spec(default_fixture / "package.json", "smoke-save-lib") != "^1.2.3":
            raise SmokeFailure("install/save-policy latest tag: expected smoke-save-lib to save as ^1.2.3")

        default_fixture = reset_save_policy_fixture(
            "default",
            SAVE_POLICY_DEFAULT_BASELINE_PACKAGE_JSON,
        )
        write_registry_npmrc(default_fixture, registry.registry_url)
        run_command(
            "install/save-policy beta tag",
            default_fixture,
            [str(LPM_BIN), "install", "smoke-save-beta@beta", *install_flags],
            extra_env=scenario_env,
        )
        if read_dependency_spec(default_fixture / "package.json", "smoke-save-beta") != "2.0.0-beta.2":
            raise SmokeFailure("install/save-policy beta tag: expected smoke-save-beta to save exact prerelease from dist-tag")
        if read_installed_package_version(default_fixture, "smoke-save-beta") != "2.0.0-beta.2":
            raise SmokeFailure("install/save-policy beta tag: expected node_modules/smoke-save-beta to install the beta dist-tag target")

        default_fixture = reset_save_policy_fixture(
            "default",
            SAVE_POLICY_DEFAULT_BASELINE_PACKAGE_JSON,
        )
        write_registry_npmrc(default_fixture, registry.registry_url)
        run_command(
            "install/save-policy prerelease exact",
            default_fixture,
            [str(LPM_BIN), "install", "smoke-save-beta@2.0.0-beta.2", *install_flags],
            extra_env=scenario_env,
        )
        if read_dependency_spec(default_fixture / "package.json", "smoke-save-beta") != "2.0.0-beta.2":
            raise SmokeFailure("install/save-policy prerelease exact: expected smoke-save-beta to save exact prerelease")

        default_fixture = reset_save_policy_fixture(
            "default",
            SAVE_POLICY_DEFAULT_BASELINE_PACKAGE_JSON,
        )
        write_registry_npmrc(default_fixture, registry.registry_url)
        run_command(
            "install/save-policy wildcard preserved",
            default_fixture,
            [str(LPM_BIN), "install", "smoke-save-lib@*", *install_flags],
            extra_env=scenario_env,
        )
        if read_dependency_spec(default_fixture / "package.json", "smoke-save-lib") != "*":
            raise SmokeFailure("install/save-policy wildcard preserved: expected smoke-save-lib to keep *")

        existing_range_fixture = reset_save_policy_fixture(
            "existing-range",
            SAVE_POLICY_EXISTING_RANGE_BASELINE_PACKAGE_JSON,
        )
        write_registry_npmrc(existing_range_fixture, registry.registry_url)
        run_command(
            "install/save-policy existing range preserved",
            existing_range_fixture,
            [str(LPM_BIN), "install", "smoke-save-lib", *install_flags],
            extra_env=scenario_env,
        )
        if read_dependency_spec(existing_range_fixture / "package.json", "smoke-save-lib") != "~1.2.3":
            raise SmokeFailure("install/save-policy existing range preserved: expected smoke-save-lib to stay at ~1.2.3")


def scenario_install_peer_deps() -> None:
    registry_packages = [
        {
            "name": "optional-peer-host",
            "dist_tags": {"latest": "1.0.0"},
            "versions": {
                "1.0.0": {
                    "metadata_extra": {
                        "dependencies": {},
                        "peerDependencies": {"ghost-peer": "^1.0.0"},
                        "peerDependenciesMeta": {
                            "ghost-peer": {"optional": True}
                        },
                    },
                    "package_json_extra": {
                        "peerDependencies": {"ghost-peer": "^1.0.0"},
                        "peerDependenciesMeta": {
                            "ghost-peer": {"optional": True}
                        },
                    },
                    "files": {},
                }
            },
        },
        {
            "name": "required-peer-host",
            "dist_tags": {"latest": "1.0.0"},
            "versions": {
                "1.0.0": {
                    "metadata_extra": {
                        "dependencies": {},
                        "peerDependencies": {"missing-peer": "^1.0.0"},
                    },
                    "package_json_extra": {
                        "peerDependencies": {"missing-peer": "^1.0.0"},
                    },
                    "files": {},
                }
            },
        },
        {
            "name": "peer-consumer-a",
            "dist_tags": {"latest": "1.0.0"},
            "versions": {
                "1.0.0": {
                    "metadata_extra": {
                        "dependencies": {},
                        "peerDependencies": {"shared-peer": "^1.0.0"},
                    },
                    "package_json_extra": {
                        "peerDependencies": {"shared-peer": "^1.0.0"},
                    },
                    "files": {},
                }
            },
        },
        {
            "name": "peer-consumer-b",
            "dist_tags": {"latest": "1.0.0"},
            "versions": {
                "1.0.0": {
                    "metadata_extra": {
                        "dependencies": {},
                        "peerDependencies": {"shared-peer": "^2.0.0"},
                    },
                    "package_json_extra": {
                        "peerDependencies": {"shared-peer": "^2.0.0"},
                    },
                    "files": {},
                }
            },
        },
        {
            "name": "shared-peer",
            "dist_tags": {"latest": "2.0.0"},
            "versions": {
                "1.0.0": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {},
                    "files": {},
                },
                "2.0.0": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {},
                    "files": {},
                },
            },
        },
    ]

    with MockRegistry(registry_packages) as registry, tempfile.TemporaryDirectory(
        prefix="lpm-smoke-home-"
    ) as lpm_home:
        scenario_env = {"LPM_HOME": lpm_home, "LPM_STORE_VERSION": "v2"}
        install_flags = [
            "--no-skills",
            "--no-editor-setup",
            "--no-security-summary",
        ]

        optional_fixture = reset_peer_deps_fixture(
            "optional-missing",
            PEER_DEPS_OPTIONAL_MISSING_BASELINE_PACKAGE_JSON,
        )
        write_registry_npmrc(optional_fixture, registry.registry_url)
        optional_output = run_command(
            "install/peer-deps optional peer missing",
            optional_fixture,
            [str(LPM_BIN), "install", *install_flags],
            extra_env=scenario_env,
        )
        require_exists(optional_fixture / "node_modules" / "optional-peer-host" / "package.json")
        require_not_exists(optional_fixture / "node_modules" / "ghost-peer")
        require_not_contains(
            optional_output,
            "requires peer ghost-peer",
            "install/peer-deps optional peer output",
        )

        required_fixture = reset_peer_deps_fixture(
            "required-missing",
            PEER_DEPS_REQUIRED_MISSING_BASELINE_PACKAGE_JSON,
        )
        write_registry_npmrc(required_fixture, registry.registry_url)
        required_result = run_command_result(
            "install/peer-deps missing required peer json",
            required_fixture,
            [str(LPM_BIN), "--json", "install", *install_flags],
            extra_env=scenario_env,
        )
        if required_result.returncode != 0:
            raise SmokeFailure(
                "install/peer-deps missing required peer json failed with exit code "
                f"{required_result.returncode}"
            )
        required_envelope = parse_json_stdout(
            "install/peer-deps missing required peer json",
            required_result,
        )
        peer_issues = required_envelope.get("peer_issues")
        if required_envelope.get("success") is not True or not isinstance(peer_issues, dict):
            raise SmokeFailure(
                "install/peer-deps missing required peer json: expected success=true with peer_issues"
            )
        if (
            peer_issues.get("total_count") != 1
            or peer_issues.get("missing_count") != 1
            or peer_issues.get("bad_count") != 0
            or peer_issues.get("conflicts_count") != 0
        ):
            raise SmokeFailure(
                "install/peer-deps missing required peer json: expected one missing peer issue only"
            )
        missing_items = peer_issues.get("missing")
        if not isinstance(missing_items, list) or len(missing_items) != 1:
            raise SmokeFailure(
                "install/peer-deps missing required peer json: expected one missing[] entry"
            )
        missing_issue = missing_items[0]
        if not isinstance(missing_issue, dict):
            raise SmokeFailure(
                "install/peer-deps missing required peer json: missing[] entry must be an object"
            )
        if (
            missing_issue.get("package") != "required-peer-host"
            or missing_issue.get("peer") != "missing-peer"
            or missing_issue.get("required_range") != "^1.0.0"
            or missing_issue.get("resolved_version") is not None
        ):
            raise SmokeFailure(
                "install/peer-deps missing required peer json: unexpected missing peer payload"
            )
        if required_envelope.get("peer_conflicts") != []:
            raise SmokeFailure(
                "install/peer-deps missing required peer json: expected legacy peer_conflicts to stay empty"
            )
        require_exists(required_fixture / "node_modules" / "required-peer-host" / "package.json")
        require_not_exists(required_fixture / "node_modules" / "missing-peer")

        strict_fixture = reset_peer_deps_fixture(
            "required-missing",
            PEER_DEPS_REQUIRED_MISSING_BASELINE_PACKAGE_JSON,
        )
        write_registry_npmrc(strict_fixture, registry.registry_url)
        strict_output = run_command_expect_failure(
            "install/peer-deps strict missing required peer",
            strict_fixture,
            [
                str(LPM_BIN),
                "install",
                "--strict-peer-dependencies",
                *install_flags,
            ],
            extra_env=scenario_env,
        )
        require_contains(
            strict_output,
            "strict-peer-dependencies",
            "install/peer-deps strict missing required peer output",
        )
        require_contains(
            strict_output,
            "missing-peer",
            "install/peer-deps strict missing required peer output",
        )

        conflict_fixture = reset_peer_deps_fixture(
            "conflict",
            PEER_DEPS_CONFLICT_BASELINE_PACKAGE_JSON,
        )
        write_registry_npmrc(conflict_fixture, registry.registry_url)
        conflict_result = run_command_result(
            "install/peer-deps peer conflict json",
            conflict_fixture,
            [str(LPM_BIN), "--json", "install", *install_flags],
            extra_env=scenario_env,
        )
        if conflict_result.returncode != 0:
            raise SmokeFailure(
                "install/peer-deps peer conflict json failed with exit code "
                f"{conflict_result.returncode}"
            )
        conflict_envelope = parse_json_stdout(
            "install/peer-deps peer conflict json",
            conflict_result,
        )
        conflict_peer_issues = conflict_envelope.get("peer_issues")
        if conflict_envelope.get("success") is not True or not isinstance(conflict_peer_issues, dict):
            raise SmokeFailure(
                "install/peer-deps peer conflict json: expected success=true with peer_issues"
            )
        if (
            conflict_peer_issues.get("total_count") != 2
            or conflict_peer_issues.get("missing_count") != 0
            or conflict_peer_issues.get("bad_count") != 1
            or conflict_peer_issues.get("conflicts_count") != 1
        ):
            raise SmokeFailure(
                "install/peer-deps peer conflict json: expected one bad peer and one conflict"
            )
        bad_items = conflict_peer_issues.get("bad")
        conflict_items = conflict_peer_issues.get("conflicts")
        if not isinstance(bad_items, list) or len(bad_items) != 1:
            raise SmokeFailure(
                "install/peer-deps peer conflict json: expected one bad[] entry"
            )
        if not isinstance(conflict_items, list) or len(conflict_items) != 1:
            raise SmokeFailure(
                "install/peer-deps peer conflict json: expected one conflicts[] entry"
            )
        bad_issue = bad_items[0]
        if not isinstance(bad_issue, dict) or (
            bad_issue.get("package") != "peer-consumer-a"
            or bad_issue.get("peer") != "shared-peer"
            or bad_issue.get("resolved_version") != "2.0.0"
        ):
            raise SmokeFailure(
                "install/peer-deps peer conflict json: unexpected bad[] payload"
            )
        conflict_issue = conflict_items[0]
        if not isinstance(conflict_issue, dict) or (
            conflict_issue.get("canonical") != "shared-peer"
            or conflict_issue.get("chosen_version") != "2.0.0"
        ):
            raise SmokeFailure(
                "install/peer-deps peer conflict json: unexpected conflicts[] payload"
            )
        if conflict_envelope.get("peer_conflicts") != conflict_items:
            raise SmokeFailure(
                "install/peer-deps peer conflict json: expected peer_conflicts to match peer_issues.conflicts"
            )
        require_contains(
            read_optional_text(conflict_fixture / "lpm.lock"),
            "auto-isolated-peer-conflicts = true",
            "install/peer-deps peer conflict lpm.lock",
        )

        warm_output = run_command(
            "install/peer-deps peer conflict warm install",
            conflict_fixture,
            [str(LPM_BIN), "install", *install_flags],
            extra_env=scenario_env,
        )
        require_contains(
            warm_output,
            "Up to date",
            "install/peer-deps peer conflict warm install output",
        )

        explicit_hoisted_fixture = reset_peer_deps_fixture(
            "conflict",
            PEER_DEPS_CONFLICT_BASELINE_PACKAGE_JSON,
        )
        write_registry_npmrc(explicit_hoisted_fixture, registry.registry_url)
        run_command(
            "install/peer-deps peer conflict explicit hoisted",
            explicit_hoisted_fixture,
            [str(LPM_BIN), "install", "--linker", "hoisted", *install_flags],
            extra_env=scenario_env,
        )
        require_not_contains(
            read_optional_text(explicit_hoisted_fixture / "lpm.lock"),
            "auto-isolated-peer-conflicts = true",
            "install/peer-deps peer conflict explicit hoisted lpm.lock",
        )


def scenario_install_catalog() -> None:
    registry_packages = [
        {
            "name": "is-positive",
            "dist_tags": {"latest": "2.0.0"},
            "versions": {
                "1.0.0": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {},
                    "files": {},
                },
                "2.0.0": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {},
                    "files": {},
                },
            },
        }
    ]

    with MockRegistry(registry_packages) as registry, tempfile.TemporaryDirectory(
        prefix="lpm-smoke-home-"
    ) as lpm_home:
        scenario_env = {"LPM_HOME": lpm_home}
        install_flags = [
            "--no-skills",
            "--no-editor-setup",
            "--no-security-summary",
        ]

        manual_fixture = reset_catalog_fixture(
            "manual",
            CATALOG_MANUAL_BASELINE_PACKAGE_JSON,
        )
        write_registry_npmrc(manual_fixture, registry.registry_url)
        run_command(
            "install/catalog manual save policy",
            manual_fixture,
            [str(LPM_BIN), "install", "is-positive", *install_flags],
            extra_env=scenario_env,
        )
        if read_dependency_spec(manual_fixture / "package.json", "is-positive") != "^2.0.0":
            raise SmokeFailure(
                "install/catalog manual save policy: expected matching catalog entry to keep the raw save range"
            )

        force_default_fixture = reset_catalog_fixture(
            "manual",
            CATALOG_MANUAL_BASELINE_PACKAGE_JSON,
        )
        write_registry_npmrc(force_default_fixture, registry.registry_url)
        run_command(
            "install/catalog force default catalog flag",
            force_default_fixture,
            [str(LPM_BIN), "install", "--catalog", "is-positive", *install_flags],
            extra_env=scenario_env,
        )
        if read_dependency_spec(force_default_fixture / "package.json", "is-positive") != "catalog:":
            raise SmokeFailure(
                "install/catalog force default catalog flag: expected --catalog to save catalog:"
            )

        prefer_fixture = reset_catalog_fixture(
            "prefer",
            CATALOG_PREFER_BASELINE_PACKAGE_JSON,
        )
        write_registry_npmrc(prefer_fixture, registry.registry_url)
        run_command(
            "install/catalog prefer save policy",
            prefer_fixture,
            [str(LPM_BIN), "install", "is-positive", *install_flags],
            extra_env=scenario_env,
        )
        if read_dependency_spec(prefer_fixture / "package.json", "is-positive") != "catalog:":
            raise SmokeFailure(
                "install/catalog prefer save policy: expected matching catalog entry to save catalog:"
            )

        strict_fixture = reset_catalog_fixture(
            "strict",
            CATALOG_STRICT_BASELINE_PACKAGE_JSON,
        )
        write_registry_npmrc(strict_fixture, registry.registry_url)
        strict_output = run_command_expect_failure(
            "install/catalog strict mismatch failure",
            strict_fixture,
            [str(LPM_BIN), "install", "is-positive@2.0.0", *install_flags],
            extra_env=scenario_env,
        )
        require_contains(
            strict_output,
            "catalog",
            "install/catalog strict mismatch output",
        )
        require_contains(
            strict_output,
            "strict",
            "install/catalog strict mismatch output",
        )
        require_contains(
            strict_output,
            "is-positive@2.0.0",
            "install/catalog strict mismatch output",
        )
        require_not_contains(
            strict_output,
            "Installing 1 package",
            "install/catalog strict mismatch output",
        )
        require_not_contains(
            strict_output,
            "+ is-positive@2.0.0",
            "install/catalog strict mismatch output",
        )
        if read_dependency_spec(strict_fixture / "package.json", "is-positive") is not None:
            raise SmokeFailure(
                "install/catalog strict mismatch failure: expected package.json rollback with no dependency save"
            )
        require_not_exists(strict_fixture / "lpm.lock")
        require_not_exists(strict_fixture / "lpm.lockb")
        require_not_exists(strict_fixture / "node_modules")
        require_not_exists(strict_fixture / "node_modules" / "is-positive")

        named_fixture = reset_catalog_fixture(
            "named",
            CATALOG_NAMED_BASELINE_PACKAGE_JSON,
        )
        write_registry_npmrc(named_fixture, registry.registry_url)
        run_command(
            "install/catalog named catalog flag",
            named_fixture,
            [str(LPM_BIN), "install", "--catalog=testing", "is-positive", *install_flags],
            extra_env=scenario_env,
        )
        if read_dependency_spec(named_fixture / "package.json", "is-positive") != "catalog:testing":
            raise SmokeFailure(
                "install/catalog named catalog flag: expected --catalog=<name> to save catalog:<name>"
            )

        cleanup_fixture = reset_catalog_fixture(
            "cleanup",
            CATALOG_CLEANUP_BASELINE_PACKAGE_JSON,
        )
        write_registry_npmrc(cleanup_fixture, registry.registry_url)
        run_command(
            "install/catalog cleanupUnusedCatalogs package.json",
            cleanup_fixture,
            [str(LPM_BIN), "install", *install_flags],
            extra_env=scenario_env,
        )
        cleanup_manifest = read_json_file(cleanup_fixture / "package.json")
        cleanup_catalogs = cleanup_manifest.get("catalogs")
        if not isinstance(cleanup_catalogs, dict):
            raise SmokeFailure(
                "install/catalog cleanupUnusedCatalogs package.json: expected catalogs object after install"
            )
        default_catalog = cleanup_catalogs.get("default")
        if not isinstance(default_catalog, dict):
            raise SmokeFailure(
                "install/catalog cleanupUnusedCatalogs package.json: expected default catalog after install"
            )
        if default_catalog.get("is-positive") != "^2.0.0":
            raise SmokeFailure(
                "install/catalog cleanupUnusedCatalogs package.json: expected used catalog entry to stay intact"
            )
        if "unused-lib" in default_catalog:
            raise SmokeFailure(
                "install/catalog cleanupUnusedCatalogs package.json: expected unused catalog entry to be pruned"
            )

        pnpm_workspace_fixture = reset_catalog_fixture(
            "pnpm-workspace",
            CATALOG_PNPM_WORKSPACE_BASELINE_PACKAGE_JSON,
            pnpm_workspace_yaml=CATALOG_PNPM_WORKSPACE_BASELINE_YAML,
        )
        write_registry_npmrc(pnpm_workspace_fixture, registry.registry_url)
        run_command(
            "install/catalog pnpm-workspace catalog resolution",
            pnpm_workspace_fixture,
            [str(LPM_BIN), "install", *install_flags],
            extra_env=scenario_env,
        )
        if read_installed_package_version(pnpm_workspace_fixture, "is-positive") != "2.0.0":
            raise SmokeFailure(
                "install/catalog pnpm-workspace catalog resolution: expected catalog: dependency to resolve through pnpm-workspace.yaml"
            )
        workspace_yaml = read_optional_text(pnpm_workspace_fixture / "pnpm-workspace.yaml")
        require_contains(
            workspace_yaml,
            "is-positive: ^2.0.0",
            "install/catalog pnpm-workspace.yaml after cleanup",
        )
        require_not_contains(
            workspace_yaml,
            "unused-lib",
            "install/catalog pnpm-workspace.yaml after cleanup",
        )


def scenario_install_script_policy() -> None:
    registry_packages = [
        {
            "name": "smoke-script-green",
            "dist_tags": {"latest": "1.0.0"},
            "versions": {
                "1.0.0": {
                    "metadata_extra": {
                        "dependencies": {},
                        "scripts": {"postinstall": "node build.js"},
                    },
                    "package_json_extra": {
                        "scripts": {"postinstall": "node build.js"},
                    },
                    "files": {
                        "build.js": "require(\"node:fs\").writeFileSync(\"script-ran.txt\", \"green\\n\")\n",
                    },
                }
            },
        },
        {
            "name": "smoke-script-amber",
            "dist_tags": {"latest": "1.0.0"},
            "versions": {
                "1.0.0": {
                    "metadata_extra": {
                        "dependencies": {},
                        "scripts": {"postinstall": "node install.js"},
                    },
                    "package_json_extra": {
                        "scripts": {"postinstall": "node install.js"},
                    },
                    "files": {
                        "install.js": "require(\"node:fs\").writeFileSync(\"script-ran.txt\", \"amber\\n\")\n",
                    },
                }
            },
        },
    ]

    with MockRegistry(registry_packages) as registry, tempfile.TemporaryDirectory(
        prefix="lpm-smoke-home-"
    ) as lpm_home:
        scenario_env = {"LPM_HOME": lpm_home}
        install_flags = [
            "--no-skills",
            "--no-editor-setup",
            "--no-security-summary",
        ]

        default_deny_fixture = reset_script_policy_fixture("default-deny", "smoke-script-green")
        write_registry_npmrc(default_deny_fixture, registry.registry_url)
        default_deny_output = run_command(
            "install/script-policy default deny",
            default_deny_fixture,
            [str(LPM_BIN), "install", *install_flags],
            extra_env=scenario_env,
        )
        require_not_exists(default_deny_fixture / "node_modules" / "smoke-script-green" / "script-ran.txt")
        if not (
            "approve-scripts" in default_deny_output
            or "lifecycle script" in default_deny_output.lower()
            or "scripts" in default_deny_output.lower()
        ):
            raise SmokeFailure(
                "install/script-policy default deny output: expected a script-policy hint"
            )

        allow_fixture = reset_script_policy_fixture("manifest-allow", "smoke-script-green")
        write_registry_npmrc(allow_fixture, registry.registry_url)
        write_package_json(
            allow_fixture / "package.json",
            {
                "name": "script-policy-smoke",
                "private": True,
                "version": "0.0.0",
                "dependencies": {"smoke-script-green": "^1.0.0"},
                "lpm": {"scriptPolicy": "allow"},
            },
        )
        allow_result = run_command_result(
            "install/script-policy manifest allow requires approval",
            allow_fixture,
            [
                str(LPM_BIN),
                "--json",
                "install",
                "--auto-build",
                *install_flags,
            ],
            extra_env=scenario_env,
        )
        allow_envelope = require_security_approval_envelope(
            "install/script-policy manifest allow requires approval",
            allow_result,
            "scripts-allow",
        )
        if (
            allow_envelope.get("error", {}).get("suggested_command")
            != "lpm security unlock scripts-allow --project . --ttl 10m"
        ):
            raise SmokeFailure(
                "install/script-policy manifest allow suggested command: expected project unlock hint"
            )
        require_not_exists(allow_fixture / "node_modules" / "smoke-script-green" / "script-ran.txt")

        triage_fixture = reset_script_policy_fixture("manifest-triage", "smoke-script-amber")
        write_registry_npmrc(triage_fixture, registry.registry_url)
        write_package_json(
            triage_fixture / "package.json",
            {
                "name": "script-policy-smoke",
                "private": True,
                "version": "0.0.0",
                "dependencies": {"smoke-script-amber": "^1.0.0"},
                "lpm": {"scriptPolicy": "triage"},
            },
        )
        triage_result = run_command_result(
            "install/script-policy manifest triage requires approval",
            triage_fixture,
            [
                str(LPM_BIN),
                "--json",
                "install",
                "--auto-build",
                *install_flags,
            ],
            extra_env=scenario_env,
        )
        require_security_approval_envelope(
            "install/script-policy manifest triage requires approval",
            triage_result,
            "scripts-triage",
        )
        require_not_exists(triage_fixture / "node_modules" / "smoke-script-amber" / "script-ran.txt")
        require_not_exists(triage_fixture / ".lpm" / "build-state.json")


def scenario_install_offline_integrity() -> None:
    package_name = "smoke-offline-lib"
    version = "1.0.0"
    route_path = f"/{package_name}-{version}.tgz"
    tarball = build_package_tarball(package_name, version, {}, {})
    tarball_sri = compute_sha512_sri(tarball)
    server = LocalRegistryServer({route_path: ("application/octet-stream", tarball)})
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        host, port = server.server_address
        tarball_url = f"http://{host}:{port}{route_path}"
        install_flags = [
            "--no-skills",
            "--no-editor-setup",
            "--no-security-summary",
        ]

        with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as lpm_home:
            scenario_env = {"LPM_HOME": lpm_home}

            strict_fixture = reset_offline_integrity_fixture()
            write_package_json(
                strict_fixture / "package.json",
                {
                    "name": "offline-integrity-smoke",
                    "private": True,
                    "version": "0.0.0",
                    "dependencies": {package_name: tarball_url},
                },
            )
            strict_output = run_command_expect_failure(
                "install/offline-integrity strict-integrity rejects undeclared sri",
                strict_fixture,
                [str(LPM_BIN), "install", "--strict-integrity", *install_flags],
                extra_env=scenario_env,
            )
            require_contains(
                strict_output,
                "strict-integrity",
                "install/offline-integrity strict-integrity output",
            )
            require_contains(
                strict_output,
                "sha512",
                "install/offline-integrity strict-integrity output",
            )
            require_not_exists(strict_fixture / "node_modules" / package_name)

            seeded_fixture = reset_offline_integrity_fixture()
            write_package_json(
                seeded_fixture / "package.json",
                {
                    "name": "offline-integrity-smoke",
                    "private": True,
                    "version": "0.0.0",
                    "dependencies": {package_name: f"{tarball_url}#{tarball_sri}"},
                },
            )
            run_command(
                "install/offline-integrity online seed",
                seeded_fixture,
                [str(LPM_BIN), "install", *install_flags],
                extra_env=scenario_env,
            )
            require_exists(seeded_fixture / "lpm.lock")
            require_exists(seeded_fixture / "lpm.lockb")
            require_exists(seeded_fixture / "node_modules" / package_name)
            require_contains(
                read_optional_text(seeded_fixture / "lpm.lock"),
                tarball_sri,
                "install/offline-integrity lockfile integrity",
            )

            delete_path(seeded_fixture / "node_modules")
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

            run_command(
                "install/offline-integrity offline relink",
                seeded_fixture,
                [str(LPM_BIN), "install", "--offline", "--strict-integrity", *install_flags],
                extra_env=scenario_env,
            )
            require_exists(seeded_fixture / "node_modules" / package_name)

            delete_path(seeded_fixture / "node_modules")
            with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-cold-") as cold_home:
                cold_output = run_command_expect_failure(
                    "install/offline-integrity cold offline fails without store",
                    seeded_fixture,
                    [str(LPM_BIN), "install", "--offline", "--strict-integrity", *install_flags],
                    extra_env={"LPM_HOME": cold_home},
                )
            if not any(
                needle in cold_output.lower()
                for needle in ["offline", "store", "lockfile", "missing"]
            ):
                raise SmokeFailure(
                    "install/offline-integrity cold offline failure: expected actionable offline/store message"
                )
    finally:
        if thread.is_alive():
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def scenario_install_minimum_release_age() -> None:
    package_name = "smoke-release-age"
    version = "1.0.0"
    registry_packages = [
        {
            "name": package_name,
            "dist_tags": {"latest": version},
            "versions": {
                version: {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {},
                    "files": {},
                    "published_at": iso8601_n_secs_ago(3600),
                }
            },
        }
    ]

    with MockRegistry(registry_packages) as registry, tempfile.TemporaryDirectory(
        prefix="lpm-smoke-home-"
    ) as lpm_home:
        scenario_env = {"LPM_HOME": lpm_home}
        install_flags = [
            "--no-skills",
            "--no-editor-setup",
            "--no-security-summary",
        ]

        blocked_fixture = reset_minimum_release_age_fixture()
        write_registry_npmrc(blocked_fixture, registry.registry_url)
        write_package_json(
            blocked_fixture / "package.json",
            {
                "name": "minimum-release-age-smoke",
                "private": True,
                "version": "0.0.0",
                "dependencies": {package_name: version},
            },
        )
        blocked_output = run_command_expect_failure(
            "install/minimum-release-age default cooldown blocks recent publish",
            blocked_fixture,
            [str(LPM_BIN), "install", *install_flags],
            extra_env=scenario_env,
        )
        if not any(
            needle in blocked_output
            for needle in ["blocked by minimumReleaseAge", "published too recently"]
        ):
            raise SmokeFailure(
                "install/minimum-release-age default block: expected cooldown message"
            )

        allow_new_fixture = reset_minimum_release_age_fixture()
        write_registry_npmrc(allow_new_fixture, registry.registry_url)
        write_package_json(
            allow_new_fixture / "package.json",
            {
                "name": "minimum-release-age-smoke",
                "private": True,
                "version": "0.0.0",
                "dependencies": {package_name: version},
            },
        )
        allow_new_result = run_command_result(
            "install/minimum-release-age allow-new requires approval",
            allow_new_fixture,
            [str(LPM_BIN), "--json", "install", "--allow-new", *install_flags],
            extra_env=scenario_env,
        )
        require_security_approval_envelope(
            "install/minimum-release-age allow-new requires approval",
            allow_new_result,
            "cooldown-bypass",
        )
        require_not_exists(allow_new_fixture / "node_modules")

        zero_fixture = reset_minimum_release_age_fixture()
        write_registry_npmrc(zero_fixture, registry.registry_url)
        write_package_json(
            zero_fixture / "package.json",
            {
                "name": "minimum-release-age-smoke",
                "private": True,
                "version": "0.0.0",
                "dependencies": {package_name: version},
            },
        )
        zero_result = run_command_result(
            "install/minimum-release-age zero requires approval",
            zero_fixture,
            [str(LPM_BIN), "--json", "install", "--min-release-age=0", *install_flags],
            extra_env=scenario_env,
        )
        require_security_approval_envelope(
            "install/minimum-release-age zero requires approval",
            zero_result,
            "cooldown-bypass",
        )
        require_not_exists(zero_fixture / "node_modules")

        proposal_fixture = reset_minimum_release_age_fixture()
        write_registry_npmrc(proposal_fixture, registry.registry_url)
        write_package_json(
            proposal_fixture / "package.json",
            {
                "name": "minimum-release-age-smoke",
                "private": True,
                "version": "0.0.0",
                "dependencies": {package_name: version},
                "lpm": {"minimumReleaseAge": 0},
            },
        )
        proposal_result = run_command_result(
            "install/minimum-release-age package.json proposal requires approval",
            proposal_fixture,
            [str(LPM_BIN), "--json", "install", *install_flags],
            extra_env=scenario_env,
        )
        proposal_envelope = require_security_approval_envelope(
            "install/minimum-release-age package.json proposal requires approval",
            proposal_result,
            "cooldown-bypass",
        )
        if (
            proposal_envelope.get("error", {}).get("suggested_command")
            != "lpm security unlock cooldown-bypass --project . --ttl 10m"
        ):
            raise SmokeFailure(
                "install/minimum-release-age package.json proposal suggested command: expected project unlock hint"
            )
        require_not_exists(proposal_fixture / "node_modules")

        pinned_fixture = reset_minimum_release_age_fixture()
        write_registry_npmrc(pinned_fixture, registry.registry_url)
        pinned_output = run_command_expect_failure(
            "install/minimum-release-age explicit pin still blocked",
            pinned_fixture,
            [str(LPM_BIN), "install", f"{package_name}@{version}", *install_flags],
            extra_env=scenario_env,
        )
        if not any(
            needle in pinned_output
            for needle in ["blocked by minimumReleaseAge", "published too recently"]
        ):
            raise SmokeFailure(
                "install/minimum-release-age explicit pin: expected cooldown message"
            )
        require_not_contains(
            read_optional_text(pinned_fixture / "package.json"),
            package_name,
            "install/minimum-release-age pinned package.json",
        )


def scenario_install_security() -> None:
    package_name = "smoke-security-release"
    version = "1.0.0"
    install_flags = [
        "--no-skills",
        "--no-editor-setup",
        "--no-security-summary",
    ]
    registry_packages = [
        {
            "name": package_name,
            "dist_tags": {"latest": version},
            "versions": {
                version: {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {},
                    "files": {},
                    "published_at": iso8601_n_secs_ago(3600),
                }
            },
        }
    ]

    with MockRegistry(registry_packages) as registry, tempfile.TemporaryDirectory(
        prefix="lpm-smoke-home-"
    ) as lpm_home:
        scenario_env = {
            "LPM_HOME": lpm_home,
            "LPM_FORCE_FILE_AUTH": "1",
            "LPM_FORCE_FILE_VAULT": "1",
        }
        audit_path = Path(lpm_home) / "security" / "audit.jsonl"

        status_fixture = reset_security_fixture("status")
        status_result = run_command_result(
            "install/security status project json",
            status_fixture,
            [str(LPM_BIN), "--json", "security", "status"],
            extra_env=scenario_env,
        )
        status = require_success_payload(
            "install/security status project json",
            status_result,
            "status",
        )
        if status.get("target") != "project":
            raise SmokeFailure("install/security status project json: expected target=project")
        expected_project_root = normalize_test_path(str(status_fixture.resolve()))
        if normalize_test_path(str(status.get("project_root"))) != expected_project_root:
            raise SmokeFailure(
                "install/security status project json: expected project_root to match fixture"
            )
        effective_floor = status.get("effective_floor")
        if not isinstance(effective_floor, dict):
            raise SmokeFailure("install/security status project json: expected effective_floor object")
        if effective_floor.get("script_policy") != "deny":
            raise SmokeFailure("install/security status project json: expected script_policy=deny")
        if effective_floor.get("minimum_release_age_secs") != 86400:
            raise SmokeFailure(
                "install/security status project json: expected minimum_release_age_secs=86400"
            )
        if effective_floor.get("sandbox_mode") != "default":
            raise SmokeFailure("install/security status project json: expected sandbox_mode=default")
        if effective_floor.get("sandbox_allow_degraded") is not False:
            raise SmokeFailure(
                "install/security status project json: expected sandbox_allow_degraded=false"
            )
        if effective_floor.get("sigstore_verify") != "deny":
            raise SmokeFailure("install/security status project json: expected sigstore_verify=deny")
        expected_approved_posture_path = normalize_test_path(
            str((Path(lpm_home) / "security" / "approved-posture.json").resolve())
        )
        if normalize_test_path(str(status.get("approved_posture_path"))) != expected_approved_posture_path:
            raise SmokeFailure(
                "install/security status project json: expected approved_posture_path inside isolated LPM_HOME"
            )

        status_human = run_command(
            "install/security status project human",
            status_fixture,
            [str(LPM_BIN), "security", "status", "--project", "."],
            extra_env=scenario_env,
        )
        for needle, context in [
            ("Security Floor", "header"),
            ("approved-posture", "approved posture field"),
            ("managed-policy", "managed policy field"),
            ("Runtime Overrides", "runtime overrides header"),
            ("Active Unlocks", "active unlocks header"),
        ]:
            require_contains(status_human, needle, f"install/security status human {context}")

        global_status_result = run_command_result(
            "install/security status global json",
            status_fixture,
            [str(LPM_BIN), "--json", "security", "status", "--global"],
            extra_env=scenario_env,
        )
        global_status = require_success_payload(
            "install/security status global json",
            global_status_result,
            "status",
        )
        if global_status.get("target") != "global":
            raise SmokeFailure("install/security status global json: expected target=global")

        default_lock_result = run_command_result(
            "install/security lock default json",
            status_fixture,
            [str(LPM_BIN), "--json", "security", "lock", "default"],
            extra_env=scenario_env,
        )
        default_lock = parse_json_stdout(
            "install/security lock default json",
            default_lock_result,
        )
        if default_lock_result.returncode != 0:
            raise SmokeFailure("install/security lock default json: expected success exit code")
        if default_lock.get("success") is not True:
            raise SmokeFailure("install/security lock default json: expected success=true")
        if default_lock.get("target") != "global":
            raise SmokeFailure("install/security lock default json: expected target=global")
        if default_lock.get("scope") != "default":
            raise SmokeFailure("install/security lock default json: expected scope=default")
        if default_lock.get("revocations") != []:
            raise SmokeFailure("install/security lock default json: expected empty revocations")

        override_status_result = run_command_result(
            "install/security status env override json",
            status_fixture,
            [str(LPM_BIN), "--json", "security", "status", "--project", "."],
            extra_env={**scenario_env, "LPM_PROVENANCE_ENFORCE": "warn"},
        )
        override_status = require_success_payload(
            "install/security status env override json",
            override_status_result,
            "status",
        )
        runtime_overrides = override_status.get("active_runtime_overrides")
        if not isinstance(runtime_overrides, list) or not any(
            isinstance(row, dict)
            and row.get("control") == "sigstore.verify"
            and row.get("value") == "warn"
            and row.get("source") == "LPM_PROVENANCE_ENFORCE"
            for row in runtime_overrides
        ):
            raise SmokeFailure(
                "install/security status env override json: expected sigstore override from LPM_PROVENANCE_ENFORCE"
            )

        config_fixture = reset_security_fixture("config")
        config_commands = [
            (
                "install/security config scripts allow requires approval",
                [str(LPM_BIN), "--json", "config", "scripts", "--set", "allow"],
                "scripts-allow",
            ),
            (
                "install/security config release-age zero requires approval",
                [str(LPM_BIN), "--json", "config", "release-age", "--set", "0"],
                "cooldown-bypass",
            ),
            (
                "install/security config sandbox none requires approval",
                [str(LPM_BIN), "--json", "config", "sandbox", "--set", "none"],
                "sandbox-none",
            ),
            (
                "install/security config sigstore off requires approval",
                [str(LPM_BIN), "--json", "config", "sigstore", "--set", "off"],
                "provenance-unverified",
            ),
        ]
        for label, args, scope in config_commands:
            result = run_command_result(label, config_fixture, args, extra_env=scenario_env)
            require_security_approval_envelope(label, result, scope)

        config_audit_rows = read_jsonl(audit_path)
        for scope in [
            "scripts-allow",
            "cooldown-bypass",
            "sandbox-none",
            "provenance-unverified",
        ]:
            require_audit_event(
                config_audit_rows,
                event="persistent-guarded-attempt",
                allowed=False,
                expected_scope=scope,
                context="install/security config audit",
            )

        proposal_fixture = reset_security_fixture("proposal")
        write_registry_npmrc(proposal_fixture, registry.registry_url)
        write_package_json(
            proposal_fixture / "package.json",
            {
                "name": "security-proposal-smoke",
                "private": True,
                "version": "0.0.0",
                "dependencies": {package_name: version},
                "lpm": {"minimumReleaseAge": 0},
            },
        )
        proposal_result = run_command_result(
            "install/security package proposal requires approval",
            proposal_fixture,
            [str(LPM_BIN), "--json", "install", *install_flags],
            extra_env=scenario_env,
        )
        proposal_envelope = require_security_approval_envelope(
            "install/security package proposal requires approval",
            proposal_result,
            "cooldown-bypass",
        )
        if (
            proposal_envelope.get("error", {}).get("suggested_command")
            != "lpm security unlock cooldown-bypass --project . --ttl 10m"
        ):
            raise SmokeFailure(
                "install/security package proposal suggested command: expected project unlock hint"
            )
        require_not_exists(proposal_fixture / "node_modules")

        unlock_result = run_command_result(
            "install/security unlock json refuses automation",
            proposal_fixture,
            [
                str(LPM_BIN),
                "--json",
                "security",
                "unlock",
                "cooldown-bypass",
                "--project",
                ".",
                "--ttl",
                "10m",
            ],
            extra_env=scenario_env,
        )
        require_security_approval_envelope(
            "install/security unlock json refuses automation",
            unlock_result,
            "cooldown-bypass",
        )

        default_unlock_result = run_command_result(
            "install/security unlock default json refuses automation",
            proposal_fixture,
            [
                str(LPM_BIN),
                "--json",
                "security",
                "unlock",
                "default",
                "--ttl",
                "365d",
            ],
            extra_env=scenario_env,
        )
        default_unlock_envelope = parse_json_stdout(
            "install/security unlock default json refuses automation",
            default_unlock_result,
        )
        if default_unlock_result.returncode == 0:
            raise SmokeFailure(
                "install/security unlock default json refuses automation: unexpectedly succeeded"
            )
        if default_unlock_envelope.get("success") is not False:
            raise SmokeFailure(
                "install/security unlock default json refuses automation: expected success=false envelope"
            )
        error = default_unlock_envelope.get("error")
        if not isinstance(error, dict):
            raise SmokeFailure(
                "install/security unlock default json refuses automation: expected error object"
            )
        if error.get("code") != "SECURITY_APPROVAL_REQUIRED":
            raise SmokeFailure(
                "install/security unlock default json refuses automation: expected SECURITY_APPROVAL_REQUIRED"
            )
        requested_scopes = error.get("requested_scopes")
        if not isinstance(requested_scopes, list) or "cooldown-bypass" not in requested_scopes:
            raise SmokeFailure(
                "install/security unlock default json refuses automation: expected default bundle requested scopes"
            )
        if error.get("suggested_command") != "lpm security unlock default --global --ttl 10m":
            raise SmokeFailure(
                "install/security unlock default json refuses automation: expected global suggested command for default selector"
            )

        proposal_audit_rows = read_jsonl(audit_path)
        require_audit_event(
            proposal_audit_rows,
            event="guarded-attempt",
            allowed=False,
            expected_scope="cooldown-bypass",
            context="install/security package proposal audit",
        )

        if os.environ.get(NATIVE_SECURITY_UNLOCK_ENV) == "1":
            unlock_transcript = run_interactive_command(
                "install/security unlock native approval",
                proposal_fixture,
                [
                    str(LPM_BIN),
                    "security",
                    "unlock",
                    "cooldown-bypass",
                    "--project",
                    ".",
                    "--ttl",
                    "10m",
                ],
                prompts=[],
                extra_env=scenario_env,
            )
            require_contains(
                unlock_transcript,
                "Temporary project unlock for cooldown-bypass is active for 10 minutes.",
                "install/security unlock native approval transcript",
            )

            unlocked_status_result = run_command_result(
                "install/security status after native unlock",
                proposal_fixture,
                [str(LPM_BIN), "--json", "security", "status", "--project", "."],
                extra_env=scenario_env,
            )
            unlocked_status = require_success_payload(
                "install/security status after native unlock",
                unlocked_status_result,
                "status",
            )
            active_unlocks = unlocked_status.get("active_unlocks")
            if not isinstance(active_unlocks, list) or not any(
                isinstance(grant, dict)
                and isinstance(grant.get("scopes"), list)
                and "cooldown-bypass" in grant.get("scopes")
                for grant in active_unlocks
            ):
                raise SmokeFailure(
                    "install/security status after native unlock: expected active cooldown-bypass grant"
                )

            run_command(
                "install/security package proposal succeeds after native unlock",
                proposal_fixture,
                [str(LPM_BIN), "install", *install_flags],
                extra_env=scenario_env,
            )
            if read_installed_package_version(proposal_fixture, package_name) != version:
                raise SmokeFailure(
                    "install/security package proposal succeeds after native unlock: expected installed package"
                )

            lock_result = run_command_result(
                "install/security lock project after native unlock",
                proposal_fixture,
                [
                    str(LPM_BIN),
                    "--json",
                    "security",
                    "lock",
                    "cooldown-bypass",
                    "--project",
                    ".",
                ],
                extra_env=scenario_env,
            )
            lock_envelope = parse_json_stdout(
                "install/security lock project after native unlock",
                lock_result,
            )
            if lock_result.returncode != 0:
                raise SmokeFailure(
                    "install/security lock project after native unlock: expected success exit code"
                )
            if lock_envelope.get("success") is not True:
                raise SmokeFailure(
                    "install/security lock project after native unlock: expected success=true"
                )
            if lock_envelope.get("target") != "project":
                raise SmokeFailure(
                    "install/security lock project after native unlock: expected target=project"
                )
            revocations = lock_envelope.get("revocations")
            if not isinstance(revocations, list) or not revocations:
                raise SmokeFailure(
                    "install/security lock project after native unlock: expected one revocation"
                )
            revoked = revocations[0]
            if not isinstance(revoked, dict) or revoked.get("revoked_scopes") != ["cooldown-bypass"]:
                raise SmokeFailure(
                    "install/security lock project after native unlock: expected cooldown-bypass revocation"
                )

            locked_status_result = run_command_result(
                "install/security status after project lock",
                proposal_fixture,
                [str(LPM_BIN), "--json", "security", "status", "--project", "."],
                extra_env=scenario_env,
            )
            locked_status = require_success_payload(
                "install/security status after project lock",
                locked_status_result,
                "status",
            )
            active_unlocks = locked_status.get("active_unlocks")
            if not isinstance(active_unlocks, list):
                raise SmokeFailure(
                    "install/security status after project lock: expected active_unlocks list"
                )
            if any(
                isinstance(grant, dict)
                and isinstance(grant.get("scopes"), list)
                and "cooldown-bypass" in grant.get("scopes")
                for grant in active_unlocks
            ):
                raise SmokeFailure(
                    "install/security status after project lock: expected cooldown-bypass grant to be removed"
                )

            final_audit_rows = read_jsonl(audit_path)
            require_audit_event(
                final_audit_rows,
                event="unlock-granted",
                allowed=True,
                expected_scope="cooldown-bypass",
                context="install/security native unlock audit",
            )
            require_audit_event(
                final_audit_rows,
                event="unlock-revoked",
                allowed=True,
                expected_scope="cooldown-bypass",
                context="install/security native lock audit",
            )
        else:
            log(
                f"install/security native unlock: set {NATIVE_SECURITY_UNLOCK_ENV}=1 to exercise the macOS approval success path"
            )


def scenario_install_audit_after_install() -> None:
    package_name = "smoke-audit"
    version = "1.0.0"
    registry_packages = [
        {
            "name": package_name,
            "dist_tags": {"latest": version},
            "versions": {
                version: {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {},
                    "files": {},
                }
            },
        }
    ]

    with MockRegistry(registry_packages) as registry:
        install_flags = [
            "--no-security-summary",
            "--no-skills",
            "--no-editor-setup",
        ]

        def prepare_fixture() -> Path:
            fixture = reset_audit_after_install_fixture()
            write_registry_npmrc(fixture, registry.registry_url)
            write_package_json(
                fixture / "package.json",
                {
                    "name": "audit-after-install-smoke",
                    "private": True,
                    "version": "0.0.0",
                    "dependencies": {package_name: f"^{version}"},
                },
            )
            return fixture

        with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as default_home:
            default_fixture = prepare_fixture()
            default_output = run_command(
                "install/audit-after-install default off",
                default_fixture,
                [str(LPM_BIN), "install", *install_flags],
                extra_env={"LPM_HOME": default_home},
            )
            require_not_contains(
                default_output,
                "Audited",
                "install/audit-after-install default output",
            )

        with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as flag_home:
            flag_fixture = prepare_fixture()
            flag_output = run_command(
                "install/audit-after-install cli flag",
                flag_fixture,
                [str(LPM_BIN), "install", "--audit-after-install", *install_flags],
                extra_env={"LPM_HOME": flag_home},
            )
            require_contains(
                flag_output,
                "Audited",
                "install/audit-after-install cli flag output",
            )
            require_contains(
                flag_output,
                "run `lpm audit`",
                "install/audit-after-install cli flag output",
            )

        with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as env_home:
            env_fixture = prepare_fixture()
            env_output = run_command(
                "install/audit-after-install env on",
                env_fixture,
                [str(LPM_BIN), "install", *install_flags],
                extra_env={"LPM_HOME": env_home, "LPM_AUDIT_AFTER_INSTALL": "1"},
            )
            require_contains(
                env_output,
                "Audited",
                "install/audit-after-install env output",
            )

        with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as override_home:
            override_fixture = prepare_fixture()
            override_output = run_command(
                "install/audit-after-install no-audit overrides env",
                override_fixture,
                [str(LPM_BIN), "install", "--no-audit-after-install", *install_flags],
                extra_env={"LPM_HOME": override_home, "LPM_AUDIT_AFTER_INSTALL": "1"},
            )
            require_not_contains(
                override_output,
                "Audited",
                "install/audit-after-install no-audit override output",
            )

        with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as config_home:
            config_fixture = prepare_fixture()
            config_dir = Path(config_home) / ".lpm"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "config.toml").write_text(
                "audit-after-install = true\n",
                encoding="utf-8",
            )
            config_output = run_command(
                "install/audit-after-install config on",
                config_fixture,
                [str(LPM_BIN), "install", *install_flags],
                extra_env={"LPM_HOME": config_home, "HOME": config_home},
            )
            require_contains(
                config_output,
                "Audited",
                "install/audit-after-install config output",
            )

        with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as json_home:
            json_fixture = prepare_fixture()
            json_result = run_command_result(
                "install/audit-after-install json envelope",
                json_fixture,
                [
                    str(LPM_BIN),
                    "--json",
                    "install",
                    "--audit-after-install",
                    *install_flags,
                ],
                extra_env={"LPM_HOME": json_home},
            )
            if json_result.returncode != 0:
                raise SmokeFailure(
                    "install/audit-after-install json envelope failed with exit code "
                    f"{json_result.returncode}"
                )
            envelope = json.loads(json_result.stdout)
            audit_summary = envelope.get("audit_summary")
            if not isinstance(audit_summary, dict):
                raise SmokeFailure(
                    "install/audit-after-install json envelope: expected audit_summary object"
                )
            for key in [
                "packages_audited",
                "vulnerabilities",
                "suspicious",
                "elapsed_ms",
            ]:
                if not isinstance(audit_summary.get(key), int):
                    raise SmokeFailure(
                        f"install/audit-after-install json envelope: expected audit_summary.{key} to be numeric"
                    )
            require_not_contains(
                json_result.stderr,
                "Audited",
                "install/audit-after-install json stderr",
            )

        with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as failure_home:
            failure_fixture = prepare_fixture()
            failure_result = run_command_result(
                "install/audit-after-install failure remains informational",
                failure_fixture,
                [
                    str(LPM_BIN),
                    "--json",
                    "install",
                    "--audit-after-install",
                    *install_flags,
                ],
                extra_env={
                    "LPM_HOME": failure_home,
                    "LPM_TEST_MODE": "1",
                    "LPM_TEST_AUDIT_AFTER_INSTALL_FAIL": "1",
                },
            )
            if failure_result.returncode != 0:
                raise SmokeFailure(
                    "install/audit-after-install failure path: expected install to stay successful"
                )
            failure_envelope = json.loads(failure_result.stdout)
            if failure_envelope.get("audit_summary") is not None:
                raise SmokeFailure(
                    "install/audit-after-install failure path: audit_summary must be absent when audit hook fails"
                )
            require_not_contains(
                failure_result.stderr,
                "Audited",
                "install/audit-after-install failure stderr",
            )


def scenario_install_audit_command() -> None:
    registry_packages = [
        {
            "name": "audit-eval-pkg",
            "dist_tags": {"latest": "1.0.0"},
            "versions": {
                "1.0.0": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {"license": "MIT"},
                    "files": {
                        "index.js": "module.exports = function () { eval('1+1') }\n",
                    },
                }
            },
        },
        {
            "name": "audit-clean-pkg",
            "dist_tags": {"latest": "1.0.0"},
            "versions": {
                "1.0.0": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {"license": "MIT"},
                    "files": {
                        "index.js": "module.exports = function () { return 42 }\n",
                    },
                }
            },
        },
    ]

    osv_payload = json.dumps(
        {
            "results": [
                {"vulns": []},
                {"vulns": []},
            ]
        },
        separators=(",", ":"),
    ).encode("utf-8")
    osv_server = LocalRegistryServer({"/v1/querybatch": ("application/json", osv_payload)})
    osv_thread = threading.Thread(target=osv_server.serve_forever, daemon=True)
    osv_thread.start()

    try:
        host, port = osv_server.server_address
        osv_url = f"http://{host}:{port}/v1/querybatch"

        with MockRegistry(registry_packages) as registry, tempfile.TemporaryDirectory(
            prefix="lpm-smoke-home-"
        ) as lpm_home:
            fixture = reset_audit_command_fixture()
            write_registry_npmrc(fixture, registry.registry_url)
            scenario_env = {"LPM_HOME": lpm_home, "LPM_OSV_URL": osv_url}
            install_flags = [
                "--no-skills",
                "--no-editor-setup",
                "--no-security-summary",
            ]

            run_command(
                "install/audit install fixture packages",
                fixture,
                [str(LPM_BIN), "install", *install_flags],
                extra_env=scenario_env,
            )

            seed_node_modules_package(
                fixture,
                "leaky-pkg",
                "1.0.0",
                {
                    "config.js": (
                        "const AWS = { accessKey: 'AKIAIOSFODNN7EXAMPLE' };\n"
                        "module.exports = AWS;\n"
                    ),
                },
                package_json_extra={"license": "MIT"},
            )

            default_result = run_command_result(
                "install/audit default json",
                fixture,
                [str(LPM_BIN), "audit", "--json"],
                extra_env=scenario_env,
            )
            if default_result.returncode != 0:
                raise SmokeFailure(
                    "install/audit default json failed with exit code "
                    f"{default_result.returncode}"
                )

            default_envelope = json.loads(default_result.stdout)
            if default_envelope.get("counts", {}).get("high", 0) < 1:
                raise SmokeFailure(
                    "install/audit default json: expected at least one high-severity behavior finding"
                )
            require_contains(
                default_result.stdout,
                "audit-eval-pkg",
                "install/audit default json stdout",
            )

            behavior_result = run_command_result(
                "install/audit fail-on behavior json",
                fixture,
                [str(LPM_BIN), "audit", "--fail-on=behavior", "--json"],
                extra_env=scenario_env,
            )
            if behavior_result.returncode == 0:
                raise SmokeFailure(
                    "install/audit fail-on behavior json unexpectedly succeeded"
                )
            require_contains(
                behavior_result.stdout,
                "audit-eval-pkg",
                "install/audit fail-on behavior stdout",
            )

            secrets_result = run_command_result(
                "install/audit secrets fail-on secrets json",
                fixture,
                [str(LPM_BIN), "--json", "audit", "--secrets", "--fail-on=secrets"],
                extra_env=scenario_env,
            )
            if secrets_result.returncode == 0:
                raise SmokeFailure(
                    "install/audit secrets fail-on secrets json unexpectedly succeeded"
                )

            secrets_envelope = json.loads(secrets_result.stdout)
            if secrets_envelope.get("packagesWithSecrets") != 1:
                raise SmokeFailure(
                    "install/audit secrets json: expected exactly one packageWithSecrets"
                )
            findings = secrets_envelope.get("findings", [])
            if len(findings) != 1 or findings[0].get("package") != "leaky-pkg":
                raise SmokeFailure(
                    "install/audit secrets json: expected one finding for leaky-pkg"
                )
    finally:
        osv_server.shutdown()
        osv_server.server_close()
        osv_thread.join(timeout=5)


def scenario_install_query_command() -> None:
    registry_packages = [
        {
            "name": "query-eval-pkg",
            "dist_tags": {"latest": "1.0.0"},
            "versions": {
                "1.0.0": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {"license": "MIT"},
                    "files": {
                        "index.js": "module.exports = function () { eval('1+1') }\n",
                    },
                }
            },
        },
        {
            "name": "query-network-pkg",
            "dist_tags": {"latest": "1.0.0"},
            "versions": {
                "1.0.0": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {"license": "MIT"},
                    "files": {
                        "index.js": (
                            "module.exports = function () { fetch('https://example.com') }\n"
                        ),
                    },
                }
            },
        },
        {
            "name": "query-clean-pkg",
            "dist_tags": {"latest": "1.0.0"},
            "versions": {
                "1.0.0": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {"license": "MIT"},
                    "files": {
                        "index.js": "module.exports = function () { return 42 }\n",
                    },
                }
            },
        },
    ]

    with MockRegistry(registry_packages) as registry, tempfile.TemporaryDirectory(
        prefix="lpm-smoke-home-"
    ) as lpm_home:
        fixture = reset_query_command_fixture()
        write_registry_npmrc(fixture, registry.registry_url)
        scenario_env = {"LPM_HOME": lpm_home}
        install_flags = [
            "--no-skills",
            "--no-editor-setup",
            "--no-security-summary",
        ]

        run_command(
            "install/query install fixture packages",
            fixture,
            [str(LPM_BIN), "install", *install_flags],
            extra_env=scenario_env,
        )

        eval_output = run_command(
            "install/query selector eval",
            fixture,
            [str(LPM_BIN), "query", ":eval"],
            extra_env=scenario_env,
        )
        require_contains(eval_output, "query-eval-pkg", "install/query :eval output")
        require_not_contains(eval_output, "query-clean-pkg", "install/query :eval output")

        direct_network_output = run_command(
            "install/query root direct network",
            fixture,
            [str(LPM_BIN), "query", ":root > :network"],
            extra_env=scenario_env,
        )
        require_contains(
            direct_network_output,
            "query-network-pkg",
            "install/query :root > :network output",
        )

        assert_none_output = run_command_expect_failure(
            "install/query assert none",
            fixture,
            [str(LPM_BIN), "query", ":eval", "--assert-none"],
            extra_env=scenario_env,
        )
        if not any(
            needle in assert_none_output.lower()
            for needle in ["assertion", "matched", "expected no packages"]
        ):
            raise SmokeFailure(
                "install/query assert-none output: expected assertion-style failure text"
            )

        count_result = run_command_result(
            "install/query count json",
            fixture,
            [str(LPM_BIN), "--json", "query", "--count"],
            extra_env=scenario_env,
        )
        if count_result.returncode != 0:
            raise SmokeFailure(
                f"install/query count json failed with exit code {count_result.returncode}"
            )
        require_contains(count_result.stdout, '"eval"', "install/query --count json")

        mermaid_output = run_command(
            "install/query mermaid",
            fixture,
            [str(LPM_BIN), "query", ":eval", "--format", "mermaid"],
            extra_env=scenario_env,
        )
        require_contains(mermaid_output, "graph TD", "install/query mermaid output")
        require_contains(mermaid_output, "query-eval-pkg", "install/query mermaid output")


def scenario_install_approve_scripts_command() -> None:
    registry_packages = [
        {
            "name": "smoke-approve-scripted",
            "dist_tags": {"latest": "1.0.0"},
            "versions": {
                "1.0.0": {
                    "metadata_extra": {
                        "dependencies": {},
                        "scripts": {"postinstall": "node build.js"},
                    },
                    "package_json_extra": {
                        "license": "MIT",
                        "scripts": {"postinstall": "node build.js"},
                    },
                    "files": {
                        "build.js": (
                            "require('node:fs').writeFileSync('script-ran.txt', 'approved\\n')\n"
                        ),
                    },
                }
            },
        }
    ]

    with MockRegistry(registry_packages) as registry, tempfile.TemporaryDirectory(
        prefix="lpm-smoke-home-"
    ) as lpm_home:
        fixture = reset_approve_scripts_fixture()
        write_registry_npmrc(fixture, registry.registry_url)
        scenario_env = {"LPM_HOME": lpm_home}
        install_flags = [
            "--no-skills",
            "--no-editor-setup",
            "--no-security-summary",
        ]

        install_output = run_command(
            "install/approve-scripts blocked install",
            fixture,
            [str(LPM_BIN), "install", *install_flags],
            extra_env=scenario_env,
        )
        require_contains(
            install_output,
            "approve-scripts",
            "install/approve-scripts install output",
        )
        require_exists(fixture / ".lpm" / "build-state.json")
        require_not_exists(
            fixture / "node_modules" / "smoke-approve-scripted" / "script-ran.txt"
        )

        original_package_json = (fixture / "package.json").read_text(encoding="utf-8")

        list_result = run_command_result(
            "install/approve-scripts list json",
            fixture,
            [str(LPM_BIN), "--json", "approve-scripts", "--list"],
            extra_env=scenario_env,
        )
        if list_result.returncode != 0:
            raise SmokeFailure(
                f"install/approve-scripts list json failed with exit code {list_result.returncode}"
            )
        list_envelope = json.loads(list_result.stdout)
        if list_envelope.get("blocked_count") != 1:
            raise SmokeFailure(
                "install/approve-scripts list json: expected one blocked package"
            )
        blocked = list_envelope.get("blocked", [])
        if len(blocked) != 1 or blocked[0].get("name") != "smoke-approve-scripted":
            raise SmokeFailure(
                "install/approve-scripts list json: expected smoke-approve-scripted in blocked[]"
            )

        dry_run_result = run_command_result(
            "install/approve-scripts named dry-run json",
            fixture,
            [
                str(LPM_BIN),
                "--json",
                "approve-scripts",
                "smoke-approve-scripted",
                "--dry-run",
            ],
            extra_env=scenario_env,
        )
        if dry_run_result.returncode != 0:
            raise SmokeFailure(
                "install/approve-scripts named dry-run json failed with exit code "
                f"{dry_run_result.returncode}"
            )
        dry_run_envelope = json.loads(dry_run_result.stdout)
        if dry_run_envelope.get("dry_run") is not True:
            raise SmokeFailure(
                "install/approve-scripts named dry-run json: expected dry_run=true"
            )
        if dry_run_envelope.get("approved_count") != 1:
            raise SmokeFailure(
                "install/approve-scripts named dry-run json: expected approved_count=1"
            )
        if (fixture / "package.json").read_text(encoding="utf-8") != original_package_json:
            raise SmokeFailure(
                "install/approve-scripts named dry-run package.json: expected no mutation"
            )

        approve_result = run_command_result(
            "install/approve-scripts named approve json",
            fixture,
            [str(LPM_BIN), "--json", "approve-scripts", "smoke-approve-scripted"],
            extra_env=scenario_env,
        )
        approve_envelope = require_security_approval_envelope(
            "install/approve-scripts named approve json",
            approve_result,
            "trust-bulk-approve",
        )
        if (
            approve_envelope.get("error", {}).get("suggested_command")
            != "lpm security unlock trust-bulk-approve --project . --ttl 10m"
        ):
            raise SmokeFailure(
                "install/approve-scripts named approve json: expected project unlock hint"
            )
        if (fixture / "package.json").read_text(encoding="utf-8") != original_package_json:
            raise SmokeFailure(
                "install/approve-scripts named approve package.json: expected no mutation without approval"
            )

        empty_list_result = run_command_result(
            "install/approve-scripts list json after refused approval",
            fixture,
            [str(LPM_BIN), "--json", "approve-scripts", "--list"],
            extra_env=scenario_env,
        )
        if empty_list_result.returncode != 0:
            raise SmokeFailure(
                "install/approve-scripts list json after refused approval failed with exit code "
                f"{empty_list_result.returncode}"
            )
        empty_list_envelope = json.loads(empty_list_result.stdout)
        if empty_list_envelope.get("blocked_count") != 1:
            raise SmokeFailure(
                "install/approve-scripts list json after refused approval: expected blocked_count=1"
            )


def scenario_install_trust_command() -> None:
    scripted_package = "smoke-trust-scripted"
    keep_package = "smoke-trust-keep"
    version = "1.0.0"
    registry_packages = [
        {
            "name": scripted_package,
            "dist_tags": {"latest": version},
            "versions": {
                version: {
                    "metadata_extra": {
                        "dependencies": {},
                        "scripts": {"postinstall": "node build.js"},
                    },
                    "package_json_extra": {
                        "license": "MIT",
                        "scripts": {"postinstall": "node build.js"},
                    },
                    "files": {
                        "build.js": "require('node:fs').writeFileSync('script-ran.txt', 'trust\\n')\n",
                    },
                }
            },
        },
        {
            "name": keep_package,
            "dist_tags": {"latest": version},
            "versions": {
                version: {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {"license": "MIT"},
                    "files": {
                        "index.js": "module.exports = function () { return 'keep' }\n",
                    },
                }
            },
        },
    ]

    with MockRegistry(registry_packages) as registry, tempfile.TemporaryDirectory(
        prefix="lpm-smoke-home-"
    ) as lpm_home:
        fixture = reset_trust_command_fixture()
        write_registry_npmrc(fixture, registry.registry_url)
        scenario_env = {"LPM_HOME": lpm_home}
        install_flags = [
            "--no-skills",
            "--no-editor-setup",
            "--no-security-summary",
        ]

        run_command(
            "install/trust blocked install",
            fixture,
            [str(LPM_BIN), "install", *install_flags],
            extra_env=scenario_env,
        )
        require_exists(fixture / ".lpm" / "trust-snapshot.json")

        run_command(
            "install/trust diff assert-none clean",
            fixture,
            [str(LPM_BIN), "trust", "diff", "--assert-none"],
            extra_env=scenario_env,
        )

        approve_result = run_command_result(
            "install/trust approve scripted package",
            fixture,
            [str(LPM_BIN), "--json", "approve-scripts", scripted_package],
            extra_env=scenario_env,
        )
        approve_envelope = require_security_approval_envelope(
            "install/trust approve scripted package",
            approve_result,
            "trust-bulk-approve",
        )
        if (
            approve_envelope.get("error", {}).get("suggested_command")
            != "lpm security unlock trust-bulk-approve --project . --ttl 10m"
        ):
            raise SmokeFailure(
                "install/trust approve scripted package: expected project unlock hint"
            )

        dry_run_result = run_command_result(
            "install/trust named dry-run json",
            fixture,
            [
                str(LPM_BIN),
                "--json",
                "approve-scripts",
                scripted_package,
                "--dry-run",
            ],
            extra_env=scenario_env,
        )
        if dry_run_result.returncode != 0:
            raise SmokeFailure(
                "install/trust named dry-run json failed with exit code "
                f"{dry_run_result.returncode}"
            )
        dry_run_envelope = parse_json_stdout(
            "install/trust named dry-run json",
            dry_run_result,
        )
        approved = dry_run_envelope.get("approved")
        if not isinstance(approved, list) or len(approved) != 1:
            raise SmokeFailure(
                "install/trust named dry-run json: expected one approved entry"
            )
        approved_entry = approved[0]
        if not isinstance(approved_entry, dict):
            raise SmokeFailure(
                "install/trust named dry-run json: expected approved entry object"
            )

        package_json = read_json_file(fixture / "package.json")
        lpm_block = package_json.setdefault("lpm", {})
        if not isinstance(lpm_block, dict):
            raise SmokeFailure(
                "install/trust package.json baseline: expected lpm block to be an object"
            )
        lpm_block["trustedDependencies"] = {
            f"{scripted_package}@{version}": {
                "integrity": approved_entry.get("integrity"),
                "scriptHash": approved_entry.get("script_hash"),
            }
        }
        write_package_json(fixture / "package.json", package_json)

        diff_result = run_command_result(
            "install/trust diff json after direct trust drift",
            fixture,
            [str(LPM_BIN), "trust", "diff", "--json"],
            extra_env=scenario_env,
        )
        if diff_result.returncode != 0:
            raise SmokeFailure(
                f"install/trust diff json failed with exit code {diff_result.returncode}"
            )
        diff_envelope = json.loads(diff_result.stdout)
        added = diff_envelope.get("added", [])
        if len(added) != 1 or added[0].get("key") != f"{scripted_package}@{version}":
            raise SmokeFailure(
                "install/trust diff json: expected one added trust binding after direct manifest drift"
            )

        diff_assert_output = run_command_expect_failure(
            "install/trust diff assert-none after direct trust drift",
            fixture,
            [str(LPM_BIN), "trust", "diff", "--assert-none"],
            extra_env=scenario_env,
        )
        if not any(
            needle in diff_assert_output.lower()
            for needle in ["assertion failed", "diff", "matched"]
        ):
            raise SmokeFailure(
                "install/trust diff assert-none output: expected assertion-style drift message"
            )

        seed_registry_lockfile_entries(
            fixture,
            [(keep_package, version, "https://registry.npmjs.org")],
        )

        package_json_before_prune = (fixture / "package.json").read_text(encoding="utf-8")

        prune_dry_result = run_command_result(
            "install/trust prune dry-run json",
            fixture,
            [str(LPM_BIN), "trust", "prune", "--dry-run", "--json"],
            extra_env=scenario_env,
        )
        if prune_dry_result.returncode != 0:
            raise SmokeFailure(
                "install/trust prune dry-run json failed with exit code "
                f"{prune_dry_result.returncode}"
            )
        prune_dry_envelope = json.loads(prune_dry_result.stdout)
        if prune_dry_envelope.get("dry_run") is not True:
            raise SmokeFailure(
                "install/trust prune dry-run json: expected dry_run=true"
            )
        if prune_dry_envelope.get("mutated") is not False:
            raise SmokeFailure(
                "install/trust prune dry-run json: expected mutated=false"
            )
        if prune_dry_envelope.get("stale") != [f"{scripted_package}@{version}"]:
            raise SmokeFailure(
                "install/trust prune dry-run json: expected the approved scripted package to be stale"
            )
        if (fixture / "package.json").read_text(encoding="utf-8") != package_json_before_prune:
            raise SmokeFailure(
                "install/trust prune dry-run package.json: expected no mutation"
            )

        prune_live_result = run_command_result(
            "install/trust prune yes json",
            fixture,
            [str(LPM_BIN), "trust", "prune", "--yes", "--json"],
            extra_env=scenario_env,
        )
        if prune_live_result.returncode != 0:
            raise SmokeFailure(
                f"install/trust prune yes json failed with exit code {prune_live_result.returncode}"
            )
        prune_live_envelope = json.loads(prune_live_result.stdout)
        if prune_live_envelope.get("mutated") is not True:
            raise SmokeFailure(
                "install/trust prune yes json: expected mutated=true"
            )

        package_json_after_prune = (fixture / "package.json").read_text(encoding="utf-8")
        require_not_contains(
            package_json_after_prune,
            f'"{scripted_package}@{version}"',
            "install/trust prune yes package.json",
        )

        run_command(
            "install/trust diff assert-none after prune",
            fixture,
            [str(LPM_BIN), "trust", "diff", "--assert-none"],
            extra_env=scenario_env,
        )


def scenario_install_rebuild_command() -> None:
    package_name = "smoke-rebuild-scripted"
    version = "1.0.0"
    registry_packages = [
        {
            "name": package_name,
            "dist_tags": {"latest": version},
            "versions": {
                version: {
                    "metadata_extra": {
                        "dependencies": {},
                        "scripts": {"postinstall": "node build.js"},
                    },
                    "package_json_extra": {
                        "license": "MIT",
                        "scripts": {"postinstall": "node build.js"},
                    },
                    "files": {
                        "build.js": (
                            "const fs = require('node:fs')\n"
                            "const path = require('node:path')\n"
                            "const countPath = path.join(__dirname, 'build-count.txt')\n"
                            "let count = 0\n"
                            "if (fs.existsSync(countPath)) {\n"
                            "  count = Number(fs.readFileSync(countPath, 'utf8')) || 0\n"
                            "}\n"
                            "fs.writeFileSync(countPath, String(count + 1))\n"
                        ),
                    },
                }
            },
        }
    ]

    with MockRegistry(registry_packages) as registry, tempfile.TemporaryDirectory(
        prefix="lpm-smoke-home-"
    ) as lpm_home:
        fixture = reset_rebuild_command_fixture()
        write_registry_npmrc(fixture, registry.registry_url)
        scenario_env = {"LPM_HOME": lpm_home}
        install_flags = [
            "--no-skills",
            "--no-editor-setup",
            "--no-security-summary",
        ]

        run_command(
            "install/rebuild blocked install",
            fixture,
            [str(LPM_BIN), "install", *install_flags],
            extra_env=scenario_env,
        )
        build_count_path = fixture / "node_modules" / package_name / "build-count.txt"
        require_not_exists(build_count_path)

        approve_result = run_command_result(
            "install/rebuild approve scripted package",
            fixture,
            [str(LPM_BIN), "--json", "approve-scripts", package_name],
            extra_env=scenario_env,
        )
        approve_envelope = require_security_approval_envelope(
            "install/rebuild approve scripted package",
            approve_result,
            "trust-bulk-approve",
        )
        if (
            approve_envelope.get("error", {}).get("suggested_command")
            != "lpm security unlock trust-bulk-approve --project . --ttl 10m"
        ):
            raise SmokeFailure(
                "install/rebuild approve scripted package: expected project unlock hint"
            )

        deny_output = run_command(
            "install/rebuild deny-mode no trusted packages",
            fixture,
            [str(LPM_BIN), "rebuild"],
            extra_env=scenario_env,
        )
        require_contains(
            deny_output,
            "trustedDependencies",
            "install/rebuild deny-mode output",
        )
        require_not_contains(
            deny_output,
            "approve-scripts",
            "install/rebuild deny-mode output",
        )
        if build_count_path.exists():
            raise SmokeFailure(
                "install/rebuild deny-mode no trusted packages: expected build-count.txt to stay absent"
            )


def scenario_install_patch_command() -> None:
    package_name = "smoke-patch-lib"
    version = "1.0.0"
    original_source = "module.exports = 'ok'\n"
    patched_source = "module.exports = 'PATCHED BY SMOKE'\n"
    registry_packages = [
        {
            "name": package_name,
            "dist_tags": {"latest": version},
            "versions": {
                version: {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {"license": "MIT"},
                    "files": {},
                }
            },
        }
    ]

    with MockRegistry(registry_packages) as registry, tempfile.TemporaryDirectory(
        prefix="lpm-smoke-home-"
    ) as lpm_home:
        fixture = reset_patch_command_fixture()
        write_registry_npmrc(fixture, registry.registry_url)
        scenario_env = {"LPM_HOME": lpm_home}
        install_flags = [
            "--no-skills",
            "--no-editor-setup",
            "--no-security-summary",
        ]

        run_command(
            "install/patch initial install",
            fixture,
            [str(LPM_BIN), "install", *install_flags],
            extra_env=scenario_env,
        )

        installed_file = fixture / "node_modules" / package_name / "index.js"
        require_exists(installed_file)
        if installed_file.read_text(encoding="utf-8") != original_source:
            raise SmokeFailure(
                "install/patch initial install: expected installed file to match upstream source"
            )

        patch_result = run_command_result(
            "install/patch extract bare-name json",
            fixture,
            [str(LPM_BIN), "--json", "patch", package_name],
            extra_env=scenario_env,
        )
        if patch_result.returncode != 0:
            raise SmokeFailure(
                f"install/patch extract bare-name json failed with exit code {patch_result.returncode}"
            )
        patch_envelope = json.loads(patch_result.stdout)
        if patch_envelope.get("success") is not True:
            raise SmokeFailure("install/patch extract bare-name json: expected success=true")
        if patch_envelope.get("name") != package_name:
            raise SmokeFailure(
                "install/patch extract bare-name json: expected resolved package name in JSON output"
            )
        if patch_envelope.get("version") != version:
            raise SmokeFailure(
                "install/patch extract bare-name json: expected resolved exact version in JSON output"
            )

        staging_dir = Path(patch_envelope["staging_dir"])
        require_exists(staging_dir)

        breadcrumb_path = staging_dir / ".lpm-patch.json"
        require_exists(breadcrumb_path)
        breadcrumb = json.loads(breadcrumb_path.read_text(encoding="utf-8"))
        if breadcrumb.get("key") != f"{package_name}@{version}":
            raise SmokeFailure(
                "install/patch breadcrumb: expected resolved exact key in .lpm-patch.json"
            )

        staged_file = staging_dir / "node_modules" / package_name / "index.js"
        require_exists(staged_file)
        if staged_file.read_text(encoding="utf-8") != original_source:
            raise SmokeFailure(
                "install/patch staged file: expected pristine upstream bytes in the extracted staging dir"
            )
        require_not_exists(staged_file.parent / ".integrity")

        staged_file.write_text(patched_source, encoding="utf-8")

        commit_result = run_command_result(
            "install/patch patch-commit json",
            fixture,
            [str(LPM_BIN), "--json", "patch-commit", str(staging_dir)],
            extra_env=scenario_env,
        )
        if commit_result.returncode != 0:
            raise SmokeFailure(
                f"install/patch patch-commit json failed with exit code {commit_result.returncode}"
            )
        commit_envelope = json.loads(commit_result.stdout)
        if commit_envelope.get("success") is not True:
            raise SmokeFailure("install/patch patch-commit json: expected success=true")
        if commit_envelope.get("files_changed") != 1:
            raise SmokeFailure(
                "install/patch patch-commit json: expected files_changed=1 for the edited source file"
            )
        if not commit_envelope.get("original_integrity"):
            raise SmokeFailure(
                "install/patch patch-commit json: expected original_integrity to be present"
            )

        patch_file = fixture / "patches" / f"{package_name}@{version}.patch"
        require_exists(patch_file)
        patch_text = patch_file.read_text(encoding="utf-8")
        require_contains(patch_text, "--- a/index.js", "install/patch patch file")
        require_contains(patch_text, "+++ b/index.js", "install/patch patch file")
        require_contains(
            patch_text,
            "+module.exports = 'PATCHED BY SMOKE'",
            "install/patch patch file",
        )

        package_json = read_json_file(fixture / "package.json")
        patch_entry = (
            package_json.get("lpm", {})
            .get("patchedDependencies", {})
            .get(f"{package_name}@{version}")
        )
        if not isinstance(patch_entry, dict):
            raise SmokeFailure(
                "install/patch package.json: expected lpm.patchedDependencies entry after patch-commit"
            )
        if patch_entry.get("path") != f"patches/{package_name}@{version}.patch":
            raise SmokeFailure(
                "install/patch package.json: expected patchedDependencies path to point at the generated patch file"
            )
        if patch_entry.get("originalIntegrity") != commit_envelope.get("original_integrity"):
            raise SmokeFailure(
                "install/patch package.json: expected originalIntegrity to match patch-commit JSON output"
            )

        require_not_exists(staging_dir)

        delete_path(fixture / "node_modules")
        run_command(
            "install/patch reinstall applies patch",
            fixture,
            [str(LPM_BIN), "install", *install_flags],
            extra_env=scenario_env,
        )
        if installed_file.read_text(encoding="utf-8") != patched_source:
            raise SmokeFailure(
                "install/patch reinstall applies patch: expected patched bytes after the next install"
            )

        pristine_result = run_command_result(
            "install/patch re-extract pristine json",
            fixture,
            [str(LPM_BIN), "--json", "patch", package_name],
            extra_env=scenario_env,
        )
        if pristine_result.returncode != 0:
            raise SmokeFailure(
                f"install/patch re-extract pristine json failed with exit code {pristine_result.returncode}"
            )
        pristine_envelope = json.loads(pristine_result.stdout)
        pristine_staging_dir = Path(pristine_envelope["staging_dir"])
        pristine_file = pristine_staging_dir / "node_modules" / package_name / "index.js"
        if pristine_file.read_text(encoding="utf-8") != original_source:
            raise SmokeFailure(
                "install/patch re-extract pristine json: expected a fresh staging copy from upstream bytes, not the already-patched project copy"
            )

        no_change_output = run_command_expect_failure(
            "install/patch no-change patch-commit failure",
            fixture,
            [str(LPM_BIN), "patch-commit", str(pristine_staging_dir)],
            extra_env=scenario_env,
        )
        require_contains(
            no_change_output,
            "no changes detected",
            "install/patch no-change patch-commit failure",
        )
        delete_path(pristine_staging_dir)

        package_json_before_remove = (fixture / "package.json").read_text(encoding="utf-8")
        patch_remove_dry_run = run_command_result(
            "install/patch patch-remove dry-run bare-name json",
            fixture,
            [str(LPM_BIN), "--json", "patch-remove", "--dry-run", package_name],
            extra_env=scenario_env,
        )
        if patch_remove_dry_run.returncode != 0:
            raise SmokeFailure(
                f"install/patch patch-remove dry-run bare-name json failed with exit code {patch_remove_dry_run.returncode}"
            )
        dry_run_envelope = json.loads(patch_remove_dry_run.stdout)
        if dry_run_envelope.get("success") is not True:
            raise SmokeFailure(
                "install/patch patch-remove dry-run bare-name json: expected success=true"
            )
        if dry_run_envelope.get("dry_run") is not True:
            raise SmokeFailure(
                "install/patch patch-remove dry-run bare-name json: expected dry_run=true"
            )
        if dry_run_envelope.get("removed", [{}])[0].get("key") != f"{package_name}@{version}":
            raise SmokeFailure(
                "install/patch patch-remove dry-run bare-name json: expected bare-name selector to resolve to the exact patched key"
            )
        if dry_run_envelope.get("removed", [{}])[0].get("retained_reason") != "dry-run":
            raise SmokeFailure(
                "install/patch patch-remove dry-run bare-name json: expected retained_reason=dry-run"
            )
        if (fixture / "package.json").read_text(encoding="utf-8") != package_json_before_remove:
            raise SmokeFailure(
                "install/patch patch-remove dry-run bare-name json: expected package.json to stay unchanged"
            )
        require_exists(patch_file)

        patch_remove_result = run_command_result(
            "install/patch patch-remove exact json",
            fixture,
            [str(LPM_BIN), "--json", "patch-remove", f"{package_name}@{version}"],
            extra_env=scenario_env,
        )
        if patch_remove_result.returncode != 0:
            raise SmokeFailure(
                f"install/patch patch-remove exact json failed with exit code {patch_remove_result.returncode}"
            )
        patch_remove_envelope = json.loads(patch_remove_result.stdout)
        if patch_remove_envelope.get("success") is not True:
            raise SmokeFailure("install/patch patch-remove exact json: expected success=true")
        if patch_remove_envelope.get("removed", [{}])[0].get("deleted_patch_file") is not True:
            raise SmokeFailure(
                "install/patch patch-remove exact json: expected default removal to delete the unshared patch file"
            )
        require_not_exists(patch_file)
        package_json_after_remove = read_json_file(fixture / "package.json")
        if package_json_after_remove.get("lpm") is not None:
            raise SmokeFailure(
                "install/patch patch-remove exact json: expected empty lpm section to be removed from package.json"
            )
        if installed_file.read_text(encoding="utf-8") != patched_source:
            raise SmokeFailure(
                "install/patch patch-remove exact json: expected node_modules to stay patched until the next install"
            )

        delete_path(fixture / "node_modules")
        run_command(
            "install/patch patch-remove reinstall restores upstream",
            fixture,
            [str(LPM_BIN), "install", *install_flags],
            extra_env=scenario_env,
        )
        if installed_file.read_text(encoding="utf-8") != original_source:
            raise SmokeFailure(
                "install/patch patch-remove reinstall restores upstream: expected upstream bytes after the patch manifest entry was removed"
            )

        package_json_keep_file = read_json_file(fixture / "package.json")
        package_json_keep_file["lpm"] = {
            "patchedDependencies": {
                f"{package_name}@{version}": {
                    "path": f"patches/{package_name}@{version}.patch",
                    "originalIntegrity": commit_envelope.get("original_integrity"),
                }
            }
        }
        write_package_json(fixture / "package.json", package_json_keep_file)
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        patch_file.write_text(patch_text, encoding="utf-8")

        keep_file_result = run_command_result(
            "install/patch patch-remove keep-file json",
            fixture,
            [str(LPM_BIN), "--json", "patch-remove", "--keep-file", f"{package_name}@{version}"],
            extra_env=scenario_env,
        )
        if keep_file_result.returncode != 0:
            raise SmokeFailure(
                f"install/patch patch-remove keep-file json failed with exit code {keep_file_result.returncode}"
            )
        keep_file_envelope = json.loads(keep_file_result.stdout)
        if keep_file_envelope.get("success") is not True:
            raise SmokeFailure(
                "install/patch patch-remove keep-file json: expected success=true"
            )
        if keep_file_envelope.get("keep_file") is not True:
            raise SmokeFailure(
                "install/patch patch-remove keep-file json: expected keep_file=true"
            )
        if keep_file_envelope.get("removed", [{}])[0].get("retained_reason") != "keep-file":
            raise SmokeFailure(
                "install/patch patch-remove keep-file json: expected retained_reason=keep-file"
            )
        require_exists(patch_file)
        package_json_after_keep_file = read_json_file(fixture / "package.json")
        if package_json_after_keep_file.get("lpm") is not None:
            raise SmokeFailure(
                "install/patch patch-remove keep-file json: expected empty lpm section to be removed even when the patch file is retained"
            )

        restore_patch_command_fixture()
        if (fixture / "package.json").read_text(encoding="utf-8") != PATCH_COMMAND_TRACKED_PACKAGE_JSON:
            raise SmokeFailure(
                "install/patch cleanup: expected the tracked patch fixture package.json bytes to be restored"
            )


def scenario_install_patch_scoped_command() -> None:
    package_name = "@smoke/patch-lib"
    version = "1.0.0"
    original_source = "module.exports = 'scoped ok'\n"
    patched_source = "module.exports = 'SCOPED PATCHED BY SMOKE'\n"
    registry_packages = [
        {
            "name": package_name,
            "dist_tags": {"latest": version},
            "versions": {
                version: {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {"license": "MIT"},
                    "files": {"index.js": original_source},
                }
            },
        }
    ]

    with MockRegistry(registry_packages) as registry, tempfile.TemporaryDirectory(
        prefix="lpm-smoke-home-"
    ) as lpm_home:
        fixture = reset_patch_scoped_command_fixture()
        write_registry_npmrc(fixture, registry.registry_url)
        scenario_env = {"LPM_HOME": lpm_home}
        install_flags = [
            "--no-skills",
            "--no-editor-setup",
            "--no-security-summary",
        ]

        run_command(
            "install/patch-scoped initial install",
            fixture,
            [str(LPM_BIN), "install", *install_flags],
            extra_env=scenario_env,
        )

        installed_file = fixture / "node_modules" / "@smoke" / "patch-lib" / "index.js"
        require_exists(installed_file)
        if installed_file.read_text(encoding="utf-8") != original_source:
            raise SmokeFailure(
                "install/patch-scoped initial install: expected installed scoped package bytes to match upstream source"
            )

        patch_result = run_command_result(
            "install/patch-scoped extract exact-pin json",
            fixture,
            [str(LPM_BIN), "--json", "patch", f"{package_name}@{version}"],
            extra_env=scenario_env,
        )
        if patch_result.returncode != 0:
            raise SmokeFailure(
                f"install/patch-scoped extract exact-pin json failed with exit code {patch_result.returncode}"
            )
        patch_envelope = json.loads(patch_result.stdout)
        if patch_envelope.get("name") != package_name:
            raise SmokeFailure(
                "install/patch-scoped extract exact-pin json: expected scoped package name in JSON output"
            )
        if patch_envelope.get("version") != version:
            raise SmokeFailure(
                "install/patch-scoped extract exact-pin json: expected scoped package exact version in JSON output"
            )

        staging_dir = Path(patch_envelope["staging_dir"])
        require_exists(staging_dir)
        staged_file = staging_dir / "node_modules" / "@smoke" / "patch-lib" / "index.js"
        require_exists(staged_file)
        if staged_file.read_text(encoding="utf-8") != original_source:
            raise SmokeFailure(
                "install/patch-scoped staged file: expected pristine upstream scoped package bytes"
            )

        staged_file.write_text(patched_source, encoding="utf-8")

        commit_result = run_command_result(
            "install/patch-scoped patch-commit json",
            fixture,
            [str(LPM_BIN), "--json", "patch-commit", str(staging_dir)],
            extra_env=scenario_env,
        )
        if commit_result.returncode != 0:
            raise SmokeFailure(
                f"install/patch-scoped patch-commit json failed with exit code {commit_result.returncode}"
            )
        commit_envelope = json.loads(commit_result.stdout)
        if commit_envelope.get("success") is not True:
            raise SmokeFailure(
                "install/patch-scoped patch-commit json: expected success=true"
            )

        sanitized_patch_path = fixture / "patches" / "@smoke__patch-lib@1.0.0.patch"
        raw_slash_patch_path = fixture / "patches" / "@smoke" / "patch-lib@1.0.0.patch"
        require_exists(sanitized_patch_path)
        require_not_exists(raw_slash_patch_path)
        patch_text = sanitized_patch_path.read_text(encoding="utf-8")
        require_contains(
            patch_text,
            "+module.exports = 'SCOPED PATCHED BY SMOKE'",
            "install/patch-scoped patch file",
        )

        package_json = read_json_file(fixture / "package.json")
        patch_entry = (
            package_json.get("lpm", {})
            .get("patchedDependencies", {})
            .get(f"{package_name}@{version}")
        )
        if not isinstance(patch_entry, dict):
            raise SmokeFailure(
                "install/patch-scoped package.json: expected scoped patchedDependencies entry after patch-commit"
            )
        if patch_entry.get("path") != "patches/@smoke__patch-lib@1.0.0.patch":
            raise SmokeFailure(
                "install/patch-scoped package.json: expected manifest path to point at the sanitized scoped patch filename"
            )

        require_not_exists(staging_dir)

        delete_path(fixture / "node_modules")
        run_command(
            "install/patch-scoped reinstall applies sanitized patch",
            fixture,
            [str(LPM_BIN), "install", *install_flags],
            extra_env=scenario_env,
        )
        if installed_file.read_text(encoding="utf-8") != patched_source:
            raise SmokeFailure(
                "install/patch-scoped reinstall applies sanitized patch: expected patched scoped bytes after reinstall"
            )


def scenario_install_patch_binary_command() -> None:
    package_name = "smoke-patch-binary-lib"
    version = "1.0.0"
    original_text = "hello\n"
    registry_packages = [
        {
            "name": package_name,
            "dist_tags": {"latest": version},
            "versions": {
                version: {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {"license": "MIT"},
                    "files": {"logo.txt": original_text},
                }
            },
        }
    ]

    with MockRegistry(registry_packages) as registry, tempfile.TemporaryDirectory(
        prefix="lpm-smoke-home-"
    ) as lpm_home:
        fixture = reset_patch_binary_command_fixture()
        write_registry_npmrc(fixture, registry.registry_url)
        scenario_env = {"LPM_HOME": lpm_home}
        install_flags = [
            "--no-skills",
            "--no-editor-setup",
            "--no-security-summary",
        ]

        run_command(
            "install/patch-binary initial install",
            fixture,
            [str(LPM_BIN), "install", *install_flags],
            extra_env=scenario_env,
        )

        package_json_before_commit = (fixture / "package.json").read_text(encoding="utf-8")

        patch_result = run_command_result(
            "install/patch-binary extract exact-pin json",
            fixture,
            [str(LPM_BIN), "--json", "patch", f"{package_name}@{version}"],
            extra_env=scenario_env,
        )
        if patch_result.returncode != 0:
            raise SmokeFailure(
                f"install/patch-binary extract exact-pin json failed with exit code {patch_result.returncode}"
            )
        patch_envelope = json.loads(patch_result.stdout)
        staging_dir = Path(patch_envelope["staging_dir"])
        require_exists(staging_dir)

        staged_file = staging_dir / "node_modules" / package_name / "logo.txt"
        require_exists(staged_file)
        if staged_file.read_text(encoding="utf-8") != original_text:
            raise SmokeFailure(
                "install/patch-binary staged file: expected pristine text bytes before the binary edit"
            )

        staged_file.write_bytes(b"hello\x00binary")

        binary_error_output = run_command_expect_failure(
            "install/patch-binary patch-commit binary failure",
            fixture,
            [str(LPM_BIN), "patch-commit", str(staging_dir)],
            extra_env=scenario_env,
        )
        require_contains(
            binary_error_output,
            "binary",
            "install/patch-binary patch-commit binary failure",
        )

        if (fixture / "package.json").read_text(encoding="utf-8") != package_json_before_commit:
            raise SmokeFailure(
                "install/patch-binary package.json: expected no manifest mutation after binary patch-commit rejection"
            )

        require_not_exists(fixture / "patches" / f"{package_name}@{version}.patch")
        delete_path(staging_dir)


def scenario_install_hidden_scripts() -> None:
    with tempfile.TemporaryDirectory(prefix="lpm-hidden-scripts-home-") as lpm_home, tempfile.TemporaryDirectory(
        prefix="lpm-hidden-scripts-project-"
    ) as project_dir:
        project_path = Path(project_dir)
        write_package_json(
            project_path / "package.json",
            {
                "name": "hidden-scripts-smoke",
                "version": "1.0.0",
                "private": True,
                "scripts": {
                    "build": "node build-visible.js",
                    "invoke-hidden": "node invoke-hidden.js",
                    ".build": "node write-hidden.js",
                },
            },
        )
        write_package_json(
            project_path / "lpm.json",
            {
                "tasks": {
                    "build": {
                        "dependsOn": [".build"],
                    }
                }
            },
        )
        project_path.joinpath("write-hidden.js").write_text(
            "const fs = require('fs');\n"
            "fs.appendFileSync('hidden-ran.log', 'hidden\\n');\n",
            encoding="utf-8",
        )
        project_path.joinpath("build-visible.js").write_text(
            "process.stdout.write('visible-build\\n');\n",
            encoding="utf-8",
        )
        project_path.joinpath("invoke-hidden.js").write_text(
            "const { spawnSync } = require('child_process');\n"
            "const result = spawnSync(process.env.LPM_TEST_BIN, ['run', '.build'], { stdio: 'inherit' });\n"
            "process.exit(result.status === null ? 1 : result.status);\n",
            encoding="utf-8",
        )

        scenario_env = {
            "LPM_HOME": lpm_home,
            "LPM_TEST_BIN": str(LPM_BIN),
        }

        direct_run_output = run_command_expect_failure(
            "install/hidden-scripts direct run rejected",
            project_path,
            [str(LPM_BIN), "run", ".build"],
            extra_env=scenario_env,
        )
        require_contains(
            direct_run_output,
            "hidden script",
            "install/hidden-scripts direct run rejected",
        )
        require_contains(
            direct_run_output,
            "cannot be invoked directly",
            "install/hidden-scripts direct run rejected",
        )

        shortcut_output = run_command_expect_failure(
            "install/hidden-scripts shorthand rejected",
            project_path,
            [str(LPM_BIN), ".build"],
            extra_env=scenario_env,
        )
        require_contains(
            shortcut_output,
            "hidden script",
            "install/hidden-scripts shorthand rejected",
        )
        require_contains(
            shortcut_output,
            "cannot be invoked directly",
            "install/hidden-scripts shorthand rejected",
        )

        missing_output = run_command_expect_failure(
            "install/hidden-scripts missing suggestions omit hidden",
            project_path,
            [str(LPM_BIN), "run", "missing"],
            extra_env=scenario_env,
        )
        require_contains(
            missing_output,
            "build",
            "install/hidden-scripts missing suggestions omit hidden",
        )
        require_not_contains(
            missing_output,
            ".build",
            "install/hidden-scripts missing suggestions omit hidden",
        )

        invoke_hidden_result = run_command_result(
            "install/hidden-scripts visible script can invoke hidden",
            project_path,
            [str(LPM_BIN), "run", "invoke-hidden"],
            extra_env=scenario_env,
        )
        if invoke_hidden_result.returncode != 0:
            raise SmokeFailure(
                f"install/hidden-scripts visible script can invoke hidden failed with exit code {invoke_hidden_result.returncode}"
            )
        hidden_log = project_path.joinpath("hidden-ran.log")
        require_exists(hidden_log)
        if hidden_log.read_text(encoding="utf-8") != "hidden\n":
            raise SmokeFailure(
                "install/hidden-scripts visible script can invoke hidden: expected the hidden helper to run exactly once"
            )

        dependency_result = run_command_result(
            "install/hidden-scripts lpm-json dependency can invoke hidden",
            project_path,
            [str(LPM_BIN), "run", "build"],
            extra_env=scenario_env,
        )
        if dependency_result.returncode != 0:
            raise SmokeFailure(
                f"install/hidden-scripts lpm-json dependency can invoke hidden failed with exit code {dependency_result.returncode}"
            )
        require_contains(
            dependency_result.stdout,
            "visible-build",
            "install/hidden-scripts lpm-json dependency can invoke hidden stdout",
        )
        if hidden_log.read_text(encoding="utf-8") != "hidden\nhidden\n":
            raise SmokeFailure(
                "install/hidden-scripts lpm-json dependency can invoke hidden: expected the hidden helper to run once via the visible script and once via dependsOn"
            )


def scenario_install_sbom_command() -> None:
    package_name = "smoke-sbom-lib"
    version = "1.0.0"
    patch_rel_path = f"patches/{package_name}@{version}.patch"
    patch_text = "diff --git a/index.js b/index.js\n"
    patch_sha256 = hashlib.sha256(patch_text.encode("utf-8")).hexdigest()
    registry_packages = [
        {
            "name": package_name,
            "description": "registry description",
            "dist_tags": {"latest": version},
            "versions": {
                version: {
                    "metadata_extra": {
                        "dependencies": {},
                        "description": "registry description",
                        "license": "Apache-2.0",
                        "homepage": "https://example.test/sbom-lib",
                    },
                    "package_json_extra": {},
                    "files": {"index.js": "module.exports = 'sbom-lib'\n"},
                }
            },
        }
    ]

    def write_sbom_lockfile(project_path: Path, registry_url: str) -> None:
        lines = [
            "[metadata]",
            "lockfile-version = 2",
            'resolved-with = "greedy-fusion"',
            "",
            "[[packages]]",
            f'name = "{package_name}"',
            f'version = "{version}"',
            f'source = "registry+{registry_url.rstrip('/')}"',
            'integrity = "sha512-smoke-sbom-lib"',
            f'tarball = "{registry_url}tarballs/{package_name}/-/{package_name}-{version}.tgz"',
            "",
        ]
        (project_path / "lpm.lock").write_text("\n".join(lines), encoding="utf-8")

    def cyclonedx_component(envelope: dict[str, object], name: str) -> dict[str, object]:
        components = envelope.get("components")
        if not isinstance(components, list):
            raise SmokeFailure("install/sbom cyclonedx: expected components array")
        for component in components:
            if isinstance(component, dict) and component.get("name") == name:
                return component
        raise SmokeFailure(f"install/sbom cyclonedx: expected component {name!r}")

    def component_property_map(component: dict[str, object]) -> dict[str, str]:
        properties = component.get("properties")
        if not isinstance(properties, list):
            raise SmokeFailure("install/sbom: expected component properties array")
        result: dict[str, str] = {}
        for property_entry in properties:
            if not isinstance(property_entry, dict):
                continue
            name = property_entry.get("name")
            value = property_entry.get("value")
            if isinstance(name, str) and isinstance(value, str):
                result[name] = value
        return result

    def spdx_package(envelope: dict[str, object], name: str) -> dict[str, object]:
        packages = envelope.get("packages")
        if not isinstance(packages, list):
            raise SmokeFailure("install/sbom spdx: expected packages array")
        for package in packages:
            if isinstance(package, dict) and package.get("name") == name:
                return package
        raise SmokeFailure(f"install/sbom spdx: expected package {name!r}")

    with MockRegistry(registry_packages) as registry, tempfile.TemporaryDirectory(
        prefix="lpm-sbom-home-"
    ) as lpm_home, tempfile.TemporaryDirectory(prefix="lpm-sbom-project-") as project_dir:
        project_path = Path(project_dir)
        write_package_json(
            project_path / "package.json",
            {
                "name": "sbom-smoke-app",
                "version": "1.0.0",
                "private": True,
                "license": "MIT",
                "dependencies": {package_name: f"^{version}"},
                "lpm": {
                    "patchedDependencies": {
                        f"{package_name}@{version}": {
                            "path": patch_rel_path,
                            "originalIntegrity": "sha512-smoke-sbom-original",
                        }
                    }
                },
            },
        )
        write_registry_npmrc(project_path, registry.registry_url)
        write_sbom_lockfile(project_path, registry.registry_url)
        seed_node_modules_package(
            project_path,
            package_name,
            version,
            {"index.js": "module.exports = 'sbom-lib'\n"},
        )
        patch_path = project_path / patch_rel_path
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path.write_text(patch_text, encoding="utf-8")

        scenario_env = {"LPM_HOME": lpm_home}

        cyclonedx_result = run_command_result(
            "install/sbom cyclonedx local-first stdout",
            project_path,
            [str(LPM_BIN), "sbom"],
            extra_env=scenario_env,
        )
        if cyclonedx_result.returncode != 0:
            raise SmokeFailure(
                f"install/sbom cyclonedx local-first stdout failed with exit code {cyclonedx_result.returncode}"
            )
        cyclonedx_envelope = json.loads(cyclonedx_result.stdout)
        if cyclonedx_envelope.get("bomFormat") != "CycloneDX":
            raise SmokeFailure("install/sbom cyclonedx local-first stdout: expected bomFormat=CycloneDX")
        if cyclonedx_envelope.get("specVersion") != "1.7":
            raise SmokeFailure("install/sbom cyclonedx local-first stdout: expected specVersion=1.7")
        component = cyclonedx_component(cyclonedx_envelope, package_name)
        properties = component_property_map(component)
        if properties.get("lpm:patch:path") != patch_rel_path:
            raise SmokeFailure(
                "install/sbom cyclonedx local-first stdout: expected patch path metadata in component properties"
            )
        if properties.get("lpm:patch:sha256") != f"sha256-{patch_sha256}":
            raise SmokeFailure(
                "install/sbom cyclonedx local-first stdout: expected patch sha256 metadata in component properties"
            )
        if "description" in component:
            raise SmokeFailure(
                "install/sbom cyclonedx local-first stdout: did not expect registry-only description without --registry-metadata"
            )
        if registry.requested_paths() != []:
            raise SmokeFailure(
                "install/sbom cyclonedx local-first stdout: expected no registry requests without --registry-metadata"
            )
        dependencies = cyclonedx_envelope.get("dependencies")
        if not isinstance(dependencies, list):
            raise SmokeFailure("install/sbom cyclonedx local-first stdout: expected dependencies array")
        component_ref = component.get("bom-ref")
        if not any(
            isinstance(entry, dict)
            and entry.get("ref") == "lpm:root"
            and isinstance(entry.get("dependsOn"), list)
            and component_ref in entry.get("dependsOn")
            for entry in dependencies
        ):
            raise SmokeFailure(
                "install/sbom cyclonedx local-first stdout: expected root dependency edge to the locked package"
            )

        spdx_result = run_command_result(
            "install/sbom spdx stdout",
            project_path,
            [str(LPM_BIN), "sbom", "--format", "spdx"],
            extra_env=scenario_env,
        )
        if spdx_result.returncode != 0:
            raise SmokeFailure(f"install/sbom spdx stdout failed with exit code {spdx_result.returncode}")
        spdx_envelope = json.loads(spdx_result.stdout)
        if spdx_envelope.get("spdxVersion") != "SPDX-2.3":
            raise SmokeFailure("install/sbom spdx stdout: expected spdxVersion=SPDX-2.3")
        spdx_component = spdx_package(spdx_envelope, package_name)
        attribution_texts = spdx_component.get("attributionTexts")
        if not isinstance(attribution_texts, list) or f"lpm:patch:path={patch_rel_path}" not in attribution_texts:
            raise SmokeFailure(
                "install/sbom spdx stdout: expected patch metadata in package attributionTexts"
            )
        if not any(
            isinstance(relationship, dict) and relationship.get("relationshipType") == "DEPENDS_ON"
            for relationship in spdx_envelope.get("relationships", [])
        ):
            raise SmokeFailure(
                "install/sbom spdx stdout: expected at least one DEPENDS_ON relationship"
            )

        registry_metadata_result = run_command_result(
            "install/sbom registry-metadata output file",
            project_path,
            [
                str(LPM_BIN),
                "sbom",
                "--registry-metadata",
                "--output",
                "bom.registry.json",
            ],
            extra_env=scenario_env,
        )
        if registry_metadata_result.returncode != 0:
            raise SmokeFailure(
                f"install/sbom registry-metadata output file failed with exit code {registry_metadata_result.returncode}"
            )
        if registry_metadata_result.stdout:
            raise SmokeFailure(
                "install/sbom registry-metadata output file: expected --output to suppress stdout payload"
            )
        registry_metadata_paths = registry.requested_paths()
        if not registry_metadata_paths:
            raise SmokeFailure(
                "install/sbom registry-metadata output file: expected registry metadata requests when --registry-metadata is set"
            )
        if not any(path in {f"/{package_name}", f"/api/registry/{package_name}", "/api/registry/batch-metadata"} for path in registry_metadata_paths):
            raise SmokeFailure(
                "install/sbom registry-metadata output file: expected package metadata requests routed through the configured registry"
            )
        written_envelope = read_json_file(project_path / "bom.registry.json")
        written_component = cyclonedx_component(written_envelope, package_name)
        if written_component.get("description") != "registry description":
            raise SmokeFailure(
                "install/sbom registry-metadata output file: expected registry description enrichment in the written CycloneDX SBOM"
            )


def scenario_install_download_command() -> None:
    package_name = "smoke-download-lib"
    version = "1.2.0"
    registry_packages = [
        {
            "name": package_name,
            "description": "Download smoke fixture",
            "dist_tags": {"latest": version},
            "versions": {
                version: {
                    "metadata_extra": {"dependencies": {"left-pad": "1.3.0"}},
                    "package_json_extra": {
                        "license": "MIT",
                        "dependencies": {"left-pad": "1.3.0"},
                        "scripts": {"postinstall": "node build.js"},
                    },
                    "files": {
                        "build.js": "require('node:fs').writeFileSync('postinstall-side-effect.txt', 'download should not run scripts\\n')\n",
                        "README.md": "# smoke-download-lib\\n",
                    },
                }
            },
        }
    ]

    with MockRegistry(
        registry_packages,
        serve_proxy_metadata=False,
    ) as registry, tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as lpm_home:
        fixture = reset_download_command_fixture()
        write_registry_npmrc(fixture, registry.registry_url)
        scenario_env = {"LPM_HOME": lpm_home}
        command_prefix = [str(LPM_BIN), "--registry", registry.registry_url, "--insecure"]
        baseline_package_json = (fixture / "package.json").read_text(encoding="utf-8")

        download_result = run_command_result(
            "install/download json",
            fixture,
            command_prefix
            + [
                "download",
                package_name,
                "--version",
                version,
                "--json",
                "--output",
                "nested/../download-out",
            ],
            extra_env=scenario_env,
        )
        if download_result.returncode != 0:
            raise SmokeFailure(
                f"install/download json failed with exit code {download_result.returncode}"
            )
        download_envelope = json.loads(download_result.stdout)
        if download_envelope.get("success") is not True:
            raise SmokeFailure("install/download json: expected success=true")
        if download_envelope.get("package") != package_name:
            raise SmokeFailure("install/download json: expected package name in JSON output")
        if download_envelope.get("version") != version:
            raise SmokeFailure("install/download json: expected requested version in JSON output")
        if download_envelope.get("integrity_verified") is not True:
            raise SmokeFailure("install/download json: expected integrity_verified=true")
        if not download_envelope.get("integrity"):
            raise SmokeFailure("install/download json: expected integrity to be present")
        if download_envelope.get("files_extracted") != 4:
            raise SmokeFailure("install/download json: expected files_extracted=4")
        expected_output_dir = str((fixture / "download-out").resolve())
        if download_envelope.get("output_dir") != expected_output_dir:
            raise SmokeFailure(
                "install/download json: expected canonical absolute output_dir in JSON output"
            )

        extracted_dir = fixture / "download-out"
        require_exists(extracted_dir / "package.json")
        require_exists(extracted_dir / "index.js")
        require_exists(extracted_dir / "build.js")
        require_exists(extracted_dir / "README.md")
        require_not_exists(extracted_dir / "package")
        require_not_exists(extracted_dir / "postinstall-side-effect.txt")

        if (fixture / "package.json").read_text(encoding="utf-8") != baseline_package_json:
            raise SmokeFailure("install/download package.json: expected no manifest mutation")
        require_not_exists(fixture / "node_modules")
        require_not_exists(fixture / "lpm.lock")
        require_not_exists(fixture / "lpm.lockb")
        require_directory_empty_or_absent(Path(lpm_home) / "store", "install/download store")


def scenario_install_resolve_command() -> None:
    bare_package = "smoke-resolve-bare"
    scoped_package = "@smoke/resolve-lib"
    registry_packages = [
        {
            "name": bare_package,
            "description": "Bare resolve fixture",
            "dist_tags": {"latest": "1.5.0"},
            "versions": {
                "1.0.0": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {"license": "MIT"},
                    "files": {},
                },
                "1.5.0": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {"license": "MIT"},
                    "files": {},
                },
            },
        },
        {
            "name": scoped_package,
            "description": "Scoped resolve fixture",
            "dist_tags": {"latest": "2.3.0"},
            "versions": {
                "1.9.0": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {"license": "MIT"},
                    "files": {},
                },
                "2.3.0": {
                    "metadata_extra": {"dependencies": {}},
                    "package_json_extra": {"license": "MIT"},
                    "files": {},
                },
            },
        },
    ]

    with MockRegistry(
        registry_packages,
        serve_proxy_metadata=False,
    ) as registry, tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as lpm_home:
        fixture = reset_resolve_command_fixture()
        (fixture / ".npmrc").write_text(
            f"registry={registry.registry_url}\n@smoke:registry={registry.registry_url}\n",
            encoding="utf-8",
        )
        scenario_env = {"LPM_HOME": lpm_home}
        command_prefix = [str(LPM_BIN), "--registry", registry.registry_url, "--insecure"]
        baseline_package_json = (fixture / "package.json").read_text(encoding="utf-8")

        resolve_result = run_command_result(
            "install/resolve json",
            fixture,
            command_prefix
            + [
                "resolve",
                bare_package,
                f"{scoped_package}@^2",
                "--json",
            ],
            extra_env=scenario_env,
        )
        if resolve_result.returncode != 0:
            raise SmokeFailure(
                f"install/resolve json failed with exit code {resolve_result.returncode}"
            )
        resolve_envelope = json.loads(resolve_result.stdout)
        if resolve_envelope.get("success") is not True:
            raise SmokeFailure("install/resolve json: expected success=true")
        if resolve_envelope.get("count") != 2:
            raise SmokeFailure("install/resolve json: expected count=2")
        if not isinstance(resolve_envelope.get("elapsed_secs"), (int, float)):
            raise SmokeFailure("install/resolve json: expected numeric elapsed_secs")

        resolved_map = {
            package.get("package"): package.get("version")
            for package in resolve_envelope.get("packages", [])
        }
        if resolved_map.get(bare_package) != "1.5.0":
            raise SmokeFailure(
                "install/resolve json: expected bare package to resolve to latest version"
            )
        if resolved_map.get(scoped_package) != "2.3.0":
            raise SmokeFailure(
                "install/resolve json: expected scoped range to resolve using the last @ as the version separator"
            )

        requested_paths = registry.requested_paths()
        if f"/{bare_package}" not in requested_paths:
            raise SmokeFailure(
                "install/resolve request log: expected metadata lookup for the bare package"
            )
        if f"/{scoped_package}" not in requested_paths:
            raise SmokeFailure(
                "install/resolve request log: expected metadata lookup for the scoped package"
            )
        if any(path.startswith("/tarballs/") for path in requested_paths):
            raise SmokeFailure(
                "install/resolve request log: expected metadata-only resolution with no tarball downloads"
            )

        if (fixture / "package.json").read_text(encoding="utf-8") != baseline_package_json:
            raise SmokeFailure("install/resolve package.json: expected no manifest mutation")
        require_not_exists(fixture / "node_modules")
        require_not_exists(fixture / "lpm.lock")
        require_not_exists(fixture / "lpm.lockb")
        require_directory_empty_or_absent(Path(lpm_home) / "store", "install/resolve store")


def scenario_install_migrate_npm() -> None:
    with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as lpm_home:
        fixture = reset_migrate_npm_fixture()
        scenario_env = {"LPM_HOME": lpm_home}
        baseline_package_json = (fixture / "package.json").read_text(encoding="utf-8")
        baseline_package_lock = (fixture / "package-lock.json").read_text(encoding="utf-8")

        dry_run_result = run_command_result(
            "install/migrate-npm dry-run json",
            fixture,
            [str(LPM_BIN), "--json", "migrate", "--dry-run"],
            extra_env=scenario_env,
        )
        if dry_run_result.returncode != 0:
            raise SmokeFailure(
                f"install/migrate-npm dry-run json failed with exit code {dry_run_result.returncode}"
            )
        dry_run_envelope = json.loads(dry_run_result.stdout)
        if dry_run_envelope.get("success") is not True:
            raise SmokeFailure("install/migrate-npm dry-run json: expected success=true")
        if dry_run_envelope.get("dry_run") is not True:
            raise SmokeFailure("install/migrate-npm dry-run json: expected dry_run=true")
        if dry_run_envelope.get("source") != "npm":
            raise SmokeFailure("install/migrate-npm dry-run json: expected source=npm")

        require_not_exists(fixture / "lpm.lock")
        require_not_exists(fixture / "lpm.lockb")
        require_not_exists(fixture / ".npmrc")
        require_not_exists(fixture / ".gitattributes")
        require_not_exists(fixture / ".lpm-migrate-manifest.json")
        require_not_exists(fixture / "package-lock.json.backup")
        require_directory_empty_or_absent(Path(lpm_home) / "store", "install/migrate-npm dry-run store")

        if (fixture / "package.json").read_text(encoding="utf-8") != baseline_package_json:
            raise SmokeFailure("install/migrate-npm dry-run package.json: expected no manifest mutation")
        if (fixture / "package-lock.json").read_text(encoding="utf-8") != baseline_package_lock:
            raise SmokeFailure("install/migrate-npm dry-run package-lock.json: expected no lockfile mutation")

        migrate_result = run_command_result(
            "install/migrate-npm json",
            fixture,
            [str(LPM_BIN), "--json", "migrate", "--no-install", "--force"],
            extra_env=scenario_env,
        )
        if migrate_result.returncode != 0:
            raise SmokeFailure(
                f"install/migrate-npm json failed with exit code {migrate_result.returncode}"
            )
        migrate_envelope = json.loads(migrate_result.stdout)
        if migrate_envelope.get("success") is not True:
            raise SmokeFailure("install/migrate-npm json: expected success=true")
        if migrate_envelope.get("source") != "npm":
            raise SmokeFailure("install/migrate-npm json: expected source=npm")

        require_exists(fixture / "lpm.lock")
        require_exists(fixture / "lpm.lockb")
        require_exists(fixture / "package-lock.json.backup")
        require_exists(fixture / ".npmrc")
        require_exists(fixture / ".gitattributes")
        require_exists(fixture / ".lpm-migrate-manifest.json")
        require_not_exists(fixture / "node_modules")

        npmrc_text = (fixture / ".npmrc").read_text(encoding="utf-8")
        if npmrc_text != "@lpm.dev:registry=https://lpm.dev/api/registry/\n":
            raise SmokeFailure(
                "install/migrate-npm .npmrc: expected migrate to create the default @lpm.dev registry scope"
            )

        rollback_result = run_command_result(
            "install/migrate-npm rollback json",
            fixture,
            [str(LPM_BIN), "--json", "migrate", "--rollback"],
            extra_env=scenario_env,
        )
        if rollback_result.returncode != 0:
            raise SmokeFailure(
                f"install/migrate-npm rollback json failed with exit code {rollback_result.returncode}"
            )
        rollback_envelope = json.loads(rollback_result.stdout)
        if rollback_envelope.get("success") is not True:
            raise SmokeFailure("install/migrate-npm rollback json: expected success=true")
        if rollback_envelope.get("rollback") is not True:
            raise SmokeFailure("install/migrate-npm rollback json: expected rollback=true")
        if not isinstance(rollback_envelope.get("restored_files"), list):
            raise SmokeFailure(
                "install/migrate-npm rollback json: expected restored_files array"
            )

        require_not_exists(fixture / "lpm.lock")
        require_not_exists(fixture / "lpm.lockb")
        require_not_exists(fixture / ".npmrc")
        require_not_exists(fixture / ".gitattributes")
        require_not_exists(fixture / ".lpm-migrate-manifest.json")
        require_not_exists(fixture / "node_modules")
        require_directory_empty_or_absent(Path(lpm_home) / "store", "install/migrate-npm rollback store")

        if (fixture / "package.json").read_text(encoding="utf-8") != baseline_package_json:
            raise SmokeFailure("install/migrate-npm rollback package.json: expected original manifest bytes after rollback")
        if (fixture / "package-lock.json").read_text(encoding="utf-8") != baseline_package_lock:
            raise SmokeFailure(
                "install/migrate-npm rollback package-lock.json: expected original foreign lockfile bytes after rollback"
            )


def scenario_install_migrate_pnpm() -> None:
    with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as lpm_home:
        fixture = reset_migrate_pnpm_fixture()
        scenario_env = {"LPM_HOME": lpm_home}
        baseline_package_json = (fixture / "package.json").read_text(encoding="utf-8")
        baseline_pnpm_lock = (fixture / "pnpm-lock.yaml").read_text(encoding="utf-8")

        migrate_result = run_command_result(
            "install/migrate-pnpm json",
            fixture,
            [str(LPM_BIN), "--json", "migrate", "--no-install", "--force", "--no-npmrc"],
            extra_env=scenario_env,
        )
        if migrate_result.returncode != 0:
            raise SmokeFailure(
                f"install/migrate-pnpm json failed with exit code {migrate_result.returncode}"
            )
        migrate_envelope = json.loads(migrate_result.stdout)
        if migrate_envelope.get("success") is not True:
            raise SmokeFailure("install/migrate-pnpm json: expected success=true")
        if migrate_envelope.get("source") != "pnpm":
            raise SmokeFailure("install/migrate-pnpm json: expected source=pnpm")

        require_exists(fixture / "lpm.lock")
        require_exists(fixture / "lpm.lockb")
        require_exists(fixture / "pnpm-lock.yaml.backup")
        require_exists(fixture / "package.json.backup")
        require_exists(fixture / ".gitattributes")
        require_exists(fixture / ".lpm-migrate-manifest.json")
        require_not_exists(fixture / ".npmrc")
        require_not_exists(fixture / "node_modules")
        require_directory_empty_or_absent(Path(lpm_home) / "store", "install/migrate-pnpm store")

        if (fixture / "pnpm-lock.yaml").read_text(encoding="utf-8") != baseline_pnpm_lock:
            raise SmokeFailure(
                "install/migrate-pnpm pnpm-lock.yaml: expected migration to leave the source lockfile bytes untouched"
            )

        if (fixture / "package.json.backup").read_text(encoding="utf-8") != baseline_package_json:
            raise SmokeFailure(
                "install/migrate-pnpm package.json.backup: expected backup to preserve the pre-translation manifest bytes"
            )

        package_json = read_json_file(fixture / "package.json")
        lpm_overrides = package_json.get("lpm", {}).get("overrides", {})
        pnpm_overrides = package_json.get("pnpm", {}).get("overrides", {})
        if lpm_overrides.get("lodash") != "^4.17.21":
            raise SmokeFailure(
                "install/migrate-pnpm package.json: expected lodash override to be translated into lpm.overrides"
            )
        if lpm_overrides.get("react") != "18.2.0":
            raise SmokeFailure(
                "install/migrate-pnpm package.json: expected react override to be translated into lpm.overrides"
            )
        if pnpm_overrides.get("lodash") != "^4.17.21" or pnpm_overrides.get("react") != "18.2.0":
            raise SmokeFailure(
                "install/migrate-pnpm package.json: expected the original pnpm.overrides block to remain in place after migration"
            )


def scenario_install_migrate_pnpm_patches() -> None:
    with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as lpm_home:
        fixture = reset_migrate_pnpm_patches_fixture()
        scenario_env = {"LPM_HOME": lpm_home}
        baseline_package_json = (fixture / "package.json").read_text(encoding="utf-8")
        baseline_pnpm_lock = (fixture / "pnpm-lock.yaml").read_text(encoding="utf-8")
        baseline_patch = (fixture / "patches" / "ms@2.1.3.patch").read_text(encoding="utf-8")

        migrate_result = run_command_result(
            "install/migrate-pnpm-patches json",
            fixture,
            [str(LPM_BIN), "--json", "migrate", "--no-install", "--force", "--no-npmrc"],
            extra_env=scenario_env,
        )
        if migrate_result.returncode != 0:
            raise SmokeFailure(
                f"install/migrate-pnpm-patches json failed with exit code {migrate_result.returncode}"
            )
        migrate_envelope = json.loads(migrate_result.stdout)
        if migrate_envelope.get("success") is not True:
            raise SmokeFailure("install/migrate-pnpm-patches json: expected success=true")
        if migrate_envelope.get("source") != "pnpm":
            raise SmokeFailure("install/migrate-pnpm-patches json: expected source=pnpm")

        require_exists(fixture / "lpm.lock")
        require_exists(fixture / "lpm.lockb")
        require_exists(fixture / "pnpm-lock.yaml.backup")
        require_exists(fixture / "package.json.backup")
        require_exists(fixture / ".gitattributes")
        require_exists(fixture / ".lpm-migrate-manifest.json")
        require_exists(fixture / "patches" / "ms@2.1.3.patch")
        require_not_exists(fixture / ".npmrc")
        require_not_exists(fixture / "node_modules")
        require_directory_empty_or_absent(Path(lpm_home) / "store", "install/migrate-pnpm-patches store")

        if (fixture / "pnpm-lock.yaml").read_text(encoding="utf-8") != baseline_pnpm_lock:
            raise SmokeFailure(
                "install/migrate-pnpm-patches pnpm-lock.yaml: expected migration to leave the source lockfile bytes untouched"
            )
        if (fixture / "package.json.backup").read_text(encoding="utf-8") != baseline_package_json:
            raise SmokeFailure(
                "install/migrate-pnpm-patches package.json.backup: expected backup to preserve the pre-translation manifest bytes"
            )
        if (fixture / "patches" / "ms@2.1.3.patch").read_text(encoding="utf-8") != baseline_patch:
            raise SmokeFailure(
                "install/migrate-pnpm-patches patch file: expected the canonical self-copy patch file bytes to stay intact"
            )

        package_json = read_json_file(fixture / "package.json")
        lpm_patches = package_json.get("lpm", {}).get("patchedDependencies", {})
        pnpm_patches = package_json.get("pnpm", {}).get("patchedDependencies", {})
        patch_entry = lpm_patches.get("ms@2.1.3")
        if not isinstance(patch_entry, dict):
            raise SmokeFailure(
                "install/migrate-pnpm-patches package.json: expected lpm.patchedDependencies entry after migration"
            )
        if patch_entry.get("path") != "patches/ms@2.1.3.patch":
            raise SmokeFailure(
                "install/migrate-pnpm-patches package.json: expected translated patch path to remain canonical"
            )
        original_integrity = patch_entry.get("originalIntegrity")
        if not isinstance(original_integrity, str) or not original_integrity.startswith("sha512-"):
            raise SmokeFailure(
                "install/migrate-pnpm-patches package.json: expected originalIntegrity to be populated from the migrated lockfile"
            )
        if pnpm_patches.get("ms@2.1.3") != "patches/ms@2.1.3.patch":
            raise SmokeFailure(
                "install/migrate-pnpm-patches package.json: expected the original pnpm.patchedDependencies block to remain in place"
            )


def scenario_install_migrate_bun() -> None:
    with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as lpm_home:
        fixture = reset_migrate_bun_fixture()
        scenario_env = {"LPM_HOME": lpm_home}
        baseline_package_json = (fixture / "package.json").read_text(encoding="utf-8")
        baseline_bun_lock = (fixture / "bun.lock").read_text(encoding="utf-8")

        migrate_result = run_command_result(
            "install/migrate-bun json",
            fixture,
            [str(LPM_BIN), "--json", "migrate", "--no-install", "--force", "--no-npmrc"],
            extra_env=scenario_env,
        )
        if migrate_result.returncode != 0:
            raise SmokeFailure(
                f"install/migrate-bun json failed with exit code {migrate_result.returncode}"
            )
        migrate_envelope = json.loads(migrate_result.stdout)
        if migrate_envelope.get("success") is not True:
            raise SmokeFailure("install/migrate-bun json: expected success=true")
        if migrate_envelope.get("source") != "bun":
            raise SmokeFailure("install/migrate-bun json: expected source=bun")

        require_exists(fixture / "lpm.lock")
        require_exists(fixture / "lpm.lockb")
        require_exists(fixture / "bun.lock.backup")
        require_exists(fixture / ".gitattributes")
        require_exists(fixture / ".lpm-migrate-manifest.json")
        require_not_exists(fixture / ".npmrc")
        require_not_exists(fixture / "package.json.backup")
        require_not_exists(fixture / "node_modules")
        require_directory_empty_or_absent(Path(lpm_home) / "store", "install/migrate-bun store")

        if (fixture / "package.json").read_text(encoding="utf-8") != baseline_package_json:
            raise SmokeFailure(
                "install/migrate-bun package.json: expected no manifest mutation for a plain Bun migration"
            )
        if (fixture / "bun.lock").read_text(encoding="utf-8") != baseline_bun_lock:
            raise SmokeFailure(
                "install/migrate-bun bun.lock: expected migration to leave the source bun.lock bytes untouched"
            )


def scenario_install_migrate_yarn() -> None:
    with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as lpm_home:
        fixture = reset_migrate_yarn_fixture()
        scenario_env = {"LPM_HOME": lpm_home}
        baseline_package_json = (fixture / "package.json").read_text(encoding="utf-8")
        baseline_yarn_lock = (fixture / "yarn.lock").read_text(encoding="utf-8")

        migrate_result = run_command_result(
            "install/migrate-yarn json",
            fixture,
            [str(LPM_BIN), "--json", "migrate", "--no-install", "--force", "--no-npmrc"],
            extra_env=scenario_env,
        )
        if migrate_result.returncode != 0:
            raise SmokeFailure(
                f"install/migrate-yarn json failed with exit code {migrate_result.returncode}"
            )
        migrate_envelope = json.loads(migrate_result.stdout)
        if migrate_envelope.get("success") is not True:
            raise SmokeFailure("install/migrate-yarn json: expected success=true")
        if migrate_envelope.get("source") != "yarn":
            raise SmokeFailure("install/migrate-yarn json: expected source=yarn")
        if migrate_envelope.get("package_count") != 3:
            raise SmokeFailure("install/migrate-yarn json: expected package_count=3 for depd, ms, and prettier")

        require_exists(fixture / "lpm.lock")
        require_exists(fixture / "lpm.lockb")
        require_exists(fixture / "yarn.lock.backup")
        require_exists(fixture / ".gitattributes")
        require_exists(fixture / ".lpm-migrate-manifest.json")
        require_not_exists(fixture / ".npmrc")
        require_not_exists(fixture / "package.json.backup")
        require_not_exists(fixture / "node_modules")
        require_directory_empty_or_absent(Path(lpm_home) / "store", "install/migrate-yarn store")

        if (fixture / "package.json").read_text(encoding="utf-8") != baseline_package_json:
            raise SmokeFailure(
                "install/migrate-yarn package.json: expected no manifest mutation for a plain Yarn migration"
            )
        if (fixture / "yarn.lock").read_text(encoding="utf-8") != baseline_yarn_lock:
            raise SmokeFailure(
                "install/migrate-yarn yarn.lock: expected migration to leave the source yarn.lock bytes untouched"
            )

        lpm_lock_text = (fixture / "lpm.lock").read_text(encoding="utf-8")
        require_contains(lpm_lock_text, 'name = "ms"', "install/migrate-yarn lpm.lock")
        require_contains(lpm_lock_text, 'name = "depd"', "install/migrate-yarn lpm.lock")
        require_contains(lpm_lock_text, 'name = "prettier"', "install/migrate-yarn lpm.lock")


def scenario_install_remote_cache() -> None:
    build_script = """const fs = require(\"node:fs\")

fs.mkdirSync(\"dist\", { recursive: true })
fs.writeFileSync(\"dist/value.txt\", \"remote-cache-output\\n\", \"utf8\")
fs.writeFileSync(\"executed-marker\", \"ran\\n\", \"utf8\")
process.stdout.write(\"remote-build-output\\n\")
"""

    def write_remote_cache_project(
        project_dir: Path,
        package_name: str,
        remote_cache_config: dict[str, object],
    ) -> None:
        write_package_json(
            project_dir / "package.json",
            {
                "name": package_name,
                "private": True,
                "version": "1.0.0",
                "scripts": {
                    "build": "node build-script.cjs",
                },
            },
        )
        (project_dir / "build-script.cjs").write_text(build_script, encoding="utf-8")
        (project_dir / "lpm.json").write_text(
            json.dumps(
                {
                    "tasks": {
                        "build": {
                            "cache": True,
                            "outputs": ["dist/**"],
                        }
                    },
                    "remoteCache": remote_cache_config,
                },
                indent=4,
            )
            + "\n",
            encoding="utf-8",
        )

    def assert_slug_requests(
        requests: list[dict[str, object]],
        context: str,
    ) -> None:
        if not requests:
            raise SmokeFailure(f"{context}: expected at least one remote cache request")
        for request in requests:
            query = request.get("query")
            if not isinstance(query, dict) or query.get("slug") != ["acme"]:
                raise SmokeFailure(f"{context}: expected slug=acme on every remote cache request")

    with MockRemoteCache() as remote_cache:
        signature_env = {
            "LPM_REMOTE_CACHE_TOKEN": "remote-cache-token",
            "LPM_REMOTE_CACHE_SIGNATURE_KEY": "remote-cache-signature-key",
        }

        with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as lpm_home:
            with tempfile.TemporaryDirectory(prefix="lpm-remote-cache-project-") as project_dir:
                project_path = Path(project_dir)
                write_remote_cache_project(
                    project_path,
                    "remote-cache-smoke",
                    {
                        "enabled": True,
                        "team": "acme",
                        "url": remote_cache.base_url,
                        "signature": True,
                    },
                )

                scenario_env = {
                    "LPM_HOME": lpm_home,
                    **signature_env,
                }

                first_run = run_command_result(
                    "install/remote-cache initial upload",
                    project_path,
                    [str(LPM_BIN), "run", "build"],
                    extra_env=scenario_env,
                )
                if first_run.returncode != 0:
                    raise SmokeFailure(
                        "install/remote-cache initial upload failed with exit code "
                        f"{first_run.returncode}"
                    )
                require_exists(project_path / "dist" / "value.txt")
                require_exists(project_path / "executed-marker")

                initial_artifact_requests = remote_cache.requests(path="/v8/artifacts/status")
                if initial_artifact_requests:
                    raise SmokeFailure(
                        "install/remote-cache initial upload: build should not query cache status"
                    )

                initial_gets = remote_cache.requests(method="GET", path="/v8/artifacts/build")
                if initial_gets:
                    raise SmokeFailure(
                        "install/remote-cache initial upload: expected hashed artifact paths, not /v8/artifacts/build"
                    )

                initial_puts = remote_cache.requests(method="PUT")
                if len(initial_puts) != 1:
                    raise SmokeFailure(
                        "install/remote-cache initial upload: expected exactly one artifact upload"
                    )
                assert_slug_requests(remote_cache.requests(), "install/remote-cache initial upload")
                if remote_cache.artifact_tag is None or not remote_cache.artifact_tag.startswith("sha256="):
                    raise SmokeFailure(
                        "install/remote-cache initial upload: expected an HMAC artifact tag on the upload"
                    )

                status_result = run_command_result(
                    "install/remote-cache cache status json",
                    project_path,
                    [str(LPM_BIN), "--json", "cache", "status"],
                    extra_env=scenario_env,
                )
                if status_result.returncode != 0:
                    raise SmokeFailure(
                        "install/remote-cache cache status json failed with exit code "
                        f"{status_result.returncode}"
                    )
                status_envelope = json.loads(status_result.stdout)
                if status_envelope.get("success") is not True:
                    raise SmokeFailure(
                        "install/remote-cache cache status json: expected success=true"
                    )
                if status_envelope.get("local", {}).get("bytes", 0) <= 0:
                    raise SmokeFailure(
                        "install/remote-cache cache status json: expected local cache bytes after the initial build"
                    )
                remote_envelope = status_envelope.get("remote", {})
                if remote_envelope.get("enabled") is not True:
                    raise SmokeFailure(
                        "install/remote-cache cache status json: expected remote.enabled=true"
                    )
                if remote_envelope.get("url") != remote_cache.base_url:
                    raise SmokeFailure(
                        "install/remote-cache cache status json: expected the configured remote cache URL"
                    )
                if remote_envelope.get("team") != "acme":
                    raise SmokeFailure(
                        "install/remote-cache cache status json: expected remote.team=acme"
                    )
                if remote_envelope.get("status") != "enabled":
                    raise SmokeFailure(
                        "install/remote-cache cache status json: expected remote.status=enabled"
                    )
                if remote_envelope.get("usage_bytes") != 1024:
                    raise SmokeFailure(
                        "install/remote-cache cache status json: expected remote.usage_bytes=1024"
                    )
                if remote_envelope.get("limit_bytes") != 2048:
                    raise SmokeFailure(
                        "install/remote-cache cache status json: expected remote.limit_bytes=2048"
                    )

                status_requests = remote_cache.requests(method="GET", path="/v8/artifacts/status")
                if len(status_requests) != 1:
                    raise SmokeFailure(
                        "install/remote-cache cache status json: expected exactly one status request"
                    )
                assert_slug_requests(status_requests, "install/remote-cache cache status json")

                remote_cache.clear_requests()
                delete_path(Path(lpm_home) / "cache" / "tasks")
                delete_path(project_path / "dist")
                delete_path(project_path / "executed-marker")

                remote_hit = run_command_result(
                    "install/remote-cache remote hit restore",
                    project_path,
                    [str(LPM_BIN), "run", "build"],
                    extra_env=scenario_env,
                )
                if remote_hit.returncode != 0:
                    raise SmokeFailure(
                        "install/remote-cache remote hit restore failed with exit code "
                        f"{remote_hit.returncode}"
                    )
                require_exists(project_path / "dist" / "value.txt")
                require_not_exists(project_path / "executed-marker")
                require_contains(
                    remote_hit.stdout + remote_hit.stderr,
                    "remote-build-output",
                    "install/remote-cache remote hit output replay",
                )
                if remote_cache.requests(method="PUT"):
                    raise SmokeFailure(
                        "install/remote-cache remote hit restore: expected no upload on a remote cache hit"
                    )
                hit_gets = remote_cache.requests(method="GET")
                if len(hit_gets) != 1:
                    raise SmokeFailure(
                        "install/remote-cache remote hit restore: expected exactly one remote artifact fetch"
                    )
                assert_slug_requests(hit_gets, "install/remote-cache remote hit restore")

                remote_cache.set_download_tag_override("sha256=bad-signature")
                remote_cache.clear_requests()
                delete_path(Path(lpm_home) / "cache" / "tasks")
                delete_path(project_path / "dist")
                delete_path(project_path / "executed-marker")

                invalid_signature = run_command_result(
                    "install/remote-cache invalid signature fallback",
                    project_path,
                    [str(LPM_BIN), "run", "build"],
                    extra_env=scenario_env,
                )
                if invalid_signature.returncode != 0:
                    raise SmokeFailure(
                        "install/remote-cache invalid signature fallback failed with exit code "
                        f"{invalid_signature.returncode}"
                    )
                require_exists(project_path / "dist" / "value.txt")
                require_exists(project_path / "executed-marker")
                invalid_signature_requests = remote_cache.requests()
                if len([request for request in invalid_signature_requests if request.get("method") == "GET"]) != 1:
                    raise SmokeFailure(
                        "install/remote-cache invalid signature fallback: expected a remote fetch before the local rebuild"
                    )
                if len([request for request in invalid_signature_requests if request.get("method") == "PUT"]) != 1:
                    raise SmokeFailure(
                        "install/remote-cache invalid signature fallback: expected a fresh upload after the local rebuild"
                    )
                require_contains(
                    invalid_signature.stdout + invalid_signature.stderr,
                    "signature",
                    "install/remote-cache invalid signature warning",
                )
                assert_slug_requests(
                    invalid_signature_requests,
                    "install/remote-cache invalid signature fallback",
                )

                remote_cache.set_download_tag_override(None)
                remote_cache.set_status(503, {"error": "temporarily unavailable"})
                remote_cache.clear_requests()
                status_error = run_command_result(
                    "install/remote-cache cache status degraded json",
                    project_path,
                    [str(LPM_BIN), "--json", "cache", "status"],
                    extra_env=scenario_env,
                )
                if status_error.returncode != 0:
                    raise SmokeFailure(
                        "install/remote-cache cache status degraded json failed with exit code "
                        f"{status_error.returncode}"
                    )
                status_error_envelope = json.loads(status_error.stdout)
                if status_error_envelope.get("success") is not True:
                    raise SmokeFailure(
                        "install/remote-cache cache status degraded json: expected success=true"
                    )
                degraded_remote = status_error_envelope.get("remote", {})
                if degraded_remote.get("enabled") is not True:
                    raise SmokeFailure(
                        "install/remote-cache cache status degraded json: expected remote.enabled=true"
                    )
                degraded_error = degraded_remote.get("error")
                if not isinstance(degraded_error, str) or "HTTP 503" not in degraded_error:
                    raise SmokeFailure(
                        "install/remote-cache cache status degraded json: expected remote.error to mention HTTP 503"
                    )

        remote_cache.set_status(
            200,
            {
                "status": "enabled",
                "usageBytes": 1024,
                "limitBytes": 2048,
            },
        )
        remote_cache.reset_artifact()
        remote_cache.clear_requests()

        with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as read_only_home:
            with tempfile.TemporaryDirectory(prefix="lpm-remote-cache-project-") as project_dir:
                project_path = Path(project_dir)
                write_remote_cache_project(
                    project_path,
                    "remote-cache-read-only-smoke",
                    {
                        "enabled": True,
                        "team": "acme",
                        "url": remote_cache.base_url,
                    },
                )

                read_only_result = run_command_result(
                    "install/remote-cache read-only upload skip",
                    project_path,
                    [str(LPM_BIN), "run", "build"],
                    extra_env={
                        "LPM_HOME": read_only_home,
                        "LPM_REMOTE_CACHE_TOKEN": "remote-cache-token",
                        "LPM_REMOTE_CACHE_READ_ONLY": "1",
                    },
                )
                if read_only_result.returncode != 0:
                    raise SmokeFailure(
                        "install/remote-cache read-only upload skip failed with exit code "
                        f"{read_only_result.returncode}"
                    )
                if remote_cache.requests(method="PUT"):
                    raise SmokeFailure(
                        "install/remote-cache read-only upload skip: expected no upload while read-only is enabled"
                    )
                read_only_gets = remote_cache.requests(method="GET")
                if len(read_only_gets) != 1:
                    raise SmokeFailure(
                        "install/remote-cache read-only upload skip: expected a single remote miss lookup"
                    )
                assert_slug_requests(
                    read_only_gets,
                    "install/remote-cache read-only upload skip",
                )

        remote_cache.reset_artifact()
        remote_cache.clear_requests()

        with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as secret_home:
            with tempfile.TemporaryDirectory(prefix="lpm-remote-cache-project-") as project_dir:
                project_path = Path(project_dir)
                write_remote_cache_project(
                    project_path,
                    "remote-cache-secret-smoke",
                    {
                        "enabled": True,
                        "team": "acme",
                        "url": remote_cache.base_url,
                    },
                )
                (project_path / ".env").write_text(
                    "DATABASE_URL=postgres://secret@example.test/lpm\n",
                    encoding="utf-8",
                )

                secret_env = {
                    "LPM_HOME": secret_home,
                    "LPM_REMOTE_CACHE_TOKEN": "remote-cache-token",
                }

                secret_first_run = run_command_result(
                    "install/remote-cache secret env upload block",
                    project_path,
                    [str(LPM_BIN), "run", "build"],
                    extra_env=secret_env,
                )
                if secret_first_run.returncode != 0:
                    raise SmokeFailure(
                        "install/remote-cache secret env upload block failed with exit code "
                        f"{secret_first_run.returncode}"
                    )
                if remote_cache.requests(method="PUT"):
                    raise SmokeFailure(
                        "install/remote-cache secret env upload block: expected no upload when secret-looking env vars are present"
                    )
                require_contains(
                    secret_first_run.stdout + secret_first_run.stderr,
                    "DATABASE_URL",
                    "install/remote-cache secret env warning",
                )

                remote_cache.clear_requests()
                delete_path(project_path / "dist")
                delete_path(project_path / "executed-marker")

                secret_local_hit = run_command_result(
                    "install/remote-cache secret env local cache hit",
                    project_path,
                    [str(LPM_BIN), "run", "build"],
                    extra_env=secret_env,
                )
                if secret_local_hit.returncode != 0:
                    raise SmokeFailure(
                        "install/remote-cache secret env local cache hit failed with exit code "
                        f"{secret_local_hit.returncode}"
                    )
                require_exists(project_path / "dist" / "value.txt")
                require_not_exists(project_path / "executed-marker")
                if remote_cache.requests():
                    raise SmokeFailure(
                        "install/remote-cache secret env local cache hit: expected no remote requests once the local cache is warm"
                    )

        remote_cache.reset_artifact()
        remote_cache.clear_requests()

        with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as include_home:
            with tempfile.TemporaryDirectory(prefix="lpm-remote-cache-project-") as project_dir:
                project_path = Path(project_dir)
                write_remote_cache_project(
                    project_path,
                    "remote-cache-include-smoke",
                    {
                        "enabled": True,
                        "team": "acme",
                        "url": remote_cache.base_url,
                        "env": {
                            "include": ["DATABASE_URL"],
                        },
                    },
                )
                (project_path / ".env").write_text(
                    "DATABASE_URL=postgres://include@example.test/lpm\n",
                    encoding="utf-8",
                )

                include_result = run_command_result(
                    "install/remote-cache env include allow",
                    project_path,
                    [str(LPM_BIN), "run", "build"],
                    extra_env={
                        "LPM_HOME": include_home,
                        "LPM_REMOTE_CACHE_TOKEN": "remote-cache-token",
                    },
                )
                if include_result.returncode != 0:
                    raise SmokeFailure(
                        "install/remote-cache env include allow failed with exit code "
                        f"{include_result.returncode}"
                    )
                if len(remote_cache.requests(method="PUT")) != 1:
                    raise SmokeFailure(
                        "install/remote-cache env include allow: expected an upload when DATABASE_URL is explicitly included"
                    )
                require_not_contains(
                    include_result.stdout + include_result.stderr,
                    "looks secret-like",
                    "install/remote-cache env include allow warning",
                )

        remote_cache.reset_artifact()
        remote_cache.clear_requests()

        with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as exclude_home:
            with tempfile.TemporaryDirectory(prefix="lpm-remote-cache-project-") as project_dir:
                project_path = Path(project_dir)
                write_remote_cache_project(
                    project_path,
                    "remote-cache-exclude-smoke",
                    {
                        "enabled": True,
                        "team": "acme",
                        "url": remote_cache.base_url,
                        "env": {
                            "include": ["DATABASE_*"],
                            "exclude": ["*_URL"],
                        },
                    },
                )
                (project_path / ".env").write_text(
                    "DATABASE_URL=postgres://exclude@example.test/lpm\n",
                    encoding="utf-8",
                )

                exclude_result = run_command_result(
                    "install/remote-cache env exclude precedence",
                    project_path,
                    [str(LPM_BIN), "run", "build"],
                    extra_env={
                        "LPM_HOME": exclude_home,
                        "LPM_REMOTE_CACHE_TOKEN": "remote-cache-token",
                    },
                )
                if exclude_result.returncode != 0:
                    raise SmokeFailure(
                        "install/remote-cache env exclude precedence failed with exit code "
                        f"{exclude_result.returncode}"
                    )
                if remote_cache.requests(method="PUT"):
                    raise SmokeFailure(
                        "install/remote-cache env exclude precedence: expected exclude to block the upload"
                    )
                require_contains(
                    exclude_result.stdout + exclude_result.stderr,
                    "DATABASE_URL",
                    "install/remote-cache env exclude precedence warning",
                )

        remote_cache.reset_artifact()
        remote_cache.clear_requests()

        with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as allow_secrets_home:
            with tempfile.TemporaryDirectory(prefix="lpm-remote-cache-project-") as project_dir:
                project_path = Path(project_dir)
                write_remote_cache_project(
                    project_path,
                    "remote-cache-allow-secrets-smoke",
                    {
                        "enabled": True,
                        "team": "acme",
                        "url": remote_cache.base_url,
                        "env": {
                            "allowSecrets": True,
                        },
                    },
                )
                (project_path / ".env").write_text(
                    "DATABASE_URL=postgres://allow-secrets@example.test/lpm\n",
                    encoding="utf-8",
                )

                allow_secrets_result = run_command_result(
                    "install/remote-cache env allowSecrets",
                    project_path,
                    [str(LPM_BIN), "run", "build"],
                    extra_env={
                        "LPM_HOME": allow_secrets_home,
                        "LPM_REMOTE_CACHE_TOKEN": "remote-cache-token",
                    },
                )
                if allow_secrets_result.returncode != 0:
                    raise SmokeFailure(
                        "install/remote-cache env allowSecrets failed with exit code "
                        f"{allow_secrets_result.returncode}"
                    )
                if len(remote_cache.requests(method="PUT")) != 1:
                    raise SmokeFailure(
                        "install/remote-cache env allowSecrets: expected an upload when allowSecrets=true"
                    )
                require_not_contains(
                    allow_secrets_result.stdout + allow_secrets_result.stderr,
                    "looks secret-like",
                    "install/remote-cache env allowSecrets warning",
                )

        remote_cache.reset_artifact()
        remote_cache.clear_requests()
        remote_cache.set_upload_response(
            403,
            {"error": "Token does not have remote cache write permissions"},
        )

        with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as forbidden_upload_home:
            with tempfile.TemporaryDirectory(prefix="lpm-remote-cache-project-") as project_dir:
                project_path = Path(project_dir)
                write_remote_cache_project(
                    project_path,
                    "remote-cache-upload-forbidden-smoke",
                    {
                        "enabled": True,
                        "team": "acme",
                        "url": remote_cache.base_url,
                    },
                )

                forbidden_upload_result = run_command_result(
                    "install/remote-cache upload forbidden fallback",
                    project_path,
                    [str(LPM_BIN), "run", "build"],
                    extra_env={
                        "LPM_HOME": forbidden_upload_home,
                        "LPM_REMOTE_CACHE_TOKEN": "remote-cache-token",
                    },
                )
                if forbidden_upload_result.returncode != 0:
                    raise SmokeFailure(
                        "install/remote-cache upload forbidden fallback failed with exit code "
                        f"{forbidden_upload_result.returncode}"
                    )
                require_exists(project_path / "dist" / "value.txt")
                require_exists(project_path / "executed-marker")
                if len(remote_cache.requests(method="PUT")) != 1:
                    raise SmokeFailure(
                        "install/remote-cache upload forbidden fallback: expected the upload attempt to reach the remote cache"
                    )
                require_contains(
                    forbidden_upload_result.stdout + forbidden_upload_result.stderr,
                    "not authorized",
                    "install/remote-cache upload forbidden fallback warning",
                )

        remote_cache.set_upload_response(200)
        remote_cache.reset_artifact()
        remote_cache.clear_requests()

        remote_cache.reset_artifact()
        remote_cache.clear_requests()

        with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as disabled_home:
            with tempfile.TemporaryDirectory(prefix="lpm-remote-cache-project-") as project_dir:
                project_path = Path(project_dir)
                write_remote_cache_project(
                    project_path,
                    "remote-cache-disabled-smoke",
                    {
                        "enabled": True,
                        "team": "acme",
                        "url": remote_cache.base_url,
                    },
                )

                disabled_result = run_command_result(
                    "install/remote-cache env disable override",
                    project_path,
                    [str(LPM_BIN), "run", "build"],
                    extra_env={
                        "LPM_HOME": disabled_home,
                        "LPM_REMOTE_CACHE": "0",
                    },
                )
                if disabled_result.returncode != 0:
                    raise SmokeFailure(
                        "install/remote-cache env disable override failed with exit code "
                        f"{disabled_result.returncode}"
                    )
                if remote_cache.requests():
                    raise SmokeFailure(
                        "install/remote-cache env disable override: expected no remote requests when LPM_REMOTE_CACHE=0"
                    )


def scenario_install_cache_command() -> None:
    with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as lpm_home:
        fixture = reset_cache_command_fixture()
        scenario_env = {"LPM_HOME": lpm_home}

        cache_root = Path(lpm_home) / "cache"
        metadata_file = cache_root / "metadata" / "pkg-meta.json"
        tasks_file = cache_root / "tasks" / "task-cache.bin"
        dlx_file = cache_root / "dlx" / "tool-1" / "package.tgz"
        store_marker = Path(lpm_home) / "store" / "v1" / "left-pad@1.3.0" / "index.js"
        store_marker_bytes = b"module.exports = 'store survives cache clean'\n"

        write_bytes(metadata_file, b'{"cached":true}\n')
        write_bytes(tasks_file, bytes([0xAB]) * 128)
        write_bytes(dlx_file, bytes([0xCD]) * 256)
        write_bytes(store_marker, store_marker_bytes)

        path_result = run_command_result(
            "install/cache path",
            fixture,
            [str(LPM_BIN), "cache", "path"],
            extra_env=scenario_env,
        )
        if path_result.returncode != 0:
            raise SmokeFailure(
                f"install/cache path failed with exit code {path_result.returncode}"
            )
        if Path(path_result.stdout.strip()) != cache_root:
            raise SmokeFailure(
                "install/cache path: expected the isolated cache root path in stdout"
            )

        metadata_path_result = run_command_result(
            "install/cache path metadata json",
            fixture,
            [str(LPM_BIN), "--json", "cache", "path", "metadata"],
            extra_env=scenario_env,
        )
        if metadata_path_result.returncode != 0:
            raise SmokeFailure(
                "install/cache path metadata json failed with exit code "
                f"{metadata_path_result.returncode}"
            )
        metadata_path_envelope = json.loads(metadata_path_result.stdout)
        if metadata_path_envelope.get("success") is not True:
            raise SmokeFailure("install/cache path metadata json: expected success=true")
        if metadata_path_envelope.get("path") != str(cache_root / "metadata"):
            raise SmokeFailure(
                "install/cache path metadata json: expected metadata subdirectory path"
            )

        clear_result = run_command_result(
            "install/cache clear tasks json",
            fixture,
            [str(LPM_BIN), "--json", "cache", "clear", "tasks"],
            extra_env=scenario_env,
        )
        if clear_result.returncode != 0:
            raise SmokeFailure(
                f"install/cache clear tasks json failed with exit code {clear_result.returncode}"
            )
        clear_envelope = json.loads(clear_result.stdout)
        if clear_envelope.get("success") is not True:
            raise SmokeFailure("install/cache clear tasks json: expected success=true")
        cleared = clear_envelope.get("cleaned", [])
        if len(cleared) != 1 or cleared[0].get("category") != "tasks":
            raise SmokeFailure(
                "install/cache clear tasks json: expected exactly one cleaned tasks entry"
            )
        require_not_exists(tasks_file)
        require_exists(metadata_file)
        require_exists(dlx_file)

        write_bytes(tasks_file, bytes([0xEF]) * 64)

        clean_result = run_command_result(
            "install/cache clean json",
            fixture,
            [str(LPM_BIN), "--json", "cache", "clean"],
            extra_env=scenario_env,
        )
        if clean_result.returncode != 0:
            raise SmokeFailure(
                f"install/cache clean json failed with exit code {clean_result.returncode}"
            )
        clean_envelope = json.loads(clean_result.stdout)
        if clean_envelope.get("success") is not True:
            raise SmokeFailure("install/cache clean json: expected success=true")
        cleaned_categories = {
            entry.get("category") for entry in clean_envelope.get("cleaned", [])
        }
        if cleaned_categories != {"metadata", "tasks", "dlx"}:
            raise SmokeFailure(
                "install/cache clean json: expected metadata, tasks, and dlx to be reported"
            )
        if clean_envelope.get("total_bytes_freed", 0) < 320:
            raise SmokeFailure(
                "install/cache clean json: expected total_bytes_freed to include the seeded payloads"
            )

        require_not_exists(metadata_file)
        require_not_exists(tasks_file)
        require_not_exists(dlx_file)
        require_exists(store_marker)
        if store_marker.read_bytes() != store_marker_bytes:
            raise SmokeFailure(
                "install/cache clean store marker: expected cache cleaning to leave store bytes untouched"
            )


def scenario_install_cache_prune() -> None:
    with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as lpm_home:
        fixture = reset_cache_prune_fixture()
        scenario_env = {
            "LPM_HOME": lpm_home,
            "LPM_STORE_VERSION": "v2",
        }

        degraded_result = run_command_result(
            "install/cache-prune degraded dry-run json",
            fixture,
            [str(LPM_BIN), "--json", "cache", "prune"],
            extra_env=scenario_env,
        )
        if degraded_result.returncode != 0:
            raise SmokeFailure(
                "install/cache-prune degraded dry-run json failed with exit code "
                f"{degraded_result.returncode}"
            )
        degraded_envelope = json.loads(degraded_result.stdout)
        if degraded_envelope.get("applied") is not False:
            raise SmokeFailure(
                "install/cache-prune degraded dry-run json: expected applied=false"
            )
        if degraded_envelope.get("registry_missing") is not True:
            raise SmokeFailure(
                "install/cache-prune degraded dry-run json: expected registry_missing=true on a fresh LPM_HOME"
            )
        if degraded_envelope.get("link_entries_orphaned") != []:
            raise SmokeFailure(
                "install/cache-prune degraded dry-run json: expected no orphaned link entries in missing-registry mode"
            )
        if degraded_envelope.get("object_entries_orphaned") != []:
            raise SmokeFailure(
                "install/cache-prune degraded dry-run json: expected no orphaned object entries in missing-registry mode"
            )

        used_link, used_object = seed_cache_prune_entry(
            lpm_home,
            entry_name="used-cache-entry",
            package_name="used-cache-pkg",
            version="1.0.0",
            graph_key_digest_hex="1" * 64,
            object_segment="sha512-used-cache-entry",
            last_referenced_at=iso8601_n_secs_ago(3600),
        )
        recent_link, recent_object = seed_cache_prune_entry(
            lpm_home,
            entry_name="recent-orphan-entry",
            package_name="recent-orphan-pkg",
            version="1.0.0",
            graph_key_digest_hex="2" * 64,
            object_segment="sha512-recent-orphan-entry",
            last_referenced_at=iso8601_n_secs_ago(3600),
        )
        old_link, old_object = seed_cache_prune_entry(
            lpm_home,
            entry_name="old-orphan-entry",
            package_name="old-orphan-pkg",
            version="1.0.0",
            graph_key_digest_hex="3" * 64,
            object_segment="sha512-old-orphan-entry",
            last_referenced_at=iso8601_n_secs_ago(60 * 24 * 60 * 60),
        )
        seed_cache_prune_project_link(fixture, "used-cache-pkg", used_link)

        project_dry_run_result = run_command_result(
            "install/cache-prune manual repair dry-run json",
            fixture,
            [
                str(LPM_BIN),
                "--json",
                "cache",
                "prune",
                "--project",
                str(fixture),
                "--max-age",
                "30d",
            ],
            extra_env=scenario_env,
        )
        if project_dry_run_result.returncode != 0:
            raise SmokeFailure(
                "install/cache-prune manual repair dry-run json failed with exit code "
                f"{project_dry_run_result.returncode}"
            )
        project_dry_run_envelope = json.loads(project_dry_run_result.stdout)
        if project_dry_run_envelope.get("applied") is not False:
            raise SmokeFailure(
                "install/cache-prune manual repair dry-run json: expected applied=false"
            )
        if project_dry_run_envelope.get("registry_missing") is not False:
            raise SmokeFailure(
                "install/cache-prune manual repair dry-run json: expected registry_missing=false when --project is supplied"
            )
        if project_dry_run_envelope.get("projects_walked") != 1:
            raise SmokeFailure(
                "install/cache-prune manual repair dry-run json: expected projects_walked=1"
            )
        if project_dry_run_envelope.get("link_entries_total") != 3:
            raise SmokeFailure(
                "install/cache-prune manual repair dry-run json: expected link_entries_total=3"
            )
        if project_dry_run_envelope.get("link_entries_reachable") != 1:
            raise SmokeFailure(
                "install/cache-prune manual repair dry-run json: expected link_entries_reachable=1"
            )
        if project_dry_run_envelope.get("link_entries_orphaned") != [str(old_link)]:
            raise SmokeFailure(
                "install/cache-prune manual repair dry-run json: expected only the old orphan link entry to be eligible"
            )
        if project_dry_run_envelope.get("object_entries_total") != 3:
            raise SmokeFailure(
                "install/cache-prune manual repair dry-run json: expected object_entries_total=3"
            )
        if project_dry_run_envelope.get("object_entries_orphaned") != [str(old_object)]:
            raise SmokeFailure(
                "install/cache-prune manual repair dry-run json: expected only the old orphan object to be eligible"
            )
        if project_dry_run_envelope.get("bytes_freed_or_eligible", 0) == 0:
            raise SmokeFailure(
                "install/cache-prune manual repair dry-run json: expected bytes_freed_or_eligible to be non-zero"
            )

        require_exists(used_link / "node_modules" / "used-cache-pkg" / "package.json")
        require_exists(used_object)
        require_exists(recent_link / "node_modules" / "recent-orphan-pkg" / "package.json")
        require_exists(recent_object)

        require_exists(old_link / "node_modules" / "old-orphan-pkg" / "package.json")
        require_exists(old_object)

        project_apply_result = run_command_result(
            "install/cache-prune manual repair apply json",
            fixture,
            [
                str(LPM_BIN),
                "--json",
                "cache",
                "prune",
                "--project",
                str(fixture),
                "--max-age",
                "30d",
                "--apply",
            ],
            extra_env=scenario_env,
        )
        if project_apply_result.returncode != 0:
            raise SmokeFailure(
                "install/cache-prune manual repair apply json failed with exit code "
                f"{project_apply_result.returncode}"
            )
        project_apply_envelope = json.loads(project_apply_result.stdout)
        if project_apply_envelope.get("applied") is not True:
            raise SmokeFailure(
                "install/cache-prune manual repair apply json: expected applied=true"
            )
        if project_apply_envelope.get("link_entries_orphaned") != [str(old_link)]:
            raise SmokeFailure(
                "install/cache-prune manual repair apply json: expected the old orphan link to remain the only pruned entry"
            )
        if project_apply_envelope.get("object_entries_orphaned") != [str(old_object)]:
            raise SmokeFailure(
                "install/cache-prune manual repair apply json: expected the old orphan object to remain the only pruned object"
            )

        require_exists(used_link / "node_modules" / "used-cache-pkg" / "package.json")
        require_exists(used_object)
        require_exists(recent_link / "node_modules" / "recent-orphan-pkg" / "package.json")
        require_exists(recent_object)
        require_not_exists(old_link)
        require_not_exists(old_object)
        require_not_exists(Path(lpm_home) / "known-projects.json")

        corrupt_registry_path = Path(lpm_home) / "known-projects.json"
        corrupt_registry_path.write_text("not even close to json{[", encoding="utf-8")

        corrupt_json_result = run_command_result(
            "install/cache-prune corrupt registry apply json",
            fixture,
            [str(LPM_BIN), "--json", "cache", "prune", "--apply"],
            extra_env=scenario_env,
        )
        if corrupt_json_result.returncode != 0:
            raise SmokeFailure(
                "install/cache-prune corrupt registry apply json failed with exit code "
                f"{corrupt_json_result.returncode}"
            )
        corrupt_json_envelope = json.loads(corrupt_json_result.stdout)
        if corrupt_json_envelope.get("applied") is not True:
            raise SmokeFailure(
                "install/cache-prune corrupt registry apply json: expected applied=true"
            )
        if corrupt_json_envelope.get("registry_corrupt") is not True:
            raise SmokeFailure(
                "install/cache-prune corrupt registry apply json: expected registry_corrupt=true"
            )
        if corrupt_json_envelope.get("registry_missing") is not False:
            raise SmokeFailure(
                "install/cache-prune corrupt registry apply json: expected registry_missing=false when the registry file exists but is unreadable"
            )
        corrupt_reason = corrupt_json_envelope.get("registry_corrupt_reason")
        if not isinstance(corrupt_reason, str) or not corrupt_reason:
            raise SmokeFailure(
                "install/cache-prune corrupt registry apply json: expected a non-empty registry_corrupt_reason"
            )
        if corrupt_json_envelope.get("link_entries_orphaned") != []:
            raise SmokeFailure(
                "install/cache-prune corrupt registry apply json: expected no orphaned link entries when the walk degrades to tombstone-only mode"
            )
        if corrupt_json_envelope.get("object_entries_orphaned") != []:
            raise SmokeFailure(
                "install/cache-prune corrupt registry apply json: expected no orphaned object entries when the walk degrades to tombstone-only mode"
            )

        corrupt_human_result = run_command_result(
            "install/cache-prune corrupt registry apply human",
            fixture,
            [str(LPM_BIN), "cache", "prune", "--apply"],
            extra_env=scenario_env,
        )
        if corrupt_human_result.returncode != 0:
            raise SmokeFailure(
                "install/cache-prune corrupt registry apply human failed with exit code "
                f"{corrupt_human_result.returncode}"
            )
        corrupt_human_output = corrupt_human_result.stdout + corrupt_human_result.stderr
        require_contains(
            corrupt_human_output,
            "known-projects.json is unusable",
            "install/cache-prune corrupt registry apply human warning",
        )
        require_contains(
            corrupt_human_output,
            "Delete the file",
            "install/cache-prune corrupt registry apply human remediation hint",
        )
        require_contains(
            corrupt_human_output,
            "--project <path>",
            "install/cache-prune corrupt registry apply human project hint",
        )
        require_contains(
            corrupt_human_output,
            "tombstone sweep still runs under --apply",
            "install/cache-prune corrupt registry apply human degraded-mode warning",
        )
        require_contains(
            corrupt_human_output,
            corrupt_reason,
            "install/cache-prune corrupt registry apply human parse reason",
        )

        require_exists(used_link / "node_modules" / "used-cache-pkg" / "package.json")
        require_exists(used_object)
        require_exists(recent_link / "node_modules" / "recent-orphan-pkg" / "package.json")
        require_exists(recent_object)


def scenario_install_store_command() -> None:
    with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as lpm_home:
        fixture = reset_store_fixture()
        scenario_env = {"LPM_HOME": lpm_home}
        store_root = Path(lpm_home) / "store"

        path_result = run_command_result(
            "install/store path json",
            fixture,
            [str(LPM_BIN), "--json", "store", "path"],
            extra_env=scenario_env,
        )
        if path_result.returncode != 0:
            raise SmokeFailure(
                f"install/store path json failed with exit code {path_result.returncode}"
            )
        path_envelope = json.loads(path_result.stdout)
        if path_envelope.get("success") is not True:
            raise SmokeFailure("install/store path json: expected success=true")
        if path_envelope.get("path") != str(store_root):
            raise SmokeFailure("install/store path json: expected the isolated store root path")

        security_dir = seed_store_v1_entry(
            lpm_home,
            package_name="store-security-pkg",
            version="1.0.0",
            files={"index.js": "eval('hello')\n"},
            integrity="sha512-store-security-match",
        )
        integrity_dir = seed_store_v1_entry(
            lpm_home,
            package_name="store-integrity-pkg",
            version="1.0.0",
            files={"index.js": "module.exports = 'integrity'\n"},
            integrity="sha512-store-integrity-stored",
        )
        v2_link, v2_object = seed_cache_prune_entry(
            lpm_home,
            entry_name="store-v2-entry",
            package_name="store-v2-pkg",
            version="2.0.0",
            graph_key_digest_hex="4" * 64,
            object_segment="sha512-store-v2-match",
            last_referenced_at=iso8601_n_secs_ago(3600),
        )
        seed_store_verify_lockfile(
            fixture,
            [
                ("store-security-pkg", "1.0.0", "sha512-store-security-match"),
                ("store-integrity-pkg", "1.0.0", "sha512-store-integrity-expected"),
                ("store-v2-pkg", "2.0.0", "sha512-store-v2-match"),
            ],
        )

        fast_verify_result = run_command_result(
            "install/store verify fast json",
            fixture,
            [str(LPM_BIN), "--json", "store", "verify"],
            extra_env=scenario_env,
        )
        if fast_verify_result.returncode != 0:
            raise SmokeFailure(
                "install/store verify fast json failed with exit code "
                f"{fast_verify_result.returncode}"
            )
        fast_verify_envelope = json.loads(fast_verify_result.stdout)
        if fast_verify_envelope.get("success") is not True:
            raise SmokeFailure("install/store verify fast json: expected success=true")
        if fast_verify_envelope.get("check_kind") != "presence":
            raise SmokeFailure(
                "install/store verify fast json: expected check_kind=presence"
            )
        if fast_verify_envelope.get("entries_verified") != 3:
            raise SmokeFailure(
                "install/store verify fast json: expected all three seeded entries to verify in the presence-only pass"
            )
        if fast_verify_envelope.get("verified") != 3:
            raise SmokeFailure(
                "install/store verify fast json: expected verified alias to match entries_verified"
            )
        if fast_verify_envelope.get("unique_coords") != 3:
            raise SmokeFailure(
                "install/store verify fast json: expected unique_coords=3 for the three seeded packages"
            )
        if fast_verify_envelope.get("duplicated_entries") != 0:
            raise SmokeFailure(
                "install/store verify fast json: expected duplicated_entries=0"
            )
        if fast_verify_envelope.get("corrupted") != 0:
            raise SmokeFailure(
                "install/store verify fast json: expected corrupted=0 before the deep integrity cross-check"
            )

        deep_verify_result = run_command_result(
            "install/store verify deep json",
            fixture,
            [str(LPM_BIN), "--json", "store", "verify", "--deep"],
            extra_env=scenario_env,
        )
        if deep_verify_result.returncode == 0:
            raise SmokeFailure(
                "install/store verify deep json: expected a non-zero exit because the seeded integrity marker does not match lpm.lock"
            )
        deep_verify_envelope = json.loads(deep_verify_result.stdout)
        if deep_verify_envelope.get("success") is not False:
            raise SmokeFailure("install/store verify deep json: expected success=false")
        if deep_verify_envelope.get("check_kind") != "lockfile_marker_consistency":
            raise SmokeFailure(
                "install/store verify deep json: expected check_kind=lockfile_marker_consistency"
            )
        if deep_verify_envelope.get("bytes_integrity_recomputed") is not False:
            raise SmokeFailure(
                "install/store verify deep json: expected bytes_integrity_recomputed=false"
            )
        if deep_verify_envelope.get("entries_verified") != 2:
            raise SmokeFailure(
                "install/store verify deep json: expected two entries to remain verified after the integrity-mismatch failure"
            )
        if deep_verify_envelope.get("corrupted") != 1:
            raise SmokeFailure(
                "install/store verify deep json: expected corrupted=1 for the lockfile marker mismatch"
            )
        issues = deep_verify_envelope.get("issues", [])
        if not any(
            "store-integrity-pkg@1.0.0" in issue and "integrity mismatch" in issue
            for issue in issues
        ):
            raise SmokeFailure(
                "install/store verify deep json: expected issues[] to mention the seeded integrity mismatch"
            )
        if deep_verify_envelope.get("securityMismatches", 0) < 1:
            raise SmokeFailure(
                "install/store verify deep json: expected at least one missing or stale security cache to be reported"
            )
        if deep_verify_envelope.get("securityReanalyzed") != 0:
            raise SmokeFailure(
                "install/store verify deep json: expected securityReanalyzed=0 without --fix"
            )
        require_not_exists(security_dir / ".lpm-security.json")

        deep_fix_result = run_command_result(
            "install/store verify deep fix json",
            fixture,
            [str(LPM_BIN), "--json", "store", "verify", "--deep", "--fix"],
            extra_env=scenario_env,
        )
        if deep_fix_result.returncode == 0:
            raise SmokeFailure(
                "install/store verify deep fix json: expected a non-zero exit because --fix does not repair integrity mismatches"
            )
        deep_fix_envelope = json.loads(deep_fix_result.stdout)
        if deep_fix_envelope.get("success") is not False:
            raise SmokeFailure("install/store verify deep fix json: expected success=false")
        if deep_fix_envelope.get("corrupted") != 1:
            raise SmokeFailure(
                "install/store verify deep fix json: expected the integrity mismatch to remain corrupted after --fix"
            )
        if deep_fix_envelope.get("securityReanalyzed", 0) < 1:
            raise SmokeFailure(
                "install/store verify deep fix json: expected --fix to refresh at least one security cache"
            )
        require_exists(security_dir / ".lpm-security.json")
        require_exists(v2_link / "node_modules" / "store-v2-pkg" / ".lpm-security.json")

        clean_result = run_command_result(
            "install/store clean json",
            fixture,
            [str(LPM_BIN), "--json", "store", "clean"],
            extra_env=scenario_env,
        )
        if clean_result.returncode != 0:
            raise SmokeFailure(
                f"install/store clean json failed with exit code {clean_result.returncode}"
            )
        clean_envelope = json.loads(clean_result.stdout)
        if clean_envelope.get("success") is not True:
            raise SmokeFailure("install/store clean json: expected success=true")
        if clean_envelope.get("removed_bytes", 0) <= 0:
            raise SmokeFailure(
                "install/store clean json: expected removed_bytes to reflect the seeded v1 + v2 store content"
            )
        if clean_envelope.get("v1_removed_bytes", 0) <= 0:
            raise SmokeFailure(
                "install/store clean json: expected v1_removed_bytes to be non-zero"
            )
        if clean_envelope.get("v2_removed_bytes", 0) <= 0:
            raise SmokeFailure(
                "install/store clean json: expected v2_removed_bytes to be non-zero"
            )
        if clean_envelope.get("v1_path") != str(Path(lpm_home) / "store" / "v1"):
            raise SmokeFailure("install/store clean json: expected v1_path to match the isolated store path")
        if clean_envelope.get("v2_path") != str(Path(lpm_home) / "store" / "v2"):
            raise SmokeFailure("install/store clean json: expected v2_path to match the isolated store path")

        require_not_exists(security_dir)
        require_not_exists(integrity_dir)
        require_not_exists(v2_link)
        require_not_exists(v2_object)
        require_exists(store_root)
        lock_artifacts = [
            child.name for child in store_root.iterdir() if child.name.startswith(".gc.lock")
        ]
        if not lock_artifacts:
            raise SmokeFailure(
                "install/store clean json: expected the outer store root and .gc.lock* control files to remain after the blunt wipe"
            )


def scenario_install_graph_command() -> None:
    fixture = reset_graph_fixture().resolve()

    with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as home_root:
        scenario_env = {
            "HOME": home_root,
            "LPM_HOME": str(Path(home_root) / ".lpm"),
            "LPM_FORCE_FILE_AUTH": "1",
        }

        tree_output = run_command(
            "install/graph default tree",
            fixture,
            [str(LPM_BIN), "graph"],
            extra_env=scenario_env,
        )
        require_contains(
            tree_output,
            "graph-test-project@1.0.0",
            "install/graph default tree root",
        )
        require_contains(
            tree_output,
            "express@4.22.1",
            "install/graph default tree express version",
        )
        require_contains(
            tree_output,
            "@lpm.dev/neo.highlight@1.1.1",
            "install/graph default tree lpm package",
        )
        require_contains(
            tree_output,
            "8 packages, max depth 4, 1 duplicates (ms)",
            "install/graph default tree stats line",
        )
        require_not_contains(
            tree_output,
            "^4.22.0",
            "install/graph default tree should print resolved versions rather than manifest ranges",
        )

        filter_result = run_command_result(
            "install/graph filter substring json",
            fixture,
            [str(LPM_BIN), "graph", "--format", "json", "--filter", "press"],
            extra_env=scenario_env,
        )
        if filter_result.returncode != 0:
            raise SmokeFailure(
                f"install/graph filter substring json failed with exit code {filter_result.returncode}"
            )
        filter_envelope = json.loads(filter_result.stdout)
        if filter_envelope.get("success") is not True:
            raise SmokeFailure(
                "install/graph filter substring json: expected success=true"
            )
        filter_names = {
            node.get("name") for node in filter_envelope.get("nodes", [])
        }
        if "express" not in filter_names:
            raise SmokeFailure(
                "install/graph filter substring json: expected substring filter 'press' to keep express"
            )
        if "vitest" in filter_names:
            raise SmokeFailure(
                "install/graph filter substring json: expected unrelated subtree nodes to be pruned"
            )

        depth_json_result = run_command_result(
            "install/graph json depth 2",
            fixture,
            [str(LPM_BIN), "graph", "--format", "json", "--depth", "2"],
            extra_env=scenario_env,
        )
        if depth_json_result.returncode != 0:
            raise SmokeFailure(
                f"install/graph json depth 2 failed with exit code {depth_json_result.returncode}"
            )
        depth_json_envelope = json.loads(depth_json_result.stdout)
        if depth_json_envelope.get("success") is not True:
            raise SmokeFailure("install/graph json depth 2: expected success=true")
        if depth_json_envelope.get("max_depth") != 2:
            raise SmokeFailure(
                "install/graph json depth 2: expected max_depth=2"
            )
        if depth_json_envelope.get("lpm_packages") != 1:
            raise SmokeFailure(
                "install/graph json depth 2: expected one lpm.dev package in the truncated graph"
            )
        depth_json_names = {
            node.get("name") for node in depth_json_envelope.get("nodes", [])
        }
        if "express" not in depth_json_names:
            raise SmokeFailure(
                "install/graph json depth 2: expected direct dep express to remain"
            )
        if "ms" in depth_json_names or "mime-types" in depth_json_names:
            raise SmokeFailure(
                "install/graph json depth 2: expected deep transitive nodes to be pruned"
            )

        stats_output = run_command(
            "install/graph stats depth 2",
            fixture,
            [str(LPM_BIN), "graph", "--format", "stats", "--depth", "2"],
            extra_env=scenario_env,
        )
        require_contains(
            stats_output,
            "Max depth: 2",
            "install/graph stats depth 2",
        )
        require_contains(
            stats_output,
            "Duplicates: none",
            "install/graph stats depth 2 duplicates",
        )

        no_open_json_result = run_command_result(
            "install/graph no-open json warning",
            fixture,
            [str(LPM_BIN), "graph", "--no-open", "--format", "json"],
            extra_env=scenario_env,
        )
        if no_open_json_result.returncode != 0:
            raise SmokeFailure(
                f"install/graph no-open json warning failed with exit code {no_open_json_result.returncode}"
            )
        require_contains(
            no_open_json_result.stderr,
            "--no-open has no effect",
            "install/graph no-open json warning stderr",
        )
        no_open_json_envelope = json.loads(no_open_json_result.stdout)
        if no_open_json_envelope.get("success") is not True:
            raise SmokeFailure(
                "install/graph no-open json warning: expected success=true"
            )

        html_result = run_command_result(
            "install/graph html depth 2 no-open",
            fixture,
            [str(LPM_BIN), "graph", "--format", "html", "--depth", "2", "--no-open"],
            extra_env=scenario_env,
        )
        if html_result.returncode != 0:
            raise SmokeFailure(
                f"install/graph html depth 2 no-open failed with exit code {html_result.returncode}"
            )
        html_output = html_result.stdout + html_result.stderr
        require_contains(
            html_output,
            ".lpm/graph.html",
            "install/graph html success message",
        )
        html_path = fixture / ".lpm" / "graph.html"
        require_exists(html_path)
        html_text = html_path.read_text(encoding="utf-8")
        require_contains(
            html_text,
            "<!DOCTYPE html>",
            "install/graph html doctype",
        )
        require_contains(
            html_text,
            "LPM Dependency Graph",
            "install/graph html header",
        )
        require_contains(
            html_text,
            "Max depth: 2",
            "install/graph html stats summary",
        )
        require_not_contains(
            html_text,
            "ms@2.0.0",
            "install/graph html depth 2 should prune deep transitive duplicates from the embedded graph",
        )


def scenario_install_pack_command() -> None:
    fixture = reset_pack_fixture().resolve()
    marker_log = fixture / ".lpm" / "pack-invocations.jsonl"
    marker_text = "tsdown pack smoke single"

    missing_output = run_command_expect_failure(
        "install/pack missing tsdown fails fast",
        fixture,
        [str(LPM_BIN), "pack", "--entry", "src/index.ts"],
    )
    require_contains(
        missing_output,
        "tsdown not installed. Run: lpm install -D tsdown",
        "install/pack missing-tsdown output",
    )

    seed_fake_tsdown(
        fixture / "node_modules" / ".bin" / "tsdown",
        marker_log,
        marker_text,
    )

    pack_result = run_command_result(
        "install/pack forwards lpm-owned flags to project-local tsdown",
        fixture,
        [
            str(LPM_BIN),
            "pack",
            "--config",
            "tsdown.config.ts",
            "--tsconfig",
            "tsconfig.pack.json",
            "--target",
            "es2022",
            "--entry",
            "src/index.ts",
            "--out-dir",
            "dist",
            "--format",
            "esm",
            "--platform",
            "node",
            "--dts",
            "--minify",
            "--sourcemap",
        ],
    )
    if pack_result.returncode != 0:
        raise SmokeFailure(
            f"install/pack flag forwarding failed with exit code {pack_result.returncode}"
        )
    require_contains(
        pack_result.stdout,
        marker_text,
        "install/pack single-package stdout passthrough",
    )

    invocations = read_jsonl(marker_log)
    if len(invocations) != 1:
        raise SmokeFailure(
            f"install/pack expected exactly one tsdown invocation, got {len(invocations)}"
        )
    invocation = invocations[0]
    if normalize_test_path(str(invocation.get("cwd"))) != normalize_test_path(str(fixture)):
        raise SmokeFailure("install/pack expected tsdown cwd to be the project root")
    expected_args = [
        "--config",
        "tsdown.config.ts",
        "--tsconfig",
        "tsconfig.pack.json",
        "--target",
        "es2022",
        "src/index.ts",
        "--out-dir",
        "dist",
        "--format",
        "esm",
        "--platform",
        "node",
        "--dts",
        "--minify",
        "--sourcemap",
    ]
    if invocation.get("args") != expected_args:
        raise SmokeFailure(
            f"install/pack expected forwarded args {expected_args!r}, got {invocation.get('args')!r}"
        )


def scenario_workspace_pack() -> None:
    fixture = reset_workspace_pack_fixture().resolve()
    marker_log = fixture / ".lpm" / "pack-workspace-invocations.jsonl"
    marker_text = "tsdown workspace pack smoke"
    seed_fake_tsdown(
        fixture / "node_modules" / ".bin" / "tsdown",
        marker_log,
        marker_text,
    )

    workspace_result = run_command_result(
        "workspace/pack all json",
        fixture,
        [
            str(LPM_BIN),
            "pack",
            "--all",
            "--json",
            "--entry",
            "src/index.ts",
            "--out-dir",
            "dist",
            "--dts",
        ],
    )
    if workspace_result.returncode != 0:
        raise SmokeFailure(
            f"workspace/pack --all --json failed with exit code {workspace_result.returncode}"
        )
    require_not_contains(
        workspace_result.stdout + workspace_result.stderr,
        marker_text,
        "workspace/pack success stdout should stay inside the member process rather than leak into the workspace envelope",
    )
    envelope = json.loads(workspace_result.stdout)
    if envelope.get("success") is not True:
        raise SmokeFailure("workspace/pack --all --json: expected success=true")
    if envelope.get("packages") != 3:
        raise SmokeFailure("workspace/pack --all --json: expected packages=3")
    if envelope.get("succeeded") != 3 or envelope.get("failed") != 0:
        raise SmokeFailure("workspace/pack --all --json: expected 3 succeeded and 0 failed")
    member_names = {member.get("name") for member in envelope.get("members", [])}
    if member_names != {"@smoke/pack-web", "@smoke/pack-docs", "@smoke/pack-core"}:
        raise SmokeFailure(
            f"workspace/pack --all --json: unexpected member names {sorted(member_names)!r}"
        )

    invocations = read_jsonl(marker_log)
    if len(invocations) != 3:
        raise SmokeFailure(
            f"workspace/pack expected exactly three tsdown invocations, got {len(invocations)}"
        )
    cwd_set = {normalize_test_path(str(row.get("cwd"))) for row in invocations}
    expected_cwds = {
        normalize_test_path(str(fixture / "apps" / "web")),
        normalize_test_path(str(fixture / "apps" / "docs")),
        normalize_test_path(str(fixture / "packages" / "core")),
    }
    if cwd_set != expected_cwds:
        raise SmokeFailure(
            f"workspace/pack expected member cwd set {sorted(expected_cwds)!r}, got {sorted(cwd_set)!r}"
        )

    no_match_output = run_command_expect_failure(
        "workspace/pack no-match filter",
        fixture,
        [str(LPM_BIN), "pack", "--filter", "./missing/*", "--fail-if-no-match"],
    )
    require_contains(
        no_match_output.lower(),
        "match",
        "workspace/pack no-match output",
    )

    watch_output = run_command_expect_failure(
        "workspace/pack rejects multi-member watch",
        fixture,
        [str(LPM_BIN), "pack", "--all", "--entry", "src/index.ts", "--", "--watch"],
    )
    require_contains(
        watch_output,
        "--watch is not supported",
        "workspace/pack watch rejection output",
    )
    if len(read_jsonl(marker_log)) != 3:
        raise SmokeFailure(
            "workspace/pack watch rejection should not spawn extra tsdown invocations"
        )


def scenario_install_dev_command() -> None:
    fixture = reset_dev_fixture().resolve()
    capture_path = fixture / "dev-capture.json"
    dev_port = reserve_then_release_port()

    with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as home_root:
        scenario_env = {
            "HOME": home_root,
            "LPM_HOME": str(Path(home_root) / ".lpm"),
            "LPM_FORCE_FILE_AUTH": "1",
        }

        common_args = [
            str(LPM_BIN),
            "dev",
            "--no-install",
            "--no-open",
            "--port",
            str(dev_port),
            "--env",
            "staging",
            "--",
            "--port",
            str(dev_port),
            "--capture",
            capture_path.name,
            "--flag",
            "from-cli",
        ]

        validation_result = run_command_result(
            "install/dev env validation",
            fixture,
            common_args,
            extra_env=scenario_env,
        )
        if validation_result.returncode == 0:
            raise SmokeFailure(
                "install/dev env validation: expected non-zero exit when REQUIRED_TOKEN is missing"
            )
        validation_output = validation_result.stdout + validation_result.stderr
        require_contains(
            validation_output,
            "environment validation failed",
            "install/dev env validation error header",
        )
        require_contains(
            validation_output,
            "REQUIRED_TOKEN: missing (required)",
            "install/dev env validation required var",
        )
        require_contains(
            validation_output.lower(),
            "created from .env.example",
            "install/dev env bootstrap status",
        )
        env_file = fixture / ".env"
        require_exists(env_file)
        if env_file.read_text(encoding="utf-8") != DEV_COMMAND_BASELINE_ENV_EXAMPLE:
            raise SmokeFailure(
                "install/dev env validation: expected .env to be copied exactly from .env.example"
            )
        require_not_exists(capture_path)

        success_output = run_command(
            "install/dev no-env-check forwarded args",
            fixture,
            [str(LPM_BIN), *common_args[1:6], "--no-env-check", *common_args[6:]],
            extra_env=scenario_env,
        )
        require_contains(
            success_output,
            "skipped (--no-install)",
            "install/dev no-install banner",
        )
        require_contains(
            success_output,
            f"http://localhost:{dev_port}",
            "install/dev local url banner",
        )
        require_exists(capture_path)

        capture = json.loads(capture_path.read_text(encoding="utf-8"))
        expected_args = [
            "--port",
            str(dev_port),
            "--capture",
            capture_path.name,
            "--flag",
            "from-cli",
        ]
        if capture.get("args") != expected_args:
            raise SmokeFailure(
                f"install/dev no-env-check forwarded args: expected args {expected_args!r}, got {capture.get('args')!r}"
            )

        captured_env = capture.get("env") or {}
        expected_env = {
            "BASE": "from-example",
            "SHARED": "from-staging-local",
            "LOCAL_ONLY": "from-local",
            "STAGE_ONLY": "from-staging",
            "LOCAL_STAGE": "from-staging-local",
            "REQUIRED_TOKEN": None,
        }
        for key, expected_value in expected_env.items():
            actual_value = captured_env.get(key)
            if actual_value != expected_value:
                raise SmokeFailure(
                    f"install/dev no-env-check forwarded args: expected env[{key!r}]={expected_value!r}, got {actual_value!r}"
                )

        https_failure_fixture = reset_dev_fixture().resolve()
        https_failure_capture_path = https_failure_fixture / "https-failure-capture.json"
        https_failure_port = reserve_then_release_port()

        with tempfile.TemporaryDirectory(prefix="lpm-smoke-dev-https-fail-") as https_failure_home:
            https_failure_home_path = Path(https_failure_home)
            https_failure_env = {
                "HOME": https_failure_home,
                "LPM_HOME": str(https_failure_home_path / ".lpm"),
                "LPM_FORCE_FILE_AUTH": "1",
                "LPM_CERT_TEST_TRUST_STORE_DIR": str(
                    https_failure_home_path / "test-trust-store"
                ),
            }

            https_failure_args = [
                str(LPM_BIN),
                "dev",
                "--https",
                "--no-install",
                "--no-open",
                "--no-env-check",
                "--port",
                str(https_failure_port),
                "--",
                "--port",
                str(https_failure_port),
                "--capture",
                https_failure_capture_path.name,
            ]
            log(
                "install/dev https non-interactive requires yes: "
                + " ".join(https_failure_args)
            )
            https_failure_result = subprocess.run(
                https_failure_args,
                cwd=https_failure_fixture,
                env=merged_env(https_failure_env),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
            )
            if https_failure_result.stdout:
                sys.stdout.write(https_failure_result.stdout)
            if https_failure_result.stderr:
                sys.stderr.write(https_failure_result.stderr)
            if https_failure_result.returncode == 0:
                raise SmokeFailure(
                    "install/dev https non-interactive requires yes: expected a non-zero exit without --yes"
                )
            https_failure_output = (
                https_failure_result.stdout + https_failure_result.stderr
            )
            require_contains(
                https_failure_output,
                "non-interactive shell: pass `--yes`",
                "install/dev https non-interactive requires yes message",
            )
            require_exists(https_failure_home_path / ".lpm" / "certs" / "rootCA.pem")
            require_not_exists(
                https_failure_home_path
                / "test-trust-store"
                / "lpm-local-ca.pem"
            )
            require_not_exists(
                https_failure_fixture / ".lpm" / "certs" / "cert.pem"
            )
            require_not_exists(https_failure_capture_path)

        https_success_fixture = reset_dev_fixture().resolve()
        https_success_capture_path = https_success_fixture / "https-success-capture.json"
        https_success_port = reserve_then_release_port()
        ca_bootstrap_port = https_success_port + 1

        with tempfile.TemporaryDirectory(prefix="lpm-smoke-dev-https-success-") as https_success_home:
            https_success_home_path = Path(https_success_home)
            https_success_env = {
                "HOME": https_success_home,
                "LPM_HOME": str(https_success_home_path / ".lpm"),
                "LPM_FORCE_FILE_AUTH": "1",
                "LPM_CERT_TEST_TRUST_STORE_DIR": str(
                    https_success_home_path / "test-trust-store"
                ),
            }

            https_success_args = [
                str(LPM_BIN),
                "dev",
                "--https",
                "--yes",
                "--network",
                "--allow-ca-bootstrap",
                "--no-install",
                "--no-open",
                "--no-env-check",
                "--port",
                str(https_success_port),
                "--",
                "--port",
                str(https_success_port),
                "--capture",
                https_success_capture_path.name,
            ]
            log(
                "install/dev https yes bootstrap: " + " ".join(https_success_args)
            )
            https_success_process = subprocess.Popen(
                https_success_args,
                cwd=https_success_fixture,
                env=merged_env(https_success_env),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            ca_body: str | None = None
            try:
                deadline = time.monotonic() + 5
                ca_url = f"http://127.0.0.1:{ca_bootstrap_port}"
                while time.monotonic() < deadline:
                    if https_success_process.poll() is not None and ca_body is None:
                        break
                    try:
                        with urlopen(ca_url, timeout=0.5) as response:
                            ca_body = response.read().decode("utf-8")
                            break
                    except Exception:
                        time.sleep(0.1)

                stdout, stderr = https_success_process.communicate(timeout=10)
            finally:
                if https_success_process.poll() is None:
                    https_success_process.kill()
                    https_success_process.wait(timeout=5)

            if stdout:
                sys.stdout.write(stdout)
            if stderr:
                sys.stderr.write(stderr)

            if https_success_process.returncode != 0:
                raise SmokeFailure(
                    "install/dev https yes bootstrap failed with exit code "
                    f"{https_success_process.returncode}"
                )

            https_success_output = stdout + stderr
            require_contains(
                https_success_output,
                "root CA generated and installed to trust store",
                "install/dev https yes success banner",
            )
            require_contains(
                https_success_output,
                "project certificate generated",
                "install/dev https project cert banner",
            )
            require_contains(
                https_success_output,
                f"https://localhost:{https_success_port}",
                "install/dev https local url banner",
            )
            require_contains(
                https_success_output,
                "First time on mobile? Visit",
                "install/dev https allow-ca-bootstrap banner",
            )
            if ca_body is None:
                raise SmokeFailure(
                    "install/dev https yes bootstrap: expected the CA bootstrap server to answer over HTTP"
                )
            if not ca_body.startswith("-----BEGIN CERTIFICATE-----"):
                raise SmokeFailure(
                    "install/dev https yes bootstrap: expected the CA bootstrap server to return a PEM certificate"
                )

            ca_cert_path = https_success_home_path / ".lpm" / "certs" / "rootCA.pem"
            project_cert_path = https_success_fixture / ".lpm" / "certs" / "cert.pem"
            project_key_path = https_success_fixture / ".lpm" / "certs" / "key.pem"
            trust_store_path = (
                https_success_home_path / "test-trust-store" / "lpm-local-ca.pem"
            )

            require_exists(ca_cert_path)
            require_exists(project_cert_path)
            require_exists(project_key_path)
            require_exists(trust_store_path)
            require_exists(https_success_capture_path)

            if ca_body != ca_cert_path.read_text(encoding="utf-8"):
                raise SmokeFailure(
                    "install/dev https yes bootstrap: expected the CA bootstrap server body to match rootCA.pem"
                )

            https_capture = json.loads(
                https_success_capture_path.read_text(encoding="utf-8")
            )
            https_env = https_capture.get("env") or {}
            if https_env.get("NODE_EXTRA_CA_CERTS") != str(ca_cert_path):
                raise SmokeFailure(
                    "install/dev https yes bootstrap: expected NODE_EXTRA_CA_CERTS to point at the generated root CA"
                )
            if https_env.get("SSL_CERT_FILE") != str(project_cert_path):
                raise SmokeFailure(
                    "install/dev https yes bootstrap: expected SSL_CERT_FILE to point at the generated project cert"
                )
            if https_env.get("SSL_KEY_FILE") != str(project_key_path):
                raise SmokeFailure(
                    "install/dev https yes bootstrap: expected SSL_KEY_FILE to point at the generated project key"
                )

        tunnel_fixture = reset_dev_fixture().resolve()
        tunnel_capture_path = tunnel_fixture / "tunnel-capture.json"
        tunnel_dev_port = reserve_then_release_port()
        tunnel_inspect_port = reserve_then_release_port()
        tunnel_registry_port = reserve_then_release_port()
        tunnel_relay_port = reserve_then_release_port()

        with tempfile.TemporaryDirectory(prefix="lpm-smoke-dev-tunnel-") as tunnel_home:
            tunnel_home_path = Path(tunnel_home)
            tunnel_registry_url = f"http://127.0.0.1:{tunnel_registry_port}"
            tunnel_env = {
                "HOME": tunnel_home,
                "LPM_HOME": str(tunnel_home_path / ".lpm"),
                "LPM_FORCE_FILE_AUTH": "1",
                "LPM_TEST_FAST_SCRYPT": "1",
                "LPM_TUNNEL_RELAY": f"ws://127.0.0.1:{tunnel_relay_port}/connect",
            }
            seed_refresh_backed_session(
                tunnel_env,
                tunnel_registry_url,
                "at-dev-tunnel",
                "rt-dev-tunnel",
                "2099-01-01T00:00:00Z",
            )

            with FakeTunnelRelay(
                tunnel_relay_port,
                "https://dev-smoke.lpm.fyi",
                "sess-dev-smoke",
            ) as relay:
                tunnel_args = [
                    str(LPM_BIN),
                    "--registry",
                    tunnel_registry_url,
                    "--insecure",
                    "dev",
                    "--tunnel",
                    "--inspect-port",
                    str(tunnel_inspect_port),
                    "--no-install",
                    "--no-open",
                    "--no-env-check",
                    "--port",
                    str(tunnel_dev_port),
                    "--",
                    "--port",
                    str(tunnel_dev_port),
                    "--capture",
                    tunnel_capture_path.name,
                ]
                log("install/dev tunnel inspector: " + " ".join(tunnel_args))
                tunnel_process = subprocess.Popen(
                    tunnel_args,
                    cwd=tunnel_fixture,
                    env=merged_env(tunnel_env),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                tunnel_inspector_html: str | None = None
                try:
                    relay.wait_for_connection()
                    tunnel_inspector_url = f"http://127.0.0.1:{tunnel_inspect_port}/"
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        if tunnel_process.poll() is not None and tunnel_inspector_html is None:
                            break
                        try:
                            with urlopen(tunnel_inspector_url, timeout=0.5) as response:
                                tunnel_inspector_html = response.read().decode("utf-8")
                        except Exception:
                            time.sleep(0.1)
                            continue
                        if tunnel_inspector_html is not None:
                            break
                        time.sleep(0.1)

                    tunnel_stdout, tunnel_stderr = tunnel_process.communicate(timeout=10)
                finally:
                    if tunnel_process.poll() is None:
                        tunnel_process.kill()
                        tunnel_process.wait(timeout=5)

            if tunnel_stdout:
                sys.stdout.write(tunnel_stdout)
            if tunnel_stderr:
                sys.stderr.write(tunnel_stderr)

            if tunnel_process.returncode != 0:
                raise SmokeFailure(
                    "install/dev tunnel inspector failed with exit code "
                    f"{tunnel_process.returncode}"
                )

            tunnel_output = tunnel_stdout + tunnel_stderr
            require_contains(
                tunnel_output,
                f"Inspect http://127.0.0.1:{tunnel_inspect_port}/?token=",
                "install/dev tunnel inspect-port banner",
            )
            require_contains(
                tunnel_output,
                f"Tunnel https://dev-smoke.lpm.fyi → localhost:{tunnel_dev_port}",
                "install/dev tunnel success banner",
            )
            require_contains(
                tunnel_output,
                "tunnel webhook capture persists full request/response bodies and headers",
                "install/dev tunnel persistence warning",
            )
            require_exists(tunnel_capture_path)
            if tunnel_inspector_html is None:
                raise SmokeFailure(
                    "install/dev tunnel inspector: expected the inspector UI to start on the requested port"
                )
            require_contains(
                tunnel_inspector_html,
                "/api/status",
                "install/dev tunnel inspector UI",
            )
            tunnel_sessions = read_inspector_sessions(
                tunnel_fixture / ".lpm" / "inspector.db"
            )
            if not any(
                session.get("id") == "sess-dev-smoke"
                and session.get("domain") == "dev-smoke.lpm.fyi"
                and session.get("local_port") == tunnel_dev_port
                for session in tunnel_sessions
            ):
                raise SmokeFailure(
                    "install/dev tunnel inspector: expected inspector.db to persist the hello session metadata"
                )
            if relay.request_headers.get("authorization") != "Bearer at-dev-tunnel":
                raise SmokeFailure(
                    "install/dev tunnel inspector: expected the relay handshake to carry the seeded bearer token"
                )
            if relay.request_headers.get("x-tunnel-auth") is not None:
                raise SmokeFailure(
                    "install/dev tunnel inspector: expected the plain tunnel handshake to omit X-Tunnel-Auth"
                )
            tunnel_query = relay.request_query()
            if tunnel_query.get("port") != [str(tunnel_dev_port)]:
                raise SmokeFailure(
                    "install/dev tunnel inspector: expected the relay connect URL to carry the local port"
                )

        tunnel_auth_fixture = reset_dev_fixture().resolve()
        tunnel_auth_capture_path = tunnel_auth_fixture / "tunnel-auth-capture.json"
        tunnel_auth_dev_port = reserve_then_release_port()
        tunnel_auth_registry_port = reserve_then_release_port()
        tunnel_auth_relay_port = reserve_then_release_port()

        with tempfile.TemporaryDirectory(prefix="lpm-smoke-dev-tunnel-auth-") as tunnel_auth_home:
            tunnel_auth_home_path = Path(tunnel_auth_home)
            tunnel_auth_registry_url = (
                f"http://127.0.0.1:{tunnel_auth_registry_port}"
            )
            tunnel_auth_env = {
                "HOME": tunnel_auth_home,
                "LPM_HOME": str(tunnel_auth_home_path / ".lpm"),
                "LPM_FORCE_FILE_AUTH": "1",
                "LPM_TEST_FAST_SCRYPT": "1",
                "LPM_TUNNEL_RELAY": (
                    f"ws://127.0.0.1:{tunnel_auth_relay_port}/connect"
                ),
            }
            seed_refresh_backed_session(
                tunnel_auth_env,
                tunnel_auth_registry_url,
                "at-dev-tunnel-auth",
                "rt-dev-tunnel-auth",
                "2099-01-01T00:00:00Z",
            )

            with FakeTunnelRelay(
                tunnel_auth_relay_port,
                "https://private-smoke.lpm.llc",
                "sess-dev-tunnel-auth",
            ) as relay:
                tunnel_auth_args = [
                    str(LPM_BIN),
                    "--registry",
                    tunnel_auth_registry_url,
                    "--insecure",
                    "dev",
                    "--tunnel",
                    "--tunnel-auth",
                    "--no-inspect",
                    "--no-install",
                    "--no-open",
                    "--no-env-check",
                    "--port",
                    str(tunnel_auth_dev_port),
                    "--",
                    "--port",
                    str(tunnel_auth_dev_port),
                    "--capture",
                    tunnel_auth_capture_path.name,
                ]
                log("install/dev tunnel-auth: " + " ".join(tunnel_auth_args))
                tunnel_auth_process = subprocess.Popen(
                    tunnel_auth_args,
                    cwd=tunnel_auth_fixture,
                    env=merged_env(tunnel_auth_env),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                try:
                    relay.wait_for_connection()
                    tunnel_auth_stdout, tunnel_auth_stderr = (
                        tunnel_auth_process.communicate(timeout=10)
                    )
                finally:
                    if tunnel_auth_process.poll() is None:
                        tunnel_auth_process.kill()
                        tunnel_auth_process.wait(timeout=5)

            if tunnel_auth_stdout:
                sys.stdout.write(tunnel_auth_stdout)
            if tunnel_auth_stderr:
                sys.stderr.write(tunnel_auth_stderr)

            if tunnel_auth_process.returncode != 0:
                raise SmokeFailure(
                    "install/dev tunnel-auth failed with exit code "
                    f"{tunnel_auth_process.returncode}"
                )

            tunnel_auth_output = tunnel_auth_stdout + tunnel_auth_stderr
            require_contains(
                tunnel_auth_output,
                f"Tunnel https://private-smoke.lpm.llc → localhost:{tunnel_auth_dev_port}",
                "install/dev tunnel-auth success banner",
            )
            require_exists(tunnel_auth_capture_path)
            auth_line = next(
                (
                    line.strip()
                    for line in tunnel_auth_output.splitlines()
                    if "Auth required: add header X-Tunnel-Auth:" in line
                ),
                None,
            )
            if auth_line is None:
                raise SmokeFailure(
                    "install/dev tunnel-auth: expected the auth-required hint after a successful relay hello"
                )
            tunnel_auth_token = auth_line.rsplit(": ", 1)[-1]
            require_contains(
                tunnel_auth_output,
                f"Browser: https://private-smoke.lpm.llc?__tunnel_auth={tunnel_auth_token}",
                "install/dev tunnel-auth browser hint",
            )
            if relay.request_headers.get("authorization") != "Bearer at-dev-tunnel-auth":
                raise SmokeFailure(
                    "install/dev tunnel-auth: expected the relay handshake to carry the seeded bearer token"
                )
            if relay.request_headers.get("x-tunnel-auth") != tunnel_auth_token:
                raise SmokeFailure(
                    "install/dev tunnel-auth: expected X-Tunnel-Auth to match the printed session token"
                )

        tunnel_no_inspect_fixture = reset_dev_fixture().resolve()
        tunnel_no_inspect_capture_path = (
            tunnel_no_inspect_fixture / "tunnel-no-inspect-capture.json"
        )
        tunnel_no_inspect_dev_port = reserve_then_release_port()
        tunnel_no_inspect_port = reserve_then_release_port()
        tunnel_no_inspect_registry_port = reserve_then_release_port()
        tunnel_no_inspect_relay_port = reserve_then_release_port()

        with tempfile.TemporaryDirectory(prefix="lpm-smoke-dev-tunnel-no-inspect-") as tunnel_no_inspect_home:
            tunnel_no_inspect_home_path = Path(tunnel_no_inspect_home)
            tunnel_no_inspect_registry_url = (
                f"http://127.0.0.1:{tunnel_no_inspect_registry_port}"
            )
            tunnel_no_inspect_env = {
                "HOME": tunnel_no_inspect_home,
                "LPM_HOME": str(tunnel_no_inspect_home_path / ".lpm"),
                "LPM_FORCE_FILE_AUTH": "1",
                "LPM_TEST_FAST_SCRYPT": "1",
                "LPM_TUNNEL_RELAY": (
                    f"ws://127.0.0.1:{tunnel_no_inspect_relay_port}/connect"
                ),
            }
            seed_refresh_backed_session(
                tunnel_no_inspect_env,
                tunnel_no_inspect_registry_url,
                "at-dev-tunnel-no-inspect",
                "rt-dev-tunnel-no-inspect",
                "2099-01-01T00:00:00Z",
            )

            tunnel_no_inspect_args = [
                str(LPM_BIN),
                "--registry",
                tunnel_no_inspect_registry_url,
                "--insecure",
                "dev",
                "--tunnel",
                "--no-inspect",
                "--inspect-port",
                str(tunnel_no_inspect_port),
                "--no-install",
                "--no-open",
                "--no-env-check",
                "--port",
                str(tunnel_no_inspect_dev_port),
                "--",
                "--port",
                str(tunnel_no_inspect_dev_port),
                "--capture",
                tunnel_no_inspect_capture_path.name,
            ]
            log("install/dev tunnel no-inspect: " + " ".join(tunnel_no_inspect_args))
            tunnel_no_inspect_process = subprocess.Popen(
                tunnel_no_inspect_args,
                cwd=tunnel_no_inspect_fixture,
                env=merged_env(tunnel_no_inspect_env),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            tunnel_no_inspect_html: str | None = None
            try:
                deadline = time.monotonic() + 2
                tunnel_no_inspect_url = f"http://127.0.0.1:{tunnel_no_inspect_port}/"
                while time.monotonic() < deadline:
                    if tunnel_no_inspect_process.poll() is not None:
                        break
                    try:
                        with urlopen(tunnel_no_inspect_url, timeout=0.25) as response:
                            tunnel_no_inspect_html = response.read().decode("utf-8")
                            break
                    except Exception:
                        time.sleep(0.1)

                no_inspect_stdout, no_inspect_stderr = (
                    tunnel_no_inspect_process.communicate(timeout=10)
                )
            finally:
                if tunnel_no_inspect_process.poll() is None:
                    tunnel_no_inspect_process.kill()
                    tunnel_no_inspect_process.wait(timeout=5)

            if no_inspect_stdout:
                sys.stdout.write(no_inspect_stdout)
            if no_inspect_stderr:
                sys.stderr.write(no_inspect_stderr)

            if tunnel_no_inspect_process.returncode != 0:
                raise SmokeFailure(
                    "install/dev tunnel no-inspect failed with exit code "
                    f"{tunnel_no_inspect_process.returncode}"
                )

            no_inspect_output = no_inspect_stdout + no_inspect_stderr
            require_contains(
                no_inspect_output,
                "tunnel webhook capture persists full request/response bodies and headers",
                "install/dev tunnel no-inspect persistence warning",
            )
            require_exists(tunnel_no_inspect_capture_path)
            if (
                f"Inspect http://127.0.0.1:{tunnel_no_inspect_port}/?token="
                in no_inspect_output
            ):
                raise SmokeFailure(
                    "install/dev tunnel no-inspect: expected no inspector banner when --no-inspect is set"
                )
            if tunnel_no_inspect_html is not None:
                raise SmokeFailure(
                    "install/dev tunnel no-inspect: expected the inspector server to stay offline"
                )

        tunnel_strict_fixture = reset_dev_fixture().resolve()
        tunnel_strict_capture_path = (
            tunnel_strict_fixture / "tunnel-strict-capture.json"
        )
        tunnel_strict_dev_port = reserve_then_release_port()
        tunnel_strict_inspect_port = reserve_then_release_port()
        tunnel_strict_registry_port = reserve_then_release_port()
        tunnel_strict_relay_port = reserve_then_release_port()

        with tempfile.TemporaryDirectory(prefix="lpm-smoke-dev-tunnel-strict-") as tunnel_strict_home:
            tunnel_strict_home_path = Path(tunnel_strict_home)
            tunnel_strict_registry_url = (
                f"http://127.0.0.1:{tunnel_strict_registry_port}"
            )
            tunnel_strict_env = {
                "HOME": tunnel_strict_home,
                "LPM_HOME": str(tunnel_strict_home_path / ".lpm"),
                "LPM_FORCE_FILE_AUTH": "1",
                "LPM_TEST_FAST_SCRYPT": "1",
                "LPM_TUNNEL_RELAY": f"ws://127.0.0.1:{tunnel_strict_relay_port}/connect",
            }
            seed_refresh_backed_session(
                tunnel_strict_env,
                tunnel_strict_registry_url,
                "at-dev-tunnel-strict",
                "rt-dev-tunnel-strict",
                "2099-01-01T00:00:00Z",
            )

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied_inspector:
                occupied_inspector.bind(("127.0.0.1", tunnel_strict_inspect_port))
                occupied_inspector.listen()

                tunnel_strict_result = run_command_result(
                    "install/dev tunnel inspect-port addrinuse",
                    tunnel_strict_fixture,
                    [
                        str(LPM_BIN),
                        "--registry",
                        tunnel_strict_registry_url,
                        "--insecure",
                        "dev",
                        "--tunnel",
                        "--inspect-port",
                        str(tunnel_strict_inspect_port),
                        "--no-install",
                        "--no-open",
                        "--no-env-check",
                        "--port",
                        str(tunnel_strict_dev_port),
                        "--",
                        "--port",
                        str(tunnel_strict_dev_port),
                        "--capture",
                        tunnel_strict_capture_path.name,
                    ],
                    extra_env=tunnel_strict_env,
                )

            if tunnel_strict_result.returncode == 0:
                raise SmokeFailure(
                    "install/dev tunnel inspect-port addrinuse: expected a non-zero exit when the requested inspector port is occupied"
                )
            tunnel_strict_output = (
                tunnel_strict_result.stdout + tunnel_strict_result.stderr
            )
            require_contains(
                tunnel_strict_output,
                f"inspector port {tunnel_strict_inspect_port} is already in use",
                "install/dev tunnel inspect-port addrinuse message",
            )
            require_not_exists(tunnel_strict_capture_path)

        orchestration_fixture = reset_dev_orchestration_fixture().resolve()
        orchestration_events_path = orchestration_fixture / "orchestration-events.jsonl"
        db_port = reserve_then_release_port()
        api_port = reserve_then_release_port()
        web_port = reserve_then_release_port()

        orchestration_config = json.loads(
            (orchestration_fixture / "lpm.json").read_text(encoding="utf-8")
        )
        orchestration_config["services"]["db"]["port"] = db_port
        orchestration_config["services"]["db"]["readyPort"] = db_port
        orchestration_config["services"]["api"]["port"] = api_port
        orchestration_config["services"]["api"]["readyUrl"] = (
            f"http://127.0.0.1:{api_port}/health"
        )
        orchestration_config["services"]["web"]["port"] = web_port
        orchestration_config["services"]["web"]["readyPort"] = web_port
        (orchestration_fixture / "lpm.json").write_text(
            json.dumps(orchestration_config, indent=4) + "\n",
            encoding="utf-8",
        )

        orchestration_output = run_command(
            "install/dev orchestration dependsOn",
            orchestration_fixture,
            [str(LPM_BIN), "dev", "--no-install", "--no-open"],
            extra_env=scenario_env,
        )
        require_contains(
            orchestration_output,
            "(after db)",
            "install/dev orchestration startup dependency banner for api",
        )
        require_contains(
            orchestration_output,
            "(after api)",
            "install/dev orchestration startup dependency banner for web",
        )
        require_contains(
            orchestration_output,
            "[db]",
            "install/dev orchestration db output",
        )
        require_contains(
            orchestration_output,
            "[api]",
            "install/dev orchestration api output",
        )
        require_contains(
            orchestration_output,
            "[web]",
            "install/dev orchestration web output",
        )

        require_exists(orchestration_events_path)
        orchestration_events = [
            json.loads(line)
            for line in orchestration_events_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        start_events = [event for event in orchestration_events if event.get("event") == "start"]
        if [event.get("service") for event in start_events] != ["db", "api", "web"]:
            raise SmokeFailure(
                "install/dev orchestration dependsOn: expected db -> api -> web startup order"
            )

        dependency_events = {
            event.get("service"): event
            for event in orchestration_events
            if event.get("event") == "dependency-ok"
        }
        api_dependency = dependency_events.get("api")
        web_dependency = dependency_events.get("web")
        if api_dependency is None or web_dependency is None:
            raise SmokeFailure(
                "install/dev orchestration dependsOn: expected dependency-ok events for api and web"
            )
        if api_dependency.get("depUrl") != f"http://localhost:{db_port}":
            raise SmokeFailure(
                "install/dev orchestration dependsOn: expected api to probe the injected DB_URL"
            )
        if web_dependency.get("depUrl") != f"http://localhost:{api_port}":
            raise SmokeFailure(
                "install/dev orchestration dependsOn: expected web to probe the injected API_URL"
            )

        start_by_service = {event.get("service"): event for event in start_events}
        api_env = (start_by_service.get("api") or {}).get("env") or {}
        web_env = (start_by_service.get("web") or {}).get("env") or {}
        if api_env.get("DB_URL") != f"http://localhost:{db_port}":
            raise SmokeFailure(
                "install/dev orchestration dependsOn: expected api to receive DB_URL cross-service env"
            )
        if api_env.get("DB_PORT") != str(db_port):
            raise SmokeFailure(
                "install/dev orchestration dependsOn: expected api to receive DB_PORT cross-service env"
            )
        if api_env.get("API_SENTINEL") != "from-config":
            raise SmokeFailure(
                "install/dev orchestration dependsOn: expected api service env overrides to be present"
            )
        if web_env.get("API_URL") != f"http://localhost:{api_port}":
            raise SmokeFailure(
                "install/dev orchestration dependsOn: expected web to receive API_URL cross-service env"
            )
        if web_env.get("API_PORT") != str(api_port):
            raise SmokeFailure(
                "install/dev orchestration dependsOn: expected web to receive API_PORT cross-service env"
            )
        if web_env.get("WEB_SENTINEL") != "from-config":
            raise SmokeFailure(
                "install/dev orchestration dependsOn: expected web service env overrides to be present"
            )


def scenario_install_env_command() -> None:
    fixture = reset_env_fixture().resolve()

    with tempfile.TemporaryDirectory(prefix="lpm-smoke-env-") as home_root:
        scenario_env = {
            "HOME": home_root,
            "LPM_HOME": str(Path(home_root) / ".lpm"),
            "LPM_FORCE_FILE_VAULT": "1",
            "LPM_TEST_FAST_SCRYPT": "1",
        }

        missing_output = run_command_expect_failure(
            "install/env preview run blocks on missing required secrets",
            fixture,
            [str(LPM_BIN), "run", "--env=preview", "hello"],
            extra_env=scenario_env,
        )
        require_contains(
            missing_output,
            "DATABASE_URL",
            "install/env preview run missing output",
        )
        require_contains(
            missing_output,
            "STRIPE_KEY",
            "install/env preview run missing output",
        )

        set_result = run_command_result(
            "install/env set preview secrets json",
            fixture,
            [
                str(LPM_BIN),
                "--json",
                "env",
                "set",
                "--env=preview",
                "DATABASE_URL=https://preview-db.example.com",
                "STRIPE_KEY=sk_preview_smoke",
            ],
            extra_env=scenario_env,
        )
        if set_result.returncode != 0:
            raise SmokeFailure(
                "install/env set preview secrets json failed with exit code "
                f"{set_result.returncode}"
            )

        set_envelope = json.loads(set_result.stdout)
        if set_envelope.get("success") is not True:
            raise SmokeFailure("install/env set preview secrets json: expected success=true")
        if set_envelope.get("env") != "preview":
            raise SmokeFailure("install/env set preview secrets json: expected env=preview")
        if set_envelope.get("stored") != ["DATABASE_URL", "STRIPE_KEY"]:
            raise SmokeFailure(
                "install/env set preview secrets json: expected stored[] to list the written keys in order"
            )

        ls_result = run_command_result(
            "install/env ls json",
            fixture,
            [str(LPM_BIN), "--json", "env", "ls"],
            extra_env=scenario_env,
        )
        if ls_result.returncode != 0:
            raise SmokeFailure(
                f"install/env ls json failed with exit code {ls_result.returncode}"
            )

        ls_envelope = json.loads(ls_result.stdout)
        if ls_envelope.get("success") is not True:
            raise SmokeFailure("install/env ls json: expected success=true")

        preview_row = next(
            (
                row
                for row in ls_envelope.get("environments", [])
                if row.get("environment") == "preview"
            ),
            None,
        )
        if preview_row is None:
            raise SmokeFailure("install/env ls json: expected preview environment row")
        if preview_row.get("variables") != 2:
            raise SmokeFailure(
                "install/env ls json: expected preview variables=2 after writing two preview-scoped secrets"
            )
        if preview_row.get("schemaValid") != 2 or preview_row.get("schemaTotal") != 2:
            raise SmokeFailure(
                "install/env ls json: expected preview schema status to show both required secrets satisfied"
            )

        run_output = run_command(
            "install/env preview run resolves files plus vault",
            fixture,
            [str(LPM_BIN), "run", "--env=preview", "hello"],
            extra_env=scenario_env,
        )
        require_contains(run_output, "ENV=staging", "install/env preview run output")
        require_contains(run_output, "PORT=8080", "install/env preview run output")
        require_contains(
            run_output,
            "DB=https://preview-db.example.com",
            "install/env preview run output",
        )
        require_contains(
            run_output,
            "STRIPE=sk_preview_smoke",
            "install/env preview run output",
        )


def scenario_install_tunnel_command() -> None:
    fixture = reset_tunnel_fixture().resolve()

    with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as home_root:
        lpm_home = Path(home_root) / ".lpm"
        scenario_env = {
            "HOME": home_root,
            "LPM_HOME": str(lpm_home),
            "LPM_FORCE_FILE_AUTH": "1",
        }

        lpm_dir = fixture / ".lpm"
        webhooks_dir = lpm_dir / "webhooks"
        webhooks_dir.mkdir(parents=True, exist_ok=True)

        request_body = b'{"type":"payment_intent.payment_failed","id":"evt_123"}'
        response_body = b'{"error":"declined"}'
        webhook_id = "wh-stripe-402"
        timestamp = "2026-05-22T10:05:00Z"
        summary = "Stripe: payment_intent.payment_failed"

        (lpm_dir / "webhook-log.jsonl").write_text(
            json.dumps(
                {
                    "id": webhook_id,
                    "ts": timestamp,
                    "method": "POST",
                    "path": "/webhooks/stripe",
                    "status": 402,
                    "ms": 18,
                    "provider": "Stripe",
                    "summary": summary,
                    "req_size": len(request_body),
                    "res_size": len(response_body),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (webhooks_dir / f"{webhook_id}.json").write_text(
            json.dumps(
                {
                    "id": webhook_id,
                    "timestamp": timestamp,
                    "method": "POST",
                    "path": "/webhooks/stripe",
                    "request_headers": {
                        "content-type": "application/json",
                        "stripe-signature": "sig_test_123",
                        "host": "hooks.example.test",
                    },
                    "request_body": base64.b64encode(request_body).decode("ascii"),
                    "response_status": 402,
                    "response_headers": {"content-type": "application/json"},
                    "response_body": base64.b64encode(response_body).decode("ascii"),
                    "duration_ms": 18,
                    "provider": "stripe",
                    "summary": summary,
                    "signature_diagnostic": None,
                    "auto_acked": False,
                }
            ),
            encoding="utf-8",
        )

        claim_result = run_command_result(
            "install/tunnel claim json without auth",
            fixture,
            [
                str(LPM_BIN),
                "--registry",
                "http://127.0.0.1:1",
                "--insecure",
                "--json",
                "tunnel",
                "claim",
                "smoke-test.lpm.fyi",
            ],
            extra_env=scenario_env,
        )
        if claim_result.returncode == 0:
            raise SmokeFailure(
                "install/tunnel claim json without auth: expected a non-zero exit code"
            )
        claim_envelope = json.loads(claim_result.stdout)
        if claim_envelope.get("success") is not False:
            raise SmokeFailure(
                "install/tunnel claim json without auth: expected success=false"
            )
        if claim_envelope.get("error_code") != "tunnel":
            raise SmokeFailure(
                "install/tunnel claim json without auth: expected error_code='tunnel'"
            )
        require_contains(
            claim_envelope.get("error", ""),
            "refresh-backed `lpm login` session",
            "install/tunnel claim json without auth",
        )

        inspect_result = run_command_result(
            "install/tunnel inspect json",
            fixture,
            [str(LPM_BIN), "--json", "tunnel", "inspect"],
            extra_env=scenario_env,
        )
        if inspect_result.returncode != 0:
            raise SmokeFailure(
                f"install/tunnel inspect json failed with exit code {inspect_result.returncode}"
            )
        inspect_entries = json.loads(inspect_result.stdout)
        if len(inspect_entries) != 1:
            raise SmokeFailure(
                "install/tunnel inspect json: expected exactly one seeded webhook entry"
            )
        inspect_entry = inspect_entries[0]
        if inspect_entry.get("provider") != "Stripe":
            raise SmokeFailure(
                "install/tunnel inspect json: expected provider='Stripe'"
            )
        if inspect_entry.get("status") != 402:
            raise SmokeFailure(
                "install/tunnel inspect json: expected status=402"
            )
        if inspect_entry.get("path") != "/webhooks/stripe":
            raise SmokeFailure(
                "install/tunnel inspect json: expected the seeded webhook path"
            )

        filtered_inspect_result = run_command_result(
            "install/tunnel inspect filtered json",
            fixture,
            [
                str(LPM_BIN),
                "--json",
                "tunnel",
                "inspect",
                "--",
                "--filter",
                "stripe",
                "--status",
                "4xx",
            ],
            extra_env=scenario_env,
        )
        if filtered_inspect_result.returncode != 0:
            raise SmokeFailure(
                "install/tunnel inspect filtered json: expected a zero exit code"
            )
        filtered_inspect_entries = json.loads(filtered_inspect_result.stdout)
        if len(filtered_inspect_entries) != 1:
            raise SmokeFailure(
                "install/tunnel inspect filtered json: expected the seeded Stripe 4xx webhook to survive filtering"
            )

        log_result = run_command_result(
            "install/tunnel log filtered json",
            fixture,
            [
                str(LPM_BIN),
                "--json",
                "tunnel",
                "log",
                "--",
                "--filter",
                "stripe",
                "--status",
                "4xx",
            ],
            extra_env=scenario_env,
        )
        if log_result.returncode != 0:
            raise SmokeFailure(
                f"install/tunnel log filtered json failed with exit code {log_result.returncode}"
            )
        log_entries = json.loads(log_result.stdout)
        if len(log_entries) != 1:
            raise SmokeFailure(
                "install/tunnel log filtered json: expected exactly one filtered webhook row"
            )
        if log_entries[0].get("summary") != summary:
            raise SmokeFailure(
                "install/tunnel log filtered json: expected the seeded summary"
            )

        replay_port = reserve_then_release_port()
        replay_capture_path = Path(home_root) / "tunnel-replay-capture.json"
        replay_listener = subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
                    "import json, sys\n"
                    "capture_path = sys.argv[1]\n"
                    "port = int(sys.argv[2])\n"
                    "class Handler(BaseHTTPRequestHandler):\n"
                    "    def do_POST(self):\n"
                    "        length = int(self.headers.get('Content-Length', '0'))\n"
                    "        body = self.rfile.read(length)\n"
                    "        payload = {\n"
                    "            'path': self.path,\n"
                    "            'headers': {k.lower(): v for k, v in self.headers.items()},\n"
                    "            'body': body.decode('utf-8'),\n"
                    "        }\n"
                    "        with open(capture_path, 'w', encoding='utf-8') as handle:\n"
                    "            json.dump(payload, handle)\n"
                    "        self.send_response(201)\n"
                    "        self.send_header('Content-Type', 'application/json')\n"
                    "        self.end_headers()\n"
                    "        self.wfile.write(b'{\\\"ok\\\":true}')\n"
                    "    def log_message(self, format, *args):\n"
                    "        return\n"
                    "server = HTTPServer(('127.0.0.1', port), Handler)\n"
                    "print('ready', flush=True)\n"
                    "server.handle_request()\n"
                ),
                str(replay_capture_path),
                str(replay_port),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            if replay_listener.stdout is None:
                raise SmokeFailure(
                    "install/tunnel replay listener: expected a readable stdout pipe"
                )
            ready_line = replay_listener.stdout.readline().strip()
            if ready_line != "ready":
                stderr_output = ""
                if replay_listener.stderr is not None:
                    stderr_output = replay_listener.stderr.read().strip()
                raise SmokeFailure(
                    "install/tunnel replay listener failed to start"
                    f"\nstdout: {ready_line!r}\nstderr: {stderr_output!r}"
                )

            replay_output = run_command(
                "install/tunnel replay",
                fixture,
                [str(LPM_BIN), "tunnel", "replay", "1", "--", "--port", str(replay_port)],
                extra_env=scenario_env,
            )
            require_contains(
                replay_output,
                "Fixed! Was 402, now 201.",
                "install/tunnel replay",
            )

            replay_listener.wait(timeout=5)
            if replay_listener.returncode != 0:
                stderr_output = ""
                if replay_listener.stderr is not None:
                    stderr_output = replay_listener.stderr.read().strip()
                raise SmokeFailure(
                    "install/tunnel replay listener exited non-zero"
                    f"\nstderr: {stderr_output!r}"
                )
        finally:
            if replay_listener.poll() is None:
                replay_listener.kill()
                replay_listener.wait(timeout=5)

        replay_capture = json.loads(replay_capture_path.read_text(encoding="utf-8"))
        if replay_capture.get("path") != "/webhooks/stripe":
            raise SmokeFailure(
                "install/tunnel replay: expected the local server to receive the seeded webhook path"
            )
        if replay_capture.get("body") != request_body.decode("utf-8"):
            raise SmokeFailure(
                "install/tunnel replay: expected the local server to receive the original request body"
            )
        replay_headers = replay_capture.get("headers", {})
        if replay_headers.get("stripe-signature") != "sig_test_123":
            raise SmokeFailure(
                "install/tunnel replay: expected the original Stripe signature header to be preserved"
            )


def scenario_install_ports_command() -> None:
    fixture = reset_ports_fixture().resolve()

    with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as home_root:
        lpm_home = Path(home_root) / ".lpm"
        scenario_env = {
            "HOME": home_root,
            "LPM_HOME": str(lpm_home),
        }
        busy_port = reserve_then_release_port()
        free_port = reserve_then_release_port()
        listener_process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "import socket, sys, time\n"
                    "sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
                    "sock.bind(('127.0.0.1', int(sys.argv[1])))\n"
                    "sock.listen()\n"
                    "print('ready', flush=True)\n"
                    "time.sleep(600)\n"
                ),
                str(busy_port),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            if listener_process.stdout is None:
                raise SmokeFailure(
                    "install/ports busy listener: expected a readable stdout pipe"
                )
            ready_line = listener_process.stdout.readline().strip()
            if ready_line != "ready":
                stderr_output = ""
                if listener_process.stderr is not None:
                    stderr_output = listener_process.stderr.read().strip()
                raise SmokeFailure(
                    "install/ports busy listener failed to bind the seeded port"
                    f"\nstdout: {ready_line!r}\nstderr: {stderr_output!r}"
                )

            (fixture / "lpm.json").write_text(
                json.dumps(
                    {
                        "services": {
                            "web": {"command": "node web.js", "port": busy_port},
                            "api": {"command": "node api.js", "port": free_port},
                            "db": {
                                "command": "docker compose up postgres",
                                "readyPort": 5432,
                            },
                        }
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            list_result = run_command_result(
                "install/ports list json",
                fixture,
                [str(LPM_BIN), "ports", "list", "--json"],
                extra_env=scenario_env,
            )
            if list_result.returncode != 0:
                raise SmokeFailure(
                    f"install/ports list json failed with exit code {list_result.returncode}"
                )
            list_envelope = json.loads(list_result.stdout)
            if list_envelope.get("success") is not True:
                raise SmokeFailure("install/ports list json: expected success=true")
            listed_ports = sorted(
                list_envelope.get("ports", []),
                key=lambda entry: entry.get("service", ""),
            )
            expected_ports = [
                {"service": "api", "port": free_port, "status": "free"},
                {"service": "web", "port": busy_port, "status": "in_use"},
            ]
            if listed_ports != expected_ports:
                raise SmokeFailure(
                    "install/ports list json: expected only declared service.port entries with free/in_use statuses"
                    f"\nexpected: {expected_ports!r}\nactual: {listed_ports!r}"
                )

            human_output = run_command(
                "install/ports default human",
                fixture,
                [str(LPM_BIN), "ports"],
                extra_env=scenario_env,
            )
            require_contains(human_output, "Service Ports", "install/ports human header")
            require_contains(human_output, "web", "install/ports human service web")
            require_contains(human_output, "api", "install/ports human service api")
            require_contains(human_output, f":{busy_port}", "install/ports human busy port")
            require_contains(human_output, f":{free_port}", "install/ports human free port")
            require_contains(human_output, "in use", "install/ports human in-use status")
            require_contains(human_output, "free", "install/ports human free status")

            missing_kill_output = run_command_expect_failure(
                "install/ports kill missing",
                fixture,
                [str(LPM_BIN), "ports", "kill"],
                extra_env=scenario_env,
            )
            require_contains(
                missing_kill_output,
                "missing port number. Usage: lpm ports kill <port>",
                "install/ports kill missing usage",
            )

            kill_busy_result = run_command_result(
                "install/ports kill busy json",
                fixture,
                [str(LPM_BIN), "ports", "kill", str(busy_port), "--json"],
                extra_env=scenario_env,
            )
            if kill_busy_result.returncode != 0:
                raise SmokeFailure(
                    f"install/ports kill busy json failed with exit code {kill_busy_result.returncode}"
                )
            kill_busy_envelope = json.loads(kill_busy_result.stdout)
            if kill_busy_envelope.get("success") is not True:
                raise SmokeFailure("install/ports kill busy json: expected success=true")
            if kill_busy_envelope.get("port") != busy_port:
                raise SmokeFailure("install/ports kill busy json: expected the killed port to match the busy listener")
            killed_owner = kill_busy_envelope.get("killed")
            if not isinstance(killed_owner, str) or not killed_owner.strip():
                raise SmokeFailure(
                    "install/ports kill busy json: expected a non-empty killed owner description"
                )
            listener_process.wait(timeout=5)

            list_after_kill_result = run_command_result(
                "install/ports list after kill json",
                fixture,
                [str(LPM_BIN), "ports", "list", "--json"],
                extra_env=scenario_env,
            )
            if list_after_kill_result.returncode != 0:
                raise SmokeFailure(
                    "install/ports list after kill json failed with exit code "
                    f"{list_after_kill_result.returncode}"
                )
            list_after_kill_envelope = json.loads(list_after_kill_result.stdout)
            web_entry = next(
                (
                    entry
                    for entry in list_after_kill_envelope.get("ports", [])
                    if entry.get("service") == "web"
                ),
                None,
            )
            if web_entry != {"service": "web", "port": busy_port, "status": "free"}:
                raise SmokeFailure(
                    "install/ports list after kill json: expected the killed port to be reported as free"
                )

            already_free_result = run_command_result(
                "install/ports kill already-free json",
                fixture,
                [str(LPM_BIN), "ports", "kill", str(free_port), "--json"],
                extra_env=scenario_env,
            )
            if already_free_result.returncode != 0:
                raise SmokeFailure(
                    "install/ports kill already-free json failed with exit code "
                    f"{already_free_result.returncode}"
                )
            already_free_envelope = json.loads(already_free_result.stdout)
            if already_free_envelope != {
                "success": True,
                "port": free_port,
                "status": "already_free",
            }:
                raise SmokeFailure(
                    "install/ports kill already-free json: expected the stable already_free envelope"
                )

            ports_toml = lpm_home / "ports.toml"
            ports_toml.parent.mkdir(parents=True, exist_ok=True)
            current_key = project_port_override_key(fixture)
            other_key = "project_other_fixture"
            ports_toml.write_text(
                (
                    f"[{current_key}]\n"
                    f"web = {busy_port}\n\n"
                    f"[{other_key}]\n"
                    f"api = {free_port}\n"
                ),
                encoding="utf-8",
            )

            reset_result = run_command_result(
                "install/ports reset json",
                fixture,
                [str(LPM_BIN), "ports", "reset", "--json"],
                extra_env=scenario_env,
            )
            if reset_result.returncode != 0:
                raise SmokeFailure(
                    f"install/ports reset json failed with exit code {reset_result.returncode}"
                )
            reset_envelope = json.loads(reset_result.stdout)
            if reset_envelope != {"success": True, "reset": True}:
                raise SmokeFailure(
                    "install/ports reset json: expected the stable reset success envelope"
                )
            persisted = read_optional_text(ports_toml)
            if current_key in persisted:
                raise SmokeFailure(
                    "install/ports reset json: expected the current project's persisted override entry to be removed"
                )
            if other_key not in persisted or f"api = {free_port}" not in persisted:
                raise SmokeFailure(
                    "install/ports reset json: expected unrelated project overrides to be preserved"
                )
        finally:
            if listener_process.poll() is None:
                listener_process.terminate()
                try:
                    listener_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    listener_process.kill()
                    listener_process.wait(timeout=5)
            reset_ports_fixture()


def scenario_install_cert_command() -> None:
    fixture = reset_cert_fixture()

    with tempfile.TemporaryDirectory(prefix="lpm-smoke-home-") as lpm_home:
        home_root = Path(lpm_home)
        scenario_env = {
            "HOME": lpm_home,
            "LPM_HOME": lpm_home,
            "LPM_CERT_TEST_TRUST_STORE_DIR": str(home_root / ".lpm" / "test-trust-store"),
            "LPM_CERT_AUDIT_DIR": str(home_root / ".lpm" / "audit"),
        }
        ca_cert = home_root / ".lpm" / "certs" / "rootCA.pem"
        ca_key = home_root / ".lpm" / "certs" / "rootCA-key.pem"
        trust_store_entry = home_root / ".lpm" / "test-trust-store" / "lpm-local-ca.pem"
        audit_log = home_root / ".lpm" / "audit" / "cert.jsonl"
        project_cert = fixture / ".lpm" / "certs" / "cert.pem"
        project_key = fixture / ".lpm" / "certs" / "key.pem"

        try:
            absent_status_result = run_command_result(
                "install/cert status absent json",
                fixture,
                [str(LPM_BIN), "cert", "status", "--json"],
                extra_env=scenario_env,
            )
            if absent_status_result.returncode != 0:
                raise SmokeFailure(
                    f"install/cert status absent json failed with exit code {absent_status_result.returncode}"
                )
            absent_status = json.loads(absent_status_result.stdout)
            if absent_status.get("success") is not True:
                raise SmokeFailure("install/cert status absent json: expected success=true")
            if absent_status.get("ca", {}).get("exists") is not False:
                raise SmokeFailure("install/cert status absent json: expected ca.exists=false")
            if absent_status.get("project", {}).get("exists") is not False:
                raise SmokeFailure(
                    "install/cert status absent json: expected project.exists=false"
                )

            trust_result = run_command_result(
                "install/cert trust json",
                fixture,
                [str(LPM_BIN), "cert", "trust", "--json"],
                extra_env=scenario_env,
            )
            if trust_result.returncode != 0:
                raise SmokeFailure(
                    f"install/cert trust json failed with exit code {trust_result.returncode}"
                )
            trust_envelope = json.loads(trust_result.stdout)
            if trust_envelope.get("success") is not True:
                raise SmokeFailure("install/cert trust json: expected success=true")
            if trust_envelope.get("ca_installed") is not True:
                raise SmokeFailure("install/cert trust json: expected ca_installed=true")
            require_exists(ca_cert)
            require_exists(ca_key)
            require_exists(trust_store_entry)

            audit_actions: list[str] = []
            for line in read_optional_text(audit_log).splitlines():
                entry = json.loads(line)
                action = entry.get("action")
                if isinstance(action, str):
                    audit_actions.append(action)
            for required_action in {"ca.generate", "ca.trust_install"}:
                if required_action not in audit_actions:
                    raise SmokeFailure(
                        f"install/cert trust json: expected audit action {required_action}"
                    )

            uninstall_result = run_command_result(
                "install/cert uninstall json",
                fixture,
                [str(LPM_BIN), "cert", "uninstall", "--json"],
                extra_env=scenario_env,
            )
            if uninstall_result.returncode != 0:
                raise SmokeFailure(
                    f"install/cert uninstall json failed with exit code {uninstall_result.returncode}"
                )
            uninstall_envelope = json.loads(uninstall_result.stdout)
            if uninstall_envelope.get("success") is not True:
                raise SmokeFailure("install/cert uninstall json: expected success=true")
            if uninstall_envelope.get("ca_uninstalled") is not True:
                raise SmokeFailure(
                    "install/cert uninstall json: expected ca_uninstalled=true"
                )
            require_exists(ca_cert)
            require_exists(ca_key)
            require_not_exists(trust_store_entry)

            generate_result = run_command_result(
                "install/cert generate json",
                fixture,
                [str(LPM_BIN), "cert", "generate", "--json"],
                extra_env=scenario_env,
            )
            if generate_result.returncode != 0:
                raise SmokeFailure(
                    f"install/cert generate json failed with exit code {generate_result.returncode}"
                )
            generate_envelope = json.loads(generate_result.stdout)
            if generate_envelope.get("success") is not True:
                raise SmokeFailure("install/cert generate json: expected success=true")
            if generate_envelope.get("ca_freshly_installed") is not False:
                raise SmokeFailure(
                    "install/cert generate json: expected generate to avoid trust-store installation"
                )
            if generate_envelope.get("cert_freshly_generated") is not True:
                raise SmokeFailure(
                    "install/cert generate json: expected cert_freshly_generated=true"
                )
            if generate_envelope.get("cert_path") != str(project_cert):
                raise SmokeFailure("install/cert generate json: expected cert_path to match the project cert")
            if generate_envelope.get("key_path") != str(project_key):
                raise SmokeFailure("install/cert generate json: expected key_path to match the project key")
            require_exists(project_cert)
            require_exists(project_key)
            require_not_exists(trust_store_entry)

            refresh_result = run_command_result(
                "install/cert generate host json",
                fixture,
                [
                    str(LPM_BIN),
                    "cert",
                    "generate",
                    "--json",
                    "--host",
                    "myapp.local",
                    "--host",
                    "api.myapp.local",
                ],
                extra_env=scenario_env,
            )
            if refresh_result.returncode != 0:
                raise SmokeFailure(
                    f"install/cert generate host json failed with exit code {refresh_result.returncode}"
                )
            refresh_envelope = json.loads(refresh_result.stdout)
            if refresh_envelope.get("success") is not True:
                raise SmokeFailure("install/cert generate host json: expected success=true")
            if refresh_envelope.get("ca_freshly_installed") is not False:
                raise SmokeFailure(
                    "install/cert generate host json: expected generate --host to avoid trust-store installation"
                )
            if refresh_envelope.get("cert_freshly_generated") is not True:
                raise SmokeFailure(
                    "install/cert generate host json: expected the missing host to trigger regeneration"
                )

            status_result = run_command_result(
                "install/cert status generated json",
                fixture,
                [str(LPM_BIN), "cert", "status", "--json"],
                extra_env=scenario_env,
            )
            if status_result.returncode != 0:
                raise SmokeFailure(
                    f"install/cert status generated json failed with exit code {status_result.returncode}"
                )
            status_envelope = json.loads(status_result.stdout)
            if status_envelope.get("success") is not True:
                raise SmokeFailure("install/cert status generated json: expected success=true")
            if status_envelope.get("ca", {}).get("exists") is not True:
                raise SmokeFailure("install/cert status generated json: expected ca.exists=true")
            if status_envelope.get("ca", {}).get("trusted") is not False:
                raise SmokeFailure(
                    "install/cert status generated json: expected the CA to remain untrusted until explicit trust"
                )
            if status_envelope.get("project", {}).get("exists") is not True:
                raise SmokeFailure(
                    "install/cert status generated json: expected project.exists=true"
                )
            if status_envelope.get("project", {}).get("needs_renewal") is not False:
                raise SmokeFailure(
                    "install/cert status generated json: expected needs_renewal=false for the freshly generated cert"
                )
            hostnames = status_envelope.get("project", {}).get("hostnames", [])
            if not any("localhost" in hostname for hostname in hostnames):
                raise SmokeFailure(
                    f"install/cert status generated json: expected localhost in SANs, got {hostnames!r}"
                )
            for requested_host in {"myapp.local", "api.myapp.local"}:
                if not any(requested_host in hostname for hostname in hostnames):
                    raise SmokeFailure(
                        f"install/cert status generated json: expected {requested_host} in SANs, got {hostnames!r}"
                    )

            human_status = run_command(
                "install/cert status human",
                fixture,
                [str(LPM_BIN), "cert", "status"],
                extra_env=scenario_env,
            )
            require_contains(human_status, "Root CA", "install/cert status human header")
            require_contains(
                human_status,
                "Project Certificate",
                "install/cert status human project header",
            )
            require_contains(human_status, "hostnames", "install/cert status human hostnames label")
            require_contains(
                human_status,
                "myapp.local",
                "install/cert status human requested hostname",
            )
        finally:
            reset_cert_fixture()


def scenario_install_doctor_command() -> None:
    expected_vault_code = (
        "vault_storage_keychain" if sys.platform == "darwin" else "vault_storage_fallback"
    )

    with MockRegistry([]) as registry, tempfile.TemporaryDirectory(
        prefix="lpm-smoke-home-"
    ) as lpm_home:
        scenario_env = {
            "LPM_HOME": lpm_home,
            "LPM_PROVENANCE_ENFORCE": "deny",
        }
        registry_args = ["--registry", registry.registry_url, "--insecure"]

        fixture = reset_doctor_fixture()

        fast_result = run_command_result(
            "install/doctor fast json",
            fixture,
            [str(LPM_BIN), *registry_args, "doctor", "--json"],
            extra_env=scenario_env,
        )
        fast_envelope = json.loads(fast_result.stdout)
        if fast_envelope.get("success") is not True:
            raise SmokeFailure("install/doctor fast json: expected success=true")
        if fast_envelope.get("mode") != "fast":
            raise SmokeFailure("install/doctor fast json: expected mode=fast")
        if fast_envelope.get("fixes_applied") != []:
            raise SmokeFailure("install/doctor fast json: expected no fixes_applied in read-only mode")
        fast_codes = {check.get("code") for check in fast_envelope.get("checks", [])}
        for required_code in {
            "global_store_accessible",
            "package_json_present",
            "linker_mode_resolved",
            expected_vault_code,
            "sigstore_verify_enforced",
        }:
            if required_code not in fast_codes:
                raise SmokeFailure(
                    f"install/doctor fast json: expected {required_code} in the fast preset"
                )
        for unexpected_code in {"registry_reachable", "auth_missing"}:
            if unexpected_code in fast_codes:
                raise SmokeFailure(
                    f"install/doctor fast json: did not expect extended-tier code {unexpected_code} in the fast preset"
                )
        if registry.requested_paths() != []:
            raise SmokeFailure(
                "install/doctor fast json: expected the default fast preset to avoid all registry requests"
            )

        all_result = run_command_result(
            "install/doctor all json",
            fixture,
            [str(LPM_BIN), *registry_args, "doctor", "--all", "--json"],
            extra_env=scenario_env,
        )
        all_envelope = json.loads(all_result.stdout)
        if all_envelope.get("success") is not True:
            raise SmokeFailure("install/doctor all json: expected success=true")
        if all_envelope.get("mode") != "all":
            raise SmokeFailure("install/doctor all json: expected mode=all")
        all_codes = {check.get("code") for check in all_envelope.get("checks", [])}
        for required_code in {
            "registry_reachable",
            "auth_missing",
            expected_vault_code,
            "sigstore_verify_enforced",
        }:
            if required_code not in all_codes:
                raise SmokeFailure(
                    f"install/doctor all json: expected {required_code} in the full preset"
                )
        if registry.requested_paths() != ["/api/registry/health"]:
            raise SmokeFailure(
                "install/doctor all json: expected exactly one registry health probe and no whoami lookup without a token"
            )

        list_result = run_command_result(
            "install/doctor list json",
            fixture,
            [str(LPM_BIN), "doctor", "list", "--json"],
            extra_env=scenario_env,
        )
        if list_result.returncode != 0:
            raise SmokeFailure(
                f"install/doctor list json failed with exit code {list_result.returncode}"
            )
        list_envelope = json.loads(list_result.stdout)
        if list_envelope.get("success") is not True:
            raise SmokeFailure("install/doctor list json: expected success=true")
        entries = list_envelope.get("entries", [])
        if list_envelope.get("count") != len(entries):
            raise SmokeFailure(
                "install/doctor list json: expected count to match the number of returned entries"
            )
        listed_codes = {entry.get("code") for entry in entries}
        for required_code in {"registry_reachable", expected_vault_code, "sigstore_verify_enforced"}:
            if required_code not in listed_codes:
                raise SmokeFailure(
                    f"install/doctor list json: expected live catalog entry {required_code}"
                )

        code_result = run_command_result(
            "install/doctor list code json",
            fixture,
            [str(LPM_BIN), "doctor", "list", "--code", "registry_reachable", "--json"],
            extra_env=scenario_env,
        )
        if code_result.returncode != 0:
            raise SmokeFailure(
                f"install/doctor list code json failed with exit code {code_result.returncode}"
            )
        code_envelope = json.loads(code_result.stdout)
        code_entries = code_envelope.get("entries", [])
        if code_envelope.get("count") != 1 or len(code_entries) != 1:
            raise SmokeFailure(
                "install/doctor list code json: expected the exact-code filter to return one entry"
            )
        if code_entries[0].get("code") != "registry_reachable":
            raise SmokeFailure(
                "install/doctor list code json: expected the single filtered entry to be registry_reachable"
            )

        category_result = run_command_result(
            "install/doctor list category json",
            fixture,
            [str(LPM_BIN), "doctor", "list", "--category", "tunnel", "--json"],
            extra_env=scenario_env,
        )
        if category_result.returncode != 0:
            raise SmokeFailure(
                f"install/doctor list category json failed with exit code {category_result.returncode}"
            )
        category_envelope = json.loads(category_result.stdout)
        category_entries = category_envelope.get("entries", [])
        if category_envelope.get("count", 0) <= 0:
            raise SmokeFailure(
                "install/doctor list category json: expected the tunnel substring filter to return entries"
            )
        if any(entry.get("category") != "Tunnel" for entry in category_entries):
            raise SmokeFailure(
                "install/doctor list category json: expected the category filter to return only Tunnel rows"
            )

        fix_fixture = reset_doctor_fixture()
        seed_store_verify_lockfile(
            fix_fixture,
            [("doctor-lockfile-pkg", "1.0.0", "sha512-doctor-lockfile")],
        )
        requests_before_fix = list(registry.requested_paths())
        fix_result = run_command_result(
            "install/doctor fast fix json",
            fix_fixture,
            [str(LPM_BIN), *registry_args, "doctor", "--fix", "--json"],
            extra_env=scenario_env,
        )
        fix_envelope = json.loads(fix_result.stdout)
        if fix_envelope.get("success") is not True:
            raise SmokeFailure("install/doctor fast fix json: expected success=true")
        if fix_envelope.get("mode") != "fast":
            raise SmokeFailure("install/doctor fast fix json: expected mode=fast")
        fixes_applied = fix_envelope.get("fixes_applied", [])
        if "regenerated lpm.lockb" not in fixes_applied:
            raise SmokeFailure(
                "install/doctor fast fix json: expected fast --fix to regenerate lpm.lockb when only lpm.lock exists"
            )
        if "updated .gitattributes" in fixes_applied:
            raise SmokeFailure(
                "install/doctor fast fix json: expected fast --fix to avoid dispatching the extended-only .gitattributes fixer"
            )
        require_exists(fix_fixture / "lpm.lockb")
        if registry.requested_paths() != requests_before_fix:
            raise SmokeFailure(
                "install/doctor fast fix json: expected fast --fix to remain local-only and avoid registry requests"
            )
        delete_path(fix_fixture / ".gitattributes")
        delete_path(fix_fixture / ".gitignore")
        reset_doctor_fixture()


def scenario_install_health_command() -> None:
    with MockRegistry([]) as registry, tempfile.TemporaryDirectory(
        prefix="lpm-smoke-home-"
    ) as lpm_home:
        fixture = reset_health_fixture()
        scenario_env = {"LPM_HOME": lpm_home}
        registry_args = ["--registry", registry.registry_url, "--insecure"]

        healthy_result = run_command_result(
            "install/health healthy json",
            fixture,
            [str(LPM_BIN), *registry_args, "health", "--json"],
            extra_env=scenario_env,
        )
        if healthy_result.returncode != 0:
            raise SmokeFailure(
                f"install/health healthy json failed with exit code {healthy_result.returncode}"
            )
        healthy_envelope = json.loads(healthy_result.stdout)
        if healthy_envelope.get("success") is not True:
            raise SmokeFailure("install/health healthy json: expected success=true")
        if healthy_envelope.get("healthy") is not True:
            raise SmokeFailure("install/health healthy json: expected healthy=true")
        if healthy_envelope.get("registry_url", "").rstrip("/") != registry.registry_url.rstrip("/"):
            raise SmokeFailure(
                "install/health healthy json: expected registry_url to match the configured registry"
            )
        response_time_ms = healthy_envelope.get("response_time_ms")
        if not isinstance(response_time_ms, int) or response_time_ms < 0:
            raise SmokeFailure(
                "install/health healthy json: expected response_time_ms to be a non-negative integer"
            )
        if registry.requested_paths() != ["/api/registry/health"]:
            raise SmokeFailure(
                "install/health healthy json: expected exactly one health-endpoint round trip"
            )

        unhealthy_result = run_command_result(
            "install/health unreachable json",
            fixture,
            [
                str(LPM_BIN),
                "--registry",
                "http://127.0.0.1:1",
                "--insecure",
                "health",
                "--json",
            ],
            extra_env=scenario_env,
        )
        if unhealthy_result.returncode == 0:
            raise SmokeFailure(
                "install/health unreachable json: expected a non-zero exit when the registry is unreachable"
            )


def scenario_install_setup_commands() -> None:
    token_response = {
        "token": "lpm_read_only_smoke_token",
        "expiresAt": "2030-01-02T03:04:05Z",
    }

    with MockRegistry([], token_create_response=token_response) as registry, tempfile.TemporaryDirectory(
        prefix="lpm-smoke-home-"
    ) as lpm_home, tempfile.TemporaryDirectory(prefix="lpm-setup-ci-") as ci_project, tempfile.TemporaryDirectory(
        prefix="lpm-setup-local-"
    ) as local_project:
        registry_base = registry.registry_url.rstrip("/")
        scenario_env = {
            "LPM_HOME": lpm_home,
            "LPM_TOKEN": "lpm_ci_smoke_token",
        }

        ci_project_path = Path(ci_project)
        local_project_path = Path(local_project)
        (ci_project_path / "package.json").write_text(
            '{"name":"setup-ci-smoke","private":true,"version":"0.0.0"}\n',
            encoding="utf-8",
        )
        (local_project_path / "package.json").write_text(
            '{"name":"setup-local-smoke","private":true,"version":"0.0.0"}\n',
            encoding="utf-8",
        )

        ci_result = run_command_result(
            "install/setup ci json",
            ci_project_path,
            [
                str(LPM_BIN),
                "--registry",
                registry_base,
                "--insecure",
                "--json",
                "setup",
                "ci",
            ],
            extra_env=scenario_env,
        )
        if ci_result.returncode != 0:
            raise SmokeFailure(
                f"install/setup ci json failed with exit code {ci_result.returncode}"
            )
        ci_envelope = json.loads(ci_result.stdout)
        if ci_envelope.get("success") is not True:
            raise SmokeFailure("install/setup ci json: expected success=true")
        if ci_envelope.get("oidc") is not False:
            raise SmokeFailure("install/setup ci json: expected oidc=false")
        if ci_envelope.get("proxy") is not False:
            raise SmokeFailure("install/setup ci json: expected proxy=false")
        if ci_envelope.get("uses_env_var") is not False:
            raise SmokeFailure(
                "install/setup ci json: expected uses_env_var=false when LPM_TOKEN is provided"
            )
        ci_content = ci_envelope.get("content")
        if not isinstance(ci_content, str) or "${LPM_TOKEN}" not in ci_content:
            raise SmokeFailure(
                "install/setup ci json: expected JSON envelope content to use the literal ${LPM_TOKEN} placeholder"
            )
        ci_npmrc = (ci_project_path / ".npmrc").read_text(encoding="utf-8")
        if "@lpm.dev:registry=" not in ci_npmrc:
            raise SmokeFailure(
                "install/setup ci .npmrc: expected scoped registry config"
            )
        if "lpm_ci_smoke_token" not in ci_npmrc:
            raise SmokeFailure(
                "install/setup ci .npmrc: expected the provided LPM_TOKEN to be written into the on-disk file"
            )

        local_result = run_command_result(
            "install/setup local json",
            local_project_path,
            [
                str(LPM_BIN),
                "--registry",
                registry_base,
                "--insecure",
                "--json",
                "setup",
                "local",
                "--days",
                "7",
            ],
            extra_env=scenario_env,
        )
        if local_result.returncode != 0:
            raise SmokeFailure(
                f"install/setup local json failed with exit code {local_result.returncode}"
            )
        local_envelope = json.loads(local_result.stdout)
        if local_envelope.get("success") is not True:
            raise SmokeFailure("install/setup local json: expected success=true")
        if local_envelope.get("expiry_days") != 7:
            raise SmokeFailure("install/setup local json: expected expiry_days=7")
        if local_envelope.get("expires_at") != token_response["expiresAt"]:
            raise SmokeFailure(
                "install/setup local json: expected expires_at to match the mock token response"
            )
        if local_envelope.get("gitignore_updated") is not True:
            raise SmokeFailure(
                "install/setup local json: expected gitignore_updated=true"
            )

        local_npmrc = (local_project_path / ".npmrc").read_text(encoding="utf-8")
        if "generated by lpm setup local" not in local_npmrc:
            raise SmokeFailure(
                "install/setup local .npmrc: expected the generated comment to name the renamed command"
            )
        if token_response["token"] not in local_npmrc:
            raise SmokeFailure(
                "install/setup local .npmrc: expected the issued read-only token to be written"
            )
        if (local_project_path / ".gitignore").read_text(encoding="utf-8") != ".npmrc\n":
            raise SmokeFailure(
                "install/setup local .gitignore: expected .npmrc to be auto-added"
            )

        request_paths = registry.requested_paths()
        if request_paths.count("/api/registry/-/token/create") != 1:
            raise SmokeFailure(
                "install/setup local json: expected exactly one token-create request"
            )


def scenario_install_auth_commands() -> None:
    def credentials_path(home: str) -> Path:
        return Path(home) / ".lpm" / ".credentials"

    def write_publish_package(project_path: Path, package_name: str) -> None:
        project_path.joinpath("package.json").write_text(
            json.dumps(
                {
                    "name": package_name,
                    "version": "1.0.0",
                    "description": "Publish auth smoke",
                    "main": "index.js",
                    "license": "MIT",
                }
            )
            + "\n",
            encoding="utf-8",
        )

    common_auth_env = {
        "LPM_FORCE_FILE_AUTH": "1",
        "LPM_TEST_FAST_SCRYPT": "1",
        "LPM_DISABLE_HOST_CLI_AUTH": "0",
    }

    with tempfile.TemporaryDirectory(prefix="lpm-auth-fake-bin-") as fake_bin_dir:
        fake_bin = Path(fake_bin_dir)
        empty_bin = fake_bin / "empty"
        empty_bin.mkdir(parents=True, exist_ok=True)

        write_executable(
            fake_bin / "gh",
            "#!/bin/sh\n"
            "if [ \"$1\" = auth ] && [ \"$2\" = token ]; then\n"
            "  printf 'gh-cli-token\\n'\n"
            "  exit 0\n"
            "fi\n"
            "exit 1\n",
        )

        with tempfile.TemporaryDirectory(prefix="lpm-auth-gh-home-") as gh_home, tempfile.TemporaryDirectory(
            prefix="lpm-auth-gh-project-"
        ) as gh_project:
            gh_result = run_command_result(
                "install/auth github host-cli login json",
                Path(gh_project),
                [str(LPM_BIN), "--json", "login", "--github"],
                extra_env={
                    **common_auth_env,
                    "LPM_HOME": gh_home,
                    "PATH": os.pathsep.join([str(fake_bin), os.environ.get("PATH", "")]),
                },
            )
            if gh_result.returncode != 0:
                raise SmokeFailure(
                    f"install/auth github host-cli login json failed with exit code {gh_result.returncode}"
                )
            gh_envelope = json.loads(gh_result.stdout)
            if gh_envelope.get("success") is not True:
                raise SmokeFailure(
                    "install/auth github host-cli login json: expected success=true"
                )
            if gh_envelope.get("source") != "gh":
                raise SmokeFailure(
                    "install/auth github host-cli login json: expected source='gh'"
                )
            if gh_envelope.get("stored") is not False:
                raise SmokeFailure(
                    "install/auth github host-cli login json: expected stored=false"
                )
            if credentials_path(gh_home).exists():
                raise SmokeFailure(
                    "install/auth github host-cli login json: expected gh-backed login to avoid creating ~/.lpm/.credentials"
                )

        with tempfile.TemporaryDirectory(prefix="lpm-auth-npm-home-") as npm_home, tempfile.TemporaryDirectory(
            prefix="lpm-auth-npm-project-"
        ) as npm_project:
            npm_result = run_command_result(
                "install/auth npm env login json",
                Path(npm_project),
                [str(LPM_BIN), "--json", "login", "--npm"],
                extra_env={
                    **common_auth_env,
                    "LPM_HOME": npm_home,
                    "NPM_TOKEN": "npm-env-token",
                },
            )
            if npm_result.returncode != 0:
                raise SmokeFailure(
                    f"install/auth npm env login json failed with exit code {npm_result.returncode}"
                )
            npm_envelope = json.loads(npm_result.stdout)
            if npm_envelope.get("success") is not True:
                raise SmokeFailure(
                    "install/auth npm env login json: expected success=true"
                )
            if npm_envelope.get("source") != "env:NPM_TOKEN":
                raise SmokeFailure(
                    "install/auth npm env login json: expected source='env:NPM_TOKEN'"
                )
            if npm_envelope.get("stored") is not True:
                raise SmokeFailure(
                    "install/auth npm env login json: expected stored=true"
                )
            if not credentials_path(npm_home).exists():
                raise SmokeFailure(
                    "install/auth npm env login json: expected npm env-token login to create ~/.lpm/.credentials"
                )

        with tempfile.TemporaryDirectory(prefix="lpm-auth-gitlab-home-") as gitlab_home, tempfile.TemporaryDirectory(
            prefix="lpm-auth-gitlab-project-"
        ) as gitlab_project:
            gitlab_result = run_command_result(
                "install/auth gitlab explicit-token login json",
                Path(gitlab_project),
                [
                    str(LPM_BIN),
                    "--json",
                    "login",
                    "--gitlab",
                    "--token",
                    "gitlab-fallback-token",
                ],
                extra_env={
                    **common_auth_env,
                    "LPM_HOME": gitlab_home,
                },
            )
            if gitlab_result.returncode != 0:
                raise SmokeFailure(
                    f"install/auth gitlab explicit-token login json failed with exit code {gitlab_result.returncode}"
                )
            gitlab_envelope = json.loads(gitlab_result.stdout)
            if gitlab_envelope.get("success") is not True:
                raise SmokeFailure(
                    "install/auth gitlab explicit-token login json: expected success=true"
                )
            if gitlab_envelope.get("source") != "explicit-token":
                raise SmokeFailure(
                    "install/auth gitlab explicit-token login json: expected source='explicit-token'"
                )
            if gitlab_envelope.get("stored") is not True:
                raise SmokeFailure(
                    "install/auth gitlab explicit-token login json: expected stored=true"
                )
            if not credentials_path(gitlab_home).exists():
                raise SmokeFailure(
                    "install/auth gitlab explicit-token login json: expected explicit GitLab login to create ~/.lpm/.credentials"
                )

        with tempfile.TemporaryDirectory(prefix="lpm-publish-auth-home-") as publish_home, tempfile.TemporaryDirectory(
            prefix="lpm-publish-auth-project-"
        ) as publish_project:
            publish_project_path = Path(publish_project)
            write_publish_package(publish_project_path, "publish-auth-smoke")
            publish_project_path.joinpath("index.js").write_text(
                "module.exports = {}\n", encoding="utf-8"
            )

            hermetic_publish_env = {
                **common_auth_env,
                "LPM_HOME": publish_home,
                "PATH": str(empty_bin),
            }

            npm_publish_output = run_command_expect_failure(
                "install/auth publish npm missing auth",
                publish_project_path,
                [str(LPM_BIN), "publish", "--yes", "--npm"],
                extra_env=hermetic_publish_env,
            )
            require_contains(
                npm_publish_output,
                "lpm login --npm",
                "install/auth publish npm missing auth guidance",
            )
            require_contains(
                npm_publish_output,
                "NPM_TOKEN",
                "install/auth publish npm missing auth env guidance",
            )

            write_publish_package(publish_project_path, "@smoke/publish-auth-smoke")

            github_publish_output = run_command_expect_failure(
                "install/auth publish github missing auth",
                publish_project_path,
                [str(LPM_BIN), "publish", "--yes", "--github"],
                extra_env=hermetic_publish_env,
            )
            require_contains(
                github_publish_output,
                "gh auth login",
                "install/auth publish github missing auth gh guidance",
            )
            require_contains(
                github_publish_output,
                "GITHUB_TOKEN",
                "install/auth publish github missing auth env guidance",
            )

            publish_project_path.joinpath("lpm.json").write_text(
                json.dumps({"publish": {"gitlab": {"projectId": "12345"}}}) + "\n",
                encoding="utf-8",
            )
            gitlab_publish_output = run_command_expect_failure(
                "install/auth publish gitlab missing auth",
                publish_project_path,
                [str(LPM_BIN), "publish", "--yes", "--gitlab"],
                extra_env=hermetic_publish_env,
            )
            require_contains(
                gitlab_publish_output,
                "glab auth login",
                "install/auth publish gitlab missing auth glab guidance",
            )
            require_contains(
                gitlab_publish_output,
                "GITLAB_TOKEN/CI_JOB_TOKEN",
                "install/auth publish gitlab missing auth env guidance",
            )


def scenario_install_bun_runtime() -> None:
    minimal_shell_path = os.pathsep.join(["/usr/bin", "/bin", "/usr/sbin", "/sbin"])

    def write_package(
        project_path: Path,
        *,
        package_name: str,
        scripts: dict[str, str] | None = None,
        engines: dict[str, str] | None = None,
    ) -> None:
        package_json: dict[str, object] = {
            "name": package_name,
            "version": "1.0.0",
            "private": True,
        }
        if scripts:
            package_json["scripts"] = scripts
        if engines:
            package_json["engines"] = engines
        project_path.joinpath("package.json").write_text(
            json.dumps(package_json) + "\n", encoding="utf-8"
        )

    def seed_path_executable(
        bin_dir: Path,
        name: str,
        output: str,
        *,
        log_path: Path | None = None,
    ) -> None:
        lines = ["#!/bin/sh"]
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            lines.append(f"printf '%s\\n' {json.dumps(name)} >> {json.dumps(str(log_path))}")
        lines.append(f"printf '%s\\n' {json.dumps(output)}")
        write_executable(bin_dir / name, "\n".join(lines) + "\n")

    def managed_runtime_bin(home: str, runtime: str, version: str) -> Path:
        return Path(home) / "runtimes" / runtime / version / "bin"

    def seed_managed_runtime_executable(
        home: str,
        runtime: str,
        version: str,
        name: str,
        output: str,
        *,
        log_path: Path | None = None,
    ) -> None:
        seed_path_executable(
            managed_runtime_bin(home, runtime, version),
            name,
            output,
            log_path=log_path,
        )

    with tempfile.TemporaryDirectory(prefix="lpm-bun-use-home-") as lpm_home, tempfile.TemporaryDirectory(
        prefix="lpm-bun-use-project-"
    ) as project_dir:
        project_path = Path(project_dir)
        write_package(project_path, package_name="bun-use-smoke")
        seed_managed_runtime_executable(lpm_home, "bun", "1.3.14", "bun", "managed-bun-1.3.14")
        seed_managed_runtime_executable(lpm_home, "bun", "1.3.9", "bun", "managed-bun-1.3.9")
        seed_managed_runtime_executable(lpm_home, "bun", "1.2.23", "bun", "managed-bun-1.2.23")

        use_env = {"LPM_HOME": lpm_home, "PATH": minimal_shell_path}

        list_result = run_command_result(
            "install/bun-runtime use list bun json",
            project_path,
            [str(LPM_BIN), "--json", "use", "--list", "bun"],
            extra_env=use_env,
        )
        if list_result.returncode != 0:
            raise SmokeFailure(
                f"install/bun-runtime use list bun json failed with exit code {list_result.returncode}"
            )
        list_envelope = json.loads(list_result.stdout)
        if list_envelope.get("success") is not True:
            raise SmokeFailure("install/bun-runtime use list bun json: expected success=true")
        if list_envelope.get("runtime") != "bun":
            raise SmokeFailure("install/bun-runtime use list bun json: expected runtime=bun")
        if list_envelope.get("versions") != ["1.3.14", "1.3.9", "1.2.23"]:
            raise SmokeFailure(
                "install/bun-runtime use list bun json: expected descending managed Bun versions"
            )

        pin_result = run_command_result(
            "install/bun-runtime use pin bun major-minor",
            project_path,
            [str(LPM_BIN), "use", "bun@1.3", "--pin"],
            extra_env=use_env,
        )
        if pin_result.returncode != 0:
            raise SmokeFailure(
                f"install/bun-runtime use pin bun major-minor failed with exit code {pin_result.returncode}"
            )
        require_contains(
            pin_result.stderr,
            "Pinned bun@1.3.14 in lpm.json",
            "install/bun-runtime use pin bun major-minor stderr",
        )
        pinned_lpm_json = json.loads(project_path.joinpath("lpm.json").read_text(encoding="utf-8"))
        if pinned_lpm_json.get("runtime", {}).get("bun") != "1.3.14":
            raise SmokeFailure(
                "install/bun-runtime use pin bun major-minor: expected lpm.json runtime.bun=1.3.14"
            )

        lts_output = run_command_expect_failure(
            "install/bun-runtime use bun lts rejected",
            project_path,
            [str(LPM_BIN), "use", "bun@lts", "--pin"],
            extra_env=use_env,
        )
        require_contains(
            lts_output,
            "Bun does not publish an LTS channel",
            "install/bun-runtime use bun lts rejected",
        )

        remove_result = run_command_result(
            "install/bun-runtime use remove bun major-minor",
            project_path,
            [str(LPM_BIN), "use", "remove", "bun@1.3"],
            extra_env=use_env,
        )
        if remove_result.returncode != 0:
            raise SmokeFailure(
                f"install/bun-runtime use remove bun major-minor failed with exit code {remove_result.returncode}"
            )
        require_contains(
            remove_result.stderr,
            "Removed 2 Bun versions",
            "install/bun-runtime use remove bun major-minor stderr",
        )
        require_contains(
            remove_result.stderr,
            "lpm.json still pins bun@1.3.14",
            "install/bun-runtime use remove bun major-minor pin warning",
        )
        if managed_runtime_bin(lpm_home, "bun", "1.3.14").parent.exists():
            raise SmokeFailure(
                "install/bun-runtime use remove bun major-minor: expected 1.3.14 managed Bun to be removed"
            )
        if managed_runtime_bin(lpm_home, "bun", "1.3.9").parent.exists():
            raise SmokeFailure(
                "install/bun-runtime use remove bun major-minor: expected 1.3.9 managed Bun to be removed"
            )
        if not managed_runtime_bin(lpm_home, "bun", "1.2.23").parent.exists():
            raise SmokeFailure(
                "install/bun-runtime use remove bun major-minor: expected 1.2.23 managed Bun to remain installed"
            )

    with tempfile.TemporaryDirectory(prefix="lpm-bun-engines-home-") as lpm_home, tempfile.TemporaryDirectory(
        prefix="lpm-bun-engines-project-"
    ) as project_dir, tempfile.TemporaryDirectory(prefix="lpm-bun-engines-path-") as system_bin_dir:
        project_path = Path(project_dir)
        system_bin = Path(system_bin_dir)
        write_package(
            project_path,
            package_name="bun-engines-smoke",
            scripts={"show-bun": "bun"},
            engines={"bun": ">=1.0.0"},
        )
        seed_managed_runtime_executable(
            lpm_home,
            "bun",
            "1.3.14",
            "bun",
            "managed-bun-from-lpm-json-only",
        )
        seed_path_executable(system_bin, "bun", "system-bun-from-path")

        engines_env = {
            "LPM_HOME": lpm_home,
            "PATH": os.pathsep.join([str(system_bin), minimal_shell_path]),
        }

        engines_run = run_command_result(
            "install/bun-runtime engines bun ignored run",
            project_path,
            [str(LPM_BIN), "run", "show-bun"],
            extra_env=engines_env,
        )
        if engines_run.returncode != 0:
            raise SmokeFailure(
                f"install/bun-runtime engines bun ignored run failed with exit code {engines_run.returncode}"
            )
        require_contains(
            engines_run.stdout,
            "system-bun-from-path",
            "install/bun-runtime engines bun ignored stdout",
        )
        require_not_contains(
            engines_run.stdout,
            "managed-bun-from-lpm-json-only",
            "install/bun-runtime engines bun ignored stdout",
        )
        require_not_contains(
            engines_run.stderr,
            "Using bun",
            "install/bun-runtime engines bun ignored stderr",
        )

        with MockRegistry([]) as registry:
            doctor_all = run_command_result(
                "install/bun-runtime engines bun doctor all json",
                project_path,
                [
                    str(LPM_BIN),
                    "--registry",
                    registry.registry_url,
                    "--insecure",
                    "doctor",
                    "--all",
                    "--json",
                ],
                extra_env=engines_env,
            )
            if doctor_all.returncode not in {0, 1}:
                raise SmokeFailure(
                    f"install/bun-runtime engines bun doctor all json failed with exit code {doctor_all.returncode}"
                )
            doctor_envelope = json.loads(doctor_all.stdout)
            if doctor_envelope.get("success") is not True:
                raise SmokeFailure(
                    "install/bun-runtime engines bun doctor all json: expected success=true envelope"
                )
            all_codes = {check.get("code") for check in doctor_envelope.get("checks", [])}
            if "engines_bun_ignored" not in all_codes:
                raise SmokeFailure(
                    "install/bun-runtime engines bun doctor all json: expected engines_bun_ignored"
                )
            for unexpected_code in {"bun_managed_match", "bun_pinned_unmet", "bun_missing_pinned"}:
                if unexpected_code in all_codes:
                    raise SmokeFailure(
                        f"install/bun-runtime engines bun doctor all json: did not expect {unexpected_code} without runtime.bun"
                    )
            if registry.requested_paths() != ["/api/registry/health"]:
                raise SmokeFailure(
                    "install/bun-runtime engines bun doctor all json: expected only the health probe under --all"
                )

    with tempfile.TemporaryDirectory(prefix="lpm-bun-managed-home-") as lpm_home, tempfile.TemporaryDirectory(
        prefix="lpm-bun-managed-project-"
    ) as project_dir:
        project_path = Path(project_dir)
        bun_invocation_log = Path(lpm_home) / "bun-invocations.log"
        write_package(
            project_path,
            package_name="bun-managed-smoke",
            scripts={
                "show-order": "shared && node && bun",
                "shell-runner": "printf 'runner-stays-shell\\n'",
            },
        )
        project_path.joinpath("lpm.json").write_text(
            json.dumps({"runtime": {"node": "22.12.0", "bun": "1.3.14"}}) + "\n",
            encoding="utf-8",
        )
        seed_managed_runtime_executable(lpm_home, "node", "22.12.0", "node", "managed-node-22.12.0")
        seed_managed_runtime_executable(lpm_home, "node", "22.12.0", "shared", "node-shared")
        seed_managed_runtime_executable(
            lpm_home,
            "bun",
            "1.3.14",
            "bun",
            "managed-bun-1.3.14",
            log_path=bun_invocation_log,
        )
        seed_managed_runtime_executable(lpm_home, "bun", "1.3.14", "shared", "bun-shared")

        managed_env = {"LPM_HOME": lpm_home, "PATH": minimal_shell_path}

        show_order = run_command_result(
            "install/bun-runtime managed path order run",
            project_path,
            [str(LPM_BIN), "run", "show-order"],
            extra_env=managed_env,
        )
        if show_order.returncode != 0:
            raise SmokeFailure(
                f"install/bun-runtime managed path order run failed with exit code {show_order.returncode}"
            )
        show_order_lines = [line.strip() for line in show_order.stdout.splitlines() if line.strip()]
        if show_order_lines != ["node-shared", "managed-node-22.12.0", "managed-bun-1.3.14"]:
            raise SmokeFailure(
                "install/bun-runtime managed path order run: expected node helper first, then managed node, then managed bun"
            )
        require_contains(
            show_order.stderr,
            "Using node 22.12.0",
            "install/bun-runtime managed path order stderr",
        )
        require_contains(
            show_order.stderr,
            "Using bun 1.3.14",
            "install/bun-runtime managed path order stderr",
        )

        doctor_fast = run_command_result(
            "install/bun-runtime managed doctor fast json",
            project_path,
            [str(LPM_BIN), "doctor", "--json"],
            extra_env=managed_env,
        )
        if doctor_fast.returncode not in {0, 1}:
            raise SmokeFailure(
                f"install/bun-runtime managed doctor fast json failed with exit code {doctor_fast.returncode}"
            )
        doctor_fast_envelope = json.loads(doctor_fast.stdout)
        if doctor_fast_envelope.get("success") is not True:
            raise SmokeFailure(
                "install/bun-runtime managed doctor fast json: expected success=true envelope"
            )
        doctor_fast_codes = {
            check.get("code") for check in doctor_fast_envelope.get("checks", [])
        }
        if "bun_managed_match" not in doctor_fast_codes:
            raise SmokeFailure(
                "install/bun-runtime managed doctor fast json: expected bun_managed_match"
            )
        if "lpm_json_schema_warnings" in doctor_fast_codes:
            raise SmokeFailure(
                "install/bun-runtime managed doctor fast json: did not expect stale lpm.json runtime.bun schema warnings"
            )

        if bun_invocation_log.exists():
            bun_invocations_before = bun_invocation_log.read_text(encoding="utf-8").splitlines()
        else:
            bun_invocations_before = []
        if not bun_invocations_before:
            raise SmokeFailure(
                "install/bun-runtime managed path order run: expected at least one explicit bun invocation"
            )

        shell_runner = run_command_result(
            "install/bun-runtime managed shell runner stays lpm",
            project_path,
            [str(LPM_BIN), "run", "shell-runner"],
            extra_env=managed_env,
        )
        if shell_runner.returncode != 0:
            raise SmokeFailure(
                f"install/bun-runtime managed shell runner stays lpm failed with exit code {shell_runner.returncode}"
            )
        require_contains(
            shell_runner.stdout,
            "runner-stays-shell",
            "install/bun-runtime managed shell runner stdout",
        )
        bun_invocations_after = bun_invocation_log.read_text(encoding="utf-8").splitlines()
        if bun_invocations_after != bun_invocations_before:
            raise SmokeFailure(
                "install/bun-runtime managed shell runner: runtime.bun should not make lpm run invoke bun run"
            )

    with tempfile.TemporaryDirectory(prefix="lpm-bun-noauto-home-") as lpm_home, tempfile.TemporaryDirectory(
        prefix="lpm-bun-noauto-project-"
    ) as project_dir, tempfile.TemporaryDirectory(prefix="lpm-bun-noauto-path-") as system_bin_dir:
        project_path = Path(project_dir)
        system_bin = Path(system_bin_dir)
        write_package(
            project_path,
            package_name="bun-no-auto-smoke",
            scripts={"show-bun": "bun"},
        )
        project_path.joinpath("lpm.json").write_text(
            json.dumps({"runtime": {"bun": "1.3.14"}}) + "\n",
            encoding="utf-8",
        )
        seed_path_executable(system_bin, "bun", "system-bun-fallback")

        no_auto_env = {
            "LPM_HOME": lpm_home,
            "LPM_NO_AUTO_INSTALL": "true",
            "PATH": os.pathsep.join([str(system_bin), minimal_shell_path]),
        }

        no_auto_run = run_command_result(
            "install/bun-runtime no-auto-install fallback run",
            project_path,
            [str(LPM_BIN), "run", "show-bun"],
            extra_env=no_auto_env,
        )
        if no_auto_run.returncode != 0:
            raise SmokeFailure(
                f"install/bun-runtime no-auto-install fallback run failed with exit code {no_auto_run.returncode}"
            )
        require_contains(
            no_auto_run.stdout,
            "system-bun-fallback",
            "install/bun-runtime no-auto-install fallback stdout",
        )
        require_contains(
            no_auto_run.stderr,
            "lpm.json requires bun 1.3.14, but it's not installed. Using system bun.",
            "install/bun-runtime no-auto-install fallback stderr",
        )
        require_contains(
            no_auto_run.stderr,
            "lpm use bun@1.3.14",
            "install/bun-runtime no-auto-install fallback guidance",
        )

        no_auto_doctor = run_command_result(
            "install/bun-runtime no-auto-install doctor fast json",
            project_path,
            [str(LPM_BIN), "doctor", "--json"],
            extra_env=no_auto_env,
        )
        if no_auto_doctor.returncode not in {0, 1}:
            raise SmokeFailure(
                f"install/bun-runtime no-auto-install doctor fast json failed with exit code {no_auto_doctor.returncode}"
            )
        no_auto_envelope = json.loads(no_auto_doctor.stdout)
        if no_auto_envelope.get("success") is not True:
            raise SmokeFailure(
                "install/bun-runtime no-auto-install doctor fast json: expected success=true envelope"
            )
        no_auto_codes = {
            check.get("code") for check in no_auto_envelope.get("checks", [])
        }
        if "bun_pinned_unmet" not in no_auto_codes:
            raise SmokeFailure(
                "install/bun-runtime no-auto-install doctor fast json: expected bun_pinned_unmet"
            )
        if "bun_managed_match" in no_auto_codes:
            raise SmokeFailure(
                "install/bun-runtime no-auto-install doctor fast json: did not expect bun_managed_match without a managed Bun install"
            )


def scenario_install_global_install() -> None:
    shared_bin = "smoke-global"
    alias_bin = "smoke-global-beta"
    registry_packages = [
        {
            "name": "smoke-global-alpha",
            "dist_tags": {"latest": "1.0.0"},
            "versions": {
                "1.0.0": {
                    "metadata_extra": {
                        "bin": {shared_bin: "bin/cli.js"},
                        "dependencies": {},
                    },
                    "package_json_extra": {
                        "bin": {shared_bin: "bin/cli.js"},
                    },
                    "files": {
                        "bin/cli.js": "#!/usr/bin/env node\nprocess.stdout.write('alpha\\n')\n",
                    },
                }
            },
        },
        {
            "name": "smoke-global-beta",
            "dist_tags": {"latest": "1.0.0"},
            "versions": {
                "1.0.0": {
                    "metadata_extra": {
                        "bin": {shared_bin: "bin/cli.js"},
                        "dependencies": {},
                    },
                    "package_json_extra": {
                        "bin": {shared_bin: "bin/cli.js"},
                    },
                    "files": {
                        "bin/cli.js": "#!/usr/bin/env node\nprocess.stdout.write('beta\\n')\n",
                    },
                }
            },
        },
    ]

    with MockRegistry(registry_packages) as registry, tempfile.TemporaryDirectory(
        prefix="lpm-smoke-home-"
    ) as lpm_home:
        registry_args = ["--registry", registry.registry_url, "--insecure"]
        registry_env = {"LPM_HOME": lpm_home, "LPM_NPM_ROUTE": "proxy"}
        install_flags = [
            "--no-skills",
            "--no-editor-setup",
        ]
        fixture = reset_global_install_fixture("basic")
        baseline_package_json = (fixture / "package.json").read_text(encoding="utf-8")

        run_command(
            "install/global-install initial package",
            fixture,
            [
                str(LPM_BIN),
                *registry_args,
                "install",
                "-g",
                "smoke-global-alpha@1.0.0",
                *install_flags,
            ],
            extra_env=registry_env,
        )

        if (fixture / "package.json").read_text(encoding="utf-8") != baseline_package_json:
            raise SmokeFailure("install/global-install initial package: expected fixture package.json to stay unchanged")

        require_exists(Path(lpm_home) / "global" / "manifest.toml")
        require_exists(Path(lpm_home) / "global" / "installs" / "smoke-global-alpha@1.0.0")

        alpha_shim = resolve_global_shim_path(lpm_home, shared_bin)
        require_exists(alpha_shim)
        require_contains(
            run_command(
                "install/global-install initial shim output",
                fixture,
                [str(alpha_shim)],
            ),
            "alpha",
            "install/global-install initial shim output",
        )

        manifest_after_alpha = read_optional_text(Path(lpm_home) / "global" / "manifest.toml")
        require_contains(
            manifest_after_alpha,
            "smoke-global-alpha",
            "install/global-install manifest after initial install",
        )

        collision_output = run_command_expect_failure(
            "install/global-install collision hint",
            fixture,
            [
                str(LPM_BIN),
                *registry_args,
                "install",
                "-g",
                "smoke-global-beta@1.0.0",
                *install_flags,
            ],
            extra_env=registry_env,
        )
        require_contains(collision_output, "--replace-bin", "install/global-install collision output")
        require_contains(collision_output, "--alias", "install/global-install collision output")
        require_not_contains(
            read_optional_text(Path(lpm_home) / "global" / "manifest.toml"),
            "smoke-global-beta",
            "install/global-install manifest after collision",
        )

        run_command(
            "install/global-install alias success",
            fixture,
            [
                str(LPM_BIN),
                *registry_args,
                "install",
                "-g",
                "smoke-global-beta@1.0.0",
                "--alias",
                f"{shared_bin}={alias_bin}",
                *install_flags,
            ],
            extra_env=registry_env,
        )

        if (fixture / "package.json").read_text(encoding="utf-8") != baseline_package_json:
            raise SmokeFailure("install/global-install alias success: expected fixture package.json to stay unchanged")

        beta_shim = resolve_global_shim_path(lpm_home, alias_bin)
        require_exists(beta_shim)
        require_contains(
            run_command(
                "install/global-install alias shim output",
                fixture,
                [str(beta_shim)],
            ),
            "beta",
            "install/global-install alias shim output",
        )
        require_contains(
            run_command(
                "install/global-install original shim still owned",
                fixture,
                [str(alpha_shim)],
            ),
            "alpha",
            "install/global-install original shim output",
        )
        require_contains(
            read_optional_text(Path(lpm_home) / "global" / "manifest.toml"),
            "smoke-global-beta",
            "install/global-install manifest after alias install",
        )


SCENARIOS = {
    "install-trust": (
        "Run lpm trust coverage for guarded approval refusal plus diff/prune behavior over direct manifest-and-snapshot drift.",
        scenario_install_trust_command,
    ),
    "install-rebuild": (
        "Run lpm rebuild coverage for guarded trust approval refusal plus deny-mode skip messaging with no script execution.",
        scenario_install_rebuild_command,
    ),
    "install-patch": (
        "Run lpm patch, patch-commit, and patch-remove coverage for lockfile resolution, patch file generation, dry-run and keep-file removal, reinstall refresh behavior, pristine re-extracts, and no-change aborts.",
        scenario_install_patch_command,
    ),
    "install-patch-scoped": (
        "Run scoped-package lpm patch and patch-commit coverage for sanitized patch filenames, manifest selector preservation, and reinstall auto-apply.",
        scenario_install_patch_scoped_command,
    ),
    "install-patch-binary": (
        "Run lpm patch-commit binary-edit rejection coverage and prove the failed commit writes neither a patch file nor a manifest mutation.",
        scenario_install_patch_binary_command,
    ),
    "install-hidden-scripts": (
        "Run hidden package.json script coverage for direct rejection, omission from missing-script suggestions, nested invocation from visible scripts, and lpm.json dependsOn allowance.",
        scenario_install_hidden_scripts,
    ),
    "install-sbom": (
        "Run lpm sbom coverage for default CycloneDX output, SPDX output, offline local-first behavior, registry metadata enrichment, output-file writes, dependency edges, and patch metadata.",
        scenario_install_sbom_command,
    ),
    "install-download": (
        "Run lpm download coverage for JSON output, canonical output paths, stripped extraction layout, and read-only no-install side effects.",
        scenario_install_download_command,
    ),
    "install-resolve": (
        "Run lpm resolve coverage for multi-spec JSON output, scoped last-@ parsing, metadata-only routing, and read-only no-download behavior.",
        scenario_install_resolve_command,
    ),
    "install-remote-cache": (
        "Run hosted remote-cache coverage for cache-status JSON, team-scoped remote hits, signature fallback, read-only and forbidden-upload degradation, remoteCache.env policy overrides, secret-env upload blocking, and the LPM_REMOTE_CACHE=0 override.",
        scenario_install_remote_cache,
    ),
    "install-cache": (
        "Run lpm cache coverage for path output, metadata-path JSON, clear alias semantics, blanket clean JSON, and store/cache separation.",
        scenario_install_cache_command,
    ),
    "install-cache-prune": (
        "Run lpm cache prune coverage for missing-registry and corrupt-registry degraded modes plus manual-repair --project pruning with --max-age and --apply.",
        scenario_install_cache_prune,
    ),
    "install-store": (
        "Run lpm store coverage for path output, fast-vs-deep verify semantics, --fix security-cache refreshes, and full v1+v2 store wipes.",
        scenario_install_store_command,
    ),
    "install-graph": (
        "Run lpm graph coverage for resolved tree output, substring filtering, graph-level depth pruning across json/stats/html, and the --no-open warning contract.",
        scenario_install_graph_command,
    ),
    "install-pack": (
        "Run lpm pack smoke coverage for missing-tsdown fail-fast behavior, project-local tsdown resolution, and single-package stdout passthrough with forwarded pack flags.",
        scenario_install_pack_command,
    ),
    "install-dev": (
        "Run lpm dev coverage for .env.example bootstrap, env-schema validation vs --no-env-check, explicit --env layering, hermetic HTTPS consent/bootstrap, tunnel inspector/no-inspect/strict inspect-port behavior, single-service arg forwarding, and multi-service dependsOn orchestration.",
        scenario_install_dev_command,
    ),
    "install-env": (
        "Run lpm env coverage for required-secret gating, preview-scoped writes, env ls schema counts, and lpm run task injection through named-environment file inheritance.",
        scenario_install_env_command,
    ),
    "install-tunnel": (
        "Run lpm tunnel coverage for auth-gated relay actions plus local inspect/log/replay behavior from the on-disk webhook log.",
        scenario_install_tunnel_command,
    ),
    "install-ports": (
        "Run lpm ports coverage for declared-port listing, missing-port kill failures, live owner termination, and per-project ports.toml reset semantics.",
        scenario_install_ports_command,
    ),
    "install-cert": (
        "Run lpm cert coverage for absent status, isolated trust-store install/uninstall, generate --host SAN refreshes, and human status output.",
        scenario_install_cert_command,
    ),
    "install-doctor": (
        "Run lpm doctor coverage for fast-vs-all presets, live doctor-list filters, and fast --fix staying local-only while regenerating lpm.lockb.",
        scenario_install_doctor_command,
    ),
    "install-health": (
        "Run lpm health coverage for healthy JSON output, single health-endpoint probing, and unreachable-registry non-zero exits.",
        scenario_install_health_command,
    ),
    "install-setup": (
        "Run lpm setup ci/local coverage for renamed command parsing, CI .npmrc generation, and local read-only token setup.",
        scenario_install_setup_commands,
    ),
    "install-auth": (
        "Run third-party login fallback coverage plus missing-auth publish guidance for npm, GitHub Packages, and GitLab Packages.",
        scenario_install_auth_commands,
    ),
    "install-bun-runtime": (
        "Run managed Bun runtime coverage for use/list/remove/pin, lpm.json-only Bun detection, PATH ordering after Node, doctor runtime codes, and LPM_NO_AUTO_INSTALL fallback semantics.",
        scenario_install_bun_runtime,
    ),
    "install-migrate-npm": (
        "Run lpm migrate npm coverage for dry-run no-write behavior, non-destructive backup creation, default .npmrc setup, and rollback cleanup.",
        scenario_install_migrate_npm,
    ),
    "install-migrate-pnpm": (
        "Run lpm migrate pnpm coverage for override translation into lpm.overrides while preserving pnpm.overrides and skipping install side effects.",
        scenario_install_migrate_pnpm,
    ),
    "install-migrate-pnpm-patches": (
        "Run lpm migrate pnpm patchedDependencies coverage for canonical patch translation, originalIntegrity binding, preserved pnpm.patchedDependencies, and no-install side effects.",
        scenario_install_migrate_pnpm_patches,
    ),
    "install-migrate-bun": (
        "Run lpm migrate bun coverage for Bun lockfile detection, LPM lockfile emission, and --no-install/--no-npmrc no-side-effect behavior.",
        scenario_install_migrate_bun,
    ),
    "install-migrate-yarn": (
        "Run lpm migrate yarn coverage for Yarn v1 lock detection, lockfile emission, mixed dependency conversion, and --no-install/--no-npmrc no-side-effect behavior.",
        scenario_install_migrate_yarn,
    ),
    "install-audit": (
        "Run lpm audit coverage for default informational high behaviors, behavior fail-on, and secret-scan gating.",
        scenario_install_audit_command,
    ),
    "install-query": (
        "Run lpm query coverage for selectors, assert-none gating, count mode, and Mermaid output on an LPM-managed project.",
        scenario_install_query_command,
    ),
    "install-approve-scripts": (
        "Run lpm approve-scripts coverage for blocked-set listing, dry-run preview, and guarded named approval refusal.",
        scenario_install_approve_scripts_command,
    ),
    "install-security": (
        "Run lpm security coverage for status output, guarded config writes, guarded repo proposals, audit records, and optional native unlock success.",
        scenario_install_security,
    ),
    "install-read-only-routing": (
        "Run info, resolve, search, and download against a project-local .npmrc registry without the proxy metadata path.",
        scenario_install_read_only_routing,
    ),
    "install-outdated": (
        "Run outdated coverage for dependencies plus devDependencies, resolved wanted versions, and the human-readable table.",
        scenario_install_outdated,
    ),
    "install-outdated-skipped-private": (
        "Run outdated and upgrade dry-run coverage for internal-registry packages that must be skipped without registry leakage.",
        scenario_install_outdated_skipped_private,
    ),
    "install-global-install": (
        "Run global install coverage for manifest writes, shims, collision hints, and alias success.",
        scenario_install_global_install,
    ),
    "install-upgrade": (
        "Run npm upgrade coverage for public-npm lockfile sources through dry-run discovery and real upgrade application.",
        scenario_install_upgrade,
    ),
    "install-uninstall-global": (
        "Run global uninstall coverage for lpm uninstall -g manifest, install-dir, and shim cleanup.",
        scenario_install_uninstall_global,
    ),
    "install-audit-after-install": (
        "Run audit-after-install coverage for default off, precedence, JSON output, and informational failure handling.",
        scenario_install_audit_after_install,
    ),
    "install-minimum-release-age": (
        "Run recent-publish cooldown coverage for default blocking, guarded CLI and package weakeners, and explicit pins.",
        scenario_install_minimum_release_age,
    ),
    "install-offline-integrity": (
        "Run tarball URL strict-integrity checks plus warm-store offline relink coverage.",
        scenario_install_offline_integrity,
    ),
    "install-script-policy": (
        "Run default-deny lifecycle-script coverage plus guarded allow and triage manifest proposals.",
        scenario_install_script_policy,
    ),
    "install-save-policy": (
        "Run save-policy coverage for bare, explicit, tag, prerelease, wildcard, and re-install cases.",
        scenario_install_save_policy,
    ),
    "install-peer-deps": (
        "Run peer-dependency coverage for optional peers, strict failures, peer_issues JSON, and auto-isolated peer-conflict installs.",
        scenario_install_peer_deps,
    ),
    "install-catalog": (
        "Run catalog coverage for manual/prefer/strict save policy, --catalog flags, cleanupUnusedCatalogs, and pnpm-workspace catalogs.",
        scenario_install_catalog,
    ),
    "install-project-discovery": (
        "Run nearest-ancestor and fresh-dir project discovery checks for lpm install.",
        scenario_install_project_discovery,
    ),
    "install-engines": (
        "Run install-time engines enforcement and per-project opt-out checks.",
        scenario_install_engines,
    ),
    "workspace-basic": (
        "Run member-cwd install in workspace/basic and verify the app executes.",
        scenario_workspace_basic,
    ),
    "workspace-complex": (
        "Run repeated member-cwd installs in workspace/complex and verify both apps execute.",
        scenario_workspace_complex,
    ),
    "workspace-nested-boundary": (
        "Run the nested package-boundary workspace smoke and assert nested child imports stay isolated.",
        scenario_workspace_nested_boundary,
    ),
    "workspace-targeting": (
        "Run filtered workspace installs and assert app-only targets mutate while unmatched filters fail.",
        scenario_workspace_targeting,
    ),
    "workspace-filter-controls": (
        "Run workspace-filter control coverage for --filter-prod, --no-bail, and --workspace-concurrency.",
        scenario_workspace_filter_controls,
    ),
    "workspace-filter-selectors": (
        "Run workspace-filter selector coverage for changed-file ignore patterns, --test-pattern, and pkg{path}.",
        scenario_workspace_filter_selectors,
    ),
    "workspace-pack": (
        "Run lpm pack workspace E2E coverage for root-bin reuse, per-member JSON envelopes, no-match failures, and multi-member watch rejection.",
        scenario_workspace_pack,
    ),
    "workspace-uninstall": (
        "Run workspace uninstall coverage for filtered member cleanup, -w root cleanup, and fail-if-no-match.",
        scenario_workspace_uninstall,
    ),
    "install-config-aware": (
        "Drive the interactive config-aware lpm add flow against @lpm-registry/ex-source.",
        scenario_install_config_aware,
    ),
    "install-remove": (
        "Run manifest-backed lpm add/remove coverage for a bare package installed into a custom path.",
        scenario_install_remove,
    ),
    "install-uninstall": (
        "Run local uninstall coverage for dependency cleanup while leaving peer, optional, and trusted deps untouched.",
        scenario_install_uninstall,
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live smoke scenarios in test-packages.")
    parser.add_argument(
        "scenarios",
        nargs="*",
        default=["all"],
        help="Scenario names to run. Use 'all' for every scenario.",
    )
    parser.add_argument("--list", action="store_true", help="List available scenarios and exit.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.list:
        for name, (description, _) in SCENARIOS.items():
            print(f"{name}: {description}")
        return 0

    requested = args.scenarios
    if "all" in requested:
        selected = list(SCENARIOS.keys())
    else:
        selected = requested

    unknown = [name for name in selected if name not in SCENARIOS]
    if unknown:
        raise SmokeFailure(f"unknown scenario(s): {', '.join(unknown)}")

    ensure_lpm_binary()

    for name in selected:
        description, scenario = SCENARIOS[name]
        log(f"starting {name}: {description}")
        with isolated_default_smoke_home():
            scenario()
        log(f"finished {name}")

    log("all requested scenarios passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeFailure as error:
        print(f"[smoke] FAILURE: {error}", file=sys.stderr)
        raise SystemExit(1)
