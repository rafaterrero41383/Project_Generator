const path = require('path');
const { expect } = require('chai');
const mockFactory = require('../common/mockFactory');
const requireUncached = require('../common/requireUncached');

const parentDirectory = path.join(__dirname, '../..');
const jsFile = `${parentDirectory}/../src/main/apigee/apiproxies/referenceData/apiproxy/resources/jsc/retrieveCustomerT1.js`;

describe('testing retrieve customer transform 1 policy', () => {
  it('should transform retrieveCustomer data', () => {
    const mocks = mockFactory.getMock();
    const customerBody = {
      companyReference: '001',
      option: 3,
      partyReference: {
        personName: {
          familyName: '15276e7fd43ab63d6b0a6a3bc03f313f',
          secondLastName: '07232a5d792f96d44ac593e43d6592c3',
          firstName: '1276c190f7197fd82d7f0ad19c1c93d2',
          secondName: 'da598699cef750ee8e5ef3b2daf47719',
          marriedName: 'da598699cef750ee8e5ef3b2daf47719',
          fullName: 'da598699cef750ee8e5ef3b2daf47719',
        },
        identifications: [
          {
            identifier: {
              identifierValue: 'A93B64AE1FB376A15EC21132E65B478F',
            },
            personIdentificationType: 'Registro Federal Contribuyentes',
          },
        ],
        dateOfBirth: 'f5c4aa0648d87d54176a1e77000b6be8',
        contactPoint: [
          {
            contactPointValue: 'c2a63a9f1fce966ecabae6e7ee4204a3',
            contactPointType: 'cellphone',
          },
        ],
        referenceId: 'c2a63a9f1fce966ecabae6e7ee4204a3',
      },
      paymentCard: {
        cardNumber: 'D4DB7298729FCA8E66F1E69A28ECE2F0',
      },
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
      .returns(JSON.stringify(customerBody));

    requireUncached(jsFile);

    const requestHeaderCustomerRequestId = mocks.contextSetVariableMethod.getCall(0).args[1];
    const requestHeaderToken = mocks.contextSetVariableMethod.getCall(1).args[1];
    const requestContent = JSON.parse(mocks.contextSetVariableMethod.getCall(2).args[1]);

    expect(requestHeaderCustomerRequestId).to.equals(procedureCustomerId);
    expect(requestHeaderToken).to.equal(procedureTokenDummy);
    expect(requestContent).to.deep.equal(customerBody);
  });
});
