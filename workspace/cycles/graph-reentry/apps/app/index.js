const cycleA = require('@smoke/cycle-a')
const external = require('external-reentry')
console.log(`${cycleA.name}:${cycleA.peer}:${external}`)
