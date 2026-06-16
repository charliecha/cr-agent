package com.example.api;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/users")
public class UserController {

    private final JdbcTemplate jdbc;

    public UserController(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @GetMapping("/search")
    public List<Map<String, Object>> searchUsers(@RequestParam String name) {
        String sql = "SELECT id, name, email FROM users WHERE name = '" + name + "'";
        return jdbc.queryForList(sql);
    }

    @GetMapping("/{id}")
    public Map<String, Object> getUser(@PathVariable long id) {
        return jdbc.queryForMap("SELECT id, name, email FROM users WHERE id = ?", id);
    }
}
