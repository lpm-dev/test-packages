const kleur = require("kleur");
const { renderPanel } = require("@smoke/ui");

console.log(
  kleur.magenta(`nested boundary workspace: ${renderPanel("studio")}`),
);
