// Frontend client — parses OrderResponse from backend
package frontend.client

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

@Serializable
data class Order(
    val orderId: String,
    val email: String,  // BUG: still expects "email", but backend now sends "customerEmail"
    val totalAmount: Double,
    val status: String,
)

class OrderClient(private val httpClient: HttpClient) {

    suspend fun fetchOrder(orderId: String): Order {
        val response = httpClient.get("/api/orders/$orderId")
        // Deserialization will fail or produce null for "email" field since backend sends "customerEmail"
        return Json.decodeFromString<Order>(response.body)
    }

    fun displayOrderSummary(order: Order) {
        println("Order ${order.orderId}: ${order.email} paid ${order.totalAmount}")
    }
}

interface HttpClient {
    suspend fun get(path: String): HttpResponse
}

data class HttpResponse(val body: String)
