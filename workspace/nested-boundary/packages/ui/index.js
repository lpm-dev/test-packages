const { accent } = require("@smoke/tokens");

function renderPanel(label) {
  return `[${accent}] ${label}`;
}

module.exports = {
  renderPanel,
};
