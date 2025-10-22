const assert = require("assert");
const mockFactory = require("../common/mockFactory");
const requireUncached = require("../common/requireUncached");
const path = require('path');
const schema = require("../common/schemaLocation");

// Ruta al directorio actual
const currentDirectory = path.join(__dirname, '../..');
const jsFile = `${currentDirectory}/../src/main/apigee/apiproxies/referenceData/apiproxy/resources/jsc/schema.js`;

describe("Expected-scheme", function () {
    it("should return an Expected", function () {
        const mocks = mockFactory.getMock();
        let errorThrown = false;

      try {
        requireUncached(jsFile);
      } catch (e) {
        console.log(e);
        errorThrown = true;
      }
      assert(errorThrown === false, "Ran without error");
      const spyResponse = mocks.contextSetVariableMethod.getCall(0).args[1];
      const response = JSON.stringify(spyResponse);
      const jsonSchema = JSON.stringify(schema);
      assert.equal(response, jsonSchema, "Schema is correct");
    });
});