const path = require('path');
const { expect } = require('chai');
const mockFactory = require('../common/mockFactory');
const requireUncached = require('../common/requireUncached');

const parentDirectory = path.join(__dirname, '../..');
const jsFile = `${parentDirectory}/../src/main/apigee/apiproxies/referenceData/apiproxy/resources/jsc/retrievePaymentBalancesFacilityT1.js`;

describe('testing retrieve payment balance facility transform 1 policy', () => {
  it('should transform retrieve payment balance facility data', () => {
    const retrievePaymentFacilityMocks = mockFactory.getMock();
    const retrieveBody = {
      paymentBalancesFacility: {
        companyReference: '001',
        branch: '112',
        user: '50455252454f20494e54454e534f20',
        financialTransaction: '50455252454f20494e54454e534f20',
      },
    };
    const retrieveCustomerId = '1';
    const retrieveTokenDummy = '1';

    retrievePaymentFacilityMocks.contextGetVariableMethod
      .withArgs('request.header.consumerRequestId')
      .returns(retrieveCustomerId);
    retrievePaymentFacilityMocks.contextGetVariableMethod
      .withArgs('request.header.token')
      .returns(retrieveTokenDummy);
    retrievePaymentFacilityMocks.contextGetVariableMethod
      .withArgs('request.content')
      .returns(JSON.stringify(retrieveBody));

    requireUncached(jsFile);

    const requestHeaderCustomerRequestId =
      retrievePaymentFacilityMocks.contextSetVariableMethod.getCall(0).args[1];
    const requestHeaderToken =
      retrievePaymentFacilityMocks.contextSetVariableMethod.getCall(1).args[1];
    const requestContent = JSON.parse(
      retrievePaymentFacilityMocks.contextSetVariableMethod.getCall(2).args[1],
    );

    expect(requestHeaderCustomerRequestId).to.equals(retrieveCustomerId);
    expect(requestHeaderToken).to.equal(retrieveTokenDummy);
    expect(requestContent).to.deep.equal(retrieveBody);
  });
});
