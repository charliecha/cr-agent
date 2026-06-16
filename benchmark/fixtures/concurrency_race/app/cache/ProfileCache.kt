package app.cache

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

data class UserProfile(val id: Int, val displayName: String, val avatarUrl: String)

// BUG: cache is a plain HashMap accessed from multiple coroutines (IO dispatcher = thread pool).
// Concurrent put/get/containsKey on HashMap can corrupt internal state (infinite loop on rehash,
// lost updates, ClassCastException). Should be ConcurrentHashMap or guarded by a Mutex.
class ProfileCache {

    private val cache = HashMap<Int, UserProfile>()

    suspend fun get(id: Int): UserProfile? = withContext(Dispatchers.IO) {
        cache[id]
    }

    suspend fun put(profile: UserProfile) = withContext(Dispatchers.IO) {
        cache[profile.id] = profile
    }

    suspend fun getOrLoad(id: Int, loader: suspend (Int) -> UserProfile): UserProfile {
        val cached = get(id)
        if (cached != null) return cached
        // race window: two coroutines can both pass the null check and both call loader
        val loaded = loader(id)
        put(loaded)
        return loaded
    }

    fun invalidate(id: Int) {
        // called from main thread while IO coroutines may be reading — data race
        cache.remove(id)
    }

    fun size(): Int = cache.size
}
