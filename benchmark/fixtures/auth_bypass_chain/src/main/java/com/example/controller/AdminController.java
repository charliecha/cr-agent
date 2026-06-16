package com.example.controller;

import org.springframework.web.bind.annotation.*;
import java.util.List;

@RestController
@RequestMapping("/admin")
public class AdminController {

    @GetMapping("/stats")
    public String getStats() {
        return "admin stats";
    }

    @GetMapping("/export/users")
    public List<String> exportUsers() {
        return List.of("user1@example.com", "user2@example.com");
    }
}
