// Backend API endpoint — returns order details
package backend.api

import kotlinx.serialization.Serializable

@Serializable
data class OrderResponse(
    val orderId: String,
    val customerEmail: String,  // RENAMED from "email" to "customerEmail" in this PR
    val totalAmount: Double,
    val status: String,
)

class OrderController {
    fun getOrderById(id: String): OrderResponse {
        // Mock implementation
        return OrderResponse(
            orderId = id,
            customerEmail = "user@example.com",
            totalAmount = 99.99,
            status = "pending"
        )
    }
}
