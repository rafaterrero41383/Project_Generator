const path = require('path');
const { expect } = require('chai');
const mockFactory = require('../common/mockFactory');
const requireUncached = require('../common/requireUncached');

const parentDirectory = path.join(__dirname, '../..');
const jsFile = `${parentDirectory}/../src/main/apigee/apiproxies/referenceData/apiproxy/resources/jsc/retrieveCustomerCardT1.js`;

describe('testing retrieveCustomerCard transform 1 policy', () => {
  it('should transform retrieveCustomerCard data', () => {
    const mocks = mockFactory.getMock();
    const retrieveCustomerBody = {
      companyReference: '001',
      accountIdentification: [
        {
          identifierValue: '5F600B3C636E509D8B739C57EC1AAA4F',
          accountIdentificationType: 'Account Number',
        },
      ],
    };
    const procedureCustomerId = '1';
    const procedureTokenDummy = '1';

    mocks.contextGetVariableMethod
      .withArgs('request.header.consumerRequestId')
      .returns(procedureCustomerId);
    mocks.contextGetVariableMethod.withArgs('request.header.token').returns(procedureTokenDummy);
    mocks.contextGetVariableMethod
      .withArgs('request.content')
      .returns(JSON.stringify(retrieveCustomerBody));

    requireUncached(jsFile);

    const requestHeaderCustomerRequestId = mocks.contextSetVariableMethod.getCall(0).args[1];
    const requestHeaderToken = mocks.contextSetVariableMethod.getCall(1).args[1];
    const requestContent = JSON.parse(mocks.contextSetVariableMethod.getCall(2).args[1]);

    expect(requestHeaderCustomerRequestId).to.equals(procedureCustomerId);
    expect(requestHeaderToken).to.equal(procedureTokenDummy);
    expect(requestContent).to.deep.equal(retrieveCustomerBody);
  });
});
