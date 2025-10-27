/*jshint esversion: 8 */

const requestHeaderConsumerRequestId = 'request.header.consumerRequestId';
const requestHeaderToken = 'request.header.token';
const requestContent = 'request.content';

const consumerRequestId = context.getVariable(requestHeaderConsumerRequestId);
const token = context.getVariable(requestHeaderToken);
const body = JSON.parse(context.getVariable(requestContent));

const newBody = {
  paymentBalancesFacility: {
    companyReference: body.paymentBalancesFacility.companyReference,
    branch: body.paymentBalancesFacility.branch,
    user: body.paymentBalancesFacility.user,
    financialTransaction: body.paymentBalancesFacility.financialTransaction,
  },
};

context.setVariable(requestHeaderConsumerRequestId, consumerRequestId);
context.setVariable(requestHeaderToken, token);
context.setVariable(requestContent, JSON.stringify(newBody));
