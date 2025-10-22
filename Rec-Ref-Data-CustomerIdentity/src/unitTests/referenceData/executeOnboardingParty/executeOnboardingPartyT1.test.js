const path = require('path');
const { expect } = require('chai');
const mockFactory = require('../../common/mockFactory');
const requireUncached = require('../../common/requireUncached');

const parentDirectory = path.join(__dirname, '../../..');
const jsFile = `${parentDirectory}/../src/main/apigee/apiproxies/referenceData/apiproxy/resources/jsc/executeOnboardingPartyT1.js`;

describe('testing executeOnboardingParty transform 1 policy', () => {
  it('should transform executeOnboardingParty data', () => {
    const mocks = mockFactory.getMock();
    const executeOnboardingPartyBody = {
      "partyRetailReferenceDataDirectoryEntry": {
        "partyReference": {
          "personName": {
            "familyName": "15276e7fd43ab63d6b0a6a3bc03f313f",
            "secondLastName": "07232a5d792f96d44ac593e43d6592c3",
            "firstName": "1276c190f7197fd82d7f0ad19c1c93d2"
          },
          "dateOfBirth": "f5c4aa0648d87d54176a1e77000b6be8",
          "identifications": [
            {
              "identifier": {
                "identifierValue": "c2a63a9f1fce966ecabae6e7ee4204a3"
              },
              "personIdentificationType": "Numero Persona Coppel"
            }
          ]
        }
      },
      "sessionDialogueIdentification": "GAFA9603064C3"
    };
    const headerCustomerId = '1';
    const headerTokenDummy = '1';

    mocks.contextGetVariableMethod
      .withArgs('request.header.consumerRequestId')
      .returns(headerCustomerId);
    mocks.contextGetVariableMethod.withArgs('request.header.token').returns(headerTokenDummy);
    mocks.contextGetVariableMethod
      .withArgs('request.content')
      .returns(JSON.stringify(executeOnboardingPartyBody));

    requireUncached(jsFile);

    const requestHeaderCustomerRequestId = mocks.contextSetVariableMethod.getCall(0).args[1];
    const requestHeaderToken = mocks.contextSetVariableMethod.getCall(1).args[1];
    const requestContent = JSON.parse(mocks.contextSetVariableMethod.getCall(2).args[1]);

    expect(requestHeaderCustomerRequestId).to.equals(headerCustomerId);
    expect(requestHeaderToken).to.equal(headerTokenDummy);
    expect(requestContent).to.deep.equal(executeOnboardingPartyBody);
  });
});
