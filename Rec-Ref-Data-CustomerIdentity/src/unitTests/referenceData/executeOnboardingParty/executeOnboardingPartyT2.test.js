const path = require('path');
const { expect } = require('chai');
const mockFactory = require('../../common/mockFactory');
const requireUncached = require('../../common/requireUncached');

const parentDirectory = path.join(__dirname, '../../..');
const jsFile = `${parentDirectory}/../src/main/apigee/apiproxies/referenceData/apiproxy/resources/jsc/executeOnboardingPartyT2.js`;

describe('testing executeOnboardingParty transform 2 policy', () => {
  it('should transform executeOnboardingParty data', () => {
    const mocks = mockFactory.getMock();
    const executeOnboardingPartyBody = {
      "partyReference": {
        "identifications": [
          {
            "identifier": {
              "identifierValue": "c2a63a9f1fce966ecabae6e7ee4204a3"
            },
            "personIdentificationType": "Numero Persona Coppel"
          }
        ]
      }
    };

    const customerStatusCode = 200;

    mocks.contextGetVariableMethod
      .withArgs('response.content')
      .returns(JSON.stringify(executeOnboardingPartyBody));
    mocks.contextGetVariableMethod.withArgs('response.status.code').returns(customerStatusCode);

    requireUncached(jsFile);

    const responseContent = JSON.parse(mocks.contextSetVariableMethod.getCall(0).args[1]);

    expect(responseContent).to.deep.equal(executeOnboardingPartyBody);
  });

  it('should enter the catch and not set', () => {
    const mocks = mockFactory.getMock();
    const executeOnboardingPartyBody = undefined;

    mocks.contextGetVariableMethod.withArgs('response.content').returns(executeOnboardingPartyBody);

    requireUncached(jsFile);

    expect(mocks.contextSetVariableMethod.getCall(0)).to.equal(null);
  });

  it('should transform retrieveCustomerCard data to error form', () => {
    const mocks = mockFactory.getMock();
    const executeOnboardingPartyBody = {
      statusCode: '400',
      message: 'msg',
      status: 'error',
    };

    mocks.contextGetVariableMethod.withArgs('response.status.code').returns(400);
    mocks.contextGetVariableMethod
      .withArgs('response.content')
      .returns(JSON.stringify(executeOnboardingPartyBody));

    requireUncached(jsFile);

    const retrieveStatusCodeResult = mocks.contextSetVariableMethod.getCall(0).args[1];
    const retrieveStatusResult = mocks.contextSetVariableMethod.getCall(1).args[1];
    const retrieveMessageResult = mocks.contextSetVariableMethod.getCall(2).args[1];

    expect(retrieveStatusCodeResult).to.equal(executeOnboardingPartyBody.statusCode);
    expect(retrieveStatusResult).to.equal(executeOnboardingPartyBody.status);
    expect(retrieveMessageResult).to.equal(executeOnboardingPartyBody.message);
  });
});
