package simulations

import com.typesafe.config.Config
import com.typesafe.config.ConfigFactory
import io.gatling.core.Predef._
import io.gatling.core.structure.ScenarioBuilder
import io.gatling.http.Predef._
import io.gatling.http.protocol.HttpProtocolBuilder
import simulations.api_operations.{RetrieveCustomerCard}

class StressTest extends Simulation{
  val config: Config = ConfigFactory.load("application")
  var baseUrl: String = config.getString("url.baseUrl")
  var apikey: String = config.getString("apiKeyRequest.apikeyReq")
  val configurationGatling: Config = ConfigFactory.load("gatling.conf")
  val proxyHostConfig = "gatling.http.proxy.host"
  val proxyPortConfig = "gatling.http.proxy.port"

  val httpProtocol: HttpProtocolBuilder = {
    val hp = http.baseUrl(baseUrl)

    if (configurationGatling.hasPath(proxyHostConfig) && configurationGatling.hasPath(proxyPortConfig)) {
      println("Proxy configuration applied successfully")
      val hostProxy: String = configurationGatling.getString(proxyHostConfig)
      val puertoProxy: Int = configurationGatling.getInt(proxyPortConfig)
      println("host:" + hostProxy)
      println("port:" + puertoProxy)
      hp.proxy(Proxy(hostProxy, puertoProxy).httpsPort(puertoProxy))
    }
    else {
      println("No proxy configuration found")
      hp
    }
  }

  val retrieveCustomerCard = new RetrieveCustomerCard()

  val mainScenario: ScenarioBuilder = scenario("transactions test")
    .pause(3)
    .exec(
      retrieveCustomerCard.ApiTransactions.successRetrieveCustomerCard,
      retrieveCustomerCard.ApiTransactions.badRequestRetrieveCustomerCard,
      retrieveCustomerCard.ApiTransactions.notFoundRetrieveCustomerCard
    )

  setUp (
    mainScenario.inject(rampUsers(100).during(40))
  ).protocols(httpProtocol)
}
