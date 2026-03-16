// CRACO configuration to enable TailwindCSS and Autoprefixer with CRA
/** @type {import('@craco/craco').CracoConfig} */
module.exports = {
  style: {
    postcss: {
      mode: 'file', // Let PostCSS use postcss.config.js
    },
  },
};