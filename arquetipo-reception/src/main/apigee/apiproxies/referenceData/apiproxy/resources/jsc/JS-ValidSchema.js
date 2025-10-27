/*jshint esversion: 8 */

const schemaToValid = context.getVariable('validSchema');

var requestBody = JSON.parse(context.getVariable('request.content'));

var validationResult = tv4.validateMultiple(requestBody, schemaToValid);

context.setVariable("schemaEvaluate.valid", validationResult.valid);
