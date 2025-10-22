/*jshint esversion: 8 */

const responseStatusCode = 'response.status.code';
const responseContent = 'response.content';
const generalError = 'Error General';
const generalStatus = 'Fail';

const currentStatusCode = context.getVariable(responseStatusCode);
const result = {
  content: null,
};

try {
  const body = JSON.parse(context.getVariable(responseContent));

  if (!(body.statusCode && body.message && body.status)) {
    result.content = {
      statusCode: currentStatusCode,
      message: generalError,
      status: body.status || generalStatus,
    };
  }
} catch (error) {
  result.content = {
    statusCode: currentStatusCode,
    message: generalError,
    status: generalStatus,
  };
}

if (result.content) {
  context.setVariable('failed_response.statusCode', result.content.statusCode);
  context.setVariable('failed_response.status', result.content.status);
  context.setVariable('failed_response.message', result.content.message);
}
