/*jshint esversion: 8 */

const responseStatusCode = 'response.status.code';
const responseContent = 'response.content';
const statusCode = context.getVariable(responseStatusCode);
const data = {
  body: null,
};

try {
  data.body = JSON.parse(context.getVariable(responseContent));
} catch (error) {
  data.body = null;
}

if (data.body && typeof data.body === 'object' && Object.keys(data.body).length > 0) {
  if (statusCode === 200) {
    const newBody = {
      partyReference: {
        personName: {
          familyName: data.body.partyReference.personName.familyName,
          secondLastName: data.body.partyReference.personName.secondLastName,
          firstName: data.body.partyReference.personName.firstName,
          secondName: data.body.partyReference.personName.secondName,
        },
        identifications: data.body.partyReference.identifications.map((identification) => ({
          identifier: {
            identifierValue: identification.identifier.identifierValue,
          },
          personIdentificationType: identification.personIdentificationType,
        })),
        referenceId: data.body.partyReference.referenceId,
      },
      paymentCard: {
        cardNumber: data.body.paymentCard.cardNumber,
      },
    };
    context.setVariable(responseContent, JSON.stringify(newBody));
  } else {
    context.setVariable('statusCode', data.body.statusCode);
    context.setVariable('status', data.body.status);
    context.setVariable('message', data.body.message);
  }
}
