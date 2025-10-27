const path = require('path');
const { expect } = require('chai');
const mockFactory = require('../common/mockFactory');
const requireUncached = require('../common/requireUncached');

const parentDirectory = path.join(__dirname, '../..');
const jsFile = `${parentDirectory}/../src/main/apigee/apiproxies/referenceData/apiproxy/resources/jsc/retrieveCustomerCardT2.js`;

describe('testing retrieveCustomerCard transform 2 policy', () => {
  it('should transform retrieveCustomerCard data', () => {
    const mocks = mockFactory.getMock();
    const retrieveCustomerBody = {
      partyReference: {
        personName: {
          familyName: '15276e7fd43ab63d6b0a6a3bc03f313f',
          secondLastName: '07232a5d792f96d44ac593e43d6592c3',
          firstName: '1276c190f7197fd82d7f0ad19c1c93d2',
          secondName: 'da598699cef750ee8e5ef3b2daf47719',
        },
        identifications: [
          {
            identifier: {
              identifierValue: 'A93B64AE1FB376A15EC21132E65B478F',
            },
            personIdentificationType: 'Registro Federal Contribuyentes',
          },
        ],
        referenceId: 'c2a63a9f1fce966ecabae6e7ee4204a3',
      },
      paymentCard: {
        cardNumber: 'D4DB7298729FCA8E66F1E69A28ECE2F0',
      },
    };

    const customerStatusCode = 200;

    mocks.contextGetVariableMethod
      .withArgs('response.content')
      .returns(JSON.stringify(retrieveCustomerBody));
    mocks.contextGetVariableMethod.withArgs('response.status.code').returns(customerStatusCode);

    requireUncached(jsFile);

    const responseContent = JSON.parse(mocks.contextSetVariableMethod.getCall(0).args[1]);

    expect(responseContent).to.deep.equal(retrieveCustomerBody);
  });

  it('should enter the catch and not set', () => {
    const mocks = mockFactory.getMock();
    const retrieveCustomerBody = undefined;

    mocks.contextGetVariableMethod.withArgs('response.content').returns(retrieveCustomerBody);

    requireUncached(jsFile);

    expect(mocks.contextSetVariableMethod.getCall(0)).to.equal(null);
  });

  it('should transform retrieveCustomerCard data to error form', () => {
    const mocks = mockFactory.getMock();
    const retrieveCustomerBody = {
      statusCode: '400',
      message: 'msg',
      status: 'error',
    };

    mocks.contextGetVariableMethod.withArgs('response.status.code').returns(400);
    mocks.contextGetVariableMethod
      .withArgs('response.content')
      .returns(JSON.stringify(retrieveCustomerBody));

    requireUncached(jsFile);

    const retrieveStatusCodeResult = mocks.contextSetVariableMethod.getCall(0).args[1];
    const retrieveStatusResult = mocks.contextSetVariableMethod.getCall(1).args[1];
    const retrieveMessageResult = mocks.contextSetVariableMethod.getCall(2).args[1];

    expect(retrieveStatusCodeResult).to.equal(retrieveCustomerBody.statusCode);
    expect(retrieveStatusResult).to.equal(retrieveCustomerBody.status);
    expect(retrieveMessageResult).to.equal(retrieveCustomerBody.message);
  });
});
