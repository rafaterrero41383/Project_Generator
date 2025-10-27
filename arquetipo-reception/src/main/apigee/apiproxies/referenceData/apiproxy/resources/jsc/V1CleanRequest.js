/*jshint esversion: 8 */

const requestHeaderConsumerRequestId = 'request.header.consumerRequestId';
const requestHeaderToken = 'request.header.token';
const requestHeaderSessionId = 'request.header.sessionId';
const requestContent = 'request.content';

const consumerRequestId = context.getVariable(requestHeaderConsumerRequestId);
const token = context.getVariable(requestHeaderToken);
const sessionId = context.getVariable(requestHeaderSessionId);
const body = JSON.parse(context.getVariable(requestContent));

context.setVariable(requestHeaderConsumerRequestId, consumerRequestId);
context.setVariable(requestHeaderToken, token);
context.setVariable(requestHeaderSessionId, sessionId);
context.setVariable(requestContent, JSON.stringify(body));