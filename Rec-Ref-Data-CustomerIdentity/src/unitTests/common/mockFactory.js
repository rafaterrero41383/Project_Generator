const sinon = require('sinon');

let contextGetVariableMethod = sinon.stub();
let contextSetVariableMethod = sinon.spy();
let httpClientSendMethod = sinon.spy();

beforeEach(() => {
  jest.resetModules();
  global.context = {
    getVariable() {
      // Fix solution
    },
    setVariable() {
      // Fix solution
    },
  };
  global.httpClient = {
    send() {
      // Fix solution
    },
  };

  contextGetVariableMethod = sinon.stub(global.context, 'getVariable');
  contextSetVariableMethod = sinon.spy(global.context, 'setVariable');
  httpClientSendMethod = sinon.spy(global.httpClient, 'send');
});

afterEach(() => {
  contextGetVariableMethod.restore();
  contextSetVariableMethod.restore();
  httpClientSendMethod.restore();
});

exports.getMock = () => ({
  contextGetVariableMethod,
  contextSetVariableMethod,
  httpClientSendMethod,
});
