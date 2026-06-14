import fs from "node:fs"
import { json } from "@sveltejs/kit"

export function GET() {
    return json({
        argv1: process.argv[1],
        realpath: fs.realpathSync(process.argv[1]),
    })
}
