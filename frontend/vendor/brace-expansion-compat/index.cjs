const fixedPackage = require('brace-expansion-fixed');
const expand = typeof fixedPackage === 'function' ? fixedPackage : fixedPackage.expand;

module.exports = expand;
module.exports.expand = expand;
