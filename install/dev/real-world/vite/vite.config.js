import fs from "node:fs"
import { defineConfig } from "vite"

export default defineConfig({
    plugins: [
        {
            name: "lpm-smoke-bin-realpath",
            configureServer(server) {
                server.middlewares.use("/lpm-bin-realpath", (_request, response) => {
                    response.setHeader("content-type", "application/json")
                    response.end(
                        JSON.stringify({
                            argv1: process.argv[1],
                            realpath: fs.realpathSync(process.argv[1]),
                        }),
                    )
                })
            },
        },
    ],
})
