package com.example.repository;

import com.example.model.User;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import java.util.List;

@Repository
public class UserRepository {

    private final JdbcTemplate jdbc;

    public UserRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<User> findAll() {
        return jdbc.query("SELECT id, email, role FROM users",
            (rs, i) -> { User u = new User(); u.id = rs.getLong(1); u.email = rs.getString(2); u.role = rs.getString(3); return u; });
    }

    public List<User> findByRole(String role) {
        return jdbc.query("SELECT id, email, role FROM users WHERE role = ?",
            (rs, i) -> { User u = new User(); u.id = rs.getLong(1); u.email = rs.getString(2); u.role = rs.getString(3); return u; },
            role);
    }
}
