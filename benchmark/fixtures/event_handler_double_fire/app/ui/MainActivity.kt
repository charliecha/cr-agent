package app.ui

import app.core.EventBus

class MainActivity {
    private val handler: (String) -> Unit = { event ->
        println("MainActivity received: $event")
    }

    fun onResume() {
        EventBus.register(handler)
    }

    fun onPause() {
        EventBus.unregister(handler)
    }
}
