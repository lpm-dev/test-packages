import fs from "node:fs"

export function GET() {
    return Response.json({
        argv1: process.argv[1],
        realpath: fs.realpathSync(process.argv[1]),
    })
}
