const path = require('path');
const { expect } = require('chai');
const mockFactory = require('../common/mockFactory');
const requireUncached = require('../common/requireUncached');

const parentDirectory = path.join(__dirname, '../..');
const jsFile = `${parentDirectory}/../src/main/apigee/apiproxies/referenceData/apiproxy/resources/jsc/retrieveCustomerT3.js`;

describe('testing retrieve customer transform 3 policy', () => {
  it('should transform invalid data', () => {
    const mocks = mockFactory.getMock();
    const bodyDummy = {
      status: '500',
    };
    const mockStatusCode = 500;

    mocks.contextGetVariableMethod.withArgs('response.status.code').returns(mockStatusCode);
    mocks.contextGetVariableMethod.withArgs('response.content').returns(JSON.stringify(bodyDummy));

    requireUncached(jsFile);

    const statusCodeResult = mocks.contextSetVariableMethod.getCall(0).args[1];
    const statusResult = mocks.contextSetVariableMethod.getCall(1).args[1];
    const messageResult = mocks.contextSetVariableMethod.getCall(2).args[1];

    expect(statusCodeResult).to.equal(mockStatusCode);
    expect(statusResult).to.equal(bodyDummy.status);
    expect(messageResult).to.equal('Error General');
  });

  it('should return catch data content', () => {
    const mocks = mockFactory.getMock();
    const bodyDummy = null;
    const mockStatusCode = 500;

    mocks.contextGetVariableMethod.withArgs('response.status.code').returns(mockStatusCode);
    mocks.contextGetVariableMethod.withArgs('response.content').returns(JSON.stringify(bodyDummy));

    requireUncached(jsFile);

    const statusCodeResult = mocks.contextSetVariableMethod.getCall(0).args[1];
    const statusResult = mocks.contextSetVariableMethod.getCall(1).args[1];
    const messageResult = mocks.contextSetVariableMethod.getCall(2).args[1];

    expect(statusCodeResult).to.equal(mockStatusCode);
    expect(statusResult).to.equal('invalid response format');
    expect(messageResult).to.equal('Error General');
  });

  it('should not assign content', () => {
    const mocks = mockFactory.getMock();
    const bodyDummy = {
      statusCode: 400,
      message: 'msg',
      status: 'error',
    };
    const mockStatusCode = 500;

    mocks.contextGetVariableMethod.withArgs('response.status.code').returns(mockStatusCode);
    mocks.contextGetVariableMethod.withArgs('response.content').returns(JSON.stringify(bodyDummy));

    requireUncached(jsFile);

    expect(mocks.contextSetVariableMethod.getCall(0)).to.equal(null);
  });

  it('should transform data without status property', () => {
    const mocks = mockFactory.getMock();
    const bodyDummy = {
      error: 'error',
    };
    const mockStatusCode = 500;

    mocks.contextGetVariableMethod.withArgs('response.status.code').returns(mockStatusCode);
    mocks.contextGetVariableMethod.withArgs('response.content').returns(JSON.stringify(bodyDummy));

    requireUncached(jsFile);

    const statusCodeResult = mocks.contextSetVariableMethod.getCall(0).args[1];
    const statusResult = mocks.contextSetVariableMethod.getCall(1).args[1];
    const messageResult = mocks.contextSetVariableMethod.getCall(2).args[1];

    expect(statusCodeResult).to.equal(mockStatusCode);
    expect(statusResult).to.equal('invalid response format');
    expect(messageResult).to.equal('Error General');
  });
});
