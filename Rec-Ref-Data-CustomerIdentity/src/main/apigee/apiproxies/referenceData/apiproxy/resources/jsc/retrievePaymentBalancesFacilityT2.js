/*jshint esversion: 8 */

const responseStatusCode = 'response.status.code';
const responseContent = 'response.content';
const statusCode = context.getVariable(responseStatusCode);
const retrievePaymentData = {
  body: null,
};

try {
  retrievePaymentData.body = JSON.parse(context.getVariable(responseContent));
} catch (error) {
  retrievePaymentData.body = null;
}

if (
  retrievePaymentData.body &&
  typeof retrievePaymentData.body === 'object' &&
  Object.keys(retrievePaymentData.body).length > 0
) {
  if (statusCode === 200) {
    const newBody = {
      paymentBalancesFacility: {
        serviceAmount: retrievePaymentData.body.paymentBalancesFacility.serviceAmount,
        currency: retrievePaymentData.body.paymentBalancesFacility.currency,
        serviceAmountCharge: retrievePaymentData.body.paymentBalancesFacility.serviceAmountCharge,
        descriptionAmountService:
          retrievePaymentData.body.paymentBalancesFacility.descriptionAmountService,
        descriptionAmountChargeService:
          retrievePaymentData.body.paymentBalancesFacility.descriptionAmountChargeService,
        description: retrievePaymentData.body.paymentBalancesFacility.description,
      },
    };
    context.setVariable(responseContent, JSON.stringify(newBody));
  } else {
    context.setVariable('statusCode', retrievePaymentData.body.statusCode);
    context.setVariable('status', retrievePaymentData.body.status);
    context.setVariable('message', retrievePaymentData.body.message);
  }
}
