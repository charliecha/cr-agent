package app.core

typealias EventHandler = (event: String) -> Unit

object EventBus {
    private val handlers = mutableListOf<EventHandler>()

    fun register(handler: EventHandler) {
        handlers.add(handler)
    }

    fun unregister(handler: EventHandler) {
        handlers.remove(handler)
    }

    fun post(event: String) {
        handlers.forEach { it(event) }
    }
}
