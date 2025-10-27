/**
 * require wrapper without caching
 *
 * @param {string} module to be loaded
 * @return {void} freshly loaded module
 */
function requireUncached(module) {
  delete require.cache[require.resolve(module)];
  // eslint-disable-next-line import/no-dynamic-require, global-require
  return require(module);
}

module.exports = requireUncached;
