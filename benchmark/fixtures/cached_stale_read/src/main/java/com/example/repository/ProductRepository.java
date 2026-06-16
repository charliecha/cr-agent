package com.example.repository;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProductRepository {

    private final JdbcTemplate jdbc;

    public ProductRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public double findPriceById(long productId) {
        return jdbc.queryForObject(
            "SELECT price FROM products WHERE id = ?",
            Double.class, productId);
    }

    public void updatePrice(long productId, double newPrice) {
        jdbc.update("UPDATE products SET price = ? WHERE id = ?", newPrice, productId);
    }
}
