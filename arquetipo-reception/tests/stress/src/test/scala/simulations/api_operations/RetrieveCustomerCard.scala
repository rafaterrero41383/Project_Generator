package simulations.api_operations

import io.gatling.core.Predef._
import io.gatling.core.structure.ChainBuilder
import io.gatling.http.Predef._

class RetrieveCustomerCard {
  private val body = """{"companyReference":"001","accountIdentification":[{"identifierValue":"5F600B3C636E509D8B739C57EC1AAA4F","accountIdentificationType":"Account Number"}]}"""
  private val apiUrl = "/experience/referenceData/v1/customerCard/retrieve"
  private val invalidApiUrl = "/experience/referenceData/v1/customerCard/noExistingResource"

  object ApiTransactions {
    var successRetrieveCustomerCard: ChainBuilder =
      exec(http("successRetrieveCustomerCard")
        .post(apiUrl)
        .body(StringBody(body)).asJson
        .header("consumerRequestId", "1")
        .header("token", "1")
        .check(status.is(200)))

    var badRequestRetrieveCustomerCard: ChainBuilder =
      exec(http("badRequestRetrieveCustomerCard")
        .post(apiUrl)
        .body(StringBody("{}")).asJson
        .check(status.is(400)))

    var notFoundRetrieveCustomerCard: ChainBuilder =
      exec(http("notFoundRetrieveCustomerCard")
        .post(invalidApiUrl)
        .check(status.is(404)))
  }
}
