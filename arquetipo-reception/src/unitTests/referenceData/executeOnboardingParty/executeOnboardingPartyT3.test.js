const path = require('path');
const { expect } = require('chai');
const mockFactory = require('../../common/mockFactory');
const requireUncached = require('../../common/requireUncached');

const parentDirectory = path.join(__dirname, '../../..');
const jsFile = `${parentDirectory}/../src/main/apigee/apiproxies/referenceData/apiproxy/resources/jsc/executeOnboardingPartyT3.js`;

describe('testing executeOnboardingParty transform 3 policy', () => {
  it('should transform executeOnboardingParty invalid data', () => {
    const mocks = mockFactory.getMock();
    const executeOnboardingPartyBody = {
      status: 'Fail',
    };

    mocks.contextGetVariableMethod.withArgs('response.status.code').returns(500);
    mocks.contextGetVariableMethod
      .withArgs('response.content')
      .returns(JSON.stringify(executeOnboardingPartyBody));

    requireUncached(jsFile);

    expect(mocks.contextSetVariableMethod.getCall(0).args[1]).to.equal(500);
    expect(mocks.contextSetVariableMethod.getCall(1).args[1]).to.equal(executeOnboardingPartyBody.status);
    expect(mocks.contextSetVariableMethod.getCall(2).args[1]).to.equal('Error General');
  });

  it('should return catch transform 3 executeOnboardingParty data content', () => {
    const mocks = mockFactory.getMock();

    mocks.contextGetVariableMethod.withArgs('response.status.code').returns(500);
    mocks.contextGetVariableMethod.withArgs('response.content').returns(JSON.stringify(null));

    requireUncached(jsFile);

    expect(mocks.contextSetVariableMethod.getCall(0).args[1]).to.equal(500);
    expect(mocks.contextSetVariableMethod.getCall(1).args[1]).to.equal('Fail');
    expect(mocks.contextSetVariableMethod.getCall(2).args[1]).to.equal('Error General');
  });

  it('should not assign transform 3 executeOnboardingParty content', () => {
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

  it('should transform 3 executeOnboardingParty data without status property', () => {
    const mocks = mockFactory.getMock();

    mocks.contextGetVariableMethod.withArgs('response.content').returns(
      JSON.stringify({
        error: 'error',
      }),
    );

    requireUncached(jsFile);

    expect(mocks.contextSetVariableMethod.getCall(1).args[1]).to.equal('Fail');
  });
});
