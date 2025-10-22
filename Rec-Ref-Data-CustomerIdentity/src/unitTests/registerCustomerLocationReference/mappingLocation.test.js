const assert = require("assert");
const mockFactory = require("../common/mockFactory");
const requireUncached = require("../common/requireUncached");
const path = require('path');
const creditInfo = require("../common/locationResponse");
const consumerRequestId="123";
const token="abc";

const currentDirectory = path.join(__dirname, '../..');
const jsFile = `${currentDirectory}/../src/main/apigee/apiproxies/referenceData/apiproxy/resources/jsc/JS-MappingLocation.js`;

describe("Valid-requiered-fieldd", function () {
    it("should return an Valid schema", function () {
      const mocks = mockFactory.getMock();

      mocks.contextGetVariableMethod
      .withArgs("request.header.consumerRequestId")
      .returns(consumerRequestId);

      mocks.contextGetVariableMethod
      .withArgs("request.header.token")
      .returns(token);

      mocks.contextGetVariableMethod
        .withArgs("request.content")
        .returns(JSON.stringify(creditInfo));

      let errorThrown = false;

      try {
        requireUncached(jsFile);
      } catch (e) {
        console.log(e);
        errorThrown = true;
      }
      assert(errorThrown === false, "Ran without error");
      const returnedConsumerRequestId = mocks.contextSetVariableMethod.getCall(0).args[1];
      const returnedToken = mocks.contextSetVariableMethod.getCall(1).args[1];
      const response = mocks.contextSetVariableMethod.getCall(2).args[1];;
      assert.equal(returnedConsumerRequestId, consumerRequestId, "Id is valid");
      assert.equal(returnedToken, token, "Token is valid");
      assert.equal(response, JSON.stringify(creditInfo), "Object is correct");
    });
});