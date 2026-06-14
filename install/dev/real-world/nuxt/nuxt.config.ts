import { realpathSync, writeFileSync } from "node:fs"

writeFileSync(
    ".lpm-bin-realpath.json",
    JSON.stringify({
        argv1: process.argv[1],
        realpath: realpathSync(process.argv[1]),
    }),
)

export default defineNuxtConfig({
    devtools: {
        enabled: false,
    },
    ignore: [
        "**/.lpm/**",
        "**/node_modules/**",
    ],
    devServer: {
        host: "127.0.0.1",
        port: Number(process.env.PORT || 3000),
    },
    vite: {
        server: {
            watch: {
                ignored: [
                    "**/.lpm/**",
                    "**/node_modules/**",
                ],
            },
        },
    },
    nitro: {
        watchOptions: {
            ignored: [
                "**/.lpm/**",
                "**/node_modules/**",
            ],
        },
    },
})
