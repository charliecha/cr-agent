package app.ui

import app.core.EventBus

class OrderFragment {
    private val orderHandler: (String) -> Unit = { event ->
        if (event == "ORDER_UPDATED") refreshOrders()
    }

    fun onResume() {
        EventBus.register(orderHandler)
    }

    fun refreshOrders() {
        println("refreshing orders")
    }
}
