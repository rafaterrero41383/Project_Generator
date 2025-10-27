const path = require('path');
const { expect } = require('chai');
const mockFactory = require('../common/mockFactory');
const requireUncached = require('../common/requireUncached');

const parentDirectory = path.join(__dirname, '../..');
const jsFile = `${parentDirectory}/../src/main/apigee/apiproxies/referenceData/apiproxy/resources/jsc/retrieveCustomerT2.js`;

describe('testing retrieve customer transform 2 policy', () => {
  it('should transform retrieveCustomer data', () => {
    const mocks = mockFactory.getMock();
    const customerBody = {
      partyReference: {
        personName: {
          familyName: '15276e7fd43ab63d6b0a6a3bc03f313f',
          secondLastName: '07232a5d792f96d44ac593e43d6592c3',
          firstName: '1276c190f7197fd82d7f0ad19c1c93d2',
          secondName: 'da598699cef750ee8e5ef3b2daf47719',
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
        referenceId: 'c2a63a9f1fce966ecabae6e7ee4204a3',
      },
    };

    const customerStatusCode = 200;

    mocks.contextGetVariableMethod
      .withArgs('response.content')
      .returns(JSON.stringify(customerBody));
    mocks.contextGetVariableMethod.withArgs('response.status.code').returns(customerStatusCode);

    requireUncached(jsFile);

    const responseContent = JSON.parse(mocks.contextSetVariableMethod.getCall(0).args[1]);

    expect(responseContent).to.deep.equal(customerBody);
  });

  it('should enter the catch and not set', () => {
    const mocks = mockFactory.getMock();
    const procedureBody = undefined;

    mocks.contextGetVariableMethod.withArgs('response.content').returns(procedureBody);

    requireUncached(jsFile);

    expect(mocks.contextSetVariableMethod.getCall(0)).to.equal(null);
  });

  it('should transform data to error form', () => {
    const mocks = mockFactory.getMock();
    const procedureBody = {
      statusCode: 400,
      message: 'msg',
      status: 'error',
    };

    mocks.contextGetVariableMethod.withArgs('response.status.code').returns(400);
    mocks.contextGetVariableMethod
      .withArgs('response.content')
      .returns(JSON.stringify(procedureBody));

    requireUncached(jsFile);

    const retrieveStatusCodeResult = mocks.contextSetVariableMethod.getCall(0).args[1];
    const retrieveStatusResult = mocks.contextSetVariableMethod.getCall(1).args[1];
    const retrieveMessageResult = mocks.contextSetVariableMethod.getCall(2).args[1];

    expect(retrieveStatusCodeResult).to.equal(procedureBody.statusCode);
    expect(retrieveStatusResult).to.equal(procedureBody.status);
    expect(retrieveMessageResult).to.equal(procedureBody.message);
  });
});
