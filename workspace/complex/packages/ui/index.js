const { accent } = require("@smoke/tokens");

function renderBadge(label) {
  return `[${accent}] ${label}`;
}

module.exports = {
  renderBadge,
};
