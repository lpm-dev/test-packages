const fs = require("node:fs")
const http = require("node:http")

const args = process.argv.slice(2)
let port = 3000
let capturePath = "dev-capture.json"

for (let index = 0; index < args.length; index += 1) {
    const arg = args[index]
    if (arg === "--port" && index + 1 < args.length) {
        port = Number(args[index + 1])
        index += 1
        continue
    }
    if (arg === "--capture" && index + 1 < args.length) {
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

fs.writeFileSync(capturePath, `${JSON.stringify(payload, null, 2)}
`, "utf8")

const server = http.createServer((_request, response) => {
    response.writeHead(200, { "content-type": "text/plain" })
    response.end("ok")
})

server.listen(port, "127.0.0.1", () => {
    setTimeout(() => {
        server.close(() => process.exit(0))
    }, 1200)
})
