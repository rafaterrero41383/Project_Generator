package simulations.api_operations

import io.gatling.core.Predef._
import io.gatling.core.structure.ChainBuilder
import io.gatling.http.Predef._

class ExecuteOnboardingParty {
  private val body = """{ "partyRetailReferenceDataDirectoryEntry": { "partyReference": { "personName": { "familyName": "15276e7fd43ab63d6b0a6a3bc03f313f", "secondLastName": "07232a5d792f96d44ac593e43d6592c3", "firstName": "1276c190f7197fd82d7f0ad19c1c93d2" }, "dateOfBirth": "f5c4aa0648d87d54176a1e77000b6be8", "identifications": [ { "identifier": { "identifierValue": "c2a63a9f1fce966ecabae6e7ee4204a3" }, "personIdentificationType": "Numero Persona Coppel" } ] } }, "sessionDialogueIdentification": "GAFA9603064C3" }"""
  private val apiUrl = "/experience/referenceData/v1/onboardingParty/execute"
  private val invalidApiUrl = "/experience/referenceData/v1/onboardingParty/noExistingResource"

  object ApiTransactions {
    var successExecuteOnboardingParty: ChainBuilder =
      exec(http("successExecuteOnboardingParty")
        .post(apiUrl)
        .body(StringBody(body)).asJson
        .header("consumerRequestId", "1")
        .header("token", "1")
        .check(status.is(200)))

    var badRequestExecuteOnboardingParty: ChainBuilder =
      exec(http("badRequestExecuteOnboardingParty")
        .post(apiUrl)
        .body(StringBody("{}")).asJson
        .check(status.is(400)))

    var notFoundExecuteOnboardingParty: ChainBuilder =
      exec(http("notFoundExecuteOnboardingParty")
        .post(invalidApiUrl)
        .check(status.is(404)))
  }
}
