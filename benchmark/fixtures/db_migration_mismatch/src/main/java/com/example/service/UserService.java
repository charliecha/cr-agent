package com.example.service;

import com.example.model.Role;
import com.example.repository.UserRepository;
import org.springframework.stereotype.Service;
import java.util.List;
import java.util.Map;

@Service
public class UserService {

    private final UserRepository userRepo;

    public UserService(UserRepository userRepo) {
        this.userRepo = userRepo;
    }

    public List<Map<String, Object>> getRegularUsers() {
        return userRepo.findByRole(Role.USER.name());
    }
}
