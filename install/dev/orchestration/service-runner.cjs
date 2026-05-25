const fs = require("node:fs")
const http = require("node:http")

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
        `${JSON.stringify({ service, event, ...extra })}
`,
        "utf8"
    )
}

const service = getArg("--service")
const capturePath = getArg("--capture", "orchestration-events.jsonl")
const requireUrlEnv = getArg("--require-url-env")
const listenDelayMs = Number(getArg("--listen-delay-ms", "0"))
const waitMs = Number(getArg("--wait-ms", "500"))
const port = Number(process.env.PORT || getArg("--port", "0"))

if (!service) {
    throw new Error("missing --service")
}

if (!Number.isInteger(port) || port <= 0) {
    throw new Error(`invalid PORT for ${service}: ${process.env.PORT ?? "unset"}`)
}

async function main() {
    appendEvent(capturePath, "start", {
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
        appendEvent(capturePath, "dependency-ok", {
            port,
            requireUrlEnv,
            depUrl,
            status: response.status,
        })
    }

    await new Promise(resolve => setTimeout(resolve, listenDelayMs))

    const server = http.createServer((request, response) => {
        if (request.url === "/health") {
            response.writeHead(200, { "content-type": "application/json" })
            response.end(JSON.stringify({ ok: true, service }))
            return
        }

        response.writeHead(200, { "content-type": "application/json" })
        response.end(JSON.stringify({ service, ok: true }))
    })

    server.listen(port, "127.0.0.1", () => {
        appendEvent(capturePath, "listening", { port })
        setTimeout(() => {
            server.close(() => {
                appendEvent(capturePath, "exit", { port })
                process.exit(0)
            })
        }, waitMs)
    })
}

main().catch(error => {
    appendEvent(capturePath, "error", { message: error.message })
    console.error(`[${service}] ${error.message}`)
    process.exit(1)
})
