const path = require('path');
const { expect } = require('chai');
const mockFactory = require('../common/mockFactory');
const requireUncached = require('../common/requireUncached');

const parentDirectory = path.join(__dirname, '../..');
const jsFile = `${parentDirectory}/../src/main/apigee/apiproxies/referenceData/apiproxy/resources/jsc/retrieveCustomerCardT3.js`;

describe('testing retrieveCustomerCard transform 3 policy', () => {
  it('should transform retrieveCustomerCard invalid data', () => {
    const mocks = mockFactory.getMock();
    const retrieveCustomerBody = {
      status: '500',
    };

    mocks.contextGetVariableMethod.withArgs('response.status.code').returns(500);
    mocks.contextGetVariableMethod
      .withArgs('response.content')
      .returns(JSON.stringify(retrieveCustomerBody));

    requireUncached(jsFile);

    expect(mocks.contextSetVariableMethod.getCall(0).args[1]).to.equal('500');
    expect(mocks.contextSetVariableMethod.getCall(1).args[1]).to.equal(retrieveCustomerBody.status);
    expect(mocks.contextSetVariableMethod.getCall(2).args[1]).to.equal('Error General');
  });

  it('should return catch transform 3 retrieveCustomerCard data content', () => {
    const mocks = mockFactory.getMock();

    mocks.contextGetVariableMethod.withArgs('response.status.code').returns(500);
    mocks.contextGetVariableMethod.withArgs('response.content').returns(JSON.stringify(null));

    requireUncached(jsFile);

    expect(mocks.contextSetVariableMethod.getCall(0).args[1]).to.equal(500);
    expect(mocks.contextSetVariableMethod.getCall(1).args[1]).to.equal('500');
    expect(mocks.contextSetVariableMethod.getCall(2).args[1]).to.equal('Failed');
    expect(mocks.contextSetVariableMethod.getCall(3).args[1]).to.equal('Error General');
  });

  it('should not assign transform 3 retrieveCustomerCard content', () => {
    const mocks = mockFactory.getMock();

    mocks.contextGetVariableMethod.withArgs('response.content').returns(
      JSON.stringify({
        statusCode: '400',
        message: 'msg',
        status: 'error',
      }),
    );

    requireUncached(jsFile);

    expect(mocks.contextSetVariableMethod.getCall(0)).to.equal(null);
  });

  it('should transform 3 retrieveCustomerCard data without status property', () => {
    const mocks = mockFactory.getMock();

    mocks.contextGetVariableMethod.withArgs('response.content').returns(
      JSON.stringify({
        error: 'error',
      }),
    );

    requireUncached(jsFile);

    expect(mocks.contextSetVariableMethod.getCall(1).args[1]).to.equal('Failed');
  });
});
