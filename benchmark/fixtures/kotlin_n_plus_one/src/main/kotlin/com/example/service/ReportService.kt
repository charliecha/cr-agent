package com.example.service

import com.example.model.OrderSummary
import com.example.repository.OrderRepository
import com.example.repository.ProductRepository
import org.springframework.stereotype.Service

@Service
class ReportService(
    private val orderRepo: OrderRepository,
    private val productRepo: ProductRepository,
) {
    fun buildOrderSummaries(userId: Long): List<OrderSummary> {
        val orders = orderRepo.findByUserId(userId)
        return orders.map { order ->
            val product = productRepo.findById(order.productId)
            OrderSummary(
                orderId = order.id,
                productName = product?.name ?: "Unknown",
                quantity = order.quantity,
            )
        }
    }
}
