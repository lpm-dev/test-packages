import fs from "node:fs"

export function GET() {
    return new Response(
        JSON.stringify({
            argv1: process.argv[1],
            realpath: fs.realpathSync(process.argv[1]),
        }),
        {
            headers: {
                "content-type": "application/json",
            },
        },
    )
}
