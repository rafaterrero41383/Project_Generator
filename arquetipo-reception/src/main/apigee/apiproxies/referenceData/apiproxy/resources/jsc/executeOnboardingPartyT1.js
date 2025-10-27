/*jshint esversion: 8 */

const requestHeaderConsumerRequestId = 'request.header.consumerRequestId';
const requestHeaderToken = 'request.header.token';
const requestContent = 'request.content';

const consumerRequestId = context.getVariable(requestHeaderConsumerRequestId);
const token = context.getVariable(requestHeaderToken);
const body = JSON.parse(context.getVariable(requestContent));

const newBody = {
  sessionDialogueIdentification: body.sessionDialogueIdentification
};

context.setVariable(requestHeaderConsumerRequestId, consumerRequestId);
context.setVariable(requestHeaderToken, token);
context.setVariable(requestContent, JSON.stringify(newBody));
