package app.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class Product(
    val id: Int,
    val name: String,
    val price: Double,
    val category: String,
    val inStock: Boolean,
    val description: String,
    val imageUrl: String,
    val rating: Double,
    val reviewCount: Int,
)

sealed class ProductListState {
    object Loading : ProductListState()
    data class Success(val products: List<Product>, val selectedCategory: String?) : ProductListState()
    data class Error(val message: String) : ProductListState()
}

class ProductListViewModel(
    private val productRepository: ProductRepository,
    private val analyticsService: AnalyticsService,
) : ViewModel() {

    private val _state = MutableStateFlow<ProductListState>(ProductListState.Loading)
    val state: StateFlow<ProductListState> = _state

    private var currentCategory: String? = null
    private var allProducts: List<Product> = emptyList()

    init {
        loadProducts()
    }

    fun loadProducts(category: String? = null) {
        viewModelScope.launch {
            _state.value = ProductListState.Loading
            try {
                currentCategory = category
                allProducts = if (category != null) {
                    productRepository.getProductsByCategory(category)
                } else {
                    productRepository.getAllProducts()
                }
                _state.value = ProductListState.Success(
                    products = allProducts,
                    selectedCategory = category
                )
                analyticsService.logEvent("products_loaded", mapOf(
                    "category" to (category ?: "all"),
                    "count" to allProducts.size
                ))
            } catch (e: Exception) {
                _state.value = ProductListState.Error(e.message ?: "Unknown error")
                analyticsService.logError("product_load_failed", e)
            }
        }
    }

    fun filterByPrice(minPrice: Double, maxPrice: Double) {
        val currentState = _state.value
        if (currentState is ProductListState.Success) {
            val filtered = allProducts.filter { it.price in minPrice..maxPrice }
            _state.value = currentState.copy(products = filtered)
            analyticsService.logEvent("price_filter_applied", mapOf(
                "min" to minPrice,
                "max" to maxPrice,
                "result_count" to filtered.size
            ))
        }
    }

    fun filterByRating(minRating: Double) {
        val currentState = _state.value
        if (currentState is ProductListState.Success) {
            val filtered = allProducts.filter { it.rating >= minRating }
            _state.value = currentState.copy(products = filtered)
            analyticsService.logEvent("rating_filter_applied", mapOf(
                "min_rating" to minRating,
                "result_count" to filtered.size
            ))
        }
    }

    fun toggleInStockOnly(inStockOnly: Boolean) {
        val currentState = _state.value
        if (currentState is ProductListState.Success) {
            val filtered = if (inStockOnly) {
                allProducts.filter { it.inStock }
            } else {
                allProducts
            }
            _state.value = currentState.copy(products = filtered)
        }
    }

    fun sortByPrice(ascending: Boolean) {
        val currentState = _state.value
        if (currentState is ProductListState.Success) {
            val sorted = if (ascending) {
                currentState.products.sortedBy { it.price }
            } else {
                currentState.products.sortedByDescending { it.price }
            }
            _state.value = currentState.copy(products = sorted)
        }
    }

    fun sortByRating() {
        val currentState = _state.value
        if (currentState is ProductListState.Success) {
            val sorted = currentState.products.sortedByDescending { it.rating }
            _state.value = currentState.copy(products = sorted)
        }
    }

    fun searchProducts(query: String) {
        viewModelScope.launch {
            _state.value = ProductListState.Loading
            try {
                val results = productRepository.searchProducts(query)
                _state.value = ProductListState.Success(
                    products = results,
                    selectedCategory = null
                )
                analyticsService.logEvent("search_executed", mapOf(
                    "query" to query,
                    "result_count" to results.size
                ))
            } catch (e: Exception) {
                _state.value = ProductListState.Error(e.message ?: "Search failed")
            }
        }
    }

    fun refreshProducts() {
        // BUG: Should call loadProducts(currentCategory) to maintain current filter,
        // but calls loadProducts() with no args, resetting to "all products"
        loadProducts()
    }

    fun clearFilters() {
        val currentState = _state.value
        if (currentState is ProductListState.Success) {
            _state.value = currentState.copy(products = allProducts)
            analyticsService.logEvent("filters_cleared", emptyMap())
        }
    }

    fun onProductClicked(productId: Int) {
        analyticsService.logEvent("product_clicked", mapOf("product_id" to productId))
    }
}

interface ProductRepository {
    suspend fun getAllProducts(): List<Product>
    suspend fun getProductsByCategory(category: String): List<Product>
    suspend fun searchProducts(query: String): List<Product>
}

interface AnalyticsService {
    fun logEvent(eventName: String, params: Map<String, Any>)
    fun logError(errorName: String, throwable: Throwable)
}
