const assert = require("assert");
const mockFactory = require("../common/mockFactory");
const requireUncached = require("../common/requireUncached");
const path = require('path');
const validSchema = require("../common/schemaLocation");
const creditInfo = require("../common/locationResponse");

const currentDirectory = path.join(__dirname, '../..');
const jsFile = `${currentDirectory}/../src/main/apigee/apiproxies/referenceData/apiproxy/resources/jsc/JS-ValidSchema.js`;
const tv4File = `${currentDirectory}/../src/main/apigee/apiproxies/referenceData/apiproxy/resources/jsc/tv4.js`;

describe("Valid-requiered-fieldd", function () {
  describe("Requiered Field", function () {
    it("should return an Valid schema", function () {
      const mocks = mockFactory.getMock();

      mocks.contextGetVariableMethod
      .withArgs("validSchema")
      .returns(JSON.stringify(validSchema));

      mocks.contextGetVariableMethod
        .withArgs("request.content")
        .returns(JSON.stringify(creditInfo));

      global.tv4 = requireUncached(tv4File);

      let errorThrown = false;

      try {
        requireUncached(jsFile);
      } catch (e) {
        console.log(e);
        errorThrown = true;
      }
      assert(errorThrown === false, "Ran without error");
      const spyResponse = mocks.contextSetVariableMethod.getCall(0).args[1];
      const response = JSON.parse(spyResponse);
      assert.equal(response, true, "Schema is valid");
    });
  });
});