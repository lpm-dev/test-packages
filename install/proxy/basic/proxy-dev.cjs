#!/usr/bin/env node

const fs = require("node:fs")
const http = require("node:http")
const path = require("node:path")

const portIndex = process.argv.indexOf("--port")
if (portIndex === -1 || !process.argv[portIndex + 1]) {
    console.error("missing --port")
    process.exit(1)
}

const port = Number(process.argv[portIndex + 1])
if (!Number.isFinite(port) || port <= 0) {
    console.error(`invalid --port value: ${process.argv[portIndex + 1] ?? ""}`)
    process.exit(1)
}

const envObservedPath = path.join(process.cwd(), "env-observed.json")
fs.writeFileSync(
    envObservedPath,
    JSON.stringify(
        {
            port: String(port),
            nodeExtraCaCerts: process.env.NODE_EXTRA_CA_CERTS ?? null,
            sslCertFile: process.env.SSL_CERT_FILE ?? null,
            sslKeyFile: process.env.SSL_KEY_FILE ?? null,
        },
        null,
        2,
    ) + "\n",
    "utf8",
)

const server = http.createServer((request, response) => {
    const chunks = []
    request.on("data", chunk => chunks.push(chunk))
    request.on("end", () => {
        const body = Buffer.concat(chunks).toString("utf8")
        response.setHeader("Content-Type", "text/plain; charset=utf-8")
        response.end(
            `${request.method} ${request.url} ${body} host=${request.headers.host ?? ""} proto=${request.headers["x-forwarded-proto"] ?? ""}`,
        )
    })
})

server.listen(port, "127.0.0.1", () => {
    console.log(`ready:${port}`)
    setTimeout(() => {
        server.close(() => process.exit(0))
    }, 8000)
})
