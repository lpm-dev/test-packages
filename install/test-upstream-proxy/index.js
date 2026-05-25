const pc = require("picocolors")
const ms = require("ms")

console.log(pc.green("Upstream proxy test"))
console.log(pc.cyan(`1 hour = ${ms("1h")}ms`))
console.log(pc.yellow("If you see this, npm packages installed through LPM proxy!"))
