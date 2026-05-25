const { workspaceName } = require("@smoke/config");
const { renderBadge } = require("@smoke/ui");
const kleur = require("kleur");

console.log(kleur.yellow(`${workspaceName}: ${renderBadge("docs")}`));
