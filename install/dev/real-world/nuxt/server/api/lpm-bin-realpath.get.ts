import { readFileSync } from "node:fs"

export default defineEventHandler(() =>
    JSON.parse(readFileSync(".lpm-bin-realpath.json", "utf8")),
)
