import fs from "node:fs"
import { json } from "@remix-run/node"

export function loader() {
    return json({
        argv1: process.argv[1],
        realpath: fs.realpathSync(process.argv[1]),
    })
}
