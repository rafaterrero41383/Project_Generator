/** @type {import('jest').Config} */
const config = {
  coverageThreshold: {
    global: {
      branches: 80,
      functions: 80,
      lines: 80,
      statements: 80,
    },
  },
  reporters: [
    'default',
    [
      'jest-junit',
      {
        outputDirectory: 'junit-test-results',
        outputName: 'unit-test-results.xml',
      },
    ],
  ],
  coveragePathIgnorePatterns: ['src/unitTests/common'],
};

module.exports = config;
