const path = require('path');
const { expect } = require('chai');
const mockFactory = require('../common/mockFactory');
const requireUncached = require('../common/requireUncached');

const parentDirectory = path.join(__dirname, '../..');
const jsFile = `${parentDirectory}/../src/main/apigee/apiproxies/referenceData/apiproxy/resources/jsc/retrievePaymentBalancesFacilityT3.js`;

describe('testing retrieve payment balance facility transform 3 policy', () => {
  it('should transform retrieve payment balance facility invalid data', () => {
    const retrievePaymentFacilityMocks = mockFactory.getMock();
    const bodyDummy = {
      status: '500',
    };
    const mockStatusCode = 500;

    retrievePaymentFacilityMocks.contextGetVariableMethod
      .withArgs('response.status.code')
      .returns(mockStatusCode);
    retrievePaymentFacilityMocks.contextGetVariableMethod
      .withArgs('response.content')
      .returns(JSON.stringify(bodyDummy));

    requireUncached(jsFile);

    const statusCodeResult =
      retrievePaymentFacilityMocks.contextSetVariableMethod.getCall(0).args[1];
    const statusResult = retrievePaymentFacilityMocks.contextSetVariableMethod.getCall(1).args[1];
    const messageResult = retrievePaymentFacilityMocks.contextSetVariableMethod.getCall(2).args[1];

    expect(statusCodeResult).to.equal(mockStatusCode);
    expect(statusResult).to.equal(bodyDummy.status);
    expect(messageResult).to.equal('Error General');
  });

  it('should return catch retrieve payment balance facility data content', () => {
    const retrievePaymentFacilityMocks = mockFactory.getMock();
    const bodyDummy = null;
    const mockStatusCode = 500;

    retrievePaymentFacilityMocks.contextGetVariableMethod
      .withArgs('response.status.code')
      .returns(mockStatusCode);
    retrievePaymentFacilityMocks.contextGetVariableMethod
      .withArgs('response.content')
      .returns(JSON.stringify(bodyDummy));

    requireUncached(jsFile);

    const statusCodeResult =
      retrievePaymentFacilityMocks.contextSetVariableMethod.getCall(0).args[1];
    const statusResult = retrievePaymentFacilityMocks.contextSetVariableMethod.getCall(1).args[1];
    const messageResult = retrievePaymentFacilityMocks.contextSetVariableMethod.getCall(2).args[1];

    expect(statusCodeResult).to.equal(mockStatusCode);
    expect(statusResult).to.equal('invalid response format');
    expect(messageResult).to.equal('Error General');
  });

  it('should not assign retrieve payment balance facility content', () => {
    const retrievePaymentFacilityMocks = mockFactory.getMock();
    const bodyDummy = {
      statusCode: 400,
      message: 'msg',
      status: 'error',
    };
    const mockStatusCode = 500;

    retrievePaymentFacilityMocks.contextGetVariableMethod
      .withArgs('response.status.code')
      .returns(mockStatusCode);
    retrievePaymentFacilityMocks.contextGetVariableMethod
      .withArgs('response.content')
      .returns(JSON.stringify(bodyDummy));

    requireUncached(jsFile);

    expect(retrievePaymentFacilityMocks.contextSetVariableMethod.getCall(0)).to.equal(null);
  });

  it('should transform retrieve payment balance facility data without status property', () => {
    const retrievePaymentFacilityMocks = mockFactory.getMock();
    const bodyDummy = {
      error: 'error',
    };
    const mockStatusCode = 500;

    retrievePaymentFacilityMocks.contextGetVariableMethod
      .withArgs('response.status.code')
      .returns(mockStatusCode);
    retrievePaymentFacilityMocks.contextGetVariableMethod
      .withArgs('response.content')
      .returns(JSON.stringify(bodyDummy));

    requireUncached(jsFile);

    const statusCodeResult =
      retrievePaymentFacilityMocks.contextSetVariableMethod.getCall(0).args[1];
    const statusResult = retrievePaymentFacilityMocks.contextSetVariableMethod.getCall(1).args[1];
    const messageResult = retrievePaymentFacilityMocks.contextSetVariableMethod.getCall(2).args[1];

    expect(statusCodeResult).to.equal(mockStatusCode);
    expect(statusResult).to.equal('invalid response format');
    expect(messageResult).to.equal('Error General');
  });
});
