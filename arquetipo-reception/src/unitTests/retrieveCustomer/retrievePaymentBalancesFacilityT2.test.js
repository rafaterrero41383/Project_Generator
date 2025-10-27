const path = require('path');
const { expect } = require('chai');
const mockFactory = require('../common/mockFactory');
const requireUncached = require('../common/requireUncached');

const parentDirectory = path.join(__dirname, '../..');
const jsFile = `${parentDirectory}/../src/main/apigee/apiproxies/referenceData/apiproxy/resources/jsc/retrievePaymentBalancesFacilityT2.js`;

describe('testing retrieve payment balance facility transform 2 policy', () => {
  it('should transform retrieve payment balance facility data', () => {
    const retrievePaymentFacilityMocks = mockFactory.getMock();
    const customerBody = {
      paymentBalancesFacility: {
        serviceAmount: '863732343AF9B144031913851D3EE48F',
        currency: 'USD',
        serviceAmountCharge: '863732343AF9B144031913851D3EE48F',
        descriptionAmountService: '863732343AF9B144031913851D3EE48F',
        descriptionAmountChargeService: 'A93B64AE1FB376A15EC21132E65B478F',
        description: 'descripcion',
      },
    };

    const customerStatusCode = 200;

    retrievePaymentFacilityMocks.contextGetVariableMethod
      .withArgs('response.content')
      .returns(JSON.stringify(customerBody));
    retrievePaymentFacilityMocks.contextGetVariableMethod
      .withArgs('response.status.code')
      .returns(customerStatusCode);

    requireUncached(jsFile);

    const responseContent = JSON.parse(
      retrievePaymentFacilityMocks.contextSetVariableMethod.getCall(0).args[1],
    );

    expect(responseContent).to.deep.equal(customerBody);
  });

  it('should enter the catch and not set', () => {
    const retrievePaymentFacilityMocks = mockFactory.getMock();
    const procedureBody = undefined;

    retrievePaymentFacilityMocks.contextGetVariableMethod
      .withArgs('response.content')
      .returns(procedureBody);

    requireUncached(jsFile);

    expect(retrievePaymentFacilityMocks.contextSetVariableMethod.getCall(0)).to.equal(null);
  });

  it('should transform data to error form', () => {
    const retrievePaymentFacilityMocks = mockFactory.getMock();
    const procedureBody = {
      statusCode: 400,
      message: 'msg',
      status: 'error',
    };

    retrievePaymentFacilityMocks.contextGetVariableMethod
      .withArgs('response.status.code')
      .returns(400);
    retrievePaymentFacilityMocks.contextGetVariableMethod
      .withArgs('response.content')
      .returns(JSON.stringify(procedureBody));

    requireUncached(jsFile);

    const retrieveStatusCodeResult =
      retrievePaymentFacilityMocks.contextSetVariableMethod.getCall(0).args[1];
    const retrieveStatusResult =
      retrievePaymentFacilityMocks.contextSetVariableMethod.getCall(1).args[1];
    const retrieveMessageResult =
      retrievePaymentFacilityMocks.contextSetVariableMethod.getCall(2).args[1];

    expect(retrieveStatusCodeResult).to.equal(procedureBody.statusCode);
    expect(retrieveStatusResult).to.equal(procedureBody.status);
    expect(retrieveMessageResult).to.equal(procedureBody.message);
  });
});
